#!/usr/bin/env python3
"""The ModInfo.xml a scaffold from ci/smoke.conf has to produce.

The smoke config carries text the substitution has to survive on purpose: a
display name and an author holding `&`, `<` and a quote, an accented letter,
a display name also holding a backslash and a straight quote, and a purpose
whose first sentence ends on a CJK stop rather than a period.
A scaffolder that writes those values raw leaves a ModInfo.xml the game
cannot parse and the mod's own xml-parses gate red, and one that writes them
raw into the C# string literal the console command's description is leaves a
file the compiler rejects; one that finds a sentence end only in `.!?`
leaves the description holding the whole purpose. All of it is pinned here,
against what a reader of the config expects to see in the file.

The mod's own gates read the mod; this reads the scaffolder's output. They
are separate because the file that carries the values is written before the
mod exists, and the mod cannot check the source it was generated from.

Usage: ci/check-smoke-mod.py <mod-dir> <config-file>
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "template", "scripts", "lib"))
from gate import check
from gate import main as report

# What ci/smoke.conf asks for, and what the substitution owes ModInfo.xml.
# Change either side and this fails, which is the point: the config is the
# input, this file is the expectation.
EXPECTED_DISPLAY_NAME = 'CI & Smoke „Mod“ \\Tag\\ "Quoted"'
EXPECTED_AUTHOR = "CI & Müller"
EXPECTED_DESCRIPTION = "このモッドはテンプレートから動くbmodレットである。"
EXPECTED_SECOND_SENTENCE = "Throwaway CI smoke mod"

CONF_KEY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
# What a backslash escapes inside a shell double-quoted value, and the only
# place one does. new-mod.sh `source`s the config, so the shell is the reader
# that decides what the value is; a checker that read the line literally
# would expect a different string than the scaffold was given.
SHELL_ESCAPE = re.compile(r"\\([\"\\$`])")


def unquote(raw: str) -> str:
    """One shell double-quoted value as the shell would expand it."""
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return SHELL_ESCAPE.sub(r"\1", raw)


def conf_values(path: str) -> dict[str, str]:
    """The `key="value"` pairs of a scaffold config, as the shell expands them.

    A config that cannot be read yields no values, which fails the check that
    compares them with the expected ones. It is not a traceback: this runs
    after the scaffolder in CI, so a config the run could not read is exactly
    the report the gate exists to make.
    """
    values: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                match = CONF_KEY.match(line)
                if match:
                    values[match["key"]] = unquote(match["value"])
    except OSError as err:
        check("smoke-config-reads", False, f"{path}: {err}")
        return {}
    return values


def modinfo(mod_dir: str) -> dict[str, str]:
    """Every value attribute of the mod's ModInfo.xml, keyed by field name.

    A file that is absent, unreadable or unparseable yields no values at all,
    so each field's own check fails and names the reason, rather than the run
    dying on it. The OSError case is the common one: a scaffolder that failed
    before the move into place leaves no mod directory, and the gate then has
    to say so rather than exit on the traceback of a missing file.
    """
    path = os.path.join(mod_dir, "ModInfo.xml")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as err:
        check("modinfo-parses", False, f"{path}: {err}")
        return {}
    except OSError as err:
        check("modinfo-parses", False, f"cannot read {path}: {err}")
        return {}
    check("modinfo-parses", True)
    return {field.tag: (field.get("value") or "") for field in root}


def read_text(path: str) -> str:
    """A file's text, or the empty string when it cannot be read.

    The walks below read every file in a scaffolded mod. One unreadable file
    among them used to end the gate on a traceback, losing the results of
    every other check, and an unreadable file is a report the gate owes
    rather than a crash: the scaffolder copies modes and permissions with the
    tree, and a file the runner cannot read is one of the things a reader of
    this report needs told. `errors="replace"` throughout, so a file that is
    not UTF-8 is scanned rather than fatal too.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def search_harmony_id(path: str) -> str:
    """The Harmony id a C# file constructs, or the empty string."""
    found = re.search(r'new Harmony\("(?P<id>[^"]+)"\)', read_text(path))
    return found["id"] if found else ""


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check-smoke-mod.py <mod-dir> <config-file>", file=sys.stderr)
        return 2
    mod_dir, conf_path = sys.argv[1], sys.argv[2]
    if not os.path.isdir(mod_dir):
        print(f"ERROR: no mod directory at {mod_dir}; did the scaffolder run?", file=sys.stderr)
        return 2
    conf = conf_values(conf_path)
    values = modinfo(mod_dir)

    # The checks below are about text that reaches the file, so each one is
    # stated as the text a reader of the config would expect to find there.
    check("smoke-config-is-the-one-this-expects",
          (conf.get("display_name"), conf.get("author"), conf.get("csharp"))
          == (EXPECTED_DISPLAY_NAME, EXPECTED_AUTHOR, "yes"),
          f"ci/smoke.conf carries {conf.get('display_name')!r} / {conf.get('author')!r} / "
          f"csharp={conf.get('csharp')!r}; update EXPECTED_* here with it")
    check("modinfo-display-name-round-trips",
          values.get("DisplayName") == EXPECTED_DISPLAY_NAME,
          repr(values.get("DisplayName")))
    check("modinfo-author-round-trips",
          values.get("Author") == EXPECTED_AUTHOR,
          repr(values.get("Author")))
    check("modinfo-description-is-the-first-sentence",
          values.get("Description") == EXPECTED_DESCRIPTION,
          repr(values.get("Description")))
    check("modinfo-description-fits-one-line",
          len(values.get("Description", "")) <= 200,
          f"{len(values.get('Description', ''))} code points")

    # The same display name is written into the console command's
    # getDescription, which is a C# string literal. A quote or a backslash
    # written raw closes it, and the mod's first `make build` fails on a
    # file the scaffolder reported as written.
    literal = EXPECTED_DISPLAY_NAME.replace("\\", "\\\\").replace('"', '\\"')
    console = ""
    for base, _dirs, files in os.walk(os.path.join(mod_dir, "src")):
        for f in files:
            if f.startswith("ConsoleCmd") and f.endswith(".cs"):
                with open(os.path.join(base, f), encoding="utf-8") as handle:
                    console = handle.read()
                break
        if console:
            break
    check("console-command-escapes-the-display-name-for-csharp",
          f'return "{literal} settings";' in console,
          f"the C# literal does not hold {literal!r}; a quote or a backslash "
          f"written raw makes the mod's first build fail")

    # The purpose's second sentence has to survive somewhere, or the
    # description check above would also pass on a scaffolder that dropped
    # it. It is seeded into the mod's own docs, which is where a reader
    # finds the rest of the purpose.
    carried = ""
    for base, dirs, files in os.walk(mod_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "dist", "obj", "bin"}]
        for f in files:
            if not f.endswith((".md", ".txt", ".toml", ".cs")):
                continue
            if EXPECTED_SECOND_SENTENCE in read_text(os.path.join(base, f)):
                carried = os.path.relpath(os.path.join(base, f), mod_dir)
                break
        if carried:
            break
    check("whole-purpose-reaches-the-mod", bool(carried),
          "no file in the mod carries the second sentence of the purpose")

    # The author token names the Harmony id. The config's author has an
    # accented letter in it, so an id spelled from the raw name comes out
    # "cimller" and one that dropped the accent altogether comes out "ci".
    # The base letters are what the id has to carry.
    harmony = ""
    for base, _dirs, files in os.walk(os.path.join(mod_dir, "src")):
        for f in files:
            if not f.endswith(".cs"):
                continue
            found = search_harmony_id(os.path.join(base, f))
            if found:
                harmony = found
                break
    check("harmony-id-is-the-expected-ascii-string",
          harmony == "com.cimuller.cismoke", repr(harmony))

    # The scaffolder's optional-feature markers are its own bookkeeping, and
    # every one of them is gone from the mod: what a marker delimits is either
    # stripped or kept, but the delimiters themselves never ship. The smoke
    # config turns off one feature and leaves the other on, so both halves of
    # that are in this tree at once, and the half that keeps its block is the
    # half whose closing marker can survive it.
    survivor = ""
    for base, dirs, files in os.walk(mod_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            path = os.path.join(base, f)
            if "ANVIL:" in read_text(path):
                survivor = os.path.relpath(path, mod_dir)
                break
        if survivor:
            break
    check("no-scaffolder-marker-survives-the-substitution", not survivor, survivor)

    # The scaffolder copies template/ with a plain `cp -R`, which ignores
    # .gitignore, so a cache the developer's own gates leave in the template
    # tree would ride along into every generated mod. None of these names is
    # source, and each one is a gitignore rule in template/ or this repo.
    caches = []
    for base, dirs, _files in os.walk(mod_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "dist", "obj", "bin"}]
        caches += [os.path.relpath(os.path.join(base, d), mod_dir)
                   for d in dirs
                   if d in {".ruff_cache", ".shamway", "__pycache__", ".local"}]
    check("no-build-cache-ships-inside-the-mod", not caches,
          f"found {caches}; new-mod.sh prunes them, so one survived")

    return report()


if __name__ == "__main__":
    sys.exit(main())

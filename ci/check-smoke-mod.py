#!/usr/bin/env python3
"""The ModInfo.xml a scaffold from ci/smoke.conf has to produce.

The smoke config carries text the substitution has to survive on purpose: a
display name and an author holding `&`, `<` and a quote, an accented letter,
and a purpose whose first sentence ends on a CJK stop rather than a period.
A scaffolder that writes those values raw leaves a ModInfo.xml the game
cannot parse and the mod's own xml-parses gate red; one that finds a
sentence end only in `.!?` leaves the description holding the whole
purpose. Both are pinned here, against what a reader of the config
expects to see in the file.

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

FAILURES: list[str] = []

# What ci/smoke.conf asks for, and what the substitution owes ModInfo.xml.
# Change either side and this fails, which is the point: the config is the
# input, this file is the expectation.
EXPECTED_DISPLAY_NAME = 'CI & Smoke „Mod“'
EXPECTED_AUTHOR = "CI & Müller"
EXPECTED_DESCRIPTION = "このモッドはテンプレートから動くbmodレットである。"
EXPECTED_SECOND_SENTENCE = "Throwaway CI smoke mod"

CONF_KEY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one assertion; `detail` explains a failure and is dropped on a pass."""
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def conf_values(path: str) -> dict[str, str]:
    """The `key="value"` pairs of a scaffold config, quotes stripped."""
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = CONF_KEY.match(line)
            if match:
                values[match["key"]] = match["value"].strip('"')
    return values


def modinfo(mod_dir: str) -> dict[str, str]:
    """Every value attribute of the mod's ModInfo.xml, keyed by field name.

    An unparseable file yields no values at all, so each field's own check
    fails and names the parse error, rather than the run dying on it.
    """
    try:
        root = ET.parse(os.path.join(mod_dir, "ModInfo.xml")).getroot()
    except ET.ParseError as err:
        check("modinfo-parses", False, str(err))
        return {}
    check("modinfo-parses", True)
    return {field.tag: (field.get("value") or "") for field in root}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check-smoke-mod.py <mod-dir> <config-file>", file=sys.stderr)
        return 2
    mod_dir, conf_path = sys.argv[1], sys.argv[2]
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
            with open(os.path.join(base, f), encoding="utf-8", errors="replace") as handle:
                if EXPECTED_SECOND_SENTENCE in handle.read():
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
            with open(os.path.join(base, f), encoding="utf-8") as handle:
                found = re.search(r'new Harmony\("(?P<id>[^"]+)"\)', handle.read())
            if found:
                harmony = found["id"]
                break
    check("harmony-id-is-the-expected-ascii-string",
          harmony == "com.cimuller.cismoke", repr(harmony))

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

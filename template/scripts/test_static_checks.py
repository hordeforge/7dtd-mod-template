#!/usr/bin/env python3
"""Static shape gates for this modlet.

Deterministic, offline, no game install needed:

- every tracked XML file parses
- every Config/**/*.xml patch file uses a `<configs>` root (declared
  exceptions only — a full-file override or settings file is a decision,
  recorded here, not an accident)
- ModInfo.xml carries the required fields, and its Name matches the mod
  directory name
- the declared version is well-formed, agrees with the release readme, and
  has a section in CHANGELOG.md
- no mod-authored `Extends` cycle closes in the mod's own Config patches
- localization ships at Config/Localization.csv, never the mod root (the
  engine only loads mod localization from <mod>/Config/)
- no pre-V3 XUi shapes: no Config/XUi/ directory, no `{binding}` syntax
"""

from __future__ import annotations

import functools
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import safe_xml
import xml_extends
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Config XML files allowed a root other than <configs>, each with a reason.
# A stale entry (file gone) fails, so this list cannot rot.
NON_PATCH_CONFIG_XML: dict[str, str] = {}


SKIP_DIRS = {".git", "dist", "bin", "obj", "__pycache__"}


@functools.cache
def tree_files(mod_dir: str) -> tuple[list[str], list[str]]:
    """(every file, the XML among them), relative and sorted.

    One walk, both lists, walked once: the gate needs the whole tree for the
    stray localization check and the XML subset for everything else, so
    walking the mod separately per list, and again for the `Extends` pass,
    traversed a small tree three times to answer one question.

    `mod_dir` is a parameter, so it is part of the cache key. Keyed on
    nothing, the first root walked answered every later question, and a
    caller that repointed `MOD_DIR` at another tree (test_xml_gates.py
    drives this gate over a fixture tree) kept being told about the first
    one's files.
    """
    found: list[str] = []
    xml: list[str] = []
    for base, dirs, files in os.walk(mod_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(base, f), mod_dir)
            found.append(rel)
            if f.endswith(".xml"):
                xml.append(rel)
    return found, xml


def all_files() -> list[str]:
    """Every tracked-tree file, relative and sorted, whatever its extension."""
    return tree_files(MOD_DIR)[0]


def xml_files() -> list[str]:
    """Every tracked-tree `*.xml`, relative and sorted."""
    return tree_files(MOD_DIR)[1]


def check_release_version(version: str) -> None:
    """The declared version is the one players are told they are running.

    ModInfo.xml is what the game reads and what a multiplayer client compares;
    the release readme's first line is what a player reads. They are two
    hand-edited files saying the same thing, and a bump that touches only one
    ships a package whose readme lies about its own version, so the two are
    gated together here.
    """
    check("modinfo-version-is-four-segments",
          bool(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version)), repr(version))
    readme = os.path.join(MOD_DIR, "README.txt")
    if not os.path.isfile(readme):
        return
    with open(readme, encoding="utf-8") as handle:
        first = handle.readline().strip()
    check("readme-first-line-names-the-declared-version",
          first.endswith(" " + version), f"{first!r} does not end with {version!r}")


# (tree root, relative path) -> (parsed root, the error that stopped it, or None)
PARSED: dict[tuple[str, str], tuple[ET.Element | None, str | None]] = {}


def parsed_root(rel: str) -> tuple[ET.Element | None, str | None]:
    """`(root, parse error)` for a tracked XML file, parsed at most once.

    Memoized per tree and path: ModInfo.xml is read by the field checks, by
    the changelog check and by `declared_version`, and each Config patch file
    is parsed once for its root tag and again for the `Extends` walk, so the
    same document was built from disk two or three times per run.

    The tree is part of the key because the path is relative to it. Keyed on
    the relative path alone, a caller that repointed `MOD_DIR` at another
    tree (test_xml_gates.py drives this gate over a fixture tree) was handed
    the first tree's document for the second tree's file name.
    """
    entry = PARSED.get((MOD_DIR, rel))
    if entry is None:
        try:
            entry = (safe_xml.parse(os.path.join(MOD_DIR, rel)).getroot(), None)
        except (ET.ParseError, safe_xml.DtdRejected) as err:
            entry = (None, str(err))
        except OSError as err:
            entry = (None, str(err))
        PARSED[(MOD_DIR, rel)] = entry
    return entry


def check_release_notes() -> None:
    """The mod keeps a changelog with a home for unreleased work.

    Without an `Unreleased` section a release has nowhere to accumulate
    changes, so the notes arrive at the next version or never. The released
    section for the declared version carries a date: an entry with no date
    is a version a reader cannot place in time, and the release procedure in
    the file's own header asks for one.
    """
    path = os.path.join(MOD_DIR, "CHANGELOG.md")
    check("changelog-exists", os.path.isfile(path), "no CHANGELOG.md in the mod root")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    check("changelog-has-unreleased-section",
          "## [Unreleased]" in text, "add a '## [Unreleased]' section")
    version = declared_version()
    section = re.search(rf"^## \[{re.escape(version)}\](.*)$", text, re.M)
    check("changelog-declares-the-declared-version", bool(section),
          f"no released section for version {version}")
    if section:
        check("changelog-dates-the-declared-version",
              bool(re.fullmatch(r"- \d{4}-\d{2}-\d{2}", section.group(1).strip())),
              f"released section reads '## [{version}]' with no date")


def check_extends_cycles() -> None:
    """A closed `Extends` chain in the mod's own patches is a config defect.

    A patch where `a` extends `b` and `b` extends `a` resolves to nothing at
    load, and every other gate reports it as a clean run, so the chain has to
    be named here. The walk is the shared model in `scripts/lib/xml_extends.py`,
    so this gate and the model cannot disagree about what a cycle is; an entry
    extending itself still resolves, as the engine reads it.
    """
    for rel in xml_files():
        if not rel.startswith("Config" + os.sep):
            continue
        root, _error = parsed_root(rel)
        if root is None:
            # xml-parses already reported this file with the parse error.
            continue
        pool = {
            node.get("name"): node
            for node in root.iter()
            if node.get("name") and xml_extends.parent_of(node)[0]
        }
        closed = xml_extends.closed_chains(pool)
        check("no-extends-cycle:" + rel, not closed, "; ".join(closed))


def declared_version() -> str:
    modinfo = os.path.join(MOD_DIR, "ModInfo.xml")
    if not os.path.isfile(modinfo):
        return ""
    root, _error = parsed_root("ModInfo.xml")
    if root is None:
        return ""
    for field in root:
        if field.tag == "Version":
            return (field.get("value") or "").strip()
    return ""


def main() -> int:
    every, files = tree_files(MOD_DIR)
    roots: dict[str, str] = {}
    for rel in files:
        root, error = parsed_root(rel)
        if root is None:
            roots[rel] = ""
            check("xml-parses:" + rel, False, error or "")
            continue
        roots[rel] = root.tag
        check("xml-parses:" + rel, True)

    for rel in files:
        if not rel.startswith("Config" + os.sep) or not roots.get(rel):
            continue
        if rel in NON_PATCH_CONFIG_XML:
            continue
        check("configs-root:" + rel, roots[rel] == "configs",
              f"root is <{roots[rel]}>, patch files use <configs>")
    for rel in sorted(NON_PATCH_CONFIG_XML):
        check("configs-root-exception-exists:" + rel,
              os.path.isfile(os.path.join(MOD_DIR, rel)),
              "stale exception entry; remove it")

    check_extends_cycles()

    modinfo = os.path.join(MOD_DIR, "ModInfo.xml")
    check("modinfo-exists", os.path.isfile(modinfo))
    if os.path.isfile(modinfo) and roots.get("ModInfo.xml"):
        values = {p.tag: (p.get("value") or "").strip()
                  for p in parsed_root("ModInfo.xml")[0]}
        for field in ("Name", "DisplayName", "Description", "Author", "Version"):
            check("modinfo-field:" + field, bool(values.get(field)), "empty or missing")
        dirname = os.path.basename(MOD_DIR)
        check("modinfo-name-matches-directory",
              values.get("Name", "") == dirname,
              f"Name={values.get('Name', '')!r} but directory is {dirname!r}")
        check_release_version(values.get("Version", ""))

    check_release_notes()

    check("release-readme-exists",
          os.path.isfile(os.path.join(MOD_DIR, "README.txt")),
          "README.txt is the player-facing release readme the package ships")

    check("localization-inside-config",
          not os.path.isfile(os.path.join(MOD_DIR, "Localization.csv")),
          "move it to Config/Localization.csv; the engine ignores a root-level file")
    stray_localization = sorted(
        rel_f for rel_f in every if os.path.basename(rel_f) == "Localization.txt")
    check("no-localization-txt",
          not stray_localization,
          "V3 uses Localization.csv; " + repr(stray_localization))

    check("no-legacy-xui-dir",
          not os.path.isdir(os.path.join(MOD_DIR, "Config", "XUi")),
          "V3 path is Config/XUi_InGame/ (plus XUi_Menu/, XUi_Common/)")
    binding = re.compile(r"\{binding\b|\{#")
    for rel in files:
        if os.sep + "XUi" in rel:
            with open(os.path.join(MOD_DIR, rel), encoding="utf-8-sig") as handle:
                check("no-legacy-binding-syntax:" + rel,
                      not binding.search(handle.read()),
                      "use V3 {% expression %} bindings")

    return report()


if __name__ == "__main__":
    sys.exit(main())

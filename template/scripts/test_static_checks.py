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
- localization ships at Config/Localization.csv, never the mod root (the
  engine only loads mod localization from <mod>/Config/)
- no pre-V3 XUi shapes: no Config/XUi/ directory, no `{binding}` syntax
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Config XML files allowed a root other than <configs>, each with a reason.
# A stale entry (file gone) fails, so this list cannot rot.
NON_PATCH_CONFIG_XML: dict[str, str] = {}


def xml_files() -> list[str]:
    found = []
    for base, dirs, files in os.walk(MOD_DIR):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "dist", "bin", "obj", "__pycache__"})
        for f in sorted(files):
            if f.endswith(".xml"):
                found.append(os.path.relpath(os.path.join(base, f), MOD_DIR))
    return found


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


def check_release_notes() -> None:
    """The mod keeps a changelog with a home for unreleased work.

    Without an `Unreleased` section a release has nowhere to accumulate
    changes, so the notes arrive at the next version or never.
    """
    path = os.path.join(MOD_DIR, "CHANGELOG.md")
    check("changelog-exists", os.path.isfile(path), "no CHANGELOG.md in the mod root")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    check("changelog-has-unreleased-section",
          "## [Unreleased]" in text, "add a '## [Unreleased]' section")
    check("changelog-declares-the-declared-version",
          bool(re.search(rf"^## \[{re.escape(declared_version())}\]", text, re.M)),
          f"no released section for version {declared_version()}")


def declared_version() -> str:
    modinfo = os.path.join(MOD_DIR, "ModInfo.xml")
    if not os.path.isfile(modinfo):
        return ""
    for field in ET.parse(modinfo).getroot():
        if field.tag == "Version":
            return (field.get("value") or "").strip()
    return ""


def main() -> int:
    files = xml_files()
    roots: dict[str, str] = {}
    for rel in files:
        try:
            roots[rel] = ET.parse(os.path.join(MOD_DIR, rel)).getroot().tag
        except ET.ParseError as err:
            roots[rel] = ""
            check("xml-parses:" + rel, False, str(err))
            continue
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

    modinfo = os.path.join(MOD_DIR, "ModInfo.xml")
    check("modinfo-exists", os.path.isfile(modinfo))
    if os.path.isfile(modinfo) and roots.get("ModInfo.xml"):
        values = {p.tag: (p.get("value") or "").strip()
                  for p in ET.parse(modinfo).getroot()}
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
    stray_localization = "Localization.txt" if os.path.isfile(
        os.path.join(MOD_DIR, "Localization.txt")) else ""
    check("no-localization-txt",
          not any(rel_f.endswith("Localization.txt")
                  for rel_f in [*files, stray_localization]),
          "V3 uses Localization.csv")

    check("no-legacy-xui-dir",
          not os.path.isdir(os.path.join(MOD_DIR, "Config", "XUi")),
          "V3 path is Config/XUi_InGame/ (plus XUi_Menu/, XUi_Common/)")
    binding = re.compile(r"\{binding\b|\{#")
    for rel in files:
        if os.sep + "XUi" in rel:
            with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
                check("no-legacy-binding-syntax:" + rel,
                      not binding.search(handle.read()),
                      "use V3 {% expression %} bindings")

    return report()


if __name__ == "__main__":
    sys.exit(main())

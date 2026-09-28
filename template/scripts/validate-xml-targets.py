#!/usr/bin/env python3
"""Verify every XPath in Config/**/*.xml targets a node that exists in vanilla.

A patch whose xpath matches nothing applies silently — the game warns at
most, and the mod ships a no-op. This checks each patch operation's xpath
against the installed game's Data/Config/<same relative file>.

Needs SEVEN_DAYS_TO_DIE_DIR (env or .local.env), so it is a `make
validate-xml` target, not part of the offline `make test` suite.

stdlib ElementTree speaks a useful XPath subset (child paths, wildcards,
[@attr='value'] predicates). An xpath it cannot parse is reported as SKIP
for manual verification, never silently passed.

Ops that create content (`append` to an existing parent, `setattribute`)
are checked against their parent path; `set`/`remove`/`csv` must match.
"""

from __future__ import annotations

import glob
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import local_env  # noqa: E402

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ops the check understands; anything else is reported, never silently passed.
KNOWN_OPS = {"append", "insertBefore", "insertAfter", "setattribute",
             "set", "remove", "removeattribute", "csv"}


def game_dir() -> str:
    found = local_env.game_dir(Path(MOD_DIR))
    if found is None or not os.path.isdir(os.path.join(found, "Data", "Config")):
        sys.exit("ERROR: set SEVEN_DAYS_TO_DIE_DIR or .local.env to a valid game install.")
    return str(found)


def parse(path: str) -> ET.Element:
    """Parse `path` or exit naming it: a bare ET.ParseError says where the
    syntax broke, never which of the two files being compared broke, and a
    traceback out of a validation gate is not a usable report.
    """
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        sys.exit(f"ERROR: {path} is not well-formed XML: {exc}")
    except OSError as exc:
        sys.exit(f"ERROR: cannot read {path}: {exc}")


def find(root: ET.Element, xpath: str) -> bool | None:
    """True/False = resolvable; None = beyond ET's XPath subset."""
    # strip the vanilla root element name: /items/item/... -> ./item/...
    parts = xpath.split("/")
    if len(parts) < 2 or parts[0] != "":
        return None
    rel = "./" + "/".join(parts[2:]) if len(parts) > 2 else "."
    if rel.endswith("/"):
        return None
    # attribute target: check the owning element
    last = rel.rsplit("/", 1)[-1]
    if last.startswith("@"):
        rel = rel.rsplit("/", 1)[0] or "."
    try:
        return root.find(rel) is not None
    except SyntaxError:
        return None


def patch_files(mod_config: str) -> list[str]:
    """Every Config XML file, by its path relative to Config/, sorted.

    Recursive because the engine loads "<mod>/Config/" plus the vanilla file's
    own relative name, so the XUi patches live a directory down
    (Config/XUi_InGame/windows.xml). A flat listing would skip every one of
    them, which is the same silent no-op this script exists to catch.
    """
    pattern = os.path.join(mod_config, "**", "*.xml")
    return sorted(
        os.path.relpath(path, mod_config).replace(os.sep, "/")
        for path in glob.glob(pattern, recursive=True)
    )


def main() -> int:
    config_dir = os.path.join(game_dir(), "Data", "Config")
    failures = 0
    skips = 0
    mod_config = os.path.join(MOD_DIR, "Config")
    if not os.path.isdir(mod_config):
        print("no Config/ directory; nothing to validate")
        return 0
    for name in patch_files(mod_config):
        patch = parse(os.path.join(mod_config, name))
        if patch.tag != "configs":
            continue
        vanilla_path = os.path.join(config_dir, *name.split("/"))
        if not os.path.isfile(vanilla_path):
            print(f"SKIP {name}: no vanilla counterpart (new file)")
            skips += 1
            continue
        vanilla = parse(vanilla_path)
        for op in patch:
            xpath = op.get("xpath")
            if xpath is None:
                continue
            if op.tag not in KNOWN_OPS:
                print(f"SKIP {name}: unknown op <{op.tag}>")
                skips += 1
                continue
            resolved = find(vanilla, xpath)
            if resolved is None:
                print(f"SKIP {name}: xpath beyond checker subset: {xpath}")
                skips += 1
            elif resolved:
                print(f"PASS {name}: {xpath}")
            else:
                print(f"FAIL {name}: xpath matches nothing in vanilla: {xpath}",
                      file=sys.stderr)
                failures += 1
    print(f"{failures} failures, {skips} skipped (verify skips manually).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

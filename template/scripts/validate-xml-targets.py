#!/usr/bin/env python3
"""Verify every XPath in Config/*.xml targets a node that exists in vanilla.

A patch whose xpath matches nothing applies silently — the game warns at
most, and the mod ships a no-op. This checks each patch operation's xpath
against the installed game's Data/Config/<same file>.xml.

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
import local_env

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ops that create content: their xpath names the *parent* that must exist.
CHECK_PARENT_ONLY = {"append", "insertBefore", "insertAfter", "setattribute"}
# Ops that select the target itself.
CHECK_FULL = {"set", "remove", "removeattribute", "csv"}


def game_dir() -> str:
    found = local_env.game_dir(Path(MOD_DIR))
    if found is None or not os.path.isdir(os.path.join(found, "Data", "Config")):
        sys.exit("ERROR: set SEVEN_DAYS_TO_DIE_DIR or .local.env to a valid game install.")
    return str(found)


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


def main() -> int:
    config_dir = os.path.join(game_dir(), "Data", "Config")
    failures = 0
    skips = 0
    mod_config = os.path.join(MOD_DIR, "Config")
    if not os.path.isdir(mod_config):
        print("no Config/ directory; nothing to validate")
        return 0
    for path in sorted(glob.glob(os.path.join(mod_config, "**", "*.xml"), recursive=True)):
        # rglob, matching the engine and verify-patched-config.py: XmlPatcher
        # loads "<mod>/Config/" + the vanilla file's own relative name, so the
        # XUi patches live a directory down and a flat scan silently skips
        # them.
        name = os.path.relpath(path, mod_config).replace(os.sep, "/")
        patch = ET.parse(path).getroot()
        if patch.tag != "configs":
            continue
        vanilla_path = os.path.join(config_dir, name)
        if not os.path.isfile(vanilla_path):
            print(f"SKIP {name}: no vanilla counterpart (new file)")
            skips += 1
            continue
        vanilla = ET.parse(vanilla_path).getroot()
        for op in patch:
            xpath = op.get("xpath")
            if xpath is None:
                continue
            if op.tag not in CHECK_PARENT_ONLY and op.tag not in CHECK_FULL:
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

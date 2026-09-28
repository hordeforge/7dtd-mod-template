#!/usr/bin/env python3
"""Prove every shipped XPath patch actually applied, from the running game's own config.

A clean log is not evidence that a patch matched: an XPath that selects
nothing applies silently and logs nothing. A mod upstream of this template was
bitten by exactly that: four `progression.xml` appends were no-ops until the
`crafting_skills` container was added to their paths, with a clean log
throughout.

The engine dumps its fully patched configuration to a `ConfigsDump` directory
inside the save game on every game start, and annotates each patched-in element
with the mod that contributed it. Comparing what this mod's `Config/` asks for
against what the dump actually contains turns "no errors" into a positive check.

Usage:
    scripts/verify-patched-config.py                     # newest smoke world
    scripts/verify-patched-config.py --save-name NAME
    scripts/verify-patched-config.py --configs-dump DIR
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import local_env  # noqa: E402

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ModInfo Name == directory name (enforced by test_static_checks.py)
MOD_NAME = os.path.basename(MOD_DIR)

# Patches whose value depends on landing inside a specific parent. These are
# the ones a wrong-but-valid XPath would silently misplace.
# Placement-sensitive patches: (file, parent tag, parent name, regex the
# element must match inside that parent). A wrong-but-valid XPath lands an
# append in the wrong container silently; list such patches here, e.g.:
#   ("progression.xml", "crafting_skill", "craftingExplosives",
#    r'item="myModItem"'),
CONTAINER_EXPECTATIONS: tuple[tuple[str, str, str, str], ...] = ()

APPENDED_BY = re.compile(r'appended by:\s*"([^"]+)"')

# Ops whose children are new elements the engine attributes to this mod, so
# they are counted as "shipped". `set`/`remove`/`csv` change a matched node
# instead of adding one and contribute no new element to the dump.
INSERT_OPS = frozenset({"append", "insertBefore", "insertAfter"})


def configured_game_dir() -> str:
    found = local_env.game_dir(Path(MOD_DIR))
    return str(found) if found else ""


class VerifyError(RuntimeError):
    pass


def expected_elements() -> dict[str, int]:
    """Count the elements this mod's Config/ inserts, per target file."""
    counts: dict[str, int] = {}
    config_dir = os.path.join(MOD_DIR, "Config")
    # rglob, matching the engine: XmlPatcher loads "<mod>/Config/" + the
    # vanilla file's own relative name, so the XUi patches live a directory
    # down (Config/XUi_InGame/windows.xml) and a flat scan would silently
    # skip them — the same reason validate-xml-targets.py uses rglob.
    for path in sorted(glob.glob(os.path.join(config_dir, "**", "*.xml"), recursive=True)):
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            raise VerifyError(f"{path} is not well-formed XML: {exc}") from exc
        total = sum(
            len(list(op))
            for op in tree.getroot().iter()
            if op.tag in INSERT_OPS
        )
        if total:
            counts[os.path.relpath(path, config_dir).replace(os.sep, "/")] = total
    return counts


def read_dump(path: str) -> str:
    """Read one dump file, or report which file is unreadable.

    A dump the engine wrote under a permissions change or a half-copied
    world turns into a bare OSError traceback here, which reads as a crash
    instead of "this file could not be read" and loses every other file's
    counts.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as exc:
        raise VerifyError(f"cannot read {path}: {exc}") from exc


def applied_elements(dump_dir: str) -> dict[str, int]:
    """Count elements the dump attributes to this mod, per file."""
    counts: dict[str, int] = {}
    # The dump mirrors Data/Config's subdirectories (ConfigsDump/
    # XUi_InGame/windows.xml), so the scan must descend too or every nested
    # patch reads as missing.
    for path in sorted(glob.glob(os.path.join(dump_dir, "**", "*.xml"), recursive=True)):
        hits = sum(1 for name in APPENDED_BY.findall(read_dump(path))
                   if name == MOD_NAME)
        if hits:
            counts[os.path.relpath(path, dump_dir).replace(os.sep, "/")] = hits
    return counts


def check_containers(dump_dir: str) -> list[str]:
    """Verify the placement-sensitive patches landed in the right parent."""
    failures = []
    for filename, parent_tag, parent_name, pattern in CONTAINER_EXPECTATIONS:
        path = os.path.join(dump_dir, filename)
        if not os.path.exists(path):
            failures.append(f"{filename} is not in the dump")
            continue
        current = None
        found = False
        wrong_parent = None
        parent_re = re.compile(rf'<{parent_tag} name="([^"]+)"')
        target_re = re.compile(pattern)
        for line in read_dump(path).splitlines():
            match = parent_re.search(line)
            if match:
                current = match.group(1)
            if target_re.search(line):
                if current == parent_name:
                    found = True
                    break
                # One item may be appended under several parents by
                # design (the timed nuke unlocks at Explosives 65 and
                # Electrician 45), so keep scanning for the expected one
                # and only report the first wrong parent if none matches.
                if wrong_parent is None:
                    wrong_parent = current
        if found:
            continue
        # wrong_parent is set only where the target matched, so its absence
        # means the target is not in this file at all. `failures` is shared
        # across every expectation, so it must not decide this: two entries
        # carrying the same pattern would silence each other.
        if wrong_parent is not None:
            failures.append(
                f"{filename}: {pattern!r} landed under "
                f"{parent_tag} {wrong_parent!r}, expected {parent_name!r}"
            )
        else:
            failures.append(f"{filename}: {pattern!r} is not present at all")
    return failures


def find_dump(game_dir: str, save_name: str) -> str:
    saves = os.environ.get("SEVEN_DAYS_TO_DIE_SAVES_DIR")
    if not saves:
        if "/steamapps/common/" not in game_dir:
            raise VerifyError("cannot derive the saves directory; set SEVEN_DAYS_TO_DIE_SAVES_DIR.")
        steamapps = game_dir.split("/common/")[0]
        saves = os.path.join(
            steamapps, "compatdata", "251570", "pfx", "drive_c", "users", "steamuser",
            "AppData", "Roaming", "7DaysToDie", "Saves",
        )
    pattern = os.path.join(saves, "*", save_name if save_name else "*", "ConfigsDump")
    candidates = [p for p in glob.glob(pattern) if os.path.isdir(p)]
    if not candidates:
        raise VerifyError(
            f"no ConfigsDump found under {saves}. Load a world first — the engine "
            "writes the dump on game start."
        )
    try:
        return max(candidates, key=os.path.getmtime)
    except OSError as exc:
        raise VerifyError(f"cannot stat the ConfigsDump directories under {saves}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs-dump", default="", help="use this ConfigsDump directory")
    parser.add_argument("--save-name", default="", help="save whose dump to check")
    parser.add_argument("--game-dir", default=configured_game_dir())
    args = parser.parse_args()

    dump = args.configs_dump or find_dump(args.game_dir, args.save_name)
    print("CONFIGS DUMP")
    print(f"  {dump}")
    print()

    expected = expected_elements()
    applied = applied_elements(dump)

    print("PATCHED ELEMENTS")
    print(f"  {'file':<22} {'shipped':>8} {'applied':>8}")
    failures = []
    for filename in sorted(set(expected) | set(applied)):
        want = expected.get(filename, 0)
        got = applied.get(filename, 0)
        flag = "" if want == got else "   <-- MISMATCH"
        print(f"  {filename:<22} {want:>8} {got:>8}{flag}")
        if want != got:
            failures.append(
                f"{filename}: Config/ inserts {want} element(s) but the running game "
                f"has {got} attributed to {MOD_NAME}"
            )
    print()

    container_failures = check_containers(dump)
    print("PLACEMENT")
    if container_failures:
        for failure in container_failures:
            print(f"  FAIL  {failure}")
    else:
        print("  OK    no placement-sensitive patches declared, or all landed"
              " in their intended parents")
    print()

    failures += container_failures
    print("RESULT")
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        print()
        print("  A patch that selects nothing applies silently, so this is the check")
        print("  that a clean log cannot give you.")
        return 1
    total = sum(applied.values())
    print(f"  PASS: all {total} shipped patch elements are present in the running")
    print("        game's own configuration, in their intended parents.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

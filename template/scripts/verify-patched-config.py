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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import config_files
import local_env
import safe_xml

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

# The Steam app id and account name the engine's saves live under once Proton
# has rewritten the Windows paths, when SEVEN_DAYS_TO_DIE_SAVES_DIR is unset.
STEAM_APP_ID = "251570"
STEAM_ACCOUNT = "steamuser"

# Ops whose children are new elements the engine attributes to this mod, so
# they are counted as "shipped". The other known ops (`setattribute`, `set`,
# `remove`, `removeattribute`, `csv`) change a matched node instead of adding
# one and contribute no new element to the dump.
INSERT_OPS = frozenset({"append", "insertBefore", "insertAfter"})


def configured_game_dir() -> str:
    found = local_env.game_dir(Path(MOD_DIR))
    return str(found) if found else ""


class VerifyError(RuntimeError):
    """Input the check could not run on, as opposed to a patch that failed.

    Everything raised here is a state problem (no save loaded, malformed
    Config/ XML), so it exits 1. Exit 2 stays reserved for argparse rejecting
    the command line, which is what a script's caller branches on.
    """


def expected_elements() -> dict[str, int]:
    """Count the elements this mod's Config/ inserts, per target file."""
    counts: dict[str, int] = {}
    config_dir = os.path.join(MOD_DIR, "Config")
    for name in config_files.patch_files(config_dir):
        path = os.path.join(config_dir, *name.split("/"))
        try:
            tree = safe_xml.parse(path)
        except (ET.ParseError, safe_xml.DtdRejected) as exc:
            raise VerifyError(f"{path} is not well-formed XML: {exc}") from exc
        total = sum(
            1
            for op in tree.getroot().iter()
            if op.tag in INSERT_OPS
            for _ in op
        )
        if total:
            counts[name] = total
    return counts


def read_dump(path: str) -> str:
    """Read one dump file, or report which file is unreadable.

    A dump the engine wrote under a permissions change or a half-copied
    world turns into a bare OSError traceback here, which reads as a crash
    instead of "this file could not be read" and loses every other file's
    counts.
    """
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except OSError as exc:
        raise VerifyError(f"cannot read {path}: {exc}") from exc


def applied_elements(dump_dir: str) -> dict[str, int]:
    """Count elements the dump attributes to this mod, per file."""
    counts: dict[str, int] = {}
    # The dump mirrors Data/Config's subdirectories (ConfigsDump/
    # XUi_InGame/windows.xml), so the scan must descend too or every nested
    # patch reads as missing. A dump file is a whole vanilla config with every
    # mod's annotations on it, so the matches are counted as they are found:
    # materializing every `appended by` name in the file first would build a
    # list of all of them to keep one per file.
    for path in sorted(glob.glob(os.path.join(dump_dir, "**", "*.xml"), recursive=True)):
        hits = sum(1 for match in APPENDED_BY.finditer(read_dump(path))
                   if match.group(1) == MOD_NAME)
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


def newest_dump(candidates: list[str]) -> str:
    """The most recently written of `candidates`.

    `st_mtime_ns`, not `os.path.getmtime`: on a filesystem that records a
    whole second per timestamp (or one whose clock resolution is coarser still
    for a write that lands inside the same tick), two worlds loaded seconds
    apart tie, and `max` on a tie keeps whichever path the glob yielded first
    rather than either one in particular, so the check could read the world
    loaded before the one the caller was looking at. The path is the second
    key, which makes the answer the same on every run for the same tree.
    """
    return max(candidates, key=lambda path: (os.stat(path).st_mtime_ns, path))


def find_dump(game_dir: str, save_name: str) -> str:
    """Newest ConfigsDump directory for the save, by mtime.

    The saves root is SEVEN_DAYS_TO_DIE_SAVES_DIR. Without it the path is
    derived from the Steam install `game_dir` sits in, so the derivation only
    holds for a Steam-managed client install running through Proton: the
    "/steamapps/common/" guard is what makes the split valid, and AppID 251570
    is 7 Days to Die.
    """
    # Through the shared reader, not os.environ: the key is documented as a
    # .local.env key, and reading the process environment alone silently
    # ignored a value recorded in that file, falling back to the derived
    # Proton path and reporting a save that was never checked.
    saves = local_env.value(Path(MOD_DIR), "SEVEN_DAYS_TO_DIE_SAVES_DIR")
    if not saves:
        if "/steamapps/common/" not in game_dir:
            raise VerifyError("cannot derive the saves directory; set SEVEN_DAYS_TO_DIE_SAVES_DIR.")
        steamapps = game_dir.split("/common/")[0]
        saves = os.path.join(
            steamapps, "compatdata", STEAM_APP_ID, "pfx", "drive_c", "users", STEAM_ACCOUNT,
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
        return newest_dump(candidates)
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
    elif not CONTAINER_EXPECTATIONS:
        # Not a pass. The shipped template declares none, so an empty list is
        # a check that ran against nothing; reporting OK here would print the
        # one line a reader is most likely to stop at, for a check that never
        # looked at a container.
        print("  N/A   no placement-sensitive patches declared in "
              "CONTAINER_EXPECTATIONS; container placement was not checked")
    else:
        print("  OK    every placement-sensitive patch landed in its intended parent")
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
    print(f"  PASS: all {total} shipped patch elements are present in the running"
          " game's own configuration.")
    if CONTAINER_EXPECTATIONS:
        print("        Every placement-sensitive patch landed in its intended parent.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

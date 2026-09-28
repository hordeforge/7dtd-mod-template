#!/usr/bin/env python3
"""`scripts/verify-reproducible.sh` must build the same tree three times, and
must not leave its scratch tree behind.

The third archive is built from a `mktemp -d` copy of the entries the script
lists in TREE, so a file build.sh reads by path and TREE does not list is a
file the third pass does not have: the copy is missing the SDK pin the C#
build resolves, and the pass dies in build.sh with a read error instead of
comparing anything. TREE and build.sh's own references are held in step here.

The script also copies the whole mod into that scratch tree. Nothing outside
the script removes the copy, and it is a full source tree (sources, scripts,
a staged modlet), so an EXIT trap alone accumulates one per interrupted run: a
shell killed by a signal never runs its EXIT trap, so every Ctrl-C during the
three packaging passes leaves a copy behind that nothing will ever clean.

Two cases drive the real script against a fixture mod. One signals it once the
scratch directory exists and then requires TMPDIR to be empty again. The other
runs the same script to completion and requires its three archives to agree. No
game install and no network: the fixture is the scripts package.sh and build.sh
need, with no src/, so no DLL is compiled and no game install is read.

The archive-equality claim the script exists to make is held here on the
fixture, where it is three small zips rather than three builds, and
`make verify-reproducible` holds it on the real modlet. Before the first pass
ran at all, that difference was the gap: the first packaging pass used
`env -u SOURCE_DATE_EPOCH variant ...`, and `env` runs a program, not a shell
function, so it failed with "env: 'variant': No such file or directory" and
`make verify-reproducible` exited 1 on every tree, CI's included. Nothing
offline drove the script past that line, because the case that signals the run
does so as soon as the scratch directory appears, long before the first pass.

What is held is the lifecycle (an interrupted run owns nothing after it
exits), the comparison the script exists to make, and the fact that the tree
the third pass builds is the tree the first two built from.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# What the fixture mod needs to package itself: the scripts, and the three
# files build.sh stages into dist/<Name>/.
COPIED = ("scripts", "ModInfo.xml", "README.txt", "CHANGELOG.md")

# TREE=(...) in verify-reproducible.sh, one entry per line or several.
TREE_BLOCK = re.compile(r"^TREE=\((.*?)\)", re.MULTILINE | re.DOTALL)
# A path build.sh reaches by name at the mod root: "$ROOT/global.json",
# "${ROOT}/ruff.toml". A name with a slash in it is a directory the script
# lists itself or derives, not a file TREE has to carry.
ROOT_FILE = re.compile(r"\$\{?ROOT\}?/([A-Za-z0-9_.][A-Za-z0-9_.-]*)")

STARTUP_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.05
# Three packaging passes over a fixture with no src/ and no game install, so
# this is a small zip three times rather than a build.
PACKAGING_TIMEOUT_SECONDS = 180.0
GIT_ENV = {
    "GIT_AUTHOR_NAME": "offline gate",
    "GIT_AUTHOR_EMAIL": "gate@example.invalid",
    "GIT_COMMITTER_NAME": "offline gate",
    "GIT_COMMITTER_EMAIL": "gate@example.invalid",
}


def git_available() -> bool:
    return shutil.which("git") is not None


def stage_mod(root: str) -> str | None:
    """A committed copy of the mod, as verify-reproducible.sh requires it.

    It reads a commit timestamp for its first archive, so an uncommitted tree
    is not the thing under test: the fixture is a real one-commit checkout.
    """
    for entry in COPIED:
        source = os.path.join(MOD_DIR, entry)
        if not os.path.exists(source):
            continue
        target = os.path.join(root, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target)
        else:
            shutil.copy(source, target)
    commands = (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "fixture"],
    )
    for command in commands:
        done = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env={**os.environ, **GIT_ENV},
        )
        if done.returncode != 0:
            return None
    return os.path.join(root, "scripts", "verify-reproducible.sh")


def wait_for_scratch(directory: str) -> str | None:
    """The script's `mktemp -d`, once it exists, or None if it never does."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        entries = sorted(os.listdir(directory))
        if entries:
            return os.path.join(directory, entries[0])
        time.sleep(POLL_INTERVAL_SECONDS)
    return None


def interrupted_run_leaves_nothing(root: str, script: str) -> None:
    scratch_root = tempfile.mkdtemp(prefix="test-reproducible-scratch-")
    try:
        # Its own session, so the signal reaches the script alone the way a
        # supervisor's `kill` does; a terminal Ctrl-C already takes down the
        # whole foreground group and would prove nothing about the trap.
        runner = subprocess.Popen(
            [script],
            cwd=root,
            env={**os.environ, "TMPDIR": scratch_root},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        scratch = wait_for_scratch(scratch_root)
        runner.terminate()
        _stdout, _stderr = runner.communicate(timeout=STARTUP_TIMEOUT_SECONDS)
        check(
            "the run starts before it is signalled",
            scratch is not None,
            f"no scratch directory under {scratch_root}",
        )
        check(
            "an interrupted run leaves no scratch tree behind",
            scratch is not None and not os.path.exists(scratch),
            f"{scratch} survived exit {runner.returncode}",
        )
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def tree_entries() -> set[str]:
    """The entry names listed in verify-reproducible.sh's TREE array."""
    script = os.path.join(MOD_DIR, "scripts", "verify-reproducible.sh")
    with open(script, encoding="utf-8") as handle:
        found = TREE_BLOCK.search(handle.read())
    if found is None:
        return set()
    return set(re.findall(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*", found.group(1)))


def root_files_build_reads() -> set[str]:
    """The mod-root files build.sh names, that this mod actually ships.

    A name that is not on disk is not a file the copy needs: a mod without
    src/ has no global.json to miss, which is the case the third pass runs in
    today.
    """
    build = os.path.join(MOD_DIR, "scripts", "build.sh")
    with open(build, encoding="utf-8") as handle:
        return {name for name in ROOT_FILE.findall(handle.read())
                if os.path.isfile(os.path.join(MOD_DIR, name))}


def third_tree_is_the_whole_build() -> None:
    listed = tree_entries()
    check("verify-reproducible-lists-a-tree",
          bool(listed),
          "no TREE=(...) in scripts/verify-reproducible.sh")
    missing = sorted(root_files_build_reads() - listed)
    check("the-copied-tree-carries-everything-build-sh-reads",
          not missing,
          f"scripts/verify-reproducible.sh copies {sorted(listed)}, so the third "
          f"pass builds a tree build.sh cannot read: {missing} missing")


def three_passes_agree(root: str, script: str) -> None:
    """The comparison the script exists to make, driven to completion here.

    The first pass ran `env -u SOURCE_DATE_EPOCH variant ...`, and `env` runs a
    program, not a shell function, so it failed with "env: 'variant': No such
    file or directory" and `make verify-reproducible` exited 1 on every tree.
    Nothing offline drove the script past that line: the case below signals it
    the moment the scratch directory appears, long before the first pass. The
    fixture is the same one, and with no src/ in it the three passes are three
    small zips, so the equality the script claims is provable without an SDK.
    """
    done = subprocess.run(
        [script], cwd=root, capture_output=True, text=True,
        timeout=PACKAGING_TIMEOUT_SECONDS, check=False)
    check("the three packaging passes agree", done.returncode == 0,
          f"exit {done.returncode}: {(done.stderr or done.stdout)[-400:]}")


def main() -> int:
    if not os.path.isfile(os.path.join(MOD_DIR, "ModInfo.xml")):
        print(f"no {os.path.join(MOD_DIR, 'ModInfo.xml')}; nothing to verify")
        return 0

    third_tree_is_the_whole_build()

    if not git_available():
        print("git not found; the script reads a commit timestamp, so nothing to verify")
        return 0

    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        if script is None:
            print("could not make a committed fixture; nothing to verify")
            return 0
        interrupted_run_leaves_nothing(root, script)
        three_passes_agree(root, script)

    return report()


if __name__ == "__main__":
    sys.exit(main())

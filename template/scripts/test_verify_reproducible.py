#!/usr/bin/env python3
"""`scripts/verify-reproducible.sh` must not leave its scratch tree behind.

The script copies the whole mod into a `mktemp -d` tree to build the third
archive from another absolute path. Nothing outside the script removes that
copy, and it is a full source tree (sources, scripts, a staged modlet), so an
EXIT trap alone accumulates one per interrupted run: a shell killed by a
signal never runs its EXIT trap, so every Ctrl-C during the three packaging
passes leaves a copy behind that nothing will ever clean.

The case drives the real script against a fixture mod and signals it once the
scratch directory exists, then requires TMPDIR to be empty again. No game
install and no network: the fixture is the scripts package.sh and build.sh
need, with no src/, so no DLL is compiled and no game install is read.

The archive-equality claim the script exists to make is not re-proved here;
that needs three real packaging passes and is what `make verify-reproducible`
is for. What is held here is the lifecycle: an interrupted run owns nothing
after it exits.
"""

from __future__ import annotations

import os
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

STARTUP_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.05
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


def main() -> int:
    if not os.path.isfile(os.path.join(MOD_DIR, "ModInfo.xml")):
        print(f"no {os.path.join(MOD_DIR, 'ModInfo.xml')}; nothing to verify")
        return 0
    if not git_available():
        print("git not found; the script reads a commit timestamp, so nothing to verify")
        return 0

    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        if script is None:
            print("could not make a committed fixture; nothing to verify")
            return 0
        interrupted_run_leaves_nothing(root, script)

    return report()


if __name__ == "__main__":
    sys.exit(main())

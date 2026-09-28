#!/usr/bin/env python3
"""`make deploy-server` must leave the deployment intact when it is interrupted.

The deploy stages the modlet outside `Mods/` and swaps it in, which takes two
moves. Between them the target does not exist, so a Ctrl-C, a SIGTERM or a
failed second move in that window leaves no deployed mod at all, not a stale
one. A rerun does eventually put the new copy back, but the interrupted run is
the one that has to leave the previous deployment loaded, and a signal between
the moves is exactly what a rerun-only answer misses.

No server and no game install: `swap_into_place` is a shell function over three
paths, driven here in a temp directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

SERVER_COMMON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "server-common.sh"
)

SWAP = 'source "$1"\nswap_into_place "$2" "$3" "$4"\n'

# Stands in for `mv` on PATH: the first move is real, then the shell running the
# swap is signalled, which is the window a plain re-run test never reaches.
INTERRUPTING_MV = """#!/usr/bin/env bash
count=$(cat "$MV_STUB_COUNT" 2>/dev/null || printf 0)
count=$((count + 1))
printf '%s\\n' "$count" > "$MV_STUB_COUNT"
"$REAL_MV" "$@"
status=$?
if ((count == 1)); then
	kill -TERM "$PPID"
fi
exit "$status"
"""


Done = subprocess.CompletedProcess


def swap(server_common: str, source: str, target: str, previous: str) -> Done:
    return subprocess.run(
        ["bash", "-c", SWAP, "bash", server_common, source, target, previous],
        capture_output=True, text=True, timeout=60, check=False,
    )


def tree(root: str) -> list[str]:
    """Every path under root, relative and sorted: the only state these gates read."""
    seen: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs) + sorted(files):
            seen.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(seen)


def read(path: str) -> str:
    with open(os.path.join(path, "marker.txt"), encoding="utf-8") as handle:
        return handle.read()


def populated(path: str, marker: str) -> str:
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "marker.txt"), "w", encoding="utf-8") as handle:
        handle.write(marker)
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as root:
        stage = os.path.join(root, "stage")
        target = os.path.join(root, "Mods", "mod")
        previous = os.path.join(root, "stage.previous")
        os.makedirs(os.path.join(root, "Mods"))  # what deploy-server.sh does

        # No deployment yet: the stage is the deployment.
        populated(stage, "first")
        done = swap(SERVER_COMMON, stage, target, previous)
        check("a first deploy lands the staged copy", done.returncode == 0, done.stderr)
        check("nothing is left under the stage names afterwards",
              not os.path.exists(stage) and not os.path.exists(previous), str(tree(root)))

        # The rerun case the AGENTS.md rule is about: same source, twice.
        before = tree(target)
        populated(stage, "first")
        again = swap(SERVER_COMMON, stage, target, previous)
        check("redeploying the same copy succeeds", again.returncode == 0, again.stderr)
        check("a redeploy reaches the state one deploy reaches", tree(target) == before)

        # A different build replaces the old one, and leaves exactly one copy.
        populated(stage, "second")
        updated = swap(SERVER_COMMON, stage, target, previous)
        check("a new copy replaces the deployed one",
              updated.returncode == 0 and read(target) == "second", updated.stderr)
        check("the replaced copy is not left lying around",
              not os.path.exists(previous), str(tree(root)))

        # The second move fails: the deployment has to come back.
        failed = swap(SERVER_COMMON, os.path.join(root, "absent"), target, previous)
        check("a swap that cannot complete fails loudly", failed.returncode != 0, "no error")
        check("a swap that cannot complete keeps the deployed copy",
              os.path.isdir(target) and read(target) == "second", str(tree(root)))
        check("a swap that cannot complete leaves no previous copy behind",
              not os.path.exists(previous), str(tree(root)))

    with tempfile.TemporaryDirectory() as root:
        bin_dir = os.path.join(root, "bin")
        os.makedirs(bin_dir)
        stub = os.path.join(bin_dir, "mv")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write(INTERRUPTING_MV)
        os.chmod(stub, 0o755)

        stage = populated(os.path.join(root, "stage"), "new")
        target = populated(os.path.join(root, "Mods", "mod"), "old")
        previous = os.path.join(root, "stage.previous")

        interrupted = subprocess.run(
            ["bash", "-c", SWAP, "bash", SERVER_COMMON, stage, target, previous],
            capture_output=True, text=True, timeout=60, check=False,
            env={**os.environ, "PATH": bin_dir + os.pathsep + os.environ["PATH"],
                 "REAL_MV": shutil.which("mv") or "/bin/mv",
                 "MV_STUB_COUNT": os.path.join(root, "mv-count")},
        )
        check("the signal between the two moves ends the run",
              interrupted.returncode == 143, str(interrupted.returncode))
        check("an interrupted swap puts the previous deployment back",
              os.path.isdir(target) and read(target) == "old", str(tree(root)))
        check("an interrupted swap leaves no previous copy behind",
              not os.path.exists(previous), str(tree(root)))

    return report()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""`make deploy-server` must leave the deployment intact when it is interrupted.

The deploy stages the modlet outside `Mods/` and swaps it in, which takes two
moves. Between them the target does not exist, so a Ctrl-C, a SIGTERM or a
failed second move in that window leaves no deployed mod at all, not a stale
one. A rerun does eventually put the new copy back, but the interrupted run is
the one that has to leave the previous deployment loaded, and a signal between
the moves is exactly what a rerun-only answer misses.

A kill no trap can see, SIGKILL or a power loss, does leave the deployment
held in the previous path, and the rerun that clears the staging area has to
put it back before it clears. That recovery is driven here too, over the same
three paths.

No server and no game install: `swap_into_place` and `recover_previous` are
shell functions over three paths, driven here in a temp directory.
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
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "lib", "server-common.sh",
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


# Fails every move from the second on, so the first one succeeds and the
# restore of the previous copy is the move that fails: the window where the
# deployment is held aside and the second move is what usually fails too.
# `mv` failing twice is a full disk or a read-only mount, and the run has to
# say the deployed mod is gone rather than that it was put back.
FAILING_RESTORE_MV = """#!/usr/bin/env bash
count=$(cat "$MV_STUB_COUNT" 2>/dev/null || printf 0)
count=$((count + 1))
printf '%s\\n' "$count" > "$MV_STUB_COUNT"
if ((count >= 2)); then
\techo "mv stub: refusing" >&2
\texit 1
fi
exec "$REAL_MV" "$@"
"""


Done = subprocess.CompletedProcess


def swap(server_common: str, source: str, target: str, previous: str,
         path_prefix: str = "") -> Done:
    """Run one swap. `path_prefix` puts a directory of `mv` stubs on PATH."""
    env = None
    if path_prefix:
        env = {**os.environ, "PATH": path_prefix + os.pathsep + os.environ["PATH"],
               "REAL_MV": shutil.which("mv") or "/bin/mv",
               "MV_STUB_COUNT": os.path.join(path_prefix, "mv-count")}
    return subprocess.run(
        ["bash", "-c", SWAP, "bash", server_common, source, target, previous],
        capture_output=True, text=True, timeout=60, check=False, env=env,
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

        interrupted = swap(SERVER_COMMON, stage, target, previous,
                           path_prefix=bin_dir)
        check("the signal between the two moves ends the run",
              interrupted.returncode == 143, str(interrupted.returncode))
        check("an interrupted swap puts the previous deployment back",
              os.path.isdir(target) and read(target) == "old", str(tree(root)))
        check("an interrupted swap leaves no previous copy behind",
              not os.path.exists(previous), str(tree(root)))

    with tempfile.TemporaryDirectory() as root:
        bin_dir = os.path.join(root, "bin")
        os.makedirs(bin_dir)
        stub = os.path.join(bin_dir, "mv")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write(FAILING_RESTORE_MV)
        os.chmod(stub, 0o755)

        # A deployment is in place and a new one is staged, as deploy-server.sh
        # leaves them, and every move from the second on fails.
        stage = populated(os.path.join(root, "stage"), "new")
        target = populated(os.path.join(root, "Mods", "mod"), "old")
        previous = os.path.join(root, "stage.previous")

        failed = swap(SERVER_COMMON, stage, target, previous,
                      path_prefix=bin_dir)
        check("a swap whose restore also fails fails loudly",
              failed.returncode != 0, str(failed.returncode))
        # The deployment is genuinely gone here: the second move and the
        # restore both failed, so nothing is at the target. The message must
        # not claim the previous copy was put back, and must name where it
        # actually is, or the operator looks for a rollback that never ran.
        check("a swap whose restore also fails does not claim a rollback",
              "has been put back" not in failed.stderr, failed.stderr)
        check("a swap whose restore also fails names where the old copy is",
              previous in failed.stderr, failed.stderr)
        check("a swap whose restore also fails leaves nothing deployed",
              not os.path.exists(target), str(tree(root)))
        check("a swap whose restore also fails keeps the old copy on disk",
              os.path.isdir(previous) and read(previous) == "old", str(tree(root)))

    # The kill the traps above cannot see: SIGKILL between the two moves, or
    # a power loss. Nothing puts the deployment back at the time, so the
    # recovery on the next run is the only thing standing between an
    # interrupted deploy and a deleted one.
    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "Mods", "mod")
        previous = os.path.join(root, "stage.previous")
        os.makedirs(os.path.join(root, "Mods"))
        populated(target, "held")
        os.rename(target, previous)
        check("a kill between the moves really does leave the target missing",
              not os.path.exists(target) and os.path.isdir(previous), str(tree(root)))

        recovered = subprocess.run(
            ["bash", "-c", 'source "$1"; recover_previous "$2" "$3"',
             "bash", SERVER_COMMON, target, previous],
            capture_output=True, text=True, timeout=60, check=False,
        )
        check("the next run puts the held deployment back",
              recovered.returncode == 0 and read(target) == "held"
              and not os.path.exists(previous),
              f"exit={recovered.returncode} {recovered.stderr!r} {tree(root)}")

    with tempfile.TemporaryDirectory() as root:
        target = populated(os.path.join(root, "Mods", "mod"), "current")
        previous = populated(os.path.join(root, "stage.previous"), "stale")
        subprocess.run(
            ["bash", "-c", 'source "$1"; recover_previous "$2" "$3"',
             "bash", SERVER_COMMON, target, previous],
            capture_output=True, text=True, timeout=60, check=False,
        )
        check("recovery leaves a live deployment alone",
              read(target) == "current" and os.path.isdir(previous), str(tree(root)))

    return report()


if __name__ == "__main__":
    sys.exit(main())

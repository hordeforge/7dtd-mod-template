#!/usr/bin/env python3
"""`make server-smoke` log pruning must keep the newest logs and touch nothing else.

Every smoke run writes `<prefix>-server-smoke-<UTC stamp>.log` into the server
install's logs/, and only this pruning removes them, so a wrong version either
grows the directory without bound or deletes the log that the pass/fail
evidence is in.

The ordering is done by sorting names, not by asking the filesystem for mtimes:
the stamp is fixed width, so byte order is time order. That is also what keeps
the function off GNU-only `find -printf` and off `stat -c`, neither of which
exists on the BSD userland in macOS. These gates pin the outcome, so a later
port of the sort to something else has to keep the same answer.

No server and no game install: the function only touches a temp directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_COMMON = os.path.join(MOD_DIR, "scripts", "server-common.sh")


def mod_name() -> str:
    root = ET.parse(os.path.join(MOD_DIR, "ModInfo.xml")).getroot()
    for field in root.findall("Name"):
        value = field.get("value") or ""
        if value:
            return value
    return ""


def prune(log_dir: str, keep: str) -> str:
    """Run the real shell function; its stderr is the only thing we assert on."""
    done = subprocess.run(
        ["bash", "-c", 'source "$1"; prune_smoke_logs "$2" "$3"',
         "bash", SERVER_COMMON, log_dir, keep],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr)
    return done.stderr


def log_names(log_dir: str, prefix: str, runs: int) -> list[str]:
    """Ask the real function for names, the way consecutive runs do, and take each."""
    names = []
    for _ in range(runs):
        done = subprocess.run(
            ["bash", "-c", 'source "$1"; smoke_log_path "$2" "$3"',
             "bash", SERVER_COMMON, log_dir, prefix],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if done.returncode != 0:
            print(done.stderr, file=sys.stderr)
            return names
        name = os.path.basename(done.stdout.strip())
        touch(log_dir, name)
        names.append(name)
    return names


def touch(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("log\n")
    return path


def listing(directory: str) -> list[str]:
    return sorted(os.listdir(directory))


def main() -> int:
    prefix = mod_name().lower() + "-server-smoke-"
    stamps = ["20260101-000000", "20260101-010101", "20260101-020202", "20260101-030303"]

    with tempfile.TemporaryDirectory() as log_dir:
        logs = [touch(log_dir, prefix + stamp + ".log") for stamp in stamps]
        # Neighbours the pruning must never touch: the game's own logs use a
        # different prefix, and a same-prefix directory is not a log file.
        game_log = touch(log_dir, "output_log.txt")
        # Oldest by byte order (the space sorts before the '.log' dot), so it is
        # one of the pruned ones: a word-splitting path leaves it behind.
        spaced = touch(log_dir, prefix + "20260101-000000 12-00-00.log")
        stray_dir = os.path.join(log_dir, prefix + "20260101-050505.log")
        os.mkdir(stray_dir)

        prune(log_dir, "2")

        remaining = listing(log_dir)
        kept_logs = [n for n in remaining
                     if n.startswith(prefix) and n.endswith(".log")
                     and n != os.path.basename(stray_dir)]
        check("the two newest smoke logs survive",
              kept_logs == [os.path.basename(p) for p in logs[2:]], repr(remaining))
        check("the two oldest smoke logs are gone",
              not any(os.path.basename(p) in remaining for p in logs[:2]), repr(remaining))
        check("the game's own log is untouched",
              os.path.basename(game_log) in remaining, repr(remaining))
        check("a log path with a space is pruned whole, never split on it",
              os.path.basename(spaced) not in remaining
              and os.path.basename(game_log) in remaining, repr(remaining))
        check("a same-prefix directory is not deleted, and takes no keep slot",
              os.path.isdir(stray_dir) and len(kept_logs) == 2, repr(remaining))

    with tempfile.TemporaryDirectory() as log_dir:
        only = touch(log_dir, prefix + "20260101-000000.log")
        prune(log_dir, "0")
        check("keep=0 removes every smoke log", not os.path.exists(only))

    with tempfile.TemporaryDirectory() as log_dir:
        touch(log_dir, prefix + "20260101-000000.log")
        prune(log_dir, "5")
        check("keep above the log count keeps them all",
              listing(log_dir) == [prefix + "20260101-000000.log"])

    with tempfile.TemporaryDirectory() as log_dir:
        touch(log_dir, prefix + "20260101-000000.log")
        prune(log_dir, "not-a-number")
        check("a non-numeric keep is a no-op, not a delete-everything",
              listing(log_dir) == [prefix + "20260101-000000.log"])

    with tempfile.TemporaryDirectory() as log_dir:
        stderr = prune(log_dir, "3")
        check("an empty log directory is not an error", stderr == "", stderr)

    # Two runs inside one second are the collision the names have to survive.
    # Nothing here freezes the clock: whatever second the calls land in, the
    # second call must not reuse the first one's name, and a reverse name sort
    # must still read the later run as the newer one.
    with tempfile.TemporaryDirectory() as log_dir:
        names = log_names(log_dir, prefix, 2)
        check("two runs in a row are given two different log names",
              len(names) == 2 and names[0] != names[1], str(names))
        check("each name is the smoke-log name the pruner collects",
              all(n.startswith(prefix) and n.endswith(".log") for n in names), str(names))
        check("a reverse name sort reads the later run as the newer one",
              sorted(names, reverse=True) == [names[1], names[0]], str(names))

        prune(log_dir, "1")
        check("the quota keeps the later of the two colliding runs",
              listing(log_dir) == [names[1]], str(listing(log_dir)))

    return report()


if __name__ == "__main__":
    sys.exit(main())

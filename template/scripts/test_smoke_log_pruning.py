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

Two smoke runs are not hypothetical: a second `make server-smoke` against the
same server install, or one run per agent session, reaches the naming code in
the same second. The name is therefore claimed by creating it (O_EXCL), and
the parallel gate below is what keeps that claim honest.

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
SERVER_COMMON = os.path.join(MOD_DIR, "scripts", "lib", "server-common.sh")


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


# Enough callers to collide on the one-second stamp several times over.
CONCURRENT_CLAIMERS = 8


def claim_in_parallel(log_dir: str, prefix: str, claimers: int) -> list[str]:
    """Start `claimers` shells at once and return the names they each claimed.

    Started together, not run one after another: the collision this pins only
    exists while they are inside the naming code together, and a check-then-act
    version hands the same name to all of them.
    """
    running = [
        subprocess.Popen(
            ["bash", "-c", 'source "$1"; smoke_log_path "$2" "$3"',
             "bash", SERVER_COMMON, log_dir, prefix],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(claimers)
    ]
    names = []
    for done in running:
        out, err = done.communicate(timeout=60)
        if done.returncode != 0:
            print(err, file=sys.stderr)
        elif out.strip():
            names.append(os.path.basename(out.strip()))
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

    # A leading zero is an octal prefix to `$(( ))`, so a quota of `08` used to
    # fail the expansion, print "value too great for base" to stderr and prune
    # nothing at all, leaving logs/ to grow by one file per run. It reads as
    # eight, and it prunes to eight.
    with tempfile.TemporaryDirectory() as log_dir:
        padded = [touch(log_dir, prefix + f"20260101-0000{n:02d}.log") for n in range(10)]
        stderr = prune(log_dir, "08")
        check("a zero-padded keep prunes as the number it reads as",
              stderr == ""
              and sorted(os.path.basename(p) for p in padded[2:])
              == sorted(n for n in listing(log_dir) if n.startswith(prefix)),
              stderr or repr(listing(log_dir)))

    # Past 64 bits the arithmetic wraps rather than failing, so a digit run
    # that long is refused instead of compared as whatever it wraps to.
    with tempfile.TemporaryDirectory() as log_dir:
        only = touch(log_dir, prefix + "20260101-000000.log")
        stderr = prune(log_dir, "18446744073709551616")
        check("a keep past 64 bits is a no-op, not a wrapped count",
              stderr == "" and listing(log_dir) == [os.path.basename(only)],
              stderr or repr(listing(log_dir)))

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

    # Concurrent smoke runs share one logs/ directory and reach the naming
    # code in the same second, so the claim has to be atomic rather than a
    # test followed by a create: every caller that comes away with a name has
    # to come away with one of its own.
    with tempfile.TemporaryDirectory() as log_dir:
        names = claim_in_parallel(log_dir, prefix, CONCURRENT_CLAIMERS)
        check(f"{CONCURRENT_CLAIMERS} concurrent runs are given {CONCURRENT_CLAIMERS} "
              "different log names",
              len(names) == CONCURRENT_CLAIMERS and len(set(names)) == CONCURRENT_CLAIMERS,
              str(sorted(names)))
        check("each concurrent run's name exists and belongs to it alone",
              all(os.path.isfile(os.path.join(log_dir, name)) for name in names)
              and sorted(listing(log_dir)) == sorted(names),
              str(sorted(listing(log_dir))))
        prune(log_dir, "1")
        check("the quota still sees every concurrent run as its own log",
              len(listing(log_dir)) == 1, str(listing(log_dir)))

    with tempfile.TemporaryDirectory() as missing:
        done = subprocess.run(
            ["bash", "-c", 'source "$1"; smoke_log_path "$2" "$3"',
             "bash", SERVER_COMMON, os.path.join(missing, "logs"), prefix],
            capture_output=True, text=True, timeout=60, check=False,
        )
        check("a log directory that is not there fails instead of returning a name",
              done.returncode != 0 and "does not exist" in done.stderr,
              f"exit={done.returncode} stderr={done.stderr!r}")

    return report()


if __name__ == "__main__":
    sys.exit(main())

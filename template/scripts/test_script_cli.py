#!/usr/bin/env python3
"""Every script with a command line answers --help, and refuses what it does not take.

The scripts under scripts/ are the mod's CLI. A script that ignores its
arguments cannot answer a question about them: `scripts/build.sh --help`
staged a modlet instead of printing help, `scripts/build.sh --dry-run` ran the
full build and looked accepted, and `scripts/playtest.sh --help` forwarded
the flag to the upstream runner as a suite id. A mistyped flag a tool
silently drops is worse than one it refuses, because the run then reports
success over work nobody asked for.

The contract, held here for every script that has one:

  -h/--help  usage on stdout, exit 0, no work started
  no argument  the run itself
  an argument the script does not take  usage on stderr, exit 2

Exit 2 is reserved for the command line so a caller can tell "I asked
wrongly" from "the work failed" (exit 1) without reading a message. Only
the argument-handling paths are exercised, so this gate needs no game
install, no server, and no dotnet SDK, and starts no run. The entry points
with arguments of their own hold their own contract where they are
implemented (`test_configure_server_config.py` for
`configure-server-config.py`, `verify-patch-targets.py`'s own parser for its
`--game-dir`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import gate

SCRIPTS = Path(__file__).resolve().parent

# Every script whose whole command line is "run it", and so must refuse an
# argument rather than drop it. A new executable script in this directory is
# added here: the set is the list, so a script that never learned to answer
# --help fails this gate.
NO_ARGUMENT_SCRIPTS = (
    "build.sh",
    "deploy-server.sh",
    "install-server.sh",
    "lint-py.sh",
    "lint-shell.sh",
    "package.sh",
    "server-smoke.sh",
    "verify-reproducible.sh",
)

# Scripts that take positional arguments of their own, and so answer --help
# and then validate the rest themselves.
POSITIONAL_SCRIPTS = ("new-session-id.sh", "playtest.sh", "run-offline-tests.sh")

PYTHON_ENTRY_POINTS = ("validate-xml-targets.py",)


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    command = ([sys.executable] if script.endswith(".py") else ["bash"])
    return subprocess.run(
        [*command, str(SCRIPTS / script), *args],
        capture_output=True, text=True, check=False, timeout=60,
    )


def check_help(script: str) -> None:
    helped = run(script, "--help")
    gate.check(f"{script} --help exits 0 with usage on stdout",
               helped.returncode == 0 and "USAGE" in helped.stdout
               and "EXIT STATUS" in helped.stdout and helped.stderr == "",
               f"exit={helped.returncode} stdout={helped.stdout!r} "
               f"stderr={helped.stderr!r}")


def main() -> int:
    for script in NO_ARGUMENT_SCRIPTS:
        check_help(script)
        wrong = run(script, "--not-a-flag")
        gate.check(f"{script} refuses an argument it does not take (exit 2)",
                   wrong.returncode == 2 and "--not-a-flag" in wrong.stderr
                   and "USAGE" in wrong.stderr and wrong.stdout == "",
                   f"exit={wrong.returncode} stdout={wrong.stdout!r} "
                   f"stderr={wrong.stderr!r}")

    for script in POSITIONAL_SCRIPTS:
        check_help(script)

    # --help must win over the positional argument it sits next to, or a
    # request for help starts the run it was asking about.
    for script, args in (("new-session-id.sh", ["--help", "claude"]),
                         ("playtest.sh", ["--help", "some-suite"]),
                         ("run-offline-tests.sh", ["--help", "telnet"])):
        helped = run(script, *args)
        gate.check(f"{script} --help wins over a positional argument",
                   helped.returncode == 0 and "USAGE" in helped.stdout,
                   f"args={args!r} exit={helped.returncode} "
                   f"stdout={helped.stdout!r} stderr={helped.stderr!r}")

    for entry in PYTHON_ENTRY_POINTS:
        check_help(entry)
        wrong = run(entry, "--not-a-flag")
        gate.check(f"{entry} refuses an argument it does not take (exit 2)",
                   wrong.returncode == 2 and "--not-a-flag" in wrong.stderr
                   and "USAGE" in wrong.stderr and wrong.stdout == "",
                   f"exit={wrong.returncode} stdout={wrong.stdout!r} "
                   f"stderr={wrong.stderr!r}")

    return gate.main()


if __name__ == "__main__":
    raise SystemExit(main())

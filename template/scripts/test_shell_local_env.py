#!/usr/bin/env python3
"""The shell reader for .local.env loads a valid file, and fails loudly on a bad one.

`.local.env` is sourced by every install-dependent target, so the four
variants of that load had drifted into a copy in each. One reader
(`load_local_env` in server-common.sh) replaced them; these gates pin what it
promises:

- keys reach the caller's environment, and an already-set environment value
  wins over the file, so a one-off `make ... KEY=value` needs no edit;
- a CRLF file, which any edit from a Windows editor leaves, loads;
- a file that cannot be parsed stops the target and names the file, instead of
  dying on a /dev/fd path or a command-not-found on a value;
- no file is not an error, and the file is not run when there is nothing to
  read.

No game install and no server: the loader only reads a temp directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_COMMON = os.path.join(MOD_DIR, "scripts", "server-common.sh")

PROBE = ('source "$1"; load_local_env "$2"; '
         'printf "%s|%s\\n" "${SEVEN_DAYS_TO_DIE_DIR:-unset}" "${DOTNET_ROOT:-unset}"')


def load(root: str, preset: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(preset or {})
    return subprocess.run(
        ["bash", "-c", PROBE, "bash", SERVER_COMMON, root],
        capture_output=True, text=True, timeout=60, env=env, check=False,
    )


def write(root: str, body: str, *, newline: str = "\n") -> None:
    with open(os.path.join(root, ".local.env"), "w", encoding="utf-8", newline="") as handle:
        handle.write(body.replace("\n", newline))


def main() -> int:
    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\nDOTNET_ROOT=""\n')
        done = load(root)
        check("a valid file loads", done.returncode == 0 and done.stdout == "/srv/7dtd|unset\n",
              done.stdout + done.stderr)

        done = load(root, {"SEVEN_DAYS_TO_DIE_DIR": "/from/env"})
        check("the environment wins over the file", done.stdout == "/from/env|unset\n", done.stdout)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\nDOTNET_ROOT=""\n', newline="\r\n")
        done = load(root)
        check("a CRLF file loads", done.returncode == 0 and done.stdout == "/srv/7dtd|unset\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd\n')
        done = load(root)
        check("an unparseable file fails the target", done.returncode != 0, done.stdout)
        check("the failure names the file", os.path.join(root, ".local.env") in done.stderr,
              done.stderr)
        check("a failed load stops before any key is used", done.stdout == "", done.stdout)

    with tempfile.TemporaryDirectory() as root:
        done = load(root)
        check("a missing file is not an error",
              done.returncode == 0 and done.stdout == "unset|unset\n", done.stdout + done.stderr)

    return report()


if __name__ == "__main__":
    sys.exit(main())

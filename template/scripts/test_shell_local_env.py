#!/usr/bin/env python3
"""The shell reader for .local.env loads a valid file, and fails loudly on a bad one.

`.local.env` is sourced by every install-dependent target, so the four
variants of that load had drifted into a copy in each. One reader
(`load_local_env` in server-common.sh) replaced them; a fifth private copy in
run-offline-tests.sh then drifted again, so the narrow read lives beside the
wide one and these gates pin what both promise:

- keys reach the caller's environment, and an already-set environment value
  wins over the file, so a one-off `make ... KEY=value` needs no edit;
- a CRLF file, which any edit from a Windows editor leaves, loads;
- a file that cannot be parsed stops the target and names the file, instead of
  dying on a /dev/fd path or a command-not-found on a value;
- no file is not an error, and the file is not run when there is nothing to
  read;
- `local_env_value` answers one key with the same grammar (single or double
  quotes, `export `, last assignment wins) and exports nothing.

No game install and no server: the loader only reads a temp directory.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_COMMON = os.path.join(MOD_DIR, "scripts", "lib", "server-common.sh")

PROBE = ('source "$1"; load_local_env "$2"; '
         'printf "%s|%s\\n" "${SEVEN_DAYS_TO_DIE_DIR:-unset}" "${DOTNET_ROOT:-unset}"')

# The narrow reader, in the environment load_local_env would have produced, so
# a key the two answer differently is caught rather than shipped.
NARROW_PROBE = ('source "$1"; local_env_value "$2" "$3"; printf "|end\\n"')

# An `if` whose condition asks whether a configuration key is set or empty:
# `if [[ -z "$KEY" ]]`, `if [[ -v KEY ]]`, `if [[ -n ${KEY:-} ]]`. This is the
# shape that made the load conditional; `if [[ -d "$SRC" ]]` is not a question
# about a key and must not match.
KEY_TEST = re.compile(
    r"\bif\b[^#]*?(\[\[\s+-[znv]\s|\[\[\s+-v\s+[A-Z]|-[znv]\s+\"?\$\{?[A-Z][A-Z0-9_]*)")

# A block opener, and the matching closer, at the start of a statement. Only
# line-leading keywords count, so a `; then` closing a one-line `if` does not
# open a block that nothing closes.
BLOCK_OPEN = re.compile(r"^(?:if|for|while|until|case)\b")
BLOCK_CLOSE = re.compile(r"^(?:fi|done|esac)\b")


def load(root: str, preset: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    # The probe reports two keys, so both are cleared from the inherited
    # environment first: a host that exports DOTNET_ROOT (any machine with a
    # dotnet SDK does) or SEVEN_DAYS_TO_DIE_DIR would answer the "a missing
    # file is not an error" case with a value the test never wrote.
    env = {k: v for k, v in os.environ.items()
           if k not in ("DOTNET_ROOT", "SEVEN_DAYS_TO_DIE_DIR")}
    env.update(preset or {})
    return subprocess.run(
        ["bash", "-c", PROBE, "bash", SERVER_COMMON, root],
        capture_output=True, text=True, timeout=60, env=env, check=False,
    )


def write(root: str, body: str, *, newline: str = "\n") -> None:
    with open(os.path.join(root, ".local.env"), "w", encoding="utf-8", newline="") as handle:
        handle.write(body.replace("\n", newline))


def server_lane_keeps_the_rest_of_the_file() -> None:
    """A one-off key overrides that key, and not the whole file.

    `load_server_environment` derives its config and SteamCMD paths from the
    file, and a caller that named only the server directory on the command line
    used to get a derived config and a default SteamCMD instead of the ones the
    machine was set up with: the file was read only when the directory was
    unset, so one set key threw the rest away. The whole scripts/ tree is
    copied, because the library finds its root from its own path.
    """
    with tempfile.TemporaryDirectory() as root:
        shutil.copytree(os.path.join(MOD_DIR, "scripts"), os.path.join(root, "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        write(root, 'SEVEN_DAYS_TO_DIE_SERVER_DIR="/srv/from-file"\n'
                    'SEVEN_DAYS_TO_DIE_SERVER_CONFIG="/etc/7dtd/mod-config.xml"\n'
                    'SEVEN_DAYS_TO_DIE_STEAMCMD_DIR="/opt/steamcmd"\n')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("SEVEN_DAYS_TO_DIE_")}
        env["SEVEN_DAYS_TO_DIE_SERVER_DIR"] = "/srv/from-env"
        done = subprocess.run(
            ["bash", "-c",
             'source "$1"; load_server_environment; printf "%s\\n" "$SERVER_DIR" "$SERVER_CONFIG"',
             "bash", os.path.join(root, "scripts", "lib", "server-common.sh")],
            capture_output=True, text=True, timeout=60, env=env, check=False,
        )
        check("the environment wins for the key it names",
              done.returncode == 0 and done.stdout.splitlines()[:1] == ["/srv/from-env"],
              done.stdout + done.stderr)
        check("the rest of the file still loads",
              done.returncode == 0
              and done.stdout.splitlines()[1:2] == ["/etc/7dtd/mod-config.xml"],
              done.stdout + done.stderr)


def read_value(root: str, key: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("DOTNET_ROOT",)}
    return subprocess.run(
        ["bash", "-c", NARROW_PROBE, "bash", SERVER_COMMON, root, key],
        capture_output=True, text=True, timeout=60, env=env, check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\nDOTNET_ROOT=""\n')
        done = load(root)
        check("a valid file loads", done.returncode == 0 and done.stdout == "/srv/7dtd|unset\n",
              done.stdout + done.stderr)

        done = load(root, {"SEVEN_DAYS_TO_DIE_DIR": "/from/env"})
        check("the environment wins over the file",
              done.returncode == 0 and done.stdout == "/from/env|unset\n",
              done.stdout + done.stderr)

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

    server_lane_keeps_the_rest_of_the_file()

    # local_env_value is the narrow read, for a caller that must not put the
    # rest of the file into its children's environment. The copy it replaced
    # was a private sed that stripped only double quotes and ignored `export`,
    # so a single-quoted OFFLINE_TEST_JOBS='2' failed its integer test and the
    # run silently used one job per core. A key now has one answer whichever
    # reader asks.
    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\n')
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("a double-quoted value is unquoted",
              done.returncode == 0 and done.stdout == "/srv/7dtd|end\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, "SEVEN_DAYS_TO_DIE_DIR='/srv/7dtd'\n")
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("a single-quoted value is unquoted",
              done.returncode == 0 and done.stdout == "/srv/7dtd|end\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'export SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\n')
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("an export prefix is accepted, as sourcing the file would",
              done.returncode == 0 and done.stdout == "/srv/7dtd|end\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/first"\nSEVEN_DAYS_TO_DIE_DIR="/second"\n')
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("a later assignment wins, as sourcing the file gives",
              done.returncode == 0 and done.stdout == "/second|end\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\n', newline="\r\n")
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("a CRLF file is read", done.returncode == 0 and done.stdout == "/srv/7dtd|end\n",
              done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        done = read_value(root, "SEVEN_DAYS_TO_DIE_DIR")
        check("a missing file prints nothing",
              done.returncode == 0 and done.stdout == "|end\n", done.stdout + done.stderr)

    with tempfile.TemporaryDirectory() as root:
        write(root, 'SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd"\nDOTNET_ROOT="/opt/dotnet"\n')
        done = read_value(root, "DOTNET_ROOT")
        check("the narrow read exports nothing",
              done.returncode == 0 and done.stdout == "/opt/dotnet|end\n"
              and "SEVEN_DAYS_TO_DIE_DIR" not in done.stdout,
              done.stdout + done.stderr)

    check("no target loads .local.env conditionally", *conditional_loads())

    return report()


def conditional_loads() -> tuple[bool, str]:
    """Whether no `load_local_env` call sits inside a test of a key.

    A caller that loaded the file only when one key was unset dropped every
    other key in it whenever that key was already exported, so a documented
    setting resolved to nothing without a word. `build.sh` read that way and
    then told a failing build to "point DOTNET_ROOT in .local.env at one".

    The test is the condition, not the nesting: a load inside a function
    body, or under `if [[ -d "$SRC" ]]`, is unconditional with respect to
    configuration and is fine. Only a load guarded by a question about a
    key's own value is the defect.
    """
    guarded: list[str] = []
    for path in sorted(Path(MOD_DIR, "scripts").rglob("*.sh")):
        # The innermost open block, and the condition of each. A load is
        # guarded when the nearest open `if` asked about a key; an inner block
        # opened for another reason (a `for` over files, a `while` reading a
        # dump) supersedes the outer condition rather than adding to it.
        blocks: list[str | None] = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if BLOCK_OPEN.match(stripped):
                match = KEY_TEST.search(stripped)
                blocks.append(match.group(0) if match else None)
            if "load_local_env" in stripped:
                for condition in blocks:
                    if condition is not None:
                        guarded.append(f"{path.name}:{number} under {condition}")
            while blocks and BLOCK_CLOSE.match(stripped):
                blocks.pop()
    return not guarded, "; ".join(guarded)


if __name__ == "__main__":
    sys.exit(main())

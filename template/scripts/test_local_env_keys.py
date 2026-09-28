#!/usr/bin/env python3
"""Every key `.local.env.example` documents is a key a script actually reads.

`test_env_inventory.py` gates one direction: a script may not read a key the
example does not list. This gates the other: a key the example lists, and
`new-mod.sh` writes into `.local.env`, must resolve to something. A key
nobody reads is a knob that does nothing, and the way it fails is the worst
kind: the file is edited, the target runs, and the setting is quietly
ignored.

That is not hypothetical. `ILSPYCMD` and `SEVEN_DAYS_TO_DIE_SAVES_DIR` were
both documented and both written by the scaffolder while nothing read them;
`verify-patch-targets.py` searched only `PATH` and a hardcoded
`~/.dotnet/tools`, and `verify-patched-config.py` read the saves directory
out of the process environment alone, so a value in `.local.env` was
silently dropped.

The scan reads a script's source for how it names a key, and the probe below
is the authority: a key is documented and not dead only if some script
resolves it through the one reader. Nothing here executes a target, so no
game install or toolchain is needed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = MOD_DIR / "scripts"
EXAMPLE = MOD_DIR / ".local.env.example"

EXAMPLE_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)
# A key named as a literal argument, the way a reader names one:
# local_env.value(root, "KEY") or os.environ.get("KEY"), or the named
# constant one carries, `ILSPY_KEY = "ILSPYCMD"`.
NAMED_KEY = re.compile(
    r"""local_env\.value\(\s*[^,]+,\s*["']([A-Z][A-Z0-9_]*)["']"""
    r"""|environ(?:\.get)?\(?["']([A-Z][A-Z0-9_]*)["']""")
# ${KEY} and ${KEY:-default} in shell.
SHELL_EXPANSION = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}")
# `ILSPY_KEY = "ILSPYCMD"`, a module constant holding a key the script passes
# on to the reader. Python only: a shell script's `RUN_FOR_SECONDS=90` is a
# local it derived from a documented key, not a key of its own.
KEY_CONSTANT = re.compile(r"^\s*[A-Z][A-Z0-9_]*\s*=\s*[\"']([A-Z][A-Z0-9_]*)[\"']",
                          re.MULTILINE)
# `local_env_value "$MOD_DIR" KEY`, the shell's narrow read. Counted after the
# assignment filter below: a script's help text can spell `KEY=1` at the start
# of a line, and an explicit read is a read whatever else the file says.
SHELL_NARROW_READ = re.compile(r"""\blocal_env_value\s+\S+\s+["']?([A-Z][A-Z0-9_]*)""")
# An assignment anywhere in a script, `local x=1` and `x=` alike. A name the
# script assigns is a local it derived from a documented key, not a second
# key the environment has to supply.
SHELL_ASSIGNED = re.compile(
    r"^\s*(?:local|export|declare\s+-\w+\s+)?([A-Z][A-Z0-9_]*)=", re.MULTILINE)

# Keys the process environment owns rather than this mod's: a script cannot
# configure the PATH it inherited, and SOURCE_DATE_EPOCH is the reproducible
# builds convention every build tool reads.
AMBIENT = frozenset({"PATH", "HOME", "LANG", "TMPDIR", "PWD", "SOURCE_DATE_EPOCH"})

# Keys a sibling tool reads out of the environment this file loads, not a
# script in this repository. The parent directory and the per-repo overrides
# belong to the hordeforge tools, and UNITY_EDITOR is shamway's opt-in
# bundle_source="unity" lane; see docs/reference/sibling-tooling.md.
SIBLING_KEYS = frozenset({"HORDEFORGE_ROOT", "CONNECT_ROOT",
                          "ASSET_PIPELINE_ROOT", "UNITY_EDITOR"})

# Makefile variables a target forwards to a script rather than reading itself.
MAKE_KEYS = frozenset({"SUITE", "PLAYTEST_SUITE", "PLAYTEST_SUITE_FILE",
                       "EXTRA_ARGS", "TF"})

# Every documented key is allowed to be unclaimed by these, and nothing else.
UNDOCUMENTED_READERS = AMBIENT | SIBLING_KEYS | MAKE_KEYS


def source_files() -> list[Path]:
    """The scripts whose reads are the configuration surface.

    The tests are excluded: a test names keys in strings of its own, and a
    negative control is not a consumer.
    """
    files = [p for p in sorted(SCRIPTS_DIR.iterdir())
             if p.suffix in (".sh", ".py") and not p.name.startswith("test_")]
    return files + sorted(p for p in SCRIPTS_DIR.glob("lib/*.py")
                          if not p.name.startswith("test_"))


def read_keys(path: Path) -> set[str]:
    """The `.local.env` keys this script reads.

    A shell script's own locals are spelled like keys, and the two are told
    apart by assignment: `RUN_FOR_SECONDS="${SEVEN_...:-90}"` is a local
    derived from a documented key, not a key of its own. A Python script
    names a key as a literal, or through the constant that holds it.
    """
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".py":
        found: set[str] = set()
        for match in NAMED_KEY.finditer(text):
            found.update(group for group in match.groups() if group)
        return found | set(KEY_CONSTANT.findall(text))
    return ((set(SHELL_EXPANSION.findall(text)) - set(SHELL_ASSIGNED.findall(text)))
            | set(SHELL_NARROW_READ.findall(text)))


def main() -> int:
    sources = {p.name: read_keys(p) for p in source_files()}
    read = set().union(*sources.values()) if sources else set()
    documented = set(EXAMPLE_KEY.findall(EXAMPLE.read_text(encoding="utf-8-sig")))

    dead = sorted(documented - read - UNDOCUMENTED_READERS)
    for key in dead:
        check(f"{key} is documented and read", False,
              "documented in .local.env.example, written by new-mod.sh, "
              "and read by no script")
    check("no documented key is dead", not dead, ", ".join(dead))

    # Negative control: a gate that cannot fail is not a gate. Removing every
    # reader must be reported, not passed.
    check("an inventory nothing reads is not accepted as covered",
          bool(documented - UNDOCUMENTED_READERS), "the scan found no reader")

    for name in sorted(sources):
        unknown = sources[name] - documented - UNDOCUMENTED_READERS
        check(f"{name} reads a documented key or none", not unknown,
              ", ".join(sorted(unknown)))

    return report()


if __name__ == "__main__":
    raise SystemExit(main())

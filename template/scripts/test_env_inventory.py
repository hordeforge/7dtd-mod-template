#!/usr/bin/env python3
"""Every environment key the scripts read is documented in .local.env.example.

An option nobody can find is an option nobody sets, and a key spelled with one
wrong letter is a key that resolves to nothing: `.local.env` holds `KEY="v"`
lines and every reader looks a key up by name, so a typo reads as "not
configured" and the target silently runs on its built-in default. The example
file is the inventory (it is what new-mod.sh and a new machine start from),
so a key that is not in it is a key with no documented valid values.

The scan covers the shell targets and the Python entry points, not the tests:
a test names keys in strings of its own, and a negative control is not an
option.
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

# ${KEY:-default} and ${KEY} in shell; KEY="v" in an os.environ lookup.
SHELL_KEY = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}")
# An assignment anywhere in a script, `local x=1` and `x=` alike.
SHELL_ASSIGNED = re.compile(
    r"^\s*(?:local|export|declare\s+-\w+\s+)?([A-Z][A-Z0-9_]*)=", re.MULTILINE)
PYTHON_KEY = re.compile(r"""environ(?:\.get)?\(?["']([A-Z][A-Z0-9_]*)["']""")
# An assignment to a key of the file, the way a reader names it.
EXAMPLE_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)
# Names the process environment owns rather than this mod: a script cannot
# configure the PATH it inherited, and documenting it here would be noise.
AMBIENT = frozenset({"PATH", "HOME", "LANG", "TMPDIR", "PWD"})


def source_files() -> list[Path]:
    """The scripts whose environment reads are the app's configuration surface."""
    files = [p for p in sorted(SCRIPTS_DIR.iterdir())
             if p.suffix in (".sh", ".py") and not p.name.startswith("test_")]
    files += sorted(p for p in SCRIPTS_DIR.glob("lib/*.py") if not p.name.startswith("test_"))
    return files


def read_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8-sig")
    keys = set(PYTHON_KEY.findall(text))
    keys |= set(re.findall(r"""environ\[["']([A-Z][A-Z0-9_]*)["']\]""", text))
    if path.suffix == ".sh":
        # A name the script assigns is a local it derived, not a key the
        # environment supplies: RUN_FOR_SECONDS and GAME_DIR are configured
        # through SEVEN_DAYS_TO_DIE_* and documented as those.
        assigned = set(SHELL_ASSIGNED.findall(text))
        keys |= set(SHELL_KEY.findall(text)) - assigned
    return keys - AMBIENT


def undocumented(sources: dict[str, set[str]], documented: set[str]) -> dict[str, list[str]]:
    return {name: sorted(keys - documented) for name, keys in sources.items() if keys - documented}


def main() -> int:
    sources = {p.name: read_keys(p) for p in source_files()}
    documented = set(EXAMPLE_KEY.findall(EXAMPLE.read_text(encoding="utf-8-sig")))

    missing = undocumented(sources, documented)
    for name in sorted(missing):
        check(f"{name} reads no undocumented key", False, ", ".join(missing[name]))

    # A gate that cannot fail is not a gate: an example file with the whole
    # inventory struck out must be reported, not passed.
    empty = undocumented(sources, set())
    check("an empty inventory is not accepted as documented",
          bool(empty) and any(empty.values()), str(sorted(empty))[:200])

    if not missing:
        print(f"PASS every key read by {len(sources)} scripts is in .local.env.example")
    return report()


if __name__ == "__main__":
    raise SystemExit(main())

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
option. Both shell spellings are read, `${KEY:-default}` and `$KEY`: a target
that only the second form mentions is a target the inventory cannot see.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = MOD_DIR / "scripts"
EXAMPLE = MOD_DIR / ".local.env.example"

# ${KEY:-default} and ${KEY} in shell; KEY="v" in an os.environ lookup.
SHELL_KEY = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}")
# The unbraced $KEY form, which is just as valid in shell and just as often
# written. Reading only the braced form left a whole spelling invisible: a
# target that `cd "$PLAYTEST_ROOT"` never entered the inventory, so an
# undocumented key written that way reported nothing at all.
SHELL_BARE_KEY = re.compile(r"\$(?!\{)([A-Z][A-Z0-9_]*)")
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


def shell_sources() -> list[Path]:
    """The shell files whose assignments name the derived locals of the set."""
    files = [p for p in sorted(SCRIPTS_DIR.iterdir())
             if p.suffix == ".sh" and not p.name.startswith("test_")]
    return files + sorted(p for p in SCRIPTS_DIR.glob("lib/*.sh"))


def derived_locals(sources: list[Path]) -> set[str]:
    """Every name any shell file in the set assigns.

    A name one script derives and another sources is a local of the set, not a
    key the environment supplies: ROOT and SERVER_DIR are assigned in
    server-common.sh and read bare from deploy-server.sh, so a per-file
    assignment set would report them as undocumented keys.
    """
    names: set[str] = set()
    for path in sources:
        names |= set(SHELL_ASSIGNED.findall(path.read_text(encoding="utf-8-sig")))
    return names


def read_keys(path: Path, derived: set[str] | None = None) -> set[str]:
    text = path.read_text(encoding="utf-8-sig")
    keys = set(PYTHON_KEY.findall(text))
    keys |= set(re.findall(r"""environ\[["']([A-Z][A-Z0-9_]*)["']\]""", text))
    if path.suffix == ".sh":
        # A name the script assigns is a local it derived, not a key the
        # environment supplies: RUN_FOR_SECONDS and GAME_DIR are configured
        # through SEVEN_DAYS_TO_DIE_* and documented as those.
        assigned = set(SHELL_ASSIGNED.findall(text))
        keys |= set(SHELL_KEY.findall(text)) - assigned
        # The bare form carries the same question, so it is asked against the
        # set's whole assignment list: the braced form above stays per-file,
        # so nothing it already reported stops being reported.
        keys |= set(SHELL_BARE_KEY.findall(text)) - (derived or set()) - assigned
    return keys - AMBIENT


def undocumented(sources: dict[str, set[str]], documented: set[str]) -> dict[str, list[str]]:
    return {name: sorted(keys - documented) for name, keys in sources.items() if keys - documented}


def negative_controls(derived: set[str]) -> None:
    """Prove the shell scan bites, in both spellings and both directions.

    A scan that reads no reference reports nothing and exits 0, so the
    controls pin that an undocumented key is caught braced and bare, and that
    a local the set derives is not. The fixtures are written to a throwaway
    directory, never into the shared scripts/, so a run this gate is killed
    out of leaves nothing behind.
    """
    with tempfile.TemporaryDirectory() as directory:
        braced = Path(directory) / "braced.sh"
        bare = Path(directory) / "bare.sh"
        assigned = Path(directory) / "assigned.sh"
        braced.write_text('cd "${UNDOCUMENTED_BRACED}"\n', encoding="utf-8")
        bare.write_text('cd "$UNDOCUMENTED_BARE"\n', encoding="utf-8")
        assigned.write_text('ROOT="/x"\ncd "$ROOT"\n', encoding="utf-8")
        check("negative control: a braced undocumented key is reported",
              "UNDOCUMENTED_BRACED" in read_keys(braced, derived),
              repr(sorted(read_keys(braced, derived))))
        check("negative control: a bare undocumented key is reported",
              "UNDOCUMENTED_BARE" in read_keys(bare, derived),
              repr(sorted(read_keys(bare, derived))))
        # The two exemptions, which are what keeps the bare form from
        # reporting every local in the tree: a name this file assigns, and a
        # name any shell file in the set assigns.
        check("negative control: a local this file assigns is exempt",
              read_keys(assigned, derived) == set(),
              repr(sorted(read_keys(assigned, derived))))
        check("negative control: a local another shell file assigns is exempt",
              read_keys(bare, derived | {"UNDOCUMENTED_BARE"}) == set(),
              repr(sorted(read_keys(bare, derived | {"UNDOCUMENTED_BARE"}))))


def main() -> int:
    derived = derived_locals(shell_sources())
    sources = {p.name: read_keys(p, derived) for p in source_files()}
    documented = set(EXAMPLE_KEY.findall(EXAMPLE.read_text(encoding="utf-8-sig")))

    missing = undocumented(sources, documented)
    for name in sorted(missing):
        check(f"{name} reads no undocumented key", False, ", ".join(missing[name]))

    # A gate that cannot fail is not a gate: an example file with the whole
    # inventory struck out must be reported, not passed.
    empty = undocumented(sources, set())
    check("an empty inventory is not accepted as documented",
          bool(empty) and any(empty.values()), str(sorted(empty))[:200])

    negative_controls(derived)

    if not missing:
        print(f"PASS every key read by {len(sources)} scripts is in .local.env.example")
    return report()


if __name__ == "__main__":
    raise SystemExit(main())

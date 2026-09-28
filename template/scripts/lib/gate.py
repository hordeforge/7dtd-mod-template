"""The pass/fail bookkeeping most `scripts/test_*.py` share.

One definition of `check` so a gate cannot drift from its neighbours: a PASS
line on stdout, a FAIL line on stderr, and a non-zero exit from `main`. The
gates that keep their own bookkeeping do not import this. The three fuzz gates
report an iteration count and a per-kind counter instead of one line per
assertion; `test_decompile_failures.py` collects its failures and prints them
at the end; `test_local_path_inventory.py`, `test_configure_server_config.py`
and `test_script_cli.py` each print a single aggregate line. All of them keep
the PASS-on-stdout, FAIL-on-stderr, non-zero-exit shape. Import it by putting
this directory on the path; a caller in `scripts/` does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from gate import check, main as report

`FAILURES` is process-wide and never reset, so a module that reports twice
counts every check twice, and a check after `report()` still reaches the
process exit code. One `main()` per process, which is how `make test` runs
each gate. The template repository's own `ci/check-*.py` import this file too,
for the same reason.
"""

from __future__ import annotations

import sys

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one assertion; `detail` explains a failure and is dropped on a pass."""
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def main() -> int:
    """Report the run and return the process exit code."""
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0

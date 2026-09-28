"""The pass/fail bookkeeping every scripts/test_*.py shares.

One definition of `check` so a gate cannot drift from its neighbours: a PASS
line on stdout, a FAIL line on stderr, and a non-zero exit from `main`.
Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
"""

from __future__ import annotations

import sys

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def main() -> int:
    """Report the run and return the process exit code."""
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0

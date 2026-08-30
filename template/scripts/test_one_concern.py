#!/usr/bin/env python3
"""One concern per playtest run. Mixing unrelated suites is a defect.

A case belongs to the suite whose feature it proves. Consecutive steps of
one feature stay in that suite. A child that is part of a built prefab is
not a second suite. Unrelated features are separate invocations, not a
comma-list. The harness (hordeforge/7dtd-playtest) refuses an undeclared
2+ suite list; this gate keeps the rule in AGENTS.md so a generated mod
cannot lose it.
"""

from __future__ import annotations

import os
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(MOD_DIR, "AGENTS.md")

REQUIRED = (
    "One concern per playtest run",
    "comma-list",
    "actions of one feature",
    "part of a built prefab",
    "separate invocations",
)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
        return
    FAILURES.append(name)
    print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def main() -> int:
    with open(AGENTS, encoding="utf-8") as handle:
        text = handle.read()
    check(
        "negative control: an AGENTS.md without the rule fails",
        "One concern per run" not in "make playtest SUITE=a,b",
    )
    missing = [item for item in REQUIRED if item not in text]
    check("AGENTS.md states one concern per playtest run", missing == [], "missing " + repr(missing))
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

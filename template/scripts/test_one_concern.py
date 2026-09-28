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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check, main as report  # noqa: E402

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(MOD_DIR, "AGENTS.md")

REQUIRED = (
    "One concern per playtest run",
    "comma-list",
    "actions of one feature",
    "part of a built prefab",
    "separate invocations",
)


def missing_from(text: str) -> list[str]:
    return [item for item in REQUIRED if item not in text]


def main() -> int:
    with open(AGENTS, encoding="utf-8") as handle:
        text = handle.read()
    check(
        "negative control: an AGENTS.md without the rule fails",
        missing_from("make playtest SUITE=a,b") == list(REQUIRED),
        repr(missing_from("make playtest SUITE=a,b")),
    )
    missing = missing_from(text)
    check("AGENTS.md states one concern per playtest run", missing == [], "missing " + repr(missing))
    return report()


if __name__ == "__main__":
    sys.exit(main())

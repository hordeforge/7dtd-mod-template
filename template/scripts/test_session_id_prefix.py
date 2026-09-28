#!/usr/bin/env python3
"""No shell script may hardcode an agent family into a playtest session id.

The session id is what the shared playtest lock file publishes as the
holder. An upstream wrapper once hardcoded a family, so every run claimed
the shared client under a family that was not the one running, and a
session reading the lock was told the wrong holder.

The prefix comes from the environment. `AGENTS.md`'s "Parallel-session IDs"
requires a real family per session; this gate only stops the wrapper from
inventing one on everybody's behalf.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")

FAMILIES = ("codex", "claude", "grok", "gemini", "gpt", "shamway")
CALL = re.compile(r"new-session-id\.sh\"?\s+(\S+)")


def hardcoded_families(body: str) -> list[str]:
    """Every agent family a `new-session-id.sh` call names as a literal."""
    hits = []
    for argument in CALL.findall(body):
        bare = argument.strip('"').strip("'")
        if bare in FAMILIES:
            hits.append(bare)
    return hits


def negative_controls() -> None:
    """Prove the scan bites, in both directions.

    A gate that finds no call site at all reports nothing and exits 0, so the
    controls pin that a literal family is caught and the environment form the
    rule prescribes is not.
    """
    check("negative control: a hardcoded family is caught",
          hardcoded_families('scripts/new-session-id.sh claude\n') == ["claude"],
          repr(hardcoded_families('scripts/new-session-id.sh claude\n')))
    check("negative control: a quoted literal is caught",
          hardcoded_families('scripts/new-session-id.sh "codex"\n') == ["codex"],
          repr(hardcoded_families('scripts/new-session-id.sh "codex"\n')))
    check("negative control: the environment form is not caught",
          hardcoded_families(
              'scripts/new-session-id.sh "${PLAYTEST_AGENT:-agent}"\n') == [])


def main() -> int:
    negative_controls()

    scripts = sorted(f for f in os.listdir(SCRIPTS) if f.endswith(".sh"))
    # A scan of nothing is a green run that checked nothing.
    check("the scan read the shell scripts it is meant to scan",
          len(scripts) > 0, "no .sh found in scripts/")

    for name in scripts:
        path = os.path.join(SCRIPTS, name)
        with open(path, encoding="utf-8-sig") as handle:
            body = handle.read()
        hits = hardcoded_families(body)
        if not hits:
            continue
        check(
            name + " takes its session prefix from the environment",
            False,
            "hardcodes " + repr(hits[0]) + "; the lock would name that family "
            "whoever is actually running. Use \"${PLAYTEST_AGENT:-agent}\".",
        )

    return report()


if __name__ == "__main__":
    raise SystemExit(main())

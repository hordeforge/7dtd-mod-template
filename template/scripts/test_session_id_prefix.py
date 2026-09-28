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
from gate import check, main as report  # noqa: E402

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")

FAMILIES = ("codex", "claude", "grok", "gemini", "gpt", "shamway")
CALL = re.compile(r"new-session-id\.sh\"?\s+(\S+)")


def main() -> int:
    for name in sorted(os.listdir(SCRIPTS)):
        if not name.endswith(".sh"):
            continue
        path = os.path.join(SCRIPTS, name)
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for argument in CALL.findall(body):
            bare = argument.strip('"').strip("'")
            check(
                name + " takes its session prefix from the environment",
                not any(bare == family for family in FAMILIES),
                "hardcodes " + repr(bare) + "; the lock would name that family "
                "whoever is actually running. Use \"${PLAYTEST_AGENT:-agent}\".",
            )
    return report()


if __name__ == "__main__":
    raise SystemExit(main())

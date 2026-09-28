#!/usr/bin/env python3
"""`make verify-patched-config` reads the newest world, and says so twice.

`newest_dump` in `scripts/verify-patched-config.py` picks which ConfigsDump
the check reads. A tie in the filesystem's timestamp granularity (a whole
second per write, or two worlds loaded inside one tick) used to leave the
choice to glob order, so the check could read the world loaded before the one
the caller was looking at and report a clean tree it never looked at. The
answer has to be the same for the same tree on every run, which is what the
tie-break is for.

Usage: scripts/test_verify_patched_config.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "verify-patched-config.py")


def load_verifier():
    """The script under test, imported under its own name.

    By path rather than by name: the file's name is not an identifier, and the
    mod directory it sits in is the one `make verify-patched-config` runs it
    from.
    """
    spec = importlib.util.spec_from_file_location("verify_patched_config", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_dump(root: str, name: str, when: float) -> str:
    path = os.path.join(root, name)
    os.mkdir(path)
    os.utime(path, (when, when))
    return path


def main() -> int:
    newest_dump = load_verifier().newest_dump
    with tempfile.TemporaryDirectory() as root:
        old = make_dump(root, "a-old", 1_700_000_000)
        new = make_dump(root, "b-new", 1_700_000_600)
        same_a = make_dump(root, "a-tie", 1_700_000_600)
        same_b = make_dump(root, "b-tie", 1_700_000_600)

        check("the most recently written dump wins, whatever the glob order",
              newest_dump([old, new, same_a, same_b]) == same_b,
              newest_dump([old, new, same_a, same_b]))
        # The same tree offered in the other order, and inside a namespace that
        # is the same one every run uses: an answer that moved with the input
        # order would pass the line above whenever the glob happened to hand
        # back the older dump first.
        check("the answer does not depend on the order the paths arrive in",
              newest_dump([same_a, same_b, new, old]) == same_b,
              newest_dump([same_a, same_b, new, old]))
        check("a tie on the timestamp is broken the same way every time",
              newest_dump([same_a, same_b]) == newest_dump([same_b, same_a]) == same_b)
        check("a single candidate is that candidate", newest_dump([old]) == old)
    return report()


if __name__ == "__main__":
    sys.exit(main())

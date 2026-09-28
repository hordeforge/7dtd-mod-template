#!/usr/bin/env python3
"""The ilspycmd install line is the pinned one, everywhere it is written.

`verify-patch-targets.py` matches signatures out of text the installed
ilspycmd wrote, so a floating decompiler decides whether a Harmony target
passes. The pin lives in `ILSPYCMD_VERSION`; the usage text and the
missing-tool error are literal strings a docstring cannot build, so this gate
holds them to the constant instead of trusting three copies to stay alike.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIER = os.path.join(SCRIPT_DIR, "verify-patch-targets.py")
UNPINNED = "dotnet tool install -g ilspycmd\n"


def load_verifier() -> ModuleType:
    """Import the hyphenated script by path; it has no package of its own."""
    spec = importlib.util.spec_from_file_location("verify_patch_targets", VERIFIER)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot load " + VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    verifier = load_verifier()
    pinned = verifier.ILSPYCMD_VERSION

    check("the pin is a concrete version, not a range or a branch",
          pinned[:1].isdigit() and pinned.count(".") >= 2
          and not any(mark in pinned for mark in "*^~<>=| ,"),
          repr(pinned))

    command = verifier.ilspy_install_command()
    check("the install line names the pinned version",
          command == f"dotnet tool install -g ilspycmd --version {pinned}", command)
    check("the usage text carries the pinned version",
          command in verifier.DESCRIPTION, "usage text drifted from the pin")

    with open(VERIFIER, encoding="utf-8-sig", errors="replace") as handle:
        source = handle.read()
    check("no unpinned install line is left in the source",
          UNPINNED not in source, "a second install line skipped the pin")

    for output, drifted in (
        (f"ILSpy version {pinned}", False),
        ("9.1.0.7988", True),
        ("no version here", True),
        ("", True),
    ):
        warning = verifier.ilspy_pin_warning(output)
        check(f"a {output!r} probe warns={drifted}", (warning is not None) is drifted,
              repr(warning))

    return report()


if __name__ == "__main__":
    sys.exit(main())

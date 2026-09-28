#!/usr/bin/env python3
"""The derived server config must be re-runnable, and a failed run must write nothing.

`make install-server` derives the mod's own serverconfig from the vanilla one
and only does so when the target is missing. That makes the target's write the
one place a second execution matters: a target left half-written by an
interrupted run is trusted forever after (the file exists, so the lane skips
the derivation) and the server lane then fails on a config no rerun will
rewrite. The write is staged and renamed, and this gate holds that, together
with the plain idempotency of the derivation itself: the same source run twice
produces byte-identical output, so a rerun after a fixed source converges
instead of drifting. The documented exit statuses (0 written, 1 the source
cannot be used, 2 wrong arguments) are held too: nothing derives them from
each other, so a caller reading the wrong one is caught only here.

No game install and no server: the script takes a source and a target path,
and this gate supplies both in a temporary directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import gate

SCRIPTS = Path(__file__).resolve().parent
CONFIGURE = SCRIPTS / "configure-server-config.py"

SOURCE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<ServerSettings>\n"
    '\t<property name="EACEnabled" value="true"/>\n'
    '\t<property name="ServerName" value="7DTD"/>\n'
    "</ServerSettings>\n"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONFIGURE), *args],
        capture_output=True, text=True, check=False, timeout=60,
    )


def read(path: Path) -> str:
    return path.read_bytes()


def main() -> int:
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        source = root / "serverconfig.xml"
        source.write_text(SOURCE, encoding="utf-8")
        target = root / "serverconfig.mod.xml"

        first = run(str(source), str(target))
        gate.check("the first run writes the target", first.returncode == 0, first.stderr)
        gate.check("the vanilla source is left untouched",
              read(source) == SOURCE.encode("utf-8"))
        gate.check("EACEnabled is off in the derived config",
              'name="EACEnabled" value="false"' in read(target).decode("utf-8"),
              read(target).decode("utf-8"))
        gate.check("no staging file is left beside the target",
              sorted(p.name for p in root.iterdir())
              == ["serverconfig.mod.xml", "serverconfig.xml"],
              repr(sorted(p.name for p in root.iterdir())))

        after_first = read(target)
        second = run(str(source), str(target))
        gate.check("a second run succeeds", second.returncode == 0, second.stderr)
        gate.check("a second run over an existing target is byte-identical",
              read(target) == after_first)

        # A failed run must leave the previous target as it was, or the server
        # lane is stuck on a config no rerun regenerates.
        broken = root / "broken.xml"
        broken.write_text("<ServerSettings><property name=\"EACEnabled\"",
                          encoding="utf-8")
        failed = run(str(broken), str(target))
        gate.check("an unparsable source is reported, not raised",
              failed.returncode == 1 and "Traceback" not in failed.stderr,
              failed.stderr)
        gate.check("a failed run leaves the previous target intact",
              read(target) == after_first)
        gate.check("a failed run leaves no staging file",
              sorted(p.name for p in root.iterdir())
              == ["broken.xml", "serverconfig.mod.xml", "serverconfig.xml"],
              repr(sorted(p.name for p in root.iterdir())))

        no_eac = root / "no-eac.xml"
        no_eac.write_text("<ServerSettings><property name=\"ServerName\" value=\"x\"/>"
                          "</ServerSettings>", encoding="utf-8")
        refused = run(str(no_eac), str(root / "never.xml"))
        gate.check("a source with no EACEnabled property is refused",
              refused.returncode == 1 and not (root / "never.xml").exists(),
              refused.stderr)

        # The script's exit statuses are a contract the server lane and any
        # caller read: 2 for wrong arguments, 1 for a source that cannot be
        # used, 0 for a help request. Nothing derives them from each other, so
        # a wrong code is only visible here.
        missing = run(str(root / "absent.xml"), str(root / "never.xml"))
        gate.check("a source that does not exist is refused and named",
              missing.returncode == 1 and "absent.xml" in missing.stderr
              and not (root / "never.xml").exists(),
              f"exit={missing.returncode} stderr={missing.stderr!r}")

        for label, args in (("none", []), ("source only", [str(source)]),
                            ("one too many", [str(source), str(target), "extra"])):
            wrong = run(*args)
            gate.check(f"wrong arguments ({label}) exit 2 with usage",
                  wrong.returncode == 2 and "usage:" in wrong.stderr,
                  f"args={args!r} exit={wrong.returncode} stderr={wrong.stderr!r}")

        helped = run("--help")
        gate.check("--help exits 0 and prints the usage contract",
              helped.returncode == 0 and "SOURCE_CONFIG TARGET_CONFIG" in helped.stdout,
              f"exit={helped.returncode} stdout={helped.stdout!r}")

    return gate.main()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""`scripts/package.sh` must reject a SOURCE_DATE_EPOCH a zip entry cannot hold.

Every entry in the archive is stamped with SOURCE_DATE_EPOCH, and the
reproducible-build contract says the same source always produces the same
archive. That only holds while the epoch is one Info-ZIP can represent: the
entry timestamp is a 32-bit DOS date, 7 bits of year counted from 1980, so it
spans 1980-01-01T00:00:00Z (315532800) through 2107-12-31T23:59:58Z
(4354819198) and nothing outside it.

Info-ZIP does not reject an out-of-range mtime, it wraps it silently. Every
epoch past 2107-12-31T23:59:58Z lands in the archive as some other date
entirely, so a mistyped or copied SOURCE_DATE_EPOCH produces an archive that is
perfectly reproducible and stamped with a date nobody asked for, and the only
sign is a wrong `unzip -l`. A value below 1980 wraps the same way. This gate
drives the real script and requires the rejection, and reads the real archive
back for the accepted case, so the range it holds is the range that works.

No game install and no network: the tree is copied into a temporary directory
with its dist/ already staged, which is the state `make package` hands
package.sh.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_NAME = os.path.basename(MOD_DIR)
# The representable range, as the DOS date field defines it: 7 bits of year
# from 1980, two-second resolution, 1980-01-01T00:00:00Z through
# 2107-12-31T23:59:58Z inclusive.
MIN_DOS_EPOCH = 315532800
MAX_DOS_EPOCH = 4354819198
# A copy of the mod that is small enough to stage in a temp directory: the
# scripts that package.sh sources, and the one file it insists is staged.
COPIED = ("scripts", "ModInfo.xml")


def stage_mod(root: str) -> str:
    """A copy of the mod with dist/<Name>/ModInfo.xml in place, as build.sh leaves it."""
    for entry in COPIED:
        source = os.path.join(MOD_DIR, entry)
        if not os.path.exists(source):
            continue
        target = os.path.join(root, entry)
        if os.path.isdir(source):
            # A gate running beside this one can be writing a bytecode file into
            # scripts/__pycache__ through a temporary name it renames away, and
            # a copy that lists the name before the rename fails on it.
            shutil.copytree(source, target,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, target)
    staged = os.path.join(root, "dist", MOD_NAME)
    os.makedirs(staged, exist_ok=True)
    shutil.copy(os.path.join(MOD_DIR, "ModInfo.xml"),
                os.path.join(staged, "ModInfo.xml"))
    return os.path.join(root, "scripts", "package.sh")


def package(script: str, epoch: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [script],
        capture_output=True, text=True, timeout=300, check=False,
        env={**os.environ, "SOURCE_DATE_EPOCH": epoch},
    )


def entry_stamps(archive: str) -> list[str]:
    """Every entry's stored date, read back out of the archive itself."""
    with zipfile.ZipFile(archive) as opened:
        return [info.date_time for info in opened.infolist()]


def main() -> int:
    if not os.path.isfile(os.path.join(MOD_DIR, "ModInfo.xml")):
        print(f"no {os.path.join(MOD_DIR, 'ModInfo.xml')}; nothing to package")
        return 0

    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        archive = os.path.join(root, "dist", MOD_NAME + ".zip")

        below = package(script, str(MIN_DOS_EPOCH - 1))
        check("an epoch before 1980 is rejected, not wrapped",
              below.returncode != 0
              and str(MIN_DOS_EPOCH) in below.stderr
              and not os.path.exists(archive),
              f"exit={below.returncode} stderr={below.stderr!r}")

        above = package(script, str(MAX_DOS_EPOCH + 1))
        check("an epoch past 2107-12-31T23:59:58Z is rejected, not wrapped",
              above.returncode != 0
              and str(MAX_DOS_EPOCH) in above.stderr
              and not os.path.exists(archive),
              f"exit={above.returncode} stderr={above.stderr!r}")

        accepted = package(script, str(MAX_DOS_EPOCH))
        check("the last representable epoch is accepted",
              accepted.returncode == 0 and os.path.exists(archive),
              f"exit={accepted.returncode} stderr={accepted.stderr!r}")
        # Read the archive back rather than trusting the exit status: an
        # accepted epoch that Info-ZIP then wrapped would still exit 0, and
        # 2107-12-31T23:59:58Z is the one value that shows it.
        check("the last representable epoch is stored as that date, read back from the zip",
              os.path.exists(archive)
              and entry_stamps(archive) == [(2107, 12, 31, 23, 59, 58)],
              str(entry_stamps(archive)) if os.path.exists(archive) else "no archive")

    # The stored stamp is the whole point of SOURCE_DATE_EPOCH, so hold the
    # round trip for an ordinary date too: 2016-01-01T00:00:00Z is the
    # script's own fallback, and an accepted epoch that Info-ZIP stored as
    # something else would leave the archive dated wrong with a green exit.
    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        done = package(script, "1451606400")
        archive = os.path.join(root, "dist", MOD_NAME + ".zip")
        stamps = entry_stamps(archive) if os.path.exists(archive) else None
        check("an ordinary epoch is stored in the archive as that date",
              done.returncode == 0 and stamps == [(2016, 1, 1, 0, 0, 0)],
              f"exit={done.returncode} stamps={stamps} stderr={done.stderr!r}")

    # A leading zero is an octal prefix to the range check, so `01451606400`
    # used to be compared as an octal number and land in a different year, and
    # a digit run past 64 bits wrapped into the accepted range instead of being
    # rejected. Both store a date nobody asked for, silently and reproducibly.
    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        done = package(script, "01451606400")
        archive = os.path.join(root, "dist", MOD_NAME + ".zip")
        stamps = entry_stamps(archive) if os.path.exists(archive) else None
        check("a zero-padded epoch is stored as the date it reads as",
              done.returncode == 0 and stamps == [(2016, 1, 1, 0, 0, 0)],
              f"exit={done.returncode} stamps={stamps} stderr={done.stderr!r}")

    # 2^64 + 1451606400 is 18446744075161158016, and `$(( ))` wraps it to
    # 1451606400: an epoch the range check reads as squarely inside 1980-2107,
    # for an input that names a date 584 billion years out.
    with tempfile.TemporaryDirectory() as root:
        script = stage_mod(root)
        done = package(script, str((1 << 64) + 1451606400))
        archive = os.path.join(root, "dist", MOD_NAME + ".zip")
        check("an epoch that wraps into the range is rejected, not wrapped",
              done.returncode != 0 and not os.path.exists(archive),
              f"exit={done.returncode} stderr={done.stderr!r}")

    return report()


if __name__ == "__main__":
    sys.exit(main())

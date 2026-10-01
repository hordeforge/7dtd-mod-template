#!/usr/bin/env python3
"""The server lane's EACEnabled check must accept the config it just wrote.

`make install-server` and `make server-smoke` both refuse a run whose
serverconfig does not set EACEnabled=false, and `configure-server-config.py`
derives that file by copying the server's own and forcing the property. The
check and the writer have to agree: the game writes its own serverconfig.xml
with `value` before `name`, XML attribute order is not significant, and a
check that insists on one order fails the config it just derived itself with
"must set EACEnabled=false" on a file that says exactly that.

So the positive case is the real pair, run end to end: the real writer over a
value-first source, and the real shell function over what it produced. The
negatives are the shapes a name-then-value match would wrongly pass, and the
two forms an XML file is allowed to write.

No server, no game install: a config file in a temp directory is the whole
input.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
SERVER_COMMON = os.path.join(SCRIPTS, "lib", "server-common.sh")
CONFIGURE = os.path.join(SCRIPTS, "configure-server-config.py")

# The order the game's own serverconfig.xml uses.
VALUE_FIRST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<ServerSettings>\n"
    '\t<property value="true" name="EACEnabled" />\n'
    '\t<property value="86400" name="ServerPort" />\n'
    "</ServerSettings>\n"
)
NAME_FIRST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<ServerSettings>\n"
    '\t<property name="EACEnabled" value="false" />\n'
    "</ServerSettings>\n"
)
# One element, attributes on their own lines: a line-oriented match never sees
# the whole element and answers about half of it.
SPLACED = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<ServerSettings>\n"
    "<property\n"
    '\tname="EACEnabled"\n'
    '\tvalue="false" />\n'
    "</ServerSettings>\n"
)
SINGLE_QUOTED = (
    "<ServerSettings><property name='EACEnabled' value='false'/></ServerSettings>\n"
)
# Properties that only look like the one the check is for.
NEAR_MISS = (
    "<ServerSettings>"
    '<property name="EACEnabledForced" value="false" />'
    '<property name="EAC" value="false" />'
    "</ServerSettings>\n"
)
# EAC off by default and the game switching it on.
DEFAULT_OFF = (
    "<ServerSettings>"
    '<property name="EACEnabled" value="true" />'
    '<property name="EACOptional" value="false" />'
    "</ServerSettings>\n"
)


def write(directory: str, name: str, text: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def eac_disabled(path: str) -> bool:
    """The real shell function's answer for one config file."""
    done = subprocess.run(
        ["bash", "-c", 'source "$1"; server_eac_disabled "$2"',
         "bash", SERVER_COMMON, path],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if done.returncode not in (0, 1):
        print(done.stderr, file=sys.stderr)
    return done.returncode == 0


def derive(source: str, target: str) -> bool:
    done = subprocess.run(
        [sys.executable, CONFIGURE, source, target],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr)
    return done.returncode == 0


def the_derived_config_is_accepted() -> None:
    with tempfile.TemporaryDirectory() as work:
        for label, source_text in (("value-first", VALUE_FIRST),
                                   ("name-first", NAME_FIRST)):
            source = write(work, f"{label}-source.xml", source_text)
            target = os.path.join(work, f"{label}-derived.xml")
            check(f"the-writer-runs-over-a-{label}-config",
                  derive(source, target),
                  f"configure-server-config.py did not write {target}")
            if os.path.isfile(target):
                check(f"the-derived-{label}-config-passes-the-eac-check",
                      eac_disabled(target),
                      "the config the writer just produced was refused")


def the_accepted_shapes() -> None:
    with tempfile.TemporaryDirectory() as work:
        for label, text in (("value-first", VALUE_FIRST), ("name-first", NAME_FIRST),
                            ("attributes-on-separate-lines", SPLACED),
                            ("single-quoted", SINGLE_QUOTED)):
            path = write(work, f"{label}.xml", text)
            want = label != "value-first"
            check(f"eac-check-answers-{label}",
                  eac_disabled(path) == want,
                  f"server_eac_disabled said {eac_disabled(path)}, wanted {want}")


def the_refused_shapes() -> None:
    with tempfile.TemporaryDirectory() as work:
        for label, text in (("a-differently-named-property", NEAR_MISS),
                            ("eac-on", DEFAULT_OFF)):
            path = write(work, f"{label}.xml", text)
            check(f"eac-check-refuses-{label}",
                  not eac_disabled(path),
                  "server_eac_disabled accepted a config with EAC not off")
        check("eac-check-refuses-a-missing-file",
              not eac_disabled(os.path.join(work, "absent.xml")),
              "a config that does not exist is not a config with EAC off")


def main() -> int:
    if not os.path.isfile(SERVER_COMMON):
        print(f"no {SERVER_COMMON}; nothing to verify")
        return 0
    the_derived_config_is_accepted()
    the_accepted_shapes()
    the_refused_shapes()
    return report()


if __name__ == "__main__":
    sys.exit(main())

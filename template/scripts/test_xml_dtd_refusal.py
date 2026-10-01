#!/usr/bin/env python3
"""A DTD in any XML this toolchain parses is refused, not expanded.

`xml.etree.ElementTree` expands an internal entity declaration with no limit of
its own: a few hundred bytes of nested `<!ENTITY>` blocks expand to gigabytes
of text, and whether that is caught depends on the expat build the developer's
Python was linked against (2.6 added the limit). Some of the files parsed here
are not first-party, so the refusal cannot be left to the runtime:
`serverconfig.xml` arrives with a SteamCMD install and the `ConfigsDump` a save
check reads is written by the game.

These assertions pin the refusal (`scripts/lib/safe_xml.py`), the cases that
must still parse, and the convention itself: a script that reaches for
`ET.parse` / `ET.fromstring` directly is a parse that can expand entities, and
the rule has to hold for the next script written, not only the ones here today.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import safe_xml
from gate import check
from gate import main as report

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# A nested-entity document: 10^13 characters of expansion from a few hundred
# bytes, which is the shape a parser with no limit spends its memory on.
BILLION_LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE l ['
    '<!ENTITY e0 "aaaaaaaaaa">'
    + "".join(f'<!ENTITY e{i} "{"&e" + str(i - 1) + ";" * 10}">' for i in range(1, 14))
    + "]><l>&e13;</l>"
)

EXTERNAL_DTD = ('<?xml version="1.0"?><!DOCTYPE l SYSTEM "http://example.invalid/l.dtd">'
                "<l/>")

# A comment naming one, and a processing instruction naming one: neither is a
# declaration, and a document is allowed to say the words.
COMMENTED = "<r><!-- <!DOCTYPE l [<!ENTITY a 'x'>]> --><a/></r>"
INSTRUCTION = "<r><?target <!DOCTYPE l>?></r>"

ORDINARY = ('<configs><append xpath="/items"><item name="a"/></append></configs>')

# The one file allowed to call ElementTree directly: it is the refusal itself.
CALLER = re.compile(r"\bET\.parse\(|\bET\.fromstring\(")


def main() -> int:
    for name, document in (("nested entity expansion", BILLION_LAUGHS),
                           ("an external DTD", EXTERNAL_DTD)):
        check(f"refused: {name}", _rejects(document), document[:60])

    check("a DTD in a comment is not a declaration",
          safe_xml.fromstring(COMMENTED).tag == "r")
    check("a DTD named in a processing instruction is not a declaration",
          safe_xml.fromstring(INSTRUCTION).tag == "r")
    check("an ordinary patch file still parses",
          safe_xml.fromstring(ORDINARY).find("append/item").get("name") == "a")

    check("a file is refused on the way in, not after it is parsed",
          _rejects_file(BILLION_LAUGHS))
    with tempfile.NamedTemporaryFile("wb", suffix=".xml", delete=False) as handle:
        handle.write(ORDINARY.encode("utf-8"))
        ordinary = handle.name
    try:
        check("an ordinary file still parses from disk",
              safe_xml.parse(ordinary).getroot().tag == "configs")
    finally:
        os.unlink(ordinary)

    for name, offenders in _direct_parsers().items():
        check("no direct ElementTree parse in " + name, not offenders,
              ", ".join(offenders))

    return report()


def _rejects(document: str) -> bool:
    try:
        safe_xml.fromstring(document)
    except safe_xml.DtdRejected:
        return True
    return False


def _rejects_file(document: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(document)
        path = handle.name
    try:
        safe_xml.parse(path)
    except safe_xml.DtdRejected:
        return True
    finally:
        os.unlink(path)
    return False


def _direct_parsers() -> dict[str, list[str]]:
    """Every script or `lib/` module that calls ElementTree directly, by file.

    The templates in this tree are placeholders, so the scan is textual and
    covers this file's own rule: `lib/safe_xml.py` is the only file exempt.
    """
    offenders: dict[str, list[str]] = {}
    for prefix in ("", "lib/"):
        directory = os.path.join(SCRIPT_DIR, prefix)
        for entry in sorted(os.listdir(directory)):
            name = prefix + entry
            if not entry.endswith(".py") or name == "lib/safe_xml.py":
                continue
            with open(os.path.join(directory, entry), encoding="utf-8") as handle:
                hits = [f"{name}:{number}"
                        for number, line in enumerate(handle, 1)
                        if CALLER.search(line) and not line.lstrip().startswith("#")]
            if hits:
                offenders[name] = hits
    return offenders


if __name__ == "__main__":
    raise SystemExit(main())

"""XML parsing that refuses a DTD.

`xml.etree.ElementTree` expands an internal entity declaration with no depth or
size limit of its own, so a document carrying a nested `<!ENTITY>` block
("billion laughs") turns a few hundred bytes of input into gigabytes of text.
expat 2.6 and later refuse that themselves, but the parsers here run on whatever
Python the developer's machine has, and not every file read here is
first-party: `serverconfig.xml` arrives with a SteamCMD install, and the
`ConfigsDump` a save check reads is written by the game.

None of the documents read here legitimately carries a DTD, so the declaration
itself is what gets refused, before the parser is handed the text. A document's
DTD can only appear in its prolog, and inside the prolog only outside comments
and processing instructions, so the walk below is exact rather than a search
for `<!DOCTYPE` anywhere in the file: a comment or a CDATA section naming one is
still the document it was.

Import it by putting this directory on the path; a caller in `scripts/` does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from safe_xml import parse
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

DOCTYPE = "<!DOCTYPE"
BOMS = ((b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))


class DtdRejected(ValueError):
    """The document declares a DTD, which no document read here may carry."""


def _scan(text: str) -> None:
    """Raise `DtdRejected` if `text` declares a DTD."""
    index = 0
    size = len(text)
    while index < size:
        start = text.find("<", index)
        if start < 0:
            return
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            index = size if end < 0 else end + 3
            continue
        if text.startswith("<?", start):
            end = text.find("?>", start + 2)
            index = size if end < 0 else end + 2
            continue
        if text.startswith("<!", start):
            if text[start:start + len(DOCTYPE)].upper() == DOCTYPE:
                raise DtdRejected(
                    f"the document declares {text[start:text.find('>', start) + 1]!r} "
                    f"at offset {start}; entity expansion is how a small file becomes "
                    "a huge one, and no config this toolchain reads needs a DTD"
                )
            return
        # The first element starts here, and a DTD cannot follow it.
        return


def _decoded(data: bytes) -> str:
    """`data` as text, keeping every ASCII byte addressable.

    latin-1 maps bytes to code points one for one and is ASCII-transparent, so
    the scan sees the same `<!DOCTYPE` in a UTF-8 document as in an ASCII one.
    A UTF-16 document is not ASCII on the wire, so it is decoded as itself.
    """
    for bom, encoding in BOMS:
        if data.startswith(bom):
            return data.decode(encoding, "replace")
    return data.decode("latin-1")


def parse(source: Path | str) -> ET.ElementTree:
    """`ET.parse`, refusing a DTD rather than expanding it."""
    with open(source, "rb") as handle:
        _scan(_decoded(handle.read()))
    return ET.parse(source)


def fromstring(text: str) -> ET.Element:
    """`ET.fromstring`, under the same refusal."""
    _scan(text)
    return ET.fromstring(text)

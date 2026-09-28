"""The one reader for a key in the mod's ignored `.local.env`.

Every install-dependent tool needs the same answer to "where is the game
install?", and three copies of the lookup had drifted: some stripped only
double quotes, so a value written as `SEVEN_DAYS_TO_DIE_DIR='/opt/7dtd'`
resolved to a path with a leading quote and failed with a path that does not
exist. Import it by putting this directory on the path; a caller in
`scripts/` does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

An unset value and an unresolvable key are the same answer (None), so a
caller reports one message instead of two that only differ in wording.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

GAME_DIR_KEY = "SEVEN_DAYS_TO_DIE_DIR"
QUOTES = ("'", '"')
# A .local.env record ends at LF, CRLF or bare CR, and at nothing else.
# str.splitlines() also ends one at NEL (U+0085), LS (U+2028) and PS (U+2029),
# each of which is a legal byte inside a path: a value written as
# SEVEN_DAYS_TO_DIE_DIR="/srv/7dtd<U+2028>alt" was cut in two, and the reader
# returned "/srv/7dtd", a directory that does not exist, for an install that
# does. The shell's own `source` reads the same file and ends a line at LF, so
# the two readers disagreed on what one line was.
LINE_BREAKS = re.compile(r"\r\n|\r|\n")


def value(root: Path, key: str) -> str | None:
    """`key` from the environment, else from `<root>/.local.env`, else None.

    The environment wins so a one-off `SEVEN_DAYS_TO_DIE_DIR=... make ...`
    overrides the file without editing it.
    """
    from_env = os.environ.get(key, "").strip()
    if from_env:
        return _unquote(from_env)

    env_file = root / ".local.env"
    if not env_file.is_file():
        return None
    # utf-8-sig, not utf-8: a file saved by a Windows editor opens with a BOM,
    # which as a leading U+FEFF made the first key unmatchable and the value
    # read as unset. The BOM is stripped here; the rest still has to be UTF-8.
    # The same grammar the shell readers apply, so one key has one answer
    # whichever reader asks: an `export ` prefix is accepted because
    # `load_local_env` sources the file and would honour it, and the last
    # assignment wins because that is what sourcing it gives. This reader
    # originally took the first match instead, which disagreed with both shell
    # readers on any key written twice.
    prefix = f"export {key}="
    found = None
    for line in LINE_BREAKS.split(env_file.read_text(encoding="utf-8-sig")):
        if line.startswith((key + "=", prefix)):
            found = line.split("=", 1)[1]
    if found is None:
        return None
    return _unquote(found.strip()) or None


def game_dir(root: Path) -> Path | None:
    """The configured 7 Days To Die client install, or None."""
    found = value(root, GAME_DIR_KEY)
    return Path(found) if found else None


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in QUOTES:
        return text[1:-1]
    return text

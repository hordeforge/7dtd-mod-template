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
from pathlib import Path

GAME_DIR_KEY = "SEVEN_DAYS_TO_DIE_DIR"
QUOTES = ("'", '"')


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
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line.startswith(key + "="):
            continue
        found = line.split("=", 1)[1].strip()
        return _unquote(found) or None
    return None


def game_dir(root: Path) -> Path | None:
    """The configured 7 Days To Die client install, or None."""
    found = value(root, GAME_DIR_KEY)
    return Path(found) if found else None


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in QUOTES:
        return text[1:-1]
    return text

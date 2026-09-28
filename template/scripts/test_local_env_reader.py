#!/usr/bin/env python3
"""The `.local.env` lookup the install-dependent tools share.

Three copies of this reader had drifted: two stripped only double quotes, so
a single-quoted value resolved to a path with a leading `'` and the tool
failed on a path that does not exist. One reader, and this gate pins the
quoting, the environment override, the absent-key answer, and the `game_dir`
wrapper the install-dependent tools call.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import local_env
from gate import check
from gate import main as report

_T = TypeVar("_T")


def read(env_text: str | None, key: str, environ: dict[str, str] | None = None) -> str | None:
    """`local_env.value` against a throwaway root holding `env_text`."""
    return _against(env_text, environ, lambda root: local_env.value(root, key))


def read_game_dir(env_text: str | None, environ: dict[str, str] | None = None) -> Path | None:
    """`local_env.game_dir` against the same throwaway root."""
    return _against(env_text, environ, local_env.game_dir)


def _against(env_text: str | None, environ: dict[str, str] | None,
             reader: Callable[[Path], _T]) -> _T:
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(environ or {})
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if env_text is not None:
                (root / ".local.env").write_text(env_text, encoding="utf-8")
            return reader(root)
    finally:
        os.environ.clear()
        os.environ.update(previous)


def main() -> int:
    key = local_env.GAME_DIR_KEY

    check("double quotes are stripped", read(f'{key}="/opt/7dtd"\n', key) == "/opt/7dtd")
    check("single quotes are stripped", read(f"{key}='/opt/7dtd'\n", key) == "/opt/7dtd",
          repr(read(f"{key}='/opt/7dtd'\n", key)))
    check("an unquoted value passes through", read(f"{key}=/opt/7dtd\n", key) == "/opt/7dtd")
    check("surrounding spaces are trimmed", read(f'{key}=  "/opt/7dtd"  \n', key) == "/opt/7dtd")
    check("a path ending in a quote is not over-stripped",
          read(f'{key}="/opt/we\'ird"\n', key) == "/opt/we'ird")
    check("a comment line is not a value", read(f'# {key}="/nope"\n', key) is None)
    check("another key is not picked up", read('OTHER="/nope"\n', key) is None)
    check("a missing file is None", read(None, key) is None)
    check("an empty value is None", read(f'{key}=""\n', key) is None)
    check("the environment wins over the file",
          read(f'{key}="/from/file"\n', key, {key: "/from/env"}) == "/from/env")
    # game_dir is what every install-dependent tool calls, so the wrapper is
    # held to the same value plus the Path type it promises.
    check("game_dir resolves the file's value as a Path",
          read_game_dir(f'{key}="/opt/7dtd"\n') == Path("/opt/7dtd"),
          repr(read_game_dir(f'{key}="/opt/7dtd"\n')))
    check("game_dir lets the environment override the file",
          read_game_dir(f'{key}="/from/file"\n', {key: "/from/env"})
          == Path("/from/env"))
    check("game_dir is None when nothing configures it",
          read_game_dir(None) is None and read_game_dir(f'{key}=""\n') is None)

    # Negative control: the drift this gate exists to prevent. The reader that
    # shipped before lib/local_env.py stripped only double quotes.
    legacy = f"{key}='/opt/7dtd'".split("=", 1)[1].strip().strip('"')
    check("negative control rejects a double-quote-only reader",
          legacy != "/opt/7dtd", f"the old reader would have resolved {legacy!r}")

    return report()


if __name__ == "__main__":
    raise SystemExit(main())

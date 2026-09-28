#!/usr/bin/env python3
"""Sibling tooling stays upstream: this mod must not reimplement it.

Playtest orchestration, the client exclusivity lock, client launch, OS audio
mute, screenshot/audio capture, and OCR/menu driving belong to the
`hordeforge/7dtd-*` repositories (docs/reference/sibling-tooling.md). This
gate scans every script's **content** for the tool calls those capabilities
need, so a local reimplementation fails whatever the file is called — a
renamed copy is still a copy.

A genuine exception (a thin wrapper that must mention an upstream path, say)
is declared in ALLOW with its reason; a stale entry fails.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
SELF = os.path.abspath(__file__)

# needle -> which upstream capability it belongs to
BANNED: dict[str, str] = {
    "pactl": "OS audio mute/unmute (7dtd-fastconnect)",
    "parec": "audio recording (7dtd-playtest capture_audio.sh)",
    "pw-record": "audio recording (7dtd-playtest capture_audio.sh)",
    "spectacle": "screenshots (shamway client capture)",
    "grim ": "screenshots (shamway client capture)",
    "xdotool": "window/input driving (upstream harness)",
    "qdbus": "window driving (shamway client capture)",
    "tesseract": "OCR menu driving (removed upstream; do not restore)",
    "-applaunch": "client launch (7dtd-fastconnect launch_client.sh)",
    "playtest_running": "the exclusivity lock (7dtd-playtest playtest_lock.py)",
    "uinput": "virtual input (removed upstream; do not restore)",
}

# relative path -> {needle: reason}
ALLOW: dict[str, dict[str, str]] = {}


def banned_in(content: str) -> list[str]:
    """Every banned tool call *content* carries, sorted."""
    return sorted(n for n in BANNED if n in content)


def negative_controls() -> None:
    """Prove the content scan bites.

    A gate whose walk reads nothing prints nothing and exits 0, so the
    controls pin that a local reimplementation is caught and an ordinary
    script line is not.
    """
    check("negative control: a local mute call is caught",
          banned_in("pactl set-sink-mute 1\n") == ["pactl"],
          repr(banned_in("pactl set-sink-mute 1\n")))
    check("negative control: a local screenshot call is caught",
          banned_in("grim -o out.png\n") == ["grim "],
          repr(banned_in("grim -o out.png\n")))
    check("negative control: a second lock file is caught",
          banned_in('LOCK="$HOME/.cache/7dtd-playtest/playtest_running"\n')
          == ["playtest_running"],
          repr(banned_in('LOCK="$HOME/.cache/7dtd-playtest/playtest_running"\n')))
    check("negative control: an ordinary script line is not caught",
          banned_in("python3 scripts/playtest_runner.py\n") == [])


def main() -> int:
    negative_controls()

    word = {n: re.compile(re.escape(n)) for n in BANNED}
    scanned = 0
    for base, dirs, files in os.walk(SCRIPTS):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            path = os.path.join(base, name)
            if os.path.abspath(path) == SELF:
                continue
            scanned += 1
            rel = os.path.relpath(path, MOD_DIR)
            with open(path, encoding="utf-8", errors="replace") as handle:
                content = handle.read()
            for needle in sorted(BANNED):
                if not word[needle].search(content):
                    continue
                if needle in ALLOW.get(rel, {}):
                    check(f"allowed:{rel}:{needle}", True)
                    continue
                check(f"banned-tool:{rel}:{needle}", False,
                      f"belongs upstream: {BANNED[needle]}")
    # A walk that read no file would report the same empty green run.
    check("the scan read the scripts it is meant to scan", scanned > 0,
          f"{scanned} file(s) under scripts/, this gate excluded")
    for rel in sorted(ALLOW):
        exists = os.path.isfile(os.path.join(MOD_DIR, rel))
        check("allow-entry-exists:" + rel, exists, "stale ALLOW entry; remove it")
        if exists:
            with open(os.path.join(MOD_DIR, rel), encoding="utf-8", errors="replace") as handle:
                content = handle.read()
            for needle in sorted(ALLOW[rel]):
                check(f"allow-entry-used:{rel}:{needle}", needle in content,
                      "stale ALLOW needle; remove it")
    return report()


if __name__ == "__main__":
    sys.exit(main())

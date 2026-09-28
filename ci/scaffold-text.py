#!/usr/bin/env python3
"""What the scaffolder does with a purpose a code-point limit cuts inside.

ModInfo.xml's Description is the mod browser's one line and the substitution
pass cuts it at 200 code points, so a purpose written in a script where one
character is several code points is cut mid-character often enough to matter:
a Devanagari matra, an emoji ZWJ sequence and a flag's two regional
indicators each render as a letter in a box, or a stranded joiner, once the
cut lands between their halves. `ci/check-smoke-mod.py` covers the values
round-tripping into the file; this covers the cut.

The other two are the same boundary seen from the other side: an author name
reaching the Harmony id, and a display name carrying a character that draws
nothing. Both are identities, so both are pinned here rather than left to a
scaffold that happens to use text the rules do not reach.

Nothing is written outside `.scratch/`, and the scaffolded mods are removed
when the run ends.

Usage: ci/scaffold-text.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

FAILURES: list[str] = []

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLDER = os.path.join(ROOT, "new-mod.sh")
WORK = os.path.join(ROOT, ".scratch", "anvil-text")
# How long one scaffolder run may take. This gate runs the scaffolder five
# times, and a run that hangs (a prompt on a stdin that is not a terminal, a
# clone waiting on a credential) would otherwise never come back.
SCAFFOLD_TIMEOUT_SECONDS = 300

# ModInfo.xml's Description limit, which the token substitution enforces.
DESCRIPTION_LIMIT = 200
# A mark, a joiner, a variation selector or a skin tone attaches to the
# character before it; a regional indicator is one half of a flag and comes
# in pairs. These are what a cut has to leave alone, restated here so the
# gate does not import the scaffolder's own answer to the question.
ATTACHING = re.compile("[\u200d\u200c\ufeff\ufe00-\ufe0f\ufe20-\ufe2f"
                       "\U0001f3fb-\U0001f3ff]")
REGIONAL = (0x1F1E6, 0x1F1FF)

FAMILY = "\U0001f469\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466"
FLAG_JP = "\U0001f1ef\U0001f1f5"
# DEVANAGARI KA with its vowel sign I: two code points, one character.
KA_I = "\u0915\u093f"


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one assertion; `detail` explains a failure and is dropped on a pass."""
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def ends_mid_character(text: str) -> bool:
    """Whether `text` stops inside one character, as a mid-cluster cut does."""
    if not text:
        return False
    if ATTACHING.match(text[-1]):
        return True
    if len(text) > 1 and text[-2] == "\u200d":
        return True
    run = 0
    for char in reversed(text):
        if REGIONAL[0] <= ord(char) <= REGIONAL[1]:
            run += 1
        else:
            break
    return run % 2 == 1


def scaffold(name: str, author: str, display: str, purpose: str,
             csharp: str = "no") -> tuple[int, str]:
    """Run the scaffolder on those values; return its status and the mod dir."""
    mod_dir = os.path.join(WORK, "mods", name)
    config = os.path.join(WORK, name + ".conf")
    os.makedirs(WORK, exist_ok=True)
    # The config is a shell file, so the values are quoted and the text this
    # gate carries holds nothing a shell would re-read.
    for key, value in (("name", name), ("author", author),
                       ("display_name", display), ("purpose", purpose)):
        if any(char in value for char in "\"'\\$`"):
            raise ValueError(f"{key} holds a character a shell config would re-read")
    with open(config, "w", encoding="utf-8", newline="") as handle:
        handle.write(f'name="{name}"\n')
        handle.write(f'author="{author}"\n')
        handle.write(f'display_name="{display}"\n')
        handle.write(f'purpose="{purpose}"\n')
        handle.write(f'target_dir="{os.path.join(WORK, "mods")}"\n')
        handle.write(f'hordeforge_root="{os.path.join(WORK, "hordeforge")}"\n')
        handle.write(f'csharp="{csharp}"\nassets="no"\nclone="no"\n')
    try:
        result = subprocess.run(
            [SCAFFOLDER, config], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, cwd=ROOT,
            timeout=SCAFFOLD_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # A scaffolder that never returns would hold this gate, and CI with
        # it, for as long as the job's timeout; a cut-off run is a reported
        # failure and the status the caller branches on is a non-zero one.
        return 124, mod_dir
    return result.returncode, mod_dir


def description(mod_dir: str) -> str:
    """The Description the scaffold wrote, or the empty string.

    A ModInfo.xml that is absent or unparseable is the empty string, not a
    traceback: the caller has already failed the run on the scaffolder's exit
    status, and a parse error here would replace that report with a stack.
    """
    try:
        root = ET.parse(os.path.join(mod_dir, "ModInfo.xml")).getroot()
    except (ET.ParseError, OSError):
        return ""
    for field in root:
        if field.tag == "Description":
            return field.get("value") or ""
    return ""


def harmony_id(mod_dir: str) -> str:
    """The Harmony id the scaffolded sources construct, or the empty string."""
    for base, _dirs, files in os.walk(os.path.join(mod_dir, "src")):
        for f in files:
            if not f.endswith(".cs"):
                continue
            try:
                with open(os.path.join(base, f), encoding="utf-8",
                          errors="replace") as handle:
                    found = re.search(r'new Harmony\("(?P<id>[^"]+)"\)', handle.read())
            except OSError:
                continue
            if found:
                return found["id"]
    return ""


def check_cut(label: str, name: str, tail: str, keep: int, kept: str) -> None:
    """A purpose of `keep` characters then `tail` has to cut inside `tail`.

    Every one of these tails is longer than the room left, so the cut lands
    inside one character: what survives is the part of it that is whole, and
    `kept` is that.
    """
    purpose = "A" * keep + tail
    status, mod_dir = scaffold(name, "CI Text", "Text Smoke", purpose)
    if status != 0:
        check(label, False, f"the scaffolder exited {status}")
        return
    written = description(mod_dir)
    check(label + "-fits-the-limit", len(written) <= DESCRIPTION_LIMIT,
          f"{len(written)} code points")
    check(label + "-ends-on-a-whole-character", not ends_mid_character(written), repr(written[-8:]))
    check(label + "-drops-the-partial-character", written == "A" * keep + kept, repr(written[-8:]))


def main() -> int:
    if not os.access(SCAFFOLDER, os.X_OK):
        print(f"ERROR: {SCAFFOLDER} is not executable", file=sys.stderr)
        return 2

    # 196 leaves room for a 4-code-point prefix of the 7-code-point family,
    # 199 for the first of the flag's two regional indicators, and 198 for the
    # base of the Devanagari character whose vowel sign lands on the limit.
    # What each cut keeps is the first whole character of its tail, and for the
    # family that is the woman the sequence starts from.
    check_cut("zwj-sequence", "TextZwj", FAMILY, DESCRIPTION_LIMIT - 4, FAMILY[0])
    check_cut("regional-indicator", "TextFlag", FLAG_JP, DESCRIPTION_LIMIT - 1, "")
    check_cut("combining-mark", "TextMark", KA_I, DESCRIPTION_LIMIT - 2, KA_I[0])

    # A name that draws nothing is a second string that reads as the first,
    # and these two are how a player tells one mod from another. The run stops
    # on the config, so nothing is written.
    status, mod_dir = scaffold("TextBidi", "CI Text", "Safe\u202etea", "A purpose.")
    check("bidi-override-in-the-display-name-is-refused", status == 2, f"exited {status}")
    check("bidi-override-writes-no-mod", not os.path.exists(mod_dir), mod_dir)
    status, mod_dir = scaffold("TextZwsp", "CI\u200bText", "Text Smoke", "A purpose.")
    check("zero-width-space-in-the-author-is-refused", status == 2, f"exited {status}")

    # The Harmony id is the author name reduced to lowercase ASCII. lower()
    # maps a German sharp s to nothing, so "Weiß" and "Wei" both reduced to
    # "wei" and two authors were given one id.
    status, mod_dir = scaffold("TextAuthor", "Wei\u00df", "Text Smoke", "A purpose.",
                               csharp="yes")
    check("author-name-scaffolds", status == 0, f"exited {status}")
    harmony = harmony_id(mod_dir)
    check("sharp-s-folds-into-the-harmony-id", harmony == "com.weiss.textauthor",
          repr(harmony))

    shutil.rmtree(WORK, ignore_errors=True)
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

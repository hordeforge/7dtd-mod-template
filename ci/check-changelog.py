#!/usr/bin/env python3
"""The release contract CHANGELOG.md states, checked.

The template's version is a git tag on `main` and `Unreleased` holds
everything landed since the last tag, so a mod scaffolded from an older tag
can be diffed against a newer one without reading the commit log. That
promise rests on three things this file holds the changelog to: an
`Unreleased` section that is always there for the next change, a dated
section per released version, and versions that only ever go down the file,
so a tag and a section cannot drift apart silently.

The mod's own `test_static_checks.py` holds the same contract for a
generated mod's `ModInfo.xml` and `README.txt`. This is the template side,
which the scaffolded mod cannot check: the file a release is cut from is
this repository's, and the mod is generated from it afterwards.

Nothing here reads a tag: `actions/checkout` fetches one commit, so a
tag-based check would be green on an empty tag list rather than on a correct
changelog. Where the newest tag is named in the changelog, that is text, and
this reads it.

Usage: ci/check-changelog.py [changelog]   (default: CHANGELOG.md)
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "template", "scripts", "lib"))
from gate import check
from gate import main as report

# The groups Keep a Changelog defines. A section under any other name is a
# group a reader of the notes does not know to look for.
GROUPS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

SECTION = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\S+))?\s*$")
GROUP = re.compile(r"^### (?P<name>\S+)\s*$")
SEMVER = re.compile(r"\d+\.\d+\.\d+")
ENTRY = re.compile(r"^- \S")

# An entry that moves the generated modlet's contract, rather than adding to
# it, opens with `**Breaking for a mod <what the mod did>:**`, so a reader
# knows the qualifier is about their mod, not the source. The README tells a
# mod author upgrading between tags to find those with a fixed-string search
# on the prefix, which makes the spelling part of the contract: a rename
# would leave that command matching nothing and every reader assuming a
# clean upgrade.
BREAKING_PREFIX = "**Breaking for a mod"
ANY_BREAKING = re.compile(r"\*\*Breaking\w*")


def version_key(version: str) -> tuple[int, ...]:
    """A SemVer version as numbers, so two sections can be ordered.

    A pre-release or build-metadata suffix sorts after the bare version it
    hangs off, so `1.0.0-rc.1` never passes for `1.0.0`: the suffix becomes
    a trailing part that no digits-only comparison would produce.

    Total over every string a `## [...]` header can hold, because the sort
    below runs over all the sections including the ones already reported as
    not being semver. A part that is not a number sorts as 0 rather than
    raising, so a typo'd version is a reported failure instead of a
    ValueError traceback that ends the gate before it reaches the last two
    checks.
    """
    bare, _, rest = version.partition("-")
    key = tuple(int(part) if part.isdigit() else 0 for part in bare.split("."))
    return (*key, 0) if not rest else (*key, 1)


def sections(text: str) -> list[dict[str, object]]:
    """Every `## [...]` section with the line it starts on and its body."""
    found: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = SECTION.match(line)
        if match:
            found.append({"version": match["version"], "date": match["date"],
                          "line": lineno, "body": []})
        elif found:
            found[-1]["body"].append(line)  # type: ignore[union-attr]
    return found


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "CHANGELOG.md"
    if len(sys.argv) > 2:
        print("usage: check-changelog.py [changelog]", file=sys.stderr)
        return 2
    if not os.path.isfile(path):
        print(f"ERROR: no {path}", file=sys.stderr)
        return 2
    # Unreadable and not-UTF-8 are both this file's business to report: the
    # existence check above is what used to be the only guard, so a file the
    # runner could not open, or one a stray non-UTF-8 byte made undecodable,
    # ended the gate on a traceback instead of a named reason.
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as err:
        print(f"ERROR: cannot read {path}: {err}", file=sys.stderr)
        return 2

    found = sections(text)
    check("changelog-has-a-section-for-each-version", bool(found), "no `## [...]` section")

    # Unreleased is the next change's home, and it is the first one: a
    # version section above it would make it read as already released.
    check("unreleased-is-the-first-section",
          bool(found) and found[0]["version"] == "Unreleased",
          f"first section is {found[0]['version']!r}" if found else "no section")

    for section in found:
        version = str(section["version"])
        if version == "Unreleased":
            continue
        check(f"released-version-is-semver[{version}]",
              bool(SEMVER.fullmatch(version)), repr(version))
        check(f"released-version-has-a-date[{version}]",
              bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(section["date"]))),
              f"header line {section['line']} reads `## [{version}]` with no date")
        body = "\n".join(section["body"])  # type: ignore[arg-type]
        groups = [m["name"] for m in
                  (GROUP.match(line) for line in body.splitlines()) if m]
        check(f"released-version-groups-are-known[{version}]",
              bool(groups) and all(name in GROUPS for name in groups),
              f"unknown group in {groups}" if groups else "no `### ` group")
        check(f"released-version-has-entries[{version}]",
              any(ENTRY.match(line) for line in body.splitlines()),
              "a released version with no entry under it")

    # Newest first: two sections out of order, or a version edited after it
    # shipped, is a tag and a changelog that disagree.
    released = [s for s in found if s["version"] != "Unreleased"]
    ordered = sorted(released, key=lambda s: version_key(str(s["version"])), reverse=True)
    check("released-versions-decrease-down-the-file",
          [str(s["version"]) for s in released] == [str(s["version"]) for s in ordered],
          " -> ".join(str(s["version"]) for s in released))

    # A move is only a move if a reader can find it. Every entry that says
    # so has to open with the marker the README's search command looks for,
    # spelled the same way, or an upgrade reads as clean and is not.
    stray = [match.start() for match in ANY_BREAKING.finditer(text)
             if not text[match.start():].startswith(BREAKING_PREFIX)]
    check("breaking-entries-use-the-documented-marker", not stray,
          f"{len(stray)} entries open with something other than {BREAKING_PREFIX!r}")

    return report()


if __name__ == "__main__":
    sys.exit(main())

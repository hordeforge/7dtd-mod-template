#!/usr/bin/env python3
"""Verify every XPath in Config/**/*.xml targets a node that exists in vanilla.

A patch whose xpath matches nothing applies silently — the game warns at
most, and the mod ships a no-op. This checks each patch operation's xpath
against the installed game's Data/Config/<same relative file>.

Needs SEVEN_DAYS_TO_DIE_DIR (env or .local.env), so it is a `make
validate-xml` target, not part of the offline `make test` suite.

stdlib ElementTree speaks a useful XPath subset (child paths, wildcards,
[@attr='value'] predicates). An xpath it cannot parse is reported as SKIP
for manual verification, never silently passed.

Every known op is checked the same way: the op's own xpath is resolved against
vanilla. An `@attr` target is resolved against the element that owns the
attribute rather than against an element of that name.

Usage:
    scripts/validate-xml-targets.py [-h | --help]

Exit status: 0 every xpath resolved, 1 a patch failed or the game install is
unusable, 2 the command line was wrong.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import config_files
import local_env

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ops the check understands; anything else is reported, never silently passed.
KNOWN_OPS = {"append", "insertBefore", "insertAfter", "setattribute",
             "set", "remove", "removeattribute", "csv"}


def usage(stream: TextIO = sys.stdout) -> None:
    print("USAGE", file=stream)
    print("  validate-xml-targets.py [-h | --help]", file=stream)
    print(file=stream)
    print("Check every xpath in Config/**/*.xml against the installed game's", file=stream)
    print("own Data/Config files. The client install comes from the environment's", file=stream)
    print("SEVEN_DAYS_TO_DIE_DIR or .local.env.", file=stream)
    print(file=stream)
    print("OPTIONS", file=stream)
    print("  -h, --help  show this help and exit", file=stream)
    print(file=stream)
    print("EXIT STATUS", file=stream)
    print("  0  every xpath resolved (a SKIP needs manual verification)", file=stream)
    print("  1  a patch's xpath matched nothing, or the game install is unusable", file=stream)
    print("  2  the command line was wrong", file=stream)


def parse_args(argv: list[str]) -> None:
    """Exit 0 for help, exit 2 for anything this script does not take.

    It reads no argument of its own, so an unrecognized one is a mistake in
    the command line and nothing more: running the full check over a tree the
    caller believed they had narrowed down reports a result about a different
    question than the one they asked.
    """
    for arg in argv:
        if arg in ("-h", "--help"):
            usage()
            sys.exit(0)
        print(f"ERROR: unknown argument: {arg}", file=sys.stderr)
        usage(sys.stderr)
        sys.exit(2)


def game_dir() -> str:
    found = local_env.game_dir(Path(MOD_DIR))
    if found is None or not os.path.isdir(os.path.join(found, "Data", "Config")):
        sys.exit("ERROR: set SEVEN_DAYS_TO_DIE_DIR or .local.env to a valid game install.")
    return str(found)


def parse(path: str) -> ET.Element:
    """Parse `path` or exit naming it: a bare ET.ParseError says where the
    syntax broke, never which of the two files being compared broke, and a
    traceback out of a validation gate is not a usable report.
    """
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        sys.exit(f"ERROR: {path} is not well-formed XML: {exc}")
    except OSError as exc:
        sys.exit(f"ERROR: cannot read {path}: {exc}")


def find(root: ET.Element, xpath: str) -> bool | None:
    """True/False = resolvable; None = beyond ET's XPath subset.

    Total by contract: an xpath is hand-written mod text, and a node step
    ET's `ElementPath` does not implement raises out of `find` rather than
    reporting a syntax error. `text()` and a bare `()` raise `KeyError` on the
    operator name, an unclosed predicate raises `TypeError` (the compiled
    selector comes back `None` and is called), and only the grammar-level
    failures raise `SyntaxError`. Each is the same answer this function owes
    the caller — check it by hand, do not fail the run — so they all become
    the `None` that prints as SKIP. `test_fuzz_xpath_targets.py` holds the
    contract: one escaping exception fails the gate.
    """
    # strip the vanilla root element name: /items/item/... -> ./item/...
    parts = xpath.split("/")
    if len(parts) < 2 or parts[0] != "":
        return None
    # A leading `//` is a descendant search from anywhere, not a child path:
    # dropping its empty segment with the root name turned it into a child
    # search, so a real match was reported as a miss. Only a leading `//`
    # keeps that segment; a mid-path one already survives the join.
    rest = parts[1:]
    tail = rest if rest[0] == "" else rest[1:]
    rel = "./" + "/".join(tail) if tail else "."
    if rel.endswith("/"):
        return None
    # attribute target: check the owning element
    last = rel.rsplit("/", 1)[-1]
    if last.startswith("@"):
        rel = rel.rsplit("/", 1)[0] or "."
    try:
        return root.find(rel) is not None
    except (SyntaxError, KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def main() -> int:
    parse_args(sys.argv[1:])
    failures = 0
    skips = 0
    mod_config = os.path.join(MOD_DIR, "Config")
    if not os.path.isdir(mod_config):
        print("no Config/ directory; nothing to validate")
        return 0
    # Only once there is a Config/ to check: a mod with none has its answer
    # already, and the game install is needed only to resolve an xpath.
    config_dir = os.path.join(game_dir(), "Data", "Config")
    for name in config_files.patch_files(mod_config):
        patch = parse(os.path.join(mod_config, name))
        if patch.tag != "configs":
            # Counted, not passed over in silence: a file rooted at anything
            # else has no xpath this script can resolve, so every element in it
            # goes unexamined and the run reports a clean result about a file
            # it never looked at. A wrong root is a SKIP the reader has to
            # verify, which is what the summary's skips are for.
            print(f"SKIP {name}: root is <{patch.tag}>, not <configs>")
            skips += 1
            continue
        vanilla_path = os.path.join(config_dir, *name.split("/"))
        if not os.path.isfile(vanilla_path):
            print(f"SKIP {name}: no vanilla counterpart (new file)")
            skips += 1
            continue
        vanilla = parse(vanilla_path)
        for op in patch:
            xpath = op.get("xpath")
            # Op name first: an element that is both an op this script does
            # not know and carries no xpath is still a patch element, and
            # asking what it was is the question the reader has to answer.
            if op.tag not in KNOWN_OPS:
                print(f"SKIP {name}: unknown op <{op.tag}>")
                skips += 1
                continue
            if xpath is None:
                print(f"SKIP {name}: <{op.tag}> has no xpath attribute")
                skips += 1
                continue
            resolved = find(vanilla, xpath)
            if resolved is None:
                print(f"SKIP {name}: xpath beyond checker subset: {xpath}")
                skips += 1
            elif resolved:
                print(f"PASS {name}: {xpath}")
            else:
                print(f"FAIL {name}: xpath matches nothing in vanilla: {xpath}",
                      file=sys.stderr)
                failures += 1
    print(f"{failures} failures, {skips} skipped (verify skips manually).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

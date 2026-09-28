#!/usr/bin/env python3
"""The static gate's memoized answers must be the current tree's, not the first one's.

`scripts/test_static_checks.py` walks the mod tree once and parses each XML
file once, because ModInfo.xml is read by three different checks. Both are
memoized, and both used to be keyed without the tree they were read from: a
zero-argument walk and a per-relative-path parse table. The tree is a module
global that callers repoint (`test_xml_gates.py` drives this gate over a
fixture tree), so a second tree was answered from the first one's walk and the
first one's parse: the fixture's `Config/items.xml` was checked against a
document belonging to a different fixture.

A test that only ever drove one tree could not see this, so the trees here are
built, walked, repointed and walked again in one process.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def load_gate() -> ModuleType:
    """The static gate, loaded by path: its file name is not importable."""
    spec = importlib.util.spec_from_file_location(
        "static_checks", os.path.join(SCRIPTS, "test_static_checks.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root: str, name: str) -> str:
    """A mod tree whose one patch file names `name` and extends `name`.

    The tree carries a file named after it, so a listing from the wrong tree
    is visible in the listing and not only in the parse.
    """
    os.makedirs(os.path.join(root, "Config"), exist_ok=True)
    with open(os.path.join(root, "Config", "items.xml"), "w", encoding="utf-8") as handle:
        handle.write('<configs><append xpath="/items">'
                     '<item name="' + name + '">'
                     '<property name="Extends" value="' + name + '"/>'
                     '</item></append></configs>')
    with open(os.path.join(root, "Config", name + ".xml"), "w", encoding="utf-8") as handle:
        handle.write("<configs/>")
    return root


def a_second_tree_is_answered_from_itself() -> tuple[bool, str]:
    """(ok, detail): each tree's listing and parse come from that tree."""
    root = tempfile.mkdtemp(prefix="test-static-check-caches-")
    try:
        first = build(os.path.join(root, "first"), "firstItem")
        second = build(os.path.join(root, "second"), "secondItem")
        gate = load_gate()
        items = os.path.join("Config", "items.xml")

        gate.MOD_DIR = first
        listed_first = gate.xml_files()
        parsed_first, _ = gate.parsed_root(items)
        gate.MOD_DIR = second
        listed_second = gate.xml_files()
        parsed_second, error = gate.parsed_root(items)

        if listed_first != sorted((items, os.path.join("Config", "firstItem.xml"))):
            return False, "first tree listed " + repr(listed_first)
        if listed_second != sorted((items, os.path.join("Config", "secondItem.xml"))):
            # The first tree's walk, served for the second tree.
            return False, "second tree listed " + repr(listed_second)
        if error is not None or parsed_second is None:
            return False, "second tree failed to parse: " + repr(error)
        first_names = [child.get("name") for child in parsed_first.iter("item")]
        second_names = [child.get("name") for child in parsed_second.iter("item")]
        if first_names != ["firstItem"] or second_names != ["secondItem"]:
            # The first tree's document, served for the second tree's file.
            return False, "parsed " + repr(first_names) + " and " + repr(second_names)
        return True, ""
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    ok, detail = a_second_tree_is_answered_from_itself()
    check("a repointed tree is walked and parsed as itself", ok, detail)
    return report()


if __name__ == "__main__":
    raise SystemExit(main())

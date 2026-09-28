"""Shared XML `Extends`-chain resolution for the offline test scripts.

One copy of the Extends walk the offline content gates share.
Import it by putting this directory on the path; a caller in `scripts/`
does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

The walk mirrors what the static checks need of the game's Extends
semantics: a mod entry may extend another mod entry or a vanilla one, pools
are searched in order, and `Extends`'s `param1` is an exclusion list that
removes inherited scalar properties *and* whole `<property class=...>`
blocks by name (verified against the game engine).

An `Extends` chain that re-enters a name is a config defect, not a walk to
follow: `resolve` stops at the entry that closes the cycle instead of
recursing until the interpreter gives up.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


class ExtendsCycle(ValueError):
    """An `Extends` chain re-entered a name, so the walk cannot continue.

    The message names the chain that closed, back to the repeated entry.
    """


def entries(xml_text: str, tag: str) -> dict[str, ET.Element]:
    """Every `<tag name=...>` this mod appends, by name."""
    root = ET.fromstring(xml_text)
    return {
        node.get("name"): node
        for append in root.iter("append")
        for node in append.iter(tag)
        if node.get("name")
    }


def own_scalars(node: ET.Element) -> dict[str, str]:
    """Top-level `<property name=... value=.../>` of this node alone.

    `Extends` is patch metadata, not a property of the item, so it is never
    listed. A property carrying a `class` is a block reported by
    `own_classes`; it is still a scalar here when it carries a `value`, which
    is how the engine reads `<property class="Tags" name="tags" value="..."/>`.
    """
    return {
        child.get("name"): child.get("value", "")
        for child in node
        if child.tag == "property"
        and child.get("name")
        and child.get("name") != "Extends"
        and (not child.get("class") or child.get("value") is not None)
    }


def own_classes(node: ET.Element) -> dict[str, dict[str, str]]:
    """Top-level `<property class=...>` blocks of this node alone."""
    return {
        child.get("class"): own_scalars(child)
        for child in node
        if child.tag == "property" and child.get("class")
    }


def parent_of(node: ET.Element) -> tuple[str | None, set[str]]:
    """(name this entry extends, names its `param1` refuses to inherit).

    `param1` excludes whole `<property class=...>` blocks by name as well as
    scalar properties.
    """
    for child in node:
        if child.tag == "property" and child.get("name") == "Extends":
            excluded = child.get("param1", "")
            return child.get("value"), {
                name.strip() for name in excluded.split(",") if name.strip()
            }
    return None, set()


def resolve(
    name: str, *pools: dict[str, ET.Element]
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(scalar properties, class blocks) after walking the whole Extends chain.

    Pools are searched in order, so the mod's own entries shadow nothing and
    a mod item extending a vanilla one resolves through the vanilla pool.

    The walk is iterative and tracks the names it has already visited: a
    mod-authored `Extends` cycle (`a` extends `b`, `b` extends `a`) is
    malformed input, and a recursive walk turned it into a RecursionError
    that killed the offline gate instead of reporting the bad patch. Cutting
    the chain silently resolved a broken patch as a working one, so the walk
    raises `ExtendsCycle` naming the path instead, and that is the one
    reported outcome for a cycle.

    An entry that extends *itself* is the one chain that resolves: the engine
    reads that as the entry's own declaration, not as a loop, so that case
    still resolves.
    """
    chain: list[tuple[ET.Element, set[str]]] = []
    path: list[str] = []
    visited: set[str] = set()
    current = name
    while True:
        node = next((pool[current] for pool in pools if current in pool), None)
        if node is None:
            break
        path.append(current)
        visited.add(current)
        parent_name, excluded = parent_of(node)
        chain.append((node, excluded))
        if not parent_name or parent_name == current:
            break
        if parent_name in visited:
            raise ExtendsCycle(" -> ".join([*path, parent_name]))
        current = parent_name

    scalars: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    for node, excluded in reversed(chain):
        # `param1` removes what was inherited; this entry's own properties
        # are written after, so a name it both excludes and sets still lands.
        for excluded_name in excluded:
            scalars.pop(excluded_name, None)
            classes.pop(excluded_name, None)
        scalars.update(own_scalars(node))
        classes.update(own_classes(node))
    return scalars, classes

#!/usr/bin/env python3
"""Structure-aware fuzz over the XPath resolver in validate-xml-targets.py.

`find` is what turns a hand-written `xpath="..."` on a `Config/*.xml` patch
operation into a PASS/FAIL/SKIP for `make validate-xml`. It splits that string
by hand and hands the rest to `ElementTree.Element.find`, whose `ElementPath`
evaluator is a small interpreter over a *different* path dialect: it answers
`text()`, `node()` and a bare `()` by looking the operator up in a table and
raising `KeyError` when it is not there, and it compiles an unclosed predicate
to a selector of `None` that it then calls, which is a `TypeError`. Neither is
a syntax error, so catching `SyntaxError` alone let both out of `find` and the
gate died partway through a target list with a traceback, reporting none of the
patches it had already checked.

There is no fuzzing engine on the host (atheris and hypothesis are absent and
nothing installs them here), so this generates the path grammar directly and
asserts the two properties a coverage-guided fuzzer cannot check on its own:

- **totality** - `find` answers True, False or None on every input and raises
  on none of them, because every malformed xpath has the same answer: a SKIP
  for manual verification. A fuzzer proves the presence of a crash; only the
  assertion makes a new interpreter dialect's exception type a visible failure
  rather than a passing run.
- **known answers** - a path built only from names and attributes that are in
  the probe document must answer True, and one naming an element that is not
  must answer False. A fuzzer cannot see a wrong verdict: a resolver that
  answered False to everything would report every patch as a failure, and one
  that answered True to everything would pass a no-op mod, and neither crashes.

The attribute step answers for the *owning element* (that is what
`setattribute` needs, and what `find` has always done), so the attribute
assertions are about the element the step lands on, not about the attribute
name existing.

Run length is fixed so the gate is deterministic; set XPATH_FUZZ_ITERS for a
longer soak (`XPATH_FUZZ_ITERS=100000 scripts/test_fuzz_xpath_targets.py`).
"""

from __future__ import annotations

import importlib.util
import os
import random
import sys
from types import ModuleType
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import safe_xml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ITERATIONS = 2000
SEED = 20260928

# The probe document, and the names its elements carry. `PRESENT` is every
# element tag in it, so a path over `PRESENT` alone must resolve.
PROBE_XML = (
    "<items>"
    "<item name='iron'>"
    "<property name='StackSize' value='10'/>"
    "<property name='Damage' value='0'/>"
    "</item>"
    "<item name='gold'>"
    "<property name='StackSize' value='5'/>"
    "</item>"
    "</items>"
)
PRESENT = ("items", "item", "property")
# Every (element, path) pair that resolves in PROBE_XML, deepest last.
CHAIN = (("items", "/items"), ("item", "/items/item"), ("property", "/items/item/property"))
NESTED = ("item", "property")
ABSENT = ("entity_class", "loot", "recipe", "quest", "block")
ATTRIBUTES = ("name", "value", "class")
# Node steps ET's ElementPath has no evaluator for; each one raised out of
# `find` before the totality catch.
UNSUPPORTED = ("text()", "node()", "comment()", "()", "processing-instruction()")
PREDICATES = (
    "[@name='iron']",
    "[@name='gold']",
    "[@name='missing']",
    "[1]",
    "[last()]",
    "[position()>1]",
    "[not(@name)]",
    "[@name='iron' and @value='10']",
    "[@name='iron' or @name='gold']",
    "[count(*) > 0]",
    "[]",
    "[@a='b']['@c='d']",
    "[@x=]",
    "[@a='b' or]",
    "[@a='b' and]",
    "[@a='b' or @c]",
    "[.",
    "[child::item]",
    "[tag()='item']",
    "[position()>]",
    "[-]",
)
JUNK = "()[]<>$\"'` \t,=/*.|:"


def load_validator() -> ModuleType:
    """Import the hyphenated script by path; it has no package of its own."""
    path = os.path.join(SCRIPT_DIR, "validate-xml-targets.py")
    spec = importlib.util.spec_from_file_location("validate_xml_targets", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot load " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe() -> ET.Element:
    return safe_xml.fromstring(PROBE_XML)


def resolvable_path(rng: random.Random) -> str:
    """A vanilla-rooted path over the probe document's real shape.

    The document is `items > item > property`, so the paths that resolve are
    exactly the prefixes of that chain. `find` drops the first name after the
    root element, so every path here is written `/items/<steps>`.
    """
    return rng.choice(CHAIN)[1]


def attribute_path(rng: random.Random) -> str:
    """A path whose last step is an attribute of an element that has it."""
    return rng.choice(CHAIN)[1] + "/" + "@" + rng.choice(ATTRIBUTES)


def arbitrary_path(rng: random.Random) -> str:
    """A path over the whole grammar, valid and not, from one pool."""
    steps = [rng.choice(PRESENT + ABSENT)]
    for _ in range(rng.randint(0, 3)):
        step = rng.random()
        if step < 0.6:
            steps.append(rng.choice(PRESENT + ABSENT + ("*", "..")))
        elif step < 0.8:
            steps.append("@" + rng.choice(ATTRIBUTES))
        else:
            steps.append(rng.choice(UNSUPPORTED))
        if rng.random() < 0.4:
            steps[-1] += rng.choice(PREDICATES)
    path = "/" + "/".join(steps)
    roll = rng.random()
    if roll < 0.05:
        path = "/" + path
    elif roll < 0.10:
        path = path.lstrip("/")
    elif roll < 0.15:
        path = path.rstrip("/")
    elif roll < 0.18:
        path = ""
    return path


def mutate(rng: random.Random, text: str) -> str:
    """Byte-level damage: well-formed input is not the only input."""
    if not text:
        return rng.choice(JUNK)
    for _ in range(rng.randint(1, 4)):
        at = rng.randrange(len(text))
        roll = rng.random()
        if roll < 0.4:
            text = text[:at] + rng.choice(JUNK) + text[at:]
        elif roll < 0.7:
            text = text[:at] + text[at + 1:]
        else:
            text = text[:at] + rng.choice("()[]<>'=,\" \t/*.") + text[at + 1:]
    return text


def main() -> int:
    module = load_validator()
    iterations = int(os.environ.get("XPATH_FUZZ_ITERS", DEFAULT_ITERATIONS))
    rng = random.Random(SEED)
    root = probe()
    failures: list[str] = []
    skips = 0

    def fail(kind: str, xpath: str, detail: str) -> None:
        if len(failures) < 5:
            failures.append(f"{kind} on {xpath[:160]!r}: {detail}")

    def verdict(xpath: str) -> bool | None:
        try:
            return module.find(root, xpath)
        except Exception as exc:
            fail("totality", xpath, f"{type(exc).__name__}: {exc}")
            return None

    for _ in range(iterations):
        # A path over names the document has, anchored at its root, resolves.
        resolvable = resolvable_path(rng)
        if verdict(resolvable) is not True:
            fail("known-answer", resolvable, "every step names an element in the probe")

        # An attribute step answers for the element that carries it.
        attribute = attribute_path(rng)
        if verdict(attribute) is not True:
            fail("known-answer", attribute, "the owning element is in the probe")

        # A name the document does not have is a patch that matches nothing:
        # the FAIL this whole script exists to catch, and it must be a plain
        # "no" rather than an answer nobody reported.
        missing = "/items/" + "/".join(
            [rng.choice(ABSENT)] + [rng.choice(PRESENT)] * rng.randint(0, 2)
        )
        if verdict(missing) is not False:
            fail("known-answer", missing, "names an element the probe does not have")

        # An xpath that does not start at the vanilla root is a question this
        # checker does not ask, so it is a SKIP, and so is one that stops on a
        # separator: both are decidable from the text alone.
        for unasked in (rng.choice(PRESENT) + "/" + rng.choice(NESTED),
                        "/items/item/", "/items//"):
            if verdict(unasked) is not None:
                fail("unasked", unasked, "answerable from the text alone: it is a SKIP")

        # Everything else: the whole grammar, and damaged copies of all of it.
        for xpath in (arbitrary_path(rng), mutate(rng, arbitrary_path(rng))):
            if verdict(xpath) is None:
                skips += 1

    if failures:
        for item in failures:
            print("FAIL " + item, file=sys.stderr)
        print(f"{len(failures)} fuzz failures over {iterations} iterations.",
              file=sys.stderr)
        return 1

    print(f"PASS xpath resolver fuzz: {iterations} iterations, {skips} paths "
          "skipped as beyond the subset, known answers intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

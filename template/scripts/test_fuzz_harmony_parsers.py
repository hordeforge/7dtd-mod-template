#!/usr/bin/env python3
"""Structure-aware fuzz over the C# source parsers in verify-patch-targets.py.

`verify-patch-targets.py` reads mod-authored C# (`[HarmonyPatch]` attributes)
and ilspycmd's decompiled text, both handed to it as raw strings and split
there with hand-rolled `index`/`rindex` bracket arithmetic. A crash in that
arithmetic is not a stack trace the author reads: the verifier dies partway
through a target list and reports nothing, which is exactly the silent-green
shape the rest of this suite exists to prevent.

There is no fuzzing engine on the host (atheris and hypothesis are both
absent and nothing installs them here), so this is a deterministic generator
over the input grammar instead: it builds well-formed signatures and
attributes where it knows the answer, mutates them into malformed text, and
asserts both properties at once.

- **round trip** — a signature synthesised from known parameter names and
  types must parse back to exactly those names and types. A fuzzer alone
  cannot see this: a parser that returns the wrong names without raising is
  indistinguishable from a correct one, so the assertion is what turns a
  correctness defect into a visible failure.
- **totality** — no parser may raise on any input, well-formed or mutated,
  because an unbalanced or renamed declaration is a normal thing to find in
  mod source, not a crash.

Run length is fixed so the gate is deterministic; set HARMONY_FUZZ_ITERS for
a longer soak (`HARMONY_FUZZ_ITERS=200000 scripts/test_fuzz_harmony_parsers.py`).
"""

from __future__ import annotations

import importlib.util
import os
import random
import string
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ITERATIONS = 3000
SEED = 20260928

TYPES = (
    "int", "string", "bool", "float", "WorldEntity", "Entity",
    "List<int>", "Dictionary<string, ItemClass>", "int[]", "int[,]",
    "Class[]", "IEnumerable<KeyValuePair<string, int>>",
    "Action<int, string>", "Nullable<int>",
)
DECLARING_TYPES = ("Game", "World", "Mod", "GameManager", "ModApi")
MODIFIERS = ("", "ref ", "out ", "in ", "params ")
NAMES = (
    "instance", "state", "entity", "__instance", "__result", "value",
    "index", "key", "data", "player", "chunk", "_args",
)
DEFAULTS = (
    "", " = null", " = 0", ' = ""', " = new[] { 1, 2 }", " = Foo(1, 2)",
    ' = ")("', ' = new Dictionary<string, int> { { "k", 1 } }',
)
JUNK = string.printable + "\t\x00 ﻿"


def load_verifier():
    """Import the hyphenated script by path; it has no package of its own."""
    path = os.path.join(SCRIPT_DIR, "verify-patch-targets.py")
    spec = importlib.util.spec_from_file_location("verify_patch_targets", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot load " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parameters_of(rng: random.Random) -> list[tuple[str, str]]:
    """Synthesised (type, name) parameters, default values attached."""
    count = rng.randint(0, 5)
    return [
        (rng.choice(TYPES), rng.choice(NAMES)) for _ in range(count)
    ]


def render(rng: random.Random, parameters: list[tuple[str, str]]) -> str:
    rendered = ", ".join(
        rng.choice(MODIFIERS) + type_name + " " + name + rng.choice(DEFAULTS)
        for type_name, name in parameters
    )
    return "public static void Patch(" + rendered + ")"


def attribute(rng: random.Random) -> str:
    parts = []
    if rng.random() < 0.85:
        parts.append("typeof(" + rng.choice(DECLARING_TYPES) + ")")
    if rng.random() < 0.6:
        parts.append('"' + rng.choice(NAMES) + '"')
    if rng.random() < 0.35:
        inner = ", ".join("typeof(" + name + ")"
                          for name in rng.sample(NAMES, rng.randint(1, 3)))
        parts.append("new Type[] { " + inner + " }")
    if not parts:
        parts.append(rng.choice(("typeof(Game)", '"Update"', '""')))
    return "[HarmonyPatch(" + ", ".join(parts) + ")]"


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
            text = text[:at] + rng.choice("()[]<>,=\"' \t") + text[at + 1:]
    return text


def main() -> int:
    module = load_verifier()
    iterations = int(os.environ.get("HARMONY_FUZZ_ITERS", DEFAULT_ITERATIONS))
    rng = random.Random(SEED)
    failures: list[str] = []

    def fail(kind: str, text: str, detail: str) -> None:
        if len(failures) < 5:
            failures.append(f"{kind} on {text[:160]!r}: {detail}")

    def tolerate(text: str) -> None:
        """Totality only: malformed text may parse to anything, never raise."""
        for kind, call in (("parameter_names", module.parameter_names),
                           ("parameter_types", module.parameter_types),
                           ("is_method_signature", module.is_method_signature)):
            try:
                call(text)
            except Exception as exc:
                fail(kind, text, f"{type(exc).__name__}: {exc}")

    def round_trip(text: str, parameters: list[tuple[str, str]]) -> None:
        tolerate(text)
        names = module.parameter_names(text)
        if names != [name for _, name in parameters]:
            fail("parameter_names", text, f"parsed {names!r}")
        wanted = [type_name for type_name, _ in parameters]
        types = module.parameter_types(text)
        if types != wanted:
            fail("parameter_types", text, f"parsed {types!r}, wanted {wanted!r}")

    for _ in range(iterations):
        parameters = parameters_of(rng)
        signature = render(rng, parameters)
        round_trip(signature, parameters)
        tolerate(mutate(rng, signature))

        attribute_text = attribute(rng)
        for text in (attribute_text, mutate(rng, attribute_text)):
            try:
                declaring_type, _method, argument_types = module.parse_attribute(text)
            except Exception as exc:
                fail("parse_attribute", text, f"{type(exc).__name__}: {exc}")
                continue
            if text != attribute_text:
                continue
            if declaring_type is not None and "typeof(" not in attribute_text:
                fail("parse_attribute", text, f"type {declaring_type!r} from no typeof()")

        declaration = "\tpublic static void Prefix(" + ", ".join(
            type_name + " " + name for type_name, name in parameters) + ")"
        for lines in ([attribute_text, declaration],
                      [mutate(rng, attribute_text), mutate(rng, declaration)]):
            try:
                injected = module.injected_parameters(lines, 1)
            except Exception as exc:
                fail("injected_parameters", "\n".join(lines),
                     f"{type(exc).__name__}: {exc}")
                continue
            if lines[1] != declaration:
                continue
            if injected != [name for _, name in parameters]:
                fail("injected_parameters", "\n".join(lines), f"parsed {injected!r}")

    if failures:
        for item in failures:
            print("FAIL " + item, file=sys.stderr)
        print(f"{len(failures)} fuzz failures over {iterations} iterations.",
              file=sys.stderr)
        return 1

    print(f"PASS harmony parser fuzz: {iterations} iterations, no crash, seeds intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Structure-aware fuzz over the XML `Extends` resolver in lib/xml_extends.py.

`resolve` walks a mod-authored `Extends` chain entry by entry, so its input
is whatever a mod author put in `Config/*.xml`: a chain longer than anyone
planned, a name that points at nothing, a self-reference, or a cycle
(`a` extends `b`, `b` extends `a`). Every one of those is a patch file, not
an attack, and all of them have to come back as a resolved entry, as empty, or
as a named `ExtendsCycle` that says which chain closed, never as a traceback
that kills the offline gate before it can report the bad patch.

No fuzzing engine is available on the host (atheris and hypothesis are
absent and nothing installs them here), so this generates the input grammar
directly and asserts the three properties a coverage-guided fuzzer cannot
check on its own:

- **termination** — every chain comes back, cycles included; a cyclic
  entry is the one input with no resolved result, and it must be the named
  `ExtendsCycle` naming the chain, never a `RecursionError`;
- **own properties win** — a property the entry declares itself is never
  lost, whatever the chain above it does;
- **`param1` excludes** — a name the entry's `Extends` refuses to inherit is
  absent unless that same entry sets it.

Truncated and mangled XML is fed to `entries` too: there the only acceptable
outcome is `ParseError`, so a different exception still fails the gate.

Run length is fixed so the gate is deterministic; set EXTENDS_FUZZ_ITERS for
a longer soak.
"""

from __future__ import annotations

import os
import random
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

# resolved against the lib/ path the line above adds
import xml_extends

DEFAULT_ITERATIONS = 2000
SEED = 20260928
NAMES = ("item", "block", "entity_class", "loot", "recipe", "quest")
SCALARS = ("StackSize", "Damage", "Price", "Tags", "Buffs")
CLASSES = ("ItemModifier", "PropertyItemClass", "ItemAction")


def entry_xml(
    tag: str,
    name: str,
    rng: random.Random,
    pool: list[str],
    own_scalars: dict[str, str],
    own_classes: dict[str, dict[str, str]],
) -> str:
    properties = []
    if pool:
        excluded = ",".join(rng.sample(SCALARS, rng.randint(0, 3)))
        properties.append(
            f'<property name="Extends" value="{rng.choice(pool)}" param1="{excluded}"/>'
        )
    for key, value in own_scalars.items():
        properties.append(f'<property name="{key}" value="{value}"/>')
    for class_name, members in own_classes.items():
        inner = "".join(
            f'<property name="{member}" value="{value}"/>'
            for member, value in members.items()
        )
        properties.append(f'<property class="{class_name}">{inner}</property>')
    return f'<{tag} name="{name}">' + "".join(properties) + f"</{tag}>"


def build_pool(rng: random.Random) -> tuple[str, str, dict[str, dict]]:
    """A mod patch XML, the tag its entries use, and what each declares."""
    tag = rng.choice(NAMES)
    xml = ["<configs><append>"]
    own: dict[str, dict] = {}
    for index in rng.sample(range(6), rng.randint(1, 5)):
        name = "e" + str(index)
        scalars = {
            key: f"v{rng.randrange(9)}"
            for key in rng.sample(SCALARS, rng.randint(0, 3))
        }
        classes = {
            class_name: {member: f"m{rng.randrange(9)}" for member in rng.sample(("A", "B"), 1)}
            for class_name in rng.sample(CLASSES, rng.randint(0, 2))
        }
        # Extends may name any entry, including itself and ones defined later:
        # a cycle is the case this gate exists for.
        xml.append(entry_xml(tag, name, rng, [f"e{i}" for i in range(6)],
                             scalars, classes))
        own[name] = {"scalars": scalars, "classes": classes}
    xml.append("</append></configs>")
    return "".join(xml), tag, own


def main() -> int:
    iterations = int(os.environ.get("EXTENDS_FUZZ_ITERS", DEFAULT_ITERATIONS))
    rng = random.Random(SEED)
    failures: list[str] = []
    cycles = 0

    def fail(kind: str, detail: str) -> None:
        if len(failures) < 5:
            failures.append(f"{kind}: {detail}")

    for _ in range(iterations):
        xml, tag, own = build_pool(rng)
        try:
            pool = xml_extends.entries(xml, tag)
        except ET.ParseError as exc:
            fail("entries", f"generated XML did not parse: {exc}")
            continue
        except Exception as exc:
            fail("entries", f"{type(exc).__name__}: {exc}")
            continue

        for name, declared in sorted(own.items()):
            try:
                scalars, classes = xml_extends.resolve(name, pool)
            except xml_extends.ExtendsCycle as exc:
                # A closed chain is malformed input with no resolved form.
                # It must name the walk and the name that closed it, or it
                # is the crash this gate exists to prevent, wearing a name.
                cycles += 1
                chain = str(exc).split(" -> ")
                if (chain[0] != name or len(chain) < 3
                        or chain[-1] not in chain[:-1]):
                    fail("cycle", f"{name}: {exc} does not name a closed chain")
                continue
            except RecursionError:
                fail("resolve", f"{name} did not terminate")
                continue
            except Exception as exc:
                fail("resolve", f"{name}: {type(exc).__name__}: {exc}")
                continue

            for key, value in declared["scalars"].items():
                if scalars.get(key) != value:
                    fail("own-property", f"{name}.{key} is {scalars.get(key)!r}, "
                                         f"the entry itself declares {value!r}")
            for class_name, members in declared["classes"].items():
                got = classes.get(class_name, {})
                for member, value in members.items():
                    if got.get(member) != value:
                        fail("own-property", f"{name}.{class_name}.{member} lost")

            parent_name, excluded = xml_extends.parent_of(pool[name])
            if parent_name in pool and parent_name != name:
                try:
                    inherited, _ = xml_extends.resolve(parent_name, pool)
                except xml_extends.ExtendsCycle:
                    # The parent is the cyclic entry; its result is the
                    # error, not a set of inherited values to compare with.
                    continue
                for excluded_name in excluded:
                    if excluded_name in declared["scalars"]:
                        continue
                    if inherited.get(excluded_name) and scalars.get(excluded_name):
                        fail("param1", f"{name} still inherits {excluded_name}")

        # Mangled XML: ParseError is the only acceptable outcome.
        broken = xml[: rng.randrange(1, max(2, len(xml)))]
        try:
            xml_extends.entries(broken, tag)
        except ET.ParseError:
            pass
        except Exception as exc:
            fail("truncated-xml", f"{type(exc).__name__}: {exc}")

    if failures:
        for item in failures:
            print("FAIL " + item, file=sys.stderr)
        print(f"{len(failures)} fuzz failures over {iterations} iterations.",
              file=sys.stderr)
        return 1

    print(f"PASS extends-chain fuzz: {iterations} iterations, {cycles} cyclic "
          "entries named, semantics intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

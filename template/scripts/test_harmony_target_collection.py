#!/usr/bin/env python3
"""The Harmony target collector resolves each attribute against its own class.

`collect_targets` carries the declaring type and the patch class name from a
class-level attribute down to the methods it covers. Those two carried over
between classes in one file, so with the fixture below the collector claimed
`PatchTwo` patched `Alpha.Two` (a method that does not exist) and filed
`PatchThree`'s target under `PatchTwo`. A wrong declaring type is worse than
a missed one: it verifies a method the mod never patches and passes on it.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from gate import check
from gate import main as report

SCRIPTS = Path(__file__).resolve().parent
MODULE = SCRIPTS / "verify-patch-targets.py"

FIXTURE = """using HarmonyLib;

namespace Demo
{
\t[HarmonyPatch(typeof(Alpha), "One")]
\tinternal static class PatchOne
\t{
\t\tstatic void Postfix() { }
\t}

\t[HarmonyPatch("Two")]
\tinternal static class PatchTwo
\t{
\t\tstatic void Postfix() { }
\t}

\tinternal static class PatchThree
\t{
\t\t[HarmonyPatch(typeof(Gamma), "Three")]
\t\tstatic void Postfix(int count) { }
\t}
}
"""

# (patch class, declaring type, method, injected parameters)
EXPECTED = (
    ("PatchOne", "Alpha", "One", ()),
    ("PatchThree", "Gamma", "Three", ("count",)),
)


def load_collector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_patch_targets", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def collected(module: ModuleType, source: Path) -> list[tuple[str, str, str, tuple[str, ...]]]:
    targets, _ = module.collect_targets(source)
    return [
        (t.patch_class, t.declaring_type, t.method, tuple(t.injected))
        for t in sorted(targets, key=lambda item: (item.patch_class, item.method))
    ]


def main() -> int:
    module = load_collector()
    with tempfile.TemporaryDirectory() as directory:
        source_dir = Path(directory) / "Demo"
        source_dir.mkdir()
        (source_dir / "Patches.cs").write_text(FIXTURE, encoding="utf-8")
        found = collected(module, source_dir)

    check(
        "each attribute resolves against its own class",
        found == list(EXPECTED),
        f"expected {list(EXPECTED)!r}, got {found!r}",
    )
    check(
        "an attribute naming no declaring type is not a verifiable target",
        not any(method == "Two" for _, _, method, _ in found),
        "a type leaked in from the previous class",
    )
    check(
        "a method-level attribute keeps its own patch class",
        ("PatchThree", "Gamma", "Three", ("count",)) in found,
        "the previous class's name was reused",
    )
    check(
        "an injected parameter name is captured",
        any(injected == ("count",) for _, _, _, injected in found),
        f"no target carried its patch method's parameter: {found!r}",
    )

    return report()


if __name__ == "__main__":
    raise SystemExit(main())

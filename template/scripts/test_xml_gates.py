#!/usr/bin/env python3
"""The XML gates must see every file the engine patches, and must not run away.

Two models sit under the offline content checks:

- `scripts/validate-xml-targets.py` answers "does this patch's xpath match
  anything in vanilla?". It walks the mod's `Config/` tree, so a flat listing
  would report a clean run for a mod whose entire XUi patch set was never
  examined — the exact silent no-op the script exists to catch.
- `scripts/lib/xml_extends.py` models the engine's `Extends` resolution. A
  chain that re-enters a name is a config defect, and the model has to name
  it rather than recurse until the interpreter gives up.

Both are driven against fixture trees in a throwaway directory, never the
shared tree, and neither prints a path from it, so the meta-gate's
byte-identical-two-runs check stays satisfiable.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import gate
import xml_extends
from gate import check
from gate import main as report

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def load_validator() -> ModuleType:
    """The hyphenated script name is not importable; load it by path."""
    return load_script("validate_xml_targets", "validate-xml-targets.py")


def load_script(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(SCRIPTS, filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def build_fixture(root: str, nested_xpath: str) -> str:
    """A mod with a flat patch and a nested XUi patch, plus a vanilla tree."""
    vanilla = os.path.join(root, "game", "Data", "Config")
    mod_config = os.path.join(root, "mod", "Config")
    # A vanilla config file is rooted at its own name (Data/Config/items.xml
    # is <items>), and a mod's xpath repeats that root, so the fixture does too.
    write(os.path.join(vanilla, "items.xml"),
          '<items><item name="vanillaItem"/></items>')
    write(os.path.join(vanilla, "XUi_InGame", "windows.xml"),
          '<windows><window name="vanillaWindow"/></windows>')
    write(os.path.join(mod_config, "items.xml"),
          '<configs><append xpath="/items/item[@name=\'vanillaItem\']">'
          '<item name="modItem"/></append></configs>')
    write(os.path.join(mod_config, "XUi_InGame", "windows.xml"),
          '<configs><append xpath="' + nested_xpath + '">'
          '<window name="modWindow"/></append></configs>')
    return mod_config


def run_validator(mod_config: str, game_dir: str) -> str:
    """Run the validator's main() over the fixture; return what it printed."""
    module = load_validator()
    module.MOD_DIR = os.path.dirname(mod_config)
    module.game_dir = lambda: game_dir
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        status = module.main()
    out.write(f"\nSTATUS {status}")
    return out.getvalue()


def nested_patches_are_checked() -> None:
    root = tempfile.mkdtemp(prefix="test-xml-gates-")
    try:
        good = build_fixture(root, "/windows/window[@name='vanillaWindow']")
        report = run_validator(good, os.path.join(root, "game"))
        check("a nested Config/XUi_InGame patch is validated against vanilla",
              "PASS XUi_InGame/windows.xml" in report and "STATUS 0" in report,
              report)
        check("the summary reports no skipped patch files",
              "0 failures, 0 skipped" in report, report)

        # Negative control: the same nested file with an xpath that matches
        # nothing. Before Config/ was walked recursively this file was never
        # opened, so the run reported a clean 0 failures either way.
        bad = build_fixture(root, "/windows/window[@name='notInVanilla']")
        bad_report = run_validator(bad, os.path.join(root, "game"))
        check("negative control: an unmatched xpath in a nested patch file fails",
              "FAIL XUi_InGame/windows.xml" in bad_report
              and "STATUS 1" in bad_report, bad_report)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def extends_model() -> None:
    def pool(*entries: str) -> dict:
        return xml_extends.entries("<configs><append>" + "".join(entries)
                                   + "</append></configs>", "item")

    inherited = pool(
        '<item name="base"><property name="Damage" value="10"/>'
        '<property class="EconomicBundle" name="bundle">'
        '<property name="Count" value="2"/></property></item>'
    )
    child = pool(
        '<item name="child"><property name="Extends" value="base" param1="StackSize"/>'
        '<property name="StackSize" value="5"/>'
        '<property name="Tier" value="1"/></item>'
    )
    scalars, classes = xml_extends.resolve("child", child, inherited)
    check("an extending entry inherits its parent's properties",
          scalars == {"Damage": "10", "StackSize": "5", "Tier": "1"},
          repr(scalars))
    check("an extending entry inherits its parent's class blocks",
          classes == {"EconomicBundle": {"Count": "2"}}, repr(classes))

    excluding = pool(
        '<item name="child"><property name="Extends" value="base" param1="Damage"/>'
        '<property name="Tier" value="1"/></item>'
    )
    excluded_scalars, _ = xml_extends.resolve("child", excluding, inherited)
    check("param1 excludes an inherited scalar", "Damage" not in excluded_scalars,
          repr(excluded_scalars))

    self_extending = pool(
        '<item name="loop"><property name="Extends" value="loop" param1=""/>'
        '<property name="Tier" value="1"/></item>'
    )
    loop_scalars, _ = xml_extends.resolve("loop", self_extending)
    check("an entry extending itself resolves to its own properties",
          loop_scalars == {"Tier": "1"}, repr(loop_scalars))

    tagged = pool(
        '<item name="tagged"><property name="Extends" value="base"/>'
        '<property class="Tags" name="tags" value="CanBeDestroyed"/></item>'
    )
    tagged_scalars, tagged_classes = xml_extends.resolve("tagged", tagged, inherited)
    check("a class property carrying a value is read as both",
          tagged_scalars.get("tags") == "CanBeDestroyed"
          and "Tags" in tagged_classes, repr((tagged_scalars, tagged_classes)))

    cyclic = pool(
        '<item name="a"><property name="Extends" value="b"/>'
        '<property name="Tier" value="1"/></item>'
        '<item name="b"><property name="Extends" value="a"/></item>'
    )
    try:
        xml_extends.resolve("a", cyclic)
        cycle_error = "resolved instead of raising"
    except xml_extends.ExtendsCycle as exc:
        cycle_error = str(exc)
    # Cutting the chain here would resolve a broken patch as a working one,
    # so the walk reports the closed chain instead (test_fuzz_extends_chain.py
    # asserts the same contract under fuzzing).
    check("a cycle is reported as ExtendsCycle naming the closed chain",
          cycle_error == "a -> b -> a", repr(cycle_error))

    missing = xml_extends.resolve("absent", child, inherited)
    check("an entry extending a name no pool has resolves to nothing",
          missing == ({}, {}), repr(missing))


def run_extends_gate(mod_dir: str) -> str:
    """Run the shipped static gate's Extends check over `mod_dir`; its stderr."""
    static = load_script("test_static_checks", "test_static_checks.py")
    static.MOD_DIR = mod_dir
    err = io.StringIO()
    recorded = len(gate.FAILURES)
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        static.check_extends_cycles()
    # The negative control fails that gate on purpose. Its failure is this
    # test's assertion, not this process's verdict, and `FAILURES` is
    # process-wide, so it is dropped again here.
    del gate.FAILURES[recorded:]
    return err.getvalue()


def cyclic_patch_is_named() -> None:
    """The shipped gate, run over a mod tree that really closes a chain.

    The model raising `ExtendsCycle` says nothing until a gate walks the mod's
    own Config files with it, so this drives `test_static_checks.py` over a
    fixture tree: the negative control has to fail with the chain named, and
    the same tree with the cycle opened has to pass.
    """
    root = tempfile.mkdtemp(prefix="test-extends-cycle-")
    try:
        cyclic = os.path.join(root, "cyclic")
        write(os.path.join(cyclic, "Config", "items.xml"),
              '<configs><append xpath="/items">'
              '<item name="a"><property name="Extends" value="b"/></item>'
              '<item name="b"><property name="Extends" value="a"/></item>'
              '</append></configs>')
        failure = run_extends_gate(cyclic)
        check("a closed Extends chain in a mod patch fails the gate, named",
              "no-extends-cycle:Config" + os.sep + "items.xml" in failure
              and "a -> b -> a" in failure, repr(failure))

        opened = os.path.join(root, "opened")
        write(os.path.join(opened, "Config", "items.xml"),
              '<configs><append xpath="/items">'
              '<item name="a"><property name="Extends" value="b"/>'
              '<property name="Tier" value="1"/></item>'
              '<item name="b"><property name="Tier" value="2"/></item>'
              '</append></configs>')
        check("an open Extends chain in a mod patch passes the gate",
              not run_extends_gate(opened), repr(run_extends_gate(opened)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    nested_patches_are_checked()
    extends_model()
    cyclic_patch_is_named()
    return report()


if __name__ == "__main__":
    raise SystemExit(main())

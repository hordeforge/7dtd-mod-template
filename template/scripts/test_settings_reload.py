#!/usr/bin/env python3
"""Structural proof of the TOML settings contract.

The mod's runtime settings are Config/<Mod>.toml, read by the DLL itself:
applied at InitMod, re-read on save without a restart (UnityUpdate watch on
the file text, debounced), reset-to-defaults-then-apply, and a broken save
keeps the current values without being reparsed on every poll. A file the
engine cannot read at all is logged with its cause, not swallowed. The
console command shares the value grammar via TrySet.
This gate holds those source-level contracts so a refactor cannot quietly
drop one; the live behavior itself is proven in game.

A mod without src/ has no settings reader; the gate passes with a note.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_NAME = os.path.basename(MOD_DIR)
SRC = os.path.join(MOD_DIR, "src", MOD_NAME)
SRC_PATH = Path(SRC)


def main() -> int:
    if not os.path.isdir(SRC):
        print("no src/ directory; no settings reader to hold to the contract")
        return 0

    def read(name: str) -> str:
        """The mod's `name` source, wherever it sits under src/<Mod>/.

        The search is recursive: a mod that files its reader one directory
        down is held to the same contract as one that keeps it at the root,
        instead of being read as an empty file and failing every check for a
        reason the report never names.
        """
        matches = sorted(SRC_PATH.rglob(name))
        for path in matches:
            if path.read_text(encoding="utf-8-sig"):
                return path.read_text(encoding="utf-8-sig")
        return ""

    settings = read("ModSettings.cs")
    api = read("ModApi.cs")
    toml_path = os.path.join(MOD_DIR, "Config", MOD_NAME + ".toml")

    check("ModSettings.cs is in src/", bool(settings),
          f"no {os.path.join('src', MOD_NAME, 'ModSettings.cs')} to read")
    check("ModApi.cs is in src/", bool(api),
          f"no {os.path.join('src', MOD_NAME, 'ModApi.cs')} to read")
    check("the shipped settings TOML exists beside its reader",
          os.path.isfile(toml_path))
    check("ModSettings reads the TOML through the shared TrySet grammar",
          "TomlSettings.TryRead" in settings
          and "TrySet(entries[i].Name, entries[i].Value" in settings)
    check("a save is picked up on UnityUpdate without a Harmony patch",
          "ModEvents.UnityUpdate.RegisterHandler" in api
          and "ModSettings.Poll()" in api
          and "FilePollIntervalSeconds" in settings
          and "FileReloadDebounceSeconds" in settings
          and "TryReadText" in settings)
    check("a change is detected by file text, not by an mtime/length stamp",
          "text == appliedText" in settings
          and "SdFile.GetLastWriteTimeUtc" not in settings)
    check("a broken file is not reparsed and relogged on every poll",
          "text == rejectedText" in settings)
    check("reload resets to defaults then applies the file",
          "ResetToDefaults();" in settings
          and '"reload " + RelativePath' in settings)
    check("a failed re-read keeps the current values",
          "keeping current settings" in settings)
    check("an unreadable settings file names its cause instead of failing silently",
          "ReportReadFailure" in settings
          and "out string failure" in settings
          and "catch (Exception ex)" in settings
          and "ex.Message" in settings)

    return report()


if __name__ == "__main__":
    sys.exit(main())

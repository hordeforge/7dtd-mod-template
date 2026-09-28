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
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_NAME = os.path.basename(MOD_DIR)
SRC = os.path.join(MOD_DIR, "src", MOD_NAME)
SRC_PATH = Path(SRC)
# How far into a dedicated server's uptime the float32 check below searches
# for the point each deadline is lost. A little over a year is past any real
# server's life and still a few hundred cheap iterations.
MAX_UPTIME_DAYS_SEARCHED = 400


def float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def code_without_comments(source: str) -> str:
    """The source with C# line and block comments removed.

    The checks below are about which clock the code reads. A comment naming
    the clock it must not read is the explanation of the rule, so matching one
    would fail the very source that documents the fix.
    """
    without_block = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", without_block)


def float32_would_lose_these_deadlines(source: str) -> bool:
    """Whether float32 is why the two deadlines have to be double.

    The deadlines are differences of readings of one engine clock. In float32
    the gap between adjacent representable values grows with the reading, so
    each interval stops being representable at some point in a server's
    uptime: the 0.25s poll interval at about 49 days, where adding it rounds
    back to the reading it started from and the poll runs every frame instead
    of four times a second; the 0.35s debounce at about 98 days, where the
    measured delta computes as 0.0 and a saved file is never applied at all.
    A double's 52-bit mantissa is exact to far under a nanosecond at those
    magnitudes, so neither happens there.

    Each interval's horizon is searched for rather than asserted, so the check
    follows the constants the file declares and fails if the claim stops being
    true. A source that no longer needs double precision returns False and has
    to drop the claim.
    """
    intervals = re.findall(
        r"const double File(?:PollInterval|ReloadDebounce)Seconds = ([0-9.]+)",
        source,
    )
    if len(intervals) != 2:
        return False
    for raw in intervals:
        interval = float(raw)
        if not _float32_loses_interval(interval):
            return False
        # double, at that interval's own horizon: it survives.
        uptime = _float32_loss_horizon_days(interval) * 24 * 60 * 60.0
        if uptime + interval == uptime or (uptime + interval) - uptime <= 0.0:
            return False
    return True


def _float32_loses_interval(interval: float) -> bool:
    """Whether float32 loses `interval` somewhere in a server's plausible life."""
    return _float32_loss_horizon_days(interval) is not None


def _float32_loss_horizon_days(interval: float) -> int | None:
    """Whole days of uptime at which float32 first loses `interval`, or None.

    Lost means both symptoms at once: adding the interval to the reading
    rounds back to the reading itself, and subtracting the reading from a
    reading one interval later gives 0.0. The search is capped at
    MAX_UPTIME_DAYS_SEARCHED, a little over a year, so a genuinely small
    interval (a millisecond, say) returns None rather than running long.
    """
    if interval <= 0.0:
        return None
    for days in range(1, MAX_UPTIME_DAYS_SEARCHED + 1):
        uptime = days * 24 * 60 * 60.0
        if (float32(float32(uptime) + interval) == float32(uptime)
                and float32(float32(uptime + interval) - float32(uptime)) <= 0.0):
            return days
    return None


SETTINGS_NAME_CONSTANT = re.compile(r"public const string (\w+)Name = ")
SETTINGS_DEFAULT_CONSTANT = re.compile(r"public const [\w<>,\[\]]+ (\w+)Default = ")
SETTINGS_PROPERTY = re.compile(
    r"public static [\w<>,\[\]]+ (\w+) \{ get; private set; \}")
TOML_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*) *=", re.MULTILINE)


def setting_names(source: str, toml_text: str) -> dict[str, set[str]]:
    """The places a setting is named, as `name -> {places that name it}`.

    A setting is spelled in five places at once: a `Name` constant, a
    `Default` constant, a property, a line each in `ResetToDefaults`,
    `TrySet` and `Describe`, and a key in the shipped TOML. Nothing in the
    C# compiler connects them, so a setting added to four of the five is a
    setting the mod declares and never reads: the property keeps its
    default, and the key the player edited is refused as unknown. This maps
    the five so the gate below can name the place that is missing rather
    than report a disagreement.
    """
    code = code_without_comments(source)
    names: dict[str, set[str]] = {}

    def mark(name: str, place: str) -> None:
        names.setdefault(name, set()).add(place)

    for match in SETTINGS_NAME_CONSTANT.finditer(code):
        mark(match.group(1), "Name")
    for match in SETTINGS_DEFAULT_CONSTANT.finditer(code):
        mark(match.group(1), "Default")
    for match in SETTINGS_PROPERTY.finditer(code):
        mark(match.group(1), "property")
    for match in re.finditer(r"string\.Equals\(name, (\w+)Name,", code):
        mark(match.group(1), "TrySet")
    for match in re.finditer(r"return new\[\][^;]*?\};", code, re.DOTALL):
        for name in re.findall(r"(\w+)Name", match.group(0)):
            mark(name, "Describe")
    reset = re.search(r"static void ResetToDefaults\(\)\s*\{(.*?)\n[ \t]+\}", code,
                      re.DOTALL)
    for name in re.findall(r"(\w+) = \w+Default;", reset.group(1) if reset else ""):
        mark(name, "ResetToDefaults")
    for key in TOML_KEY.findall(toml_text):
        mark(key, "TOML")
    return names


REQUIRED_PLACES = ("Name", "Default", "property", "ResetToDefaults",
                   "TrySet", "Describe", "TOML")


def missing_places(found: set[str]) -> str:
    return ", ".join(place for place in REQUIRED_PLACES if place not in found)


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
    code = code_without_comments(settings)
    check("the poll and debounce deadlines are read at double precision",
          float32_would_lose_these_deadlines(code)
          and "Time.unscaledTimeAsDouble" in code
          and not re.search(r"\bTime\.unscaledTime\b(?!\w)", code)
          and "const double FilePollIntervalSeconds" in code
          and "const double FileReloadDebounceSeconds" in code)

    toml_text = (Path(toml_path).read_text(encoding="utf-8-sig")
                 if os.path.isfile(toml_path) else "")
    names = setting_names(settings, toml_text)
    incomplete = sorted(
        name + " (missing " + missing_places(found) + ")"
        for name, found in names.items()
        if any(place not in found for place in REQUIRED_PLACES))
    check("every setting is named in all seven places it takes to declare one",
          not incomplete,
          f"a setting missing from one of Name/Default/property/"
          f"ResetToDefaults/TrySet/Describe/shipped TOML: "
          f"{'; '.join(incomplete)}")

    toml_reader = read("TomlSettings.cs")
    if "TomlSettings.TryRead" in settings:
        check("an array element the comma join cannot carry is refused by name",
              "a nested array is not a settings value." in toml_reader
              and "an array element cannot contain ','." in toml_reader
              and "item.IndexOf(',')" in toml_reader,
              "an element carrying a comma, or a nested array, joins into a "
              "value that means something else than the file declares")

    return report()


if __name__ == "__main__":
    sys.exit(main())

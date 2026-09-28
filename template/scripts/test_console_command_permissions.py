#!/usr/bin/env python3
"""The console command's permission level, and which process runs it.

A mod's `ConsoleCmdAbstract` subclass is a privileged operation reachable by
every connected player, so who may run it is decided by one member:
`DefaultPermissionLevel`, which the engine compares against the caller's
level in `AdminTools.CommandAllowedFor` on the networked and web paths
(0 is the highest level, a larger number is less privileged; an unlisted
player is 1000). A command that does not state a level inherits the base
class's, and the class it inherits into is the game's, not this mod's.

`IsExecuteOnClient` decides where it runs: a client-executable command is
forwarded to the caller and executed in their own process, so a command
that reads or writes the server's authoritative settings does not belong
there.

This gate holds both properties at the source level; the live behavior is
proven in game. A mod without src/ has no console command; the gate passes
with a note.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_NAME = os.path.basename(MOD_DIR)
SRC = os.path.join(MOD_DIR, "src", MOD_NAME)

# The level the 7DTD admin convention calls the highest privilege; every
# unlisted player is 1000 and therefore denied at this level.
ADMIN_LEVEL = 0

LEVEL_PROPERTY = re.compile(
    r"override\s+int\s+DefaultPermissionLevel\s*=>\s*([^;]+);")
CONST_INT = re.compile(r"\bconst\s+int\s+(\w+)\s*=\s*(-?\d+)\s*;")
CLIENT_PROPERTY = re.compile(
    r"override\s+bool\s+IsExecuteOnClient\s*=>\s*(true|false)\s*;")


def resolve_level(source: str) -> int | None:
    """The int a class's `DefaultPermissionLevel` resolves to, or None.

    The level is usually a named constant rather than a literal, so a bare
    identifier is looked up among the file's `const int`s; an inherited or
    absent declaration has no value here, which is what the gate reports.
    """
    match = LEVEL_PROPERTY.search(source)
    if match is None:
        return None
    value = match.group(1).strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    named = dict(CONST_INT.findall(source))
    return int(named[value]) if value in named else None


def command_sources() -> list[tuple[str, str]]:
    """(file name, source) for every console command class in src/."""
    if not os.path.isdir(SRC):
        return []
    sources: list[tuple[str, str]] = []
    for name in sorted(os.listdir(SRC)):
        if not (name.startswith("ConsoleCmd") and name.endswith(".cs")):
            continue
        with open(os.path.join(SRC, name), encoding="utf-8") as handle:
            sources.append((name, handle.read()))
    return sources


def declared(source: str) -> bool:
    return LEVEL_PROPERTY.search(source) is not None


def settings_is_admin_only(source: str) -> bool:
    return (resolve_level(source) == ADMIN_LEVEL
            and CLIENT_PROPERTY.search(source) is not None
            and CLIENT_PROPERTY.search(source).group(1) == "false")


def main() -> int:
    commands = command_sources()
    if not commands:
        print("no console command class in src/; nothing to hold to a level")
        return 0

    for name, source in commands:
        check("declares-its-own-permission-level:" + name, declared(source),
              "no DefaultPermissionLevel override; the game base class's level "
              "decides who may run it")

    settings = next((source for name, source in commands
                     if os.path.basename(name) == "ConsoleCmd" + MOD_NAME + ".cs"),
                    None)
    check("the settings command is the one present", settings is not None,
          "no ConsoleCmd" + MOD_NAME + ".cs in src/")
    if settings is not None:
        check("the settings command is admin-level",
              resolve_level(settings) == ADMIN_LEVEL,
              "DefaultPermissionLevel resolves to "
              + repr(resolve_level(settings)) + ", not " + repr(ADMIN_LEVEL))
        client = CLIENT_PROPERTY.search(settings)
        check("the settings command runs in the server process, not the caller's",
              client is not None and client.group(1) == "false",
              "IsExecuteOnClient is not false, so the engine forwards the "
              "command to the caller instead of running it on the server")

    # Negative control: a command that inherits the level, or that opts into
    # client execution, must fail the checks above — a gate that cannot fail
    # is not a gate.
    inherited = ("public class X : ConsoleCmdAbstract { public override bool "
                 "IsExecuteOnClient => false; }")
    check("negative control: an inherited level is caught", not declared(inherited))
    forwarded = ("public class X : ConsoleCmdAbstract { public override int "
                 "DefaultPermissionLevel => 0; public override bool "
                 "IsExecuteOnClient => true; }")
    check("negative control: a client-executable command is caught",
          not settings_is_admin_only(forwarded))

    return report()


if __name__ == "__main__":
    sys.exit(main())

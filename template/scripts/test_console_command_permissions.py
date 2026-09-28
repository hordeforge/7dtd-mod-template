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
that writes the server's authoritative settings does not belong there.

Commands are found by their base type, not by their file name: the engine
discovers every `ConsoleCmdAbstract` subclass wherever it is declared, so a
class in a file this gate did not look at would otherwise ship with an
inherited level and no check at all. Every command found is held to its
own stated, resolvable level, and any command that writes the settings is
held to admin-and-server-side like the settings command itself.

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

# A class declaration and the two things that follow it: the base list up to
# the body (or to the `;` of a forward declaration) and the balanced body.
CLASS_DECL = re.compile(r"\bclass\s+(\w+)\s*")

# Comments and string/char literals hold no declaration, and a brace inside
# one would throw the body off, so they are blanked before scanning.
NOISE = re.compile(
    r"//[^\n]*|/\*.*?\*/"
    r"|@(?:\"(?:[^\"]|\"\")*\")"
    r"|\$?\"(?:\\.|[^\"\\\n])*\""
    r"|'(?:\\.|[^'\\\n])*'",
    re.DOTALL)

# The settings members that change server state. A command calling one of
# these edits the server's authoritative copy, so it is held to the same
# admin-and-server-side contract as the settings command.
SETTING_WRITES = re.compile(r"\bModSettings\.(?:TrySet|ReloadNow)\s*\(")

# A command level stated in terms the gate cannot evaluate (another type's
# constant, a computed value). Unstated intent is not a permission.
UNREADABLE_LEVEL = "<unresolvable>"


def strip_noise(source: str) -> str:
    """The source with comments and literals blanked, so offsets survive."""
    return NOISE.sub(lambda match: " " * len(match.group(0)), source)


def class_bodies(source: str) -> list[tuple[str, str]]:
    """(name, body) for every `ConsoleCmdAbstract` class in one file.

    A class whose body is not in this file (a `partial` declaration) yields
    nothing, and another file declaring the same name contributes its own
    body: the two are concatenated by the caller, so a level or a flag
    declared in either half is seen.
    """
    text = strip_noise(source)
    found: list[tuple[str, str]] = []
    for match in CLASS_DECL.finditer(text):
        end = _body_start(text, match.end())
        if end is None or "ConsoleCmdAbstract" not in text[match.end():end]:
            continue
        close = _body_end(text, end)
        if close is not None:
            found.append((match.group(1), text[end + 1:close]))
    return found


def _body_start(text: str, start: int) -> int | None:
    """Index of the class body's `{`, or None for a bodyless declaration."""
    index = start
    while index < len(text):
        if text[index] in "{;":
            return index if text[index] == "{" else None
        index += 1
    return None


def _body_end(text: str, open_brace: int) -> int | None:
    """Index of the `}` closing the body starting at `open_brace`."""
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def csharp_sources() -> list[tuple[str, str]]:
    """(file name, source) for every .cs file under src/, at any depth."""
    if not os.path.isdir(SRC):
        return []
    sources: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(SRC):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".cs"):
                continue
            with open(os.path.join(root, name), encoding="utf-8-sig") as handle:
                sources.append((name, handle.read()))
    return sources


def command_sources(sources: list[tuple[str, str]] | None = None
                    ) -> dict[str, str]:
    """{class name: body} for every console command in src/.

    Keyed by class rather than by file, so a second command in a file that
    already carries one is a command of its own and not a bystander to the
    first one's level.
    """
    bodies: dict[str, str] = {}
    for _name, source in (csharp_sources() if sources is None else sources):
        for name, body in class_bodies(source):
            bodies[name] = bodies.get(name, "") + body
    return bodies


def resolve_level(source: str) -> int | None:
    """The int a command's `DefaultPermissionLevel` resolves to, or None.

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


def declared(source: str) -> bool:
    return LEVEL_PROPERTY.search(source) is not None


def writes_settings(body: str) -> bool:
    return SETTING_WRITES.search(body) is not None


def settings_is_admin_only(source: str) -> bool:
    return (resolve_level(source) == ADMIN_LEVEL
            and CLIENT_PROPERTY.search(source) is not None
            and CLIENT_PROPERTY.search(source).group(1) == "false")


def main() -> int:
    commands = command_sources()
    if not commands:
        print("no console command class in src/; nothing to hold to a level")
        return 0

    for name in sorted(commands):
        body = commands[name]
        check("declares-its-own-permission-level:" + name, declared(body),
              "no DefaultPermissionLevel override; the game base class's level "
              "decides who may run it")
        check("permission-level-resolves-to-a-number:" + name,
              resolve_level(body) is not None,
              "DefaultPermissionLevel is stated as " + UNREADABLE_LEVEL
              + " to this gate, so the level it enforces is unknown")
        if not writes_settings(body):
            continue
        # A command that writes the settings edits the server's copy, so it
        # holds the same contract as the settings command: admin level, run
        # in the server process rather than the caller's.
        check("a-settings-writing-command-is-admin-level:" + name,
              resolve_level(body) == ADMIN_LEVEL,
              "it calls " + SETTING_WRITES.search(body).group(0)[:-1]
              + " at level " + repr(resolve_level(body)) + ", not "
              + repr(ADMIN_LEVEL))
        check("a-settings-writing-command-runs-on-the-server:" + name,
              CLIENT_PROPERTY.search(body) is not None
              and CLIENT_PROPERTY.search(body).group(1) == "false",
              "IsExecuteOnClient is not false, so the engine forwards the "
              "command to the caller instead of running it on the server")

    settings = commands.get("ConsoleCmd" + MOD_NAME)
    check("the settings command is the one present", settings is not None,
          "no ConsoleCmd" + MOD_NAME + " in src/")
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

    # Negative controls: each shape this gate exists to catch must fail it.
    # A gate that cannot fail is not a gate.
    inherited = ("public class X : ConsoleCmdAbstract { public override bool "
                 "IsExecuteOnClient => false; }")
    check("negative control: an inherited level is caught", not declared(inherited))
    forwarded = ("public class X : ConsoleCmdAbstract { public override int "
                 "DefaultPermissionLevel => 0; public override bool "
                 "IsExecuteOnClient => true; }")
    check("negative control: a client-executable command is caught",
          not settings_is_admin_only(forwarded))
    check("negative control: an unreadable level is caught",
          resolve_level("public override int DefaultPermissionLevel => "
                        "Permissions.ForSettings;") is None)
    # A command outside a file named ConsoleCmd*.cs, at a level any player
    # has, writing the server's settings.
    off_name = command_sources([("Commands.cs", (
        "public class Sneaky : ConsoleCmdAbstract { public override int "
        "DefaultPermissionLevel => 1000; public override bool "
        "IsExecuteOnClient => true; public void Run() "
        "{ ModSettings.TrySet(); } }"))])
    check("negative control: a command is found outside a ConsoleCmd file",
          list(off_name) == ["Sneaky"], repr(sorted(off_name)))
    check("negative control: a player-level settings writer is caught",
          "Sneaky" in off_name and not settings_is_admin_only(off_name["Sneaky"]))
    # Two classes in one file: the second has no level of its own.
    two = command_sources([("ConsoleCmdX.cs", (
        "public class A : ConsoleCmdAbstract { public override int "
        "DefaultPermissionLevel => 0; } "
        "public class B : ConsoleCmdAbstract { }"))])
    check("negative control: each class in a file is held separately",
          sorted(two) == ["A", "B"] and not declared(two["B"]))
    # A command only mentioned in a comment or a string is not a command;
    # reading it as one would report a class that does not exist and miss the
    # brace it throws off.
    commented = command_sources([("Notes.cs", (
        "// class Ghost : ConsoleCmdAbstract { }\n"
        "public const string Snippet = \"class Phantom : ConsoleCmdAbstract {\";\n"
        "public class Real : ConsoleCmdAbstract { public override int "
        "DefaultPermissionLevel => 0; }"))])
    check("negative control: a command in a comment or string is not found",
          list(commented) == ["Real"], repr(sorted(commented)))

    return report()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check every Harmony patch target against the local game's Assembly-CSharp.

A `[HarmonyPatch(typeof(X), "Name")]` names its target method with a *string*,
so a rename in the game assembly still compiles here and only fails at load
time — the mod has already shipped that class of defect once. This re-checks
each target against the installed build by decompiling the declaring type.

Harmony resolves such an attribute with `AccessTools.DeclaredMethod`, which
looks only at methods declared on the named type (never inherited ones) and
throws `AmbiguousMatchException` when overloads exist and no argument types
were given. Both conditions are checked here.

The patch method's own parameters are checked too: Harmony injects an original
parameter by *name*, so a renamed engine parameter is the same silent failure
as a renamed method. Names beginning with `__` are Harmony's own injections
(`__instance`, `__result`, `___privateField`, …) and are skipped.
"""

from __future__ import annotations

import argparse
import functools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import local_env

# src/<ModName> mirrors the mod directory name (Repo layout rule in AGENTS.md).
SOURCE_DIR = Path("src") / Path(__file__).resolve().parent.parent.name
MANAGED_SUBDIR = Path("7DaysToDie_Data") / "Managed"
ASSEMBLY_NAME = "Assembly-CSharp.dll"

PATCH_ATTRIBUTE = re.compile(r"\[HarmonyPatch\((?P<args>.*)\)\]\s*$")
CLASS_DECLARATION = re.compile(r"^\s*(?:static\s+|internal\s+|public\s+|sealed\s+)*class\s+(\w+)")
TYPEOF = re.compile(r"typeof\(\s*([\w.]+)\s*\)")
QUOTED = re.compile(r'"([^"]+)"')
PATCH_METHOD = re.compile(r"^\s*(?:[A-Za-z_]\w*\s+)*static\s+(?!class\b)")
# The explicit argument-type array of `[HarmonyPatch(typeof(X), "M",
# new Type[] { typeof(A), typeof(B) })]`. Compiled here, not inside
# parse_attribute: the attribute is parsed once per patch method in the mod,
# and a per-call compile is a pattern cache lookup and a rebuild of the same
# string on every one of them.
ARGUMENT_TYPE_ARRAY = re.compile(r"new\s+Type\[\]\s*\{(?P<items>.*)\}", re.DOTALL)

# A decompile of one engine type must not hang the gate; the timeout surfaces
# as a failed check for that target, not as a killed run.
DECOMPILE_TIMEOUT_SECONDS = 300

# A decompiler version, not "latest". Every signature this gate matches is
# text the installed ilspycmd wrote, so a floating tool decides whether a
# target passes. The pin is what a reader can reproduce; ilspy_pin_warning
# says so when the installed one is not it.
ILSPYCMD_VERSION = "11.1.0.9782"
ILSPY_VERSION = re.compile(r"\d+(?:\.\d+)+")


def ilspy_install_command() -> str:
    """The pinned install line, for every place that points at a missing tool."""
    return f"dotnet tool install -g ilspycmd --version {ILSPYCMD_VERSION}"


def installed_ilspy_version(output: str) -> str | None:
    """The version ilspycmd named in its output, or None when it named none."""
    found = ILSPY_VERSION.search(output)
    return found.group(0) if found else None


def ilspy_pin_warning(output: str) -> str | None:
    """Why the installed ilspycmd is not the pinned one; None when it is.

    A different decompiler is not a failed check: the target's declarations
    are in the assembly, not in the tool. It is a warning because the
    verdict was read out of tool output the pin does not describe, so a
    disagreement with the game's own code is worth a look before it is
    accepted.
    """
    found = installed_ilspy_version(output)
    if found == ILSPYCMD_VERSION:
        return None
    if found is None:
        return f"ilspycmd named no version ({output.strip() or 'no output'})"
    return (f"ilspycmd {found}, this template pins {ILSPYCMD_VERSION}; the "
            "signatures below are that version's reading of the assembly")


def is_method_signature(line: str) -> bool:
    """Whether a line starts a static *method* declaration.

    Access modifiers come before `static`, so `public static void Prefix`
    is a declaration and not a field. Anchoring on `static` alone skipped
    every patch method written that way, so the injected-parameter check
    below it silently verified nothing.

    `static` alone also matches member fields, e.g.
    `static readonly PlaceConfirmState Confirm = new PlaceConfirmState();`.
    A declaration with its parentheses before any `=` is a method; in a
    field initializer every `(` comes after the `=`. Stopping on a field
    made the injected-parameter check silently skip the real patch method
    below it.
    """
    if not PATCH_METHOD.match(line):
        return False
    parenthesis = line.find("(")
    if parenthesis < 0:
        return False
    assignment = line.find("=")
    return assignment < 0 or parenthesis < assignment


DESCRIPTION = """\
Decompile each Harmony patch target's declaring type out of the selected
7 Days To Die client and confirm the patched method is still declared there
with the expected signature.

REQUIRES
  ilspycmd    dotnet tool install -g ilspycmd --version 11.1.0.9782
              or set ILSPYCMD (env or .local.env) to the executable.

EXAMPLES
  scripts/verify-patch-targets.py
  scripts/verify-patch-targets.py --game-dir /path/to/7dtd

EXIT STATUS
  0  every target checks out (or there is nothing to verify)
  1  a target failed, or the toolchain/game install is unusable
  2  the command line was wrong\
"""


class Target:
    def __init__(self, source: Path, line: int, patch_class: str, declaring_type: str,
                 method: str, argument_types: list[str] | None, injected: list[str]) -> None:
        self.source = source
        self.line = line
        self.patch_class = patch_class
        self.declaring_type = declaring_type
        self.method = method
        self.argument_types = argument_types
        self.injected = injected

    def label(self) -> str:
        arguments = ("" if self.argument_types is None
                     else "(" + ", ".join(self.argument_types) + ")")
        return f"{self.declaring_type}.{self.method}{arguments}"


def parse_attribute(arguments: str) -> tuple[str | None, str | None, list[str] | None]:
    """Pull (declaring type, method name, argument types) out of one attribute."""
    types = TYPEOF.findall(arguments)
    quoted = QUOTED.findall(arguments)

    array = ARGUMENT_TYPE_ARRAY.search(arguments)
    argument_types = TYPEOF.findall(array.group("items")) if array else None

    declaring_type = None
    if types:
        # An explicit argument-type array reuses typeof(); the declaring type is
        # whichever typeof() came before it.
        leading = TYPEOF.findall(arguments[:array.start()] if array else arguments)
        declaring_type = leading[0] if leading else None

    method = quoted[0] if quoted else None
    return declaring_type, method, argument_types


def injected_parameters(lines: list[str], attribute_line: int) -> list[str]:
    """Parameter names of the patch method that follows an attribute."""
    index = attribute_line  # `attribute_line` is 1-based, so this is the next line.
    while index < len(lines) and not is_method_signature(lines[index]):
        index += 1
    if index >= len(lines):
        return []

    # The parentheses are counted as the lines are added rather than
    # recounted on the accumulated text: a signature spread over several
    # lines made every pass rescan everything joined so far, so a patch
    # method with a long wrapped parameter list cost a scan per line.
    signature = ""
    depth = 0
    opened = False
    while index < len(lines):
        line = lines[index]
        signature += line
        opened = opened or "(" in line
        depth += line.count("(") - line.count(")")
        if opened and depth == 0:
            break
        index += 1

    return parameter_names(signature)


OPENERS = "([<{"
CLOSERS = ")]>}"
DEFAULT_ASSIGNMENT = re.compile(r"(?<![<>!=])=(?!=)")


def mask_literals(text: str) -> str:
    """Blank out string and char literal bodies, keeping every offset.

    A default value may hold a string full of brackets and commas
    (`string sep = "),"`); scanning the raw text would count those as
    structure and misplace the end of the parameter list.
    """
    masked = list(text)
    index = 0
    length = len(text)
    while index < length:
        quote = text[index]
        if quote not in "\"'":
            index += 1
            continue
        start = index
        index += 1
        while index < length and text[index] != quote:
            index += 2 if text[index] == "\\" else 1
        index = min(index + 1, length)
        for position in range(start, index):
            masked[position] = " "
    return "".join(masked)


def argument_list(signature: str) -> list[str] | None:
    """The call arguments of `signature`, one entry each, or None.

    Unbalanced text is None rather than an exception: a truncated
    decompilation or a half-typed declaration is something to report, not a
    crash. Splitting is bracket-aware because a C# parameter list carries
    commas inside generic arguments and default values (`List<int>`,
    `int x = Foo(1, 2)`), and a plain `split(",")` turns one parameter into
    several phantom ones.
    """
    masked = mask_literals(signature)
    start = masked.find("(")
    if start < 0:
        return None

    depth = 0
    for index in range(start, len(masked)):
        character = masked[index]
        if character in OPENERS:
            depth += 1
        elif character in CLOSERS:
            depth -= 1
            if depth == 0:
                # The masked copy is handed on rather than masked a second
                # time: masking is a pass over the whole signature, and every
                # parameter list walked it twice for one answer.
                return split_top_level(signature, masked, start + 1, index)
    return None


def split_top_level(signature: str, masked: str, start: int, end: int) -> list[str]:
    depth = 0
    entries: list[str] = []
    cursor = start
    for index in range(start, end):
        character = masked[index]
        if character in OPENERS:
            depth += 1
        elif character in CLOSERS:
            depth -= 1
        elif character == "," and depth == 0:
            entries.append(signature[cursor:index])
            cursor = index + 1
    # A trailing separator leaves an empty tail, which is not a parameter:
    # `Patch(string sep = "),(",)` declares one, and appending the tail anyway
    # reported two. A signature with no tail at all, `Patch()`, already came
    # back empty; this makes the two agree.
    tail = signature[cursor:end]
    if tail.strip():
        entries.append(tail)
    return entries


def without_default(entry: str) -> str:
    return DEFAULT_ASSIGNMENT.split(entry.strip(), 1)[0].strip()


def strip_namespace(type_text: str) -> str:
    """`Game.World` -> `World`, leaving dotted names inside generics alone."""
    depth = 0
    for index, character in enumerate(type_text):
        if character in OPENERS:
            depth += 1
        elif character in CLOSERS:
            depth -= 1
        elif character == "." and depth == 0:
            return type_text[index + 1:].strip()
    return type_text.strip()


def parameter_names(signature: str) -> list[str]:
    entries = argument_list(signature)
    if entries is None:
        return []
    names = []
    for entry in entries:
        words = without_default(entry).split()
        if len(words) >= 2:
            names.append(words[-1])
    return names


def make_target(
    source: Path,
    entry: tuple[int, str | None, str | None, list[str] | None],
    lines: list[str],
    patch_class: str | None,
    declaring_type: str | None,
) -> Target | None:
    """One verifiable target, or None when the attribute names nothing to check.

    An attribute that names no method patches every method of that name, and
    one that names no declaring type says nothing about where to look; neither
    is a target this verifier can decompile, so neither becomes a Target.
    """
    # The entry's own type is already folded into `declaring_type` by the
    # caller, which is what carries a type-only class-level attribute down to
    # the methods it covers.
    entry_line, _own_type, method, argument_types = entry
    if method is None or patch_class is None or declaring_type is None:
        return None
    return Target(source, entry_line, patch_class, declaring_type, method,
                  argument_types, injected_parameters(lines, entry_line))


def collect_targets(source_dir: Path) -> tuple[list[Target], set[str]]:
    targets: list[Target] = []
    patch_classes: set[str] = set()

    for source in sorted(source_dir.glob("*.cs")):
        lines = source.read_text(encoding="utf-8-sig").splitlines()
        # A class-level attribute may name only the type; the method names then
        # come from attributes on the individual patch methods. Both reset at
        # every class: a type named by one class must not leak into the next,
        # or a method-only attribute is checked against the wrong type.
        class_type: str | None = None
        class_name: str | None = None
        pending: list[tuple[int, str | None, str | None, list[str] | None]] = []

        for index, line in enumerate(lines, start=1):
            attribute = PATCH_ATTRIBUTE.search(line.strip())
            if attribute:
                pending.append((index, *parse_attribute(attribute.group("args"))))
                continue

            declaration = CLASS_DECLARATION.match(line)
            if declaration:
                class_name = declaration.group(1)
                class_type = None
            if pending and (declaration or (line.strip() and not line.strip().startswith("["))):
                # Either a class-level attribute, or a method-level one inside
                # an already-opened patch class.
                if class_name is not None:
                    patch_classes.add(class_name)
                for entry in pending:
                    class_type = entry[1] or class_type
                    target = make_target(source, entry, lines, class_name, class_type)
                    if target is not None:
                        targets.append(target)
                pending = []

    return targets, patch_classes


def decompile(assembly: Path, type_name: str, cache: dict[tuple[str, str], list[str]]) -> list[str]:
    """The decompiled body of `type_name` in `assembly`, cached per assembly
    and type.

    The assembly is part of the key because the answer is: the same type name
    in a second game install is a different body, and a cache keyed by the
    name alone answers every later install from the first one's decompile.

    ilspycmd writes UTF-8 regardless of the environment it is launched in, so
    the output is decoded as UTF-8 here rather than with the locale encoding.
    Under a C or POSIX locale that decoding is ASCII, and any engine type
    carrying a non-ASCII string literal (the localized tables are full of
    them) raised UnicodeDecodeError out of a gate that reports per-target
    problems instead of tracebacks.
    """

    key = (str(assembly), type_name)
    if key not in cache:
        try:
            result = subprocess.run(["ilspycmd", "-t", type_name, str(assembly)],
                                    capture_output=True, encoding="utf-8",
                                    errors="replace", check=False,
                                    timeout=DECOMPILE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # One slow type must fail its own check, not the run: the caller
            # only handles RuntimeError, and a bare TimeoutExpired here would
            # print a traceback and skip every target after this one.
            raise RuntimeError(
                f"ilspycmd timed out after {DECOMPILE_TIMEOUT_SECONDS}s "
                f"decompiling {type_name}") from None
        except OSError as exc:
            raise RuntimeError(f"ilspycmd could not run for {type_name}: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(f"ilspycmd failed for {type_name}: {result.stderr.strip()}")
        cache[key] = result.stdout.splitlines()
    return cache[key]


# A version directory name split into digit and non-digit runs.
VERSION_RUN = re.compile(r"\d+|\D+")


def editor_version_key(path: Path) -> tuple:
    """Newest editor first, comparing version segments as numbers.

    Plain `sorted(..., reverse=True)` on paths is lexicographic, so an
    installed `2022.3.9f1` outranks `2022.3.10f1` and the fallback probes
    the older SDK first. Runs of digits compare numerically, everything
    else ordinally, and the raw parts break a tie deterministically.
    """
    tokens: list[tuple[int, int, str]] = []
    for part in path.parts:
        for run in VERSION_RUN.findall(part):
            tokens.append((0, int(run), "") if run.isdigit() else (1, 0, run))
    return (tokens, path.parts)


ILSPY_PROBE_TIMEOUT_SECONDS = 60
ILSPY_KEY = "ILSPYCMD"
ILSPY_NAME = "ilspycmd"


def resolve_ilspycmd(root: Path) -> str | None:
    """Put a usable ilspycmd on PATH, or return the message naming the fix.

    Three sources, in one documented order: the ILSPYCMD key (the
    environment, then `.local.env`), a PATH lookup, then the global-tools
    directory `dotnet tool install -g` writes to. The key is listed in
    `.local.env.example` and new-mod.sh fills it from `command -v`, but
    nothing read it, so a tool on any other path resolved to "not found"
    however the file was configured.

    Returns None once one of them names a real file. A key that points at a
    missing file, or at one not named `ilspycmd` (the tool is run by that
    name off PATH), is reported as the stale value rather than silently
    replaced by another ilspycmd from PATH: a configured path is the user's
    statement about where the tool is.
    """
    configured = local_env.value(root, ILSPY_KEY)
    if configured:
        candidate = Path(configured)
        if not candidate.is_file():
            return (f"{ILSPY_KEY} points at {candidate}, which is not a file. "
                    f"Correct it in .local.env, or unset it to search PATH.")
        if candidate.name != ILSPY_NAME:
            return (f"{ILSPY_KEY} points at {candidate}; it must name the "
                    f"{ILSPY_NAME} executable itself.")
    elif shutil.which(ILSPY_NAME) is None:
        candidate = Path.home() / ".dotnet" / "tools" / ILSPY_NAME
        if not candidate.is_file():
            return (f"{ILSPY_NAME} not found on PATH, at {candidate}, and "
                    f"{ILSPY_KEY} is unset. Install it with:\n"
                    f"  {ilspy_install_command()}")
    else:
        candidate = Path(shutil.which(ILSPY_NAME) or ILSPY_NAME)
    # Prepended, not appended: the key is a statement about which ilspycmd to
    # use, and appending left any other one already on PATH ahead of it, so a
    # configured ILSPYCMD was resolved and then not the tool that ran.
    os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
    return None


def probe_ilspy() -> tuple[int | None, str]:
    """`ilspycmd --version` as (returncode, output); returncode None = could not run.

    A tool that cannot be launched at all is a broken environment, not a
    non-zero version check, and the two want different advice.
    """
    try:
        result = subprocess.run(["ilspycmd", "--version"], capture_output=True,
                                encoding="utf-8", errors="replace", check=False,
                                timeout=ILSPY_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None, f"ilspycmd --version did not answer within {ILSPY_PROBE_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return None, f"ilspycmd could not be launched: {exc}"
    return result.returncode, (result.stderr.strip() or result.stdout.strip())


def ensure_ilspy_runtime() -> str | None:
    """Make the installed ilspycmd runnable without a manual DOTNET_ROOT.

    Global dotnet tools retain their target runtime. On machines where the
    distro upgraded past that runtime, Unity Hub's editor SDK is a local,
    versioned fallback. It is sufficient for this read-only verifier and is
    preferred over silently treating every target as missing.
    """
    code, output = probe_ilspy()
    if code == 0:
        return None

    hub_editors = Path.home() / "Unity" / "Hub" / "Editor"
    candidates = sorted(
        (path / "Editor" / "Data" / "DotNetSdk" for path in hub_editors.glob("*")),
        key=editor_version_key,
        reverse=True,
    ) if hub_editors.is_dir() else []
    for runtime_root in candidates:
        if not (runtime_root / "dotnet").is_file():
            continue
        original_root = os.environ.get("DOTNET_ROOT")
        os.environ["DOTNET_ROOT"] = str(runtime_root)
        os.environ["PATH"] = str(runtime_root) + os.pathsep + os.environ.get("PATH", "")
        code, retry_output = probe_ilspy()
        if code == 0:
            print(f"ILSPY_RUNTIME {runtime_root}")
            return None
        if original_root is None:
            os.environ.pop("DOTNET_ROOT", None)
        else:
            os.environ["DOTNET_ROOT"] = original_root
        if code is None:
            output = retry_output

    return output or "unknown ilspycmd runtime error"


@functools.cache
def declaration_pattern(method: str) -> re.Pattern[str]:
    """The compiled declaration pattern for one method name.

    Cached because the pattern embeds the method name, and a mod whose
    patches target a dozen methods compiled the same shape a dozen times
    while scanning one decompiled body per name.
    """
    return re.compile(r"^\t(?!//)[^\t].*\b" + re.escape(method) + r"\s*\(")


def declared_signatures(body: list[str], method: str) -> list[str]:
    """Signature lines for `method` declared directly on the decompiled type.

    A type member sits at one tab of indentation; anything deeper is a nested
    type's member or a local function, neither of which `AccessTools`
    .DeclaredMethod would return.
    """
    pattern = declaration_pattern(method)
    return [line.strip() for line in body
            if pattern.match(line) and not line.strip().startswith("[")]


MODIFIERS = ("params", "this", "in", "out", "ref")


def parameter_types(signature: str) -> list[str]:
    entries = argument_list(signature)
    if entries is None:
        return []
    types = []
    for entry in entries:
        declaration = without_default(entry)
        if not declaration:
            continue
        # Drop the parameter name, keep the (possibly `ref`/`out`) type. The
        # type itself may hold spaces (`Dictionary<string, ItemClass>`), so
        # only the trailing identifier is removed.
        words = declaration.split()
        if len(words) >= 2:
            words = words[:-1]
        while words and words[0] in MODIFIERS:
            words = words[1:]
        if not words:
            continue
        types.append(strip_namespace(" ".join(words)))
    return types


def parse_args(argv: list[str]) -> Path | None:
    """The --game-dir value, or None to take it from the environment.

    None means "not given", so the caller falls back to .local.env. A
    command line this script does not accept is a usage error (exit 2):
    silently ignoring a misspelled flag would check a game install the
    caller never named. `append` rather than the default last-wins, so two
    --game-dir values are rejected instead of one of them going unread.
    """
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game-dir", type=Path, metavar="PATH", action="append", default=None,
        help="client install to check against; the environment's SEVEN_DAYS_TO_DIE_DIR"
             " and .local.env are the default",
    )
    given = parser.parse_args(argv).game_dir
    if given and len(given) > 1:
        parser.error("--game-dir given more than once.")
    return given[0] if given else None


def main(argv: list[str]) -> int:
    requested = parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    if not (root / SOURCE_DIR).is_dir():
        print("no " + str(SOURCE_DIR) + " directory; nothing to verify")
        return 0
    targets, patch_classes = collect_targets(root / SOURCE_DIR)
    if not targets:
        print("no [HarmonyPatch] attributes under " + str(SOURCE_DIR) + "; nothing to verify")
        return 0

    # The toolchain is only demanded once there is a target to check: an
    # XML-only mod has nothing to decompile and must not be told to install
    # ilspycmd or point at a game install.
    game_dir = requested if requested is not None else local_env.game_dir(root)

    if game_dir is None:
        print("ERROR: no game directory. Set SEVEN_DAYS_TO_DIE_DIR or pass --game-dir.",
              file=sys.stderr)
        return 1

    assembly = game_dir / MANAGED_SUBDIR / ASSEMBLY_NAME
    if not assembly.is_file():
        print(f"ERROR: {assembly} not found.", file=sys.stderr)
        return 1

    ilspy_error = resolve_ilspycmd(root)
    if ilspy_error is not None:
        print("ERROR: ilspycmd not usable.", file=sys.stderr)
        print(ilspy_error, file=sys.stderr)
        return 1

    runtime_error = ensure_ilspy_runtime()
    if runtime_error is not None:
        print("ERROR: ilspycmd is installed but cannot run.", file=sys.stderr)
        print(runtime_error, file=sys.stderr)
        print("Install its target .NET runtime, or install Unity Hub with an "
              "editor SDK so this verifier can use its local fallback.",
              file=sys.stderr)
        return 1

    code, ilspy_version = probe_ilspy()
    if code == 0:
        pin_warning = ilspy_pin_warning(ilspy_version)
        if pin_warning is not None:
            print(f"WARNING  {pin_warning}", file=sys.stderr)

    print(f"ASSEMBLY  {assembly}")
    print(f"TOOL      ilspycmd {installed_ilspy_version(ilspy_version) or 'unknown'}")
    print(f"TARGETS   {len(targets)} attributes across {len(patch_classes)} patch classes")
    print()

    cache: dict[tuple[str, str], list[str]] = {}
    failures = 0

    for target in sorted(targets, key=lambda item: (item.declaring_type, item.method)):
        try:
            body = decompile(assembly, target.declaring_type, cache)
        except RuntimeError as error:
            print(f"FAIL      {target.label()} — {error}")
            failures += 1
            continue

        signatures = declared_signatures(body, target.method)
        if not signatures:
            print(f"FAIL      {target.label()} — not declared on the installed type")
            print(f"          {target.source}:{target.line} ({target.patch_class})")
            failures += 1
            continue

        if target.argument_types is not None:
            wanted = [entry.split(".")[-1] for entry in target.argument_types]
            matched = [entry for entry in signatures if parameter_types(entry) == wanted]
            if not matched:
                print(f"FAIL      {target.label()} — no overload with those argument types")
                for signature in signatures:
                    print(f"          installed: {signature}")
                failures += 1
                continue
            signatures = matched
        elif len(signatures) > 1:
            print(f"FAIL      {target.label()} — {len(signatures)} overloads, and the")
            print("          attribute names no argument types, so Harmony's")
            print("          AccessTools.DeclaredMethod raises AmbiguousMatchException")
            failures += 1
            continue

        available = parameter_names(signatures[0])
        unknown = [name for name in target.injected
                   if not name.startswith("__") and name not in available]
        if unknown:
            print(f"FAIL      {target.label()} — patch method asks for "
                  + ", ".join(unknown))
            print(f"          installed parameters: {', '.join(available) or '(none)'}")
            print(f"          {target.source}:{target.line} ({target.patch_class})")
            failures += 1
            continue

        print(f"OK        {target.label()}")
        print(f"          {signatures[0]}")

    print()
    if failures:
        print(f"FAILED    {failures} of {len(targets)} target checks")
        return 1

    print(f"PASSED    {len(targets)} targets in {len(patch_classes)} patch classes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

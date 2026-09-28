#!/usr/bin/env bash
# The scaffolder has to take a value the user typed and write it into files
# that each read their own syntax: an XML attribute, a C# string literal, a
# markdown heading, a TOML comment. A value holding a line break or a control
# character ends the line it was written on and leaves the rest of itself as
# text the reader parses, and XML 1.0 has no production at all for a control
# character, so the game cannot load the ModInfo.xml the run reported as
# written. A value holding a quote or a backslash closes the C# literal the
# console command's description is written in, and the mod's first build
# fails on the result.
#
# Both are reached by ordinary input, not by a malformed file: a display name
# typed on a phone, a name pasted out of a spreadsheet, an author whose IME
# leaves a control character behind. The config below carries a quote, a
# backslash, a tab and a line break in the display name, a C0 control in the
# author, and a purpose whose first sentence ends on an Ethiopic stop, a
# script the `.!?` rule reads as one long sentence.
#
# The config is written here rather than committed for the same reason
# ci/scaffolder-encoding.sh writes its own: an escape a value needs does not
# survive a checked-in copy of the file without becoming a line of its own.
# It lands under .scratch/ with everything else a run produces.
#
# Usage: ci/scaffolder-hostile-text.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/.scratch/anvil-hostile"
MOD_NAME="HostileText"

rm -rf "$WORK"
mkdir -p "$WORK"

# $'...', so a value can hold the characters a line cannot: \t and \n are
# the tab and the line break, \\C is one backslash, and \x01 is the C0
# control XML has no production for.
cat > "$WORK/hostile.conf" <<CONFEOF
name="$MOD_NAME"
author=\$'Иван\x01 Петров'
display_name=\$'A"B\\C\tsecond\nline'
purpose=\$'ይህ የመጀመሪያ ሐረግ ነው።The rest of the purpose, in a second sentence.'
target_dir="$WORK/mod"
hordeforge_root="$WORK/hordeforge"
csharp="yes"
assets="no"
clone="no"
CONFEOF

"$ROOT/new-mod.sh" "$WORK/hostile.conf" > "$WORK/scaffold.log" 2>&1 || {
	echo "FAIL the scaffolder died on a hostile value; see $WORK/scaffold.log" >&2
	tail -n 20 "$WORK/scaffold.log" >&2
	exit 1
}

MOD="$WORK/mod/$MOD_NAME"
[[ -d "$MOD" ]] || {
	echo "FAIL the scaffold produced no $MOD_NAME" >&2
	exit 1
}

python3 - "$MOD" "$MOD_NAME" <<'PYEOF' || exit 1
import os, re, sys, xml.etree.ElementTree as ET

mod, name = sys.argv[1], sys.argv[2]

# The display name as a reader of the config expects to find it: the tab and
# the line break are whitespace between words, so they collapse to one space
# rather than surviving as layout the target files cannot hold.
DISPLAY = 'A"B\\C second line'
# The Ethiopic full stop ends the config's purpose, so the description is
# the sentence before it and not the whole purpose.
FIRST_SENTENCE = "ይህ የመጀመሪያ ሐረግ ነው።"

FORBIDDEN_IN_XML = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\uFFFE\uFFFF]")

bad = []
def fail(line):
    bad.append(line)

try:
    root = ET.parse(os.path.join(mod, "ModInfo.xml")).getroot()
except ET.ParseError as exc:
    fail(f"ModInfo.xml: the game cannot load it: {exc}")
    root = None

if root is not None:
    values = {field.tag: (field.get("value") or "") for field in root}
    got = values.get("DisplayName", "")
    if got != DISPLAY:
        fail(f"ModInfo.xml: DisplayName is {got!r}, not {DISPLAY!r}")
    control = FORBIDDEN_IN_XML.search(got)
    if control:
        fail(f"ModInfo.xml: DisplayName holds U+{ord(control.group()):04X}, "
             f"which XML 1.0 has no production for")
    if values.get("Description") != FIRST_SENTENCE:
        fail(f"ModInfo.xml: Description is {values.get('Description')!r}, not "
             f"{FIRST_SENTENCE!r}; an Ethiopic stop ends the first sentence")
    if values.get("Author") != "Иван Петров":
        fail(f"ModInfo.xml: Author is {values.get('Author')!r}; the C0 control "
             f"in the config has to be dropped and the rest kept")

# The same display name is written into the console command's getDescription,
# which is a C# string literal. A quote or a backslash written raw closes it,
# and the mod's first build fails on the result.
console = os.path.relpath(os.path.join(mod, "src", name, f"ConsoleCmd{name}.cs"), mod)
if not os.path.exists(os.path.join(mod, console)):
    fail(f"{console}: the C# console command is missing from the scaffold")
else:
    with open(os.path.join(mod, console), encoding="utf-8") as handle:
        source = handle.read()
    wanted = 'return "A\\"B\\\\C second line settings";'
    if wanted not in source:
        fail(f"{console}: the literal is not {wanted!r}; a quote or a "
             f"backslash written raw makes the mod's first build fail")

# A value that stayed more than one line ends the heading or the comment it
# was written into, and the rest of itself reads as the next line of that
# file. The README.txt line is checked for the same reason as the other two.
for relative, prefix in (("README.md", "# "), ("README.txt", None),
                         (f"Config/{name}.toml", "# ")):
    path = os.path.join(mod, relative)
    if not os.path.exists(path):
        fail(f"{relative}: missing from the scaffold")
        continue
    with open(path, encoding="utf-8") as handle:
        first = handle.readline().rstrip("\n")
    if DISPLAY not in first:
        fail(f"{relative}: the first line is {first!r}, which does not carry "
             f"the whole display name {DISPLAY!r} on one line")
    elif prefix is not None and not first.startswith(prefix):
        fail(f"{relative}: the first line lost its {prefix!r} prefix: {first!r}")

for line in bad:
    print(f"FAIL {line}", file=sys.stderr)
if bad:
    sys.exit(1)
print("PASS the scaffolder writes a value carrying a quote, a backslash, a tab, "
      "a line break and a control character as one line of valid XML and valid "
      "C#, and ends a description on a non-Latin sentence stop")
PYEOF

rm -rf "$WORK"

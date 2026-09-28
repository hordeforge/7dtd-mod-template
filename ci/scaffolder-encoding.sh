#!/usr/bin/env bash
# The scaffolder must survive a config file that is not UTF-8.
#
# A shell variable is a byte string and `os.environ` decodes one that is not
# UTF-8 with `surrogateescape`, so a `newmod.conf` whose author is a latin-1
# "José" (any editor still saving that encoding) reached new-mod.sh's
# substitution pass as 'Jos<udce9>'. Every write there is `encoding="utf-8"`,
# so the token raised UnicodeEncodeError and the scaffolder died with a
# traceback and no mod, over a name the user had typed.
#
# The config is written here rather than committed because the point is a byte
# that is not valid UTF-8: a checked-in copy of it is unreadable in half the
# editors that open this repo. It lands under .scratch/ with everything else a
# run produces.
#
# Usage: ci/scaffolder-encoding.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/.scratch/anvil-encoding"
MOD_NAME="EncodingSmoke"

rm -rf "$WORK"
mkdir -p "$WORK"

CONF="$WORK/encoding.conf"
# printf with a \xe9, so the author line is latin-1 whatever the caller's
# locale is. Everything else stays ASCII.
{
	printf 'name="%s"\n' "$MOD_NAME"
	printf 'author="Jos\xe9"\n'
	printf 'display_name="Caf\xe9 Smoke"\n'
	printf 'purpose="A caf\xe9 mod whose author line is latin-1, not UTF-8."\n'
	printf 'target_dir="%s"\n' "$WORK/mod"
	printf 'hordeforge_root="%s/hordeforge"\n' "$WORK"
	printf 'csharp="no"\n'
	printf 'assets="no"\n'
	printf 'clone="no"\n'
} > "$CONF"

"$ROOT/new-mod.sh" "$CONF" > "$WORK/scaffold.log" 2>&1 || {
	echo "FAIL the scaffolder died on a non-UTF-8 config; see $WORK/scaffold.log" >&2
	tail -n 20 "$WORK/scaffold.log" >&2
	exit 1
}

MOD="$WORK/mod/$MOD_NAME"
[[ -d "$MOD" ]] || {
	echo "FAIL the scaffold produced no $MOD_NAME" >&2
	exit 1
}

python3 - "$MOD" "$MOD_NAME" <<'PYEOF' || exit 1
import sys, unicodedata, xml.etree.ElementTree as ET
mod, name = sys.argv[1], sys.argv[2]

# Every file the substitution pass wrote has to be valid UTF-8 now. Reading it
# back is the check: a lone surrogate can only reach a file by a writer that
# never decoded it, and reading is where that shows up.
bad = []
for relative in ("README.md", "ModInfo.xml", "README.txt", "docs/design.md"):
    try:
        with open(f"{mod}/{relative}", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        bad.append(f"{relative}: {exc}")
        continue
    if any(unicodedata.category(c) == "Cs" for c in text):
        bad.append(f"{relative}: holds a lone surrogate")

# The substituted values came through, with each undecodable byte shown as the
# replacement character rather than dropped: a scaffold that silently lost the
# author's name would be a different failure.
fields = {tag: (node.get("value") or "")
          for node in ET.parse(f"{mod}/ModInfo.xml").getroot()
          for tag in (node.tag,)}
if not fields.get("Author", "").startswith("Jos"):
    bad.append(f'ModInfo.xml: Author is {fields.get("Author")!r}, not the name given')
if not fields.get("Description", "").startswith("A caf"):
    bad.append(f'ModInfo.xml: Description is {fields.get("Description")!r}, not the purpose given')
if "\ufffd" not in fields.get("Author", ""):
    bad.append("ModInfo.xml: the undecodable byte was dropped instead of replaced")

if bad:
    for line in bad:
        print(f"FAIL {line}", file=sys.stderr)
    sys.exit(1)
print("PASS the scaffolder substitutes a non-UTF-8 config as valid UTF-8")
PYEOF

rm -rf "$WORK"

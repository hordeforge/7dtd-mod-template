#!/usr/bin/env bash
# Scaffold a new 7DTD mod from template/ — the full setup in one run.
#
# Usage: ./new-mod.sh <config-file>
#        ./new-mod.sh --help
#
# The config file is always an argument, never a hardcoded name, so several
# configs can coexist. Format: shell key=value (see newmod.conf.example).
# Missing required keys are prompted for on a tty; non-interactive runs
# fail on them instead.
#
# One run: resolves/clones the hordeforge tool checkouts, creates the mod
# directory with every placeholder substituted, seeds the mod's purpose
# into README/design/TODO, writes the machine-local .local.env, and makes
# the initial git commit.
#
# Exit status: 0 the mod was scaffolded, 1 a step failed part way (its own
# exit status), 2 the command line or the config file was wrong.
set -euo pipefail

ANVIL="$(cd "$(dirname "$0")" && pwd)"
SELF="${0##*/}"
# What the run wants to tell the user but could not do. A warning printed
# mid-run is a line that scrolls off the terminal while the run works on, and
# the run still ends in "OK", so every warning is kept and repeated in the
# closing summary, next to what the mod was actually built with.
WARNINGS=()
warn() { # warn <message>
	WARNINGS+=("$1")
	printf 'WARN: %s\n' "$1" >&2
}
# A next step the run cannot take for the user, recorded for the same reason.
NOTES=()
note() { # note <message>
	NOTES+=("$1")
}

usage() {
	cat <<USAGE
usage: $SELF <config-file>

Scaffold a new 7 Days To Die mod from template/.

arguments:
  <config-file>  shell key=value config, see newmod.conf.example. Missing
                 required keys are prompted for on a tty and fail the run
                 without one. A prompt is asked again until the answer is
                 usable, and the re-ask says what a usable answer looks like.

options:
  -h, --help     show this help and exit

exit status:
  0  the mod was scaffolded
  1  a step failed part way (that step's own exit status)
  2  wrong arguments, or the config file is missing or invalid
USAGE
}

case "${1:-}" in
-h | --help)
	usage
	exit 0
	;;
esac

if (($# != 1)); then
	usage >&2
	exit 2
fi
CONF="$1"
[[ -f "$CONF" ]] || {
	echo "ERROR: config file not found: $CONF" >&2
	echo "       see newmod.conf.example, or run '$SELF --help'." >&2
	exit 2
}

# defaults, then the config overrides
name="" display_name="" author="" purpose="" target_dir=""
hordeforge_root="" csharp="no" assets="no" clone="yes"
game_dir="" server_dir="" unity_editor=""
# Every key this scaffolder reads. The config is sourced, so a key that is
# misspelled is not an error anywhere: it would set a variable nothing reads
# and the run would quietly take the default for it.
REQUIRED_KEYS="name author purpose target_dir"
OPTIONAL_KEYS="display_name hordeforge_root csharp assets clone game_dir server_dir unity_editor"
KNOWN_KEYS="$REQUIRED_KEYS $OPTIONAL_KEYS"
# LC_ALL=C, because this is the one pass in the run that reads bytes the user
# typed rather than bytes this repo wrote. Under a UTF-8 locale a
# multibyte-aware match cannot find a character boundary in a config value
# that is not UTF-8 (a latin-1 "Jos<e9>"), and prints the key back with that
# byte and the rest of the line glued to it: the run then died on `unknown key
# 'author<e9>"'`, naming a key nobody wrote. In the C locale the same match is
# byte-wise, the key comes out clean, and the value is left for the
# substitution pass to decode on purpose. Each key is reported with the line
# it came from, so a typo in a long config is one number away.
while IFS=$'\t' read -r conf_line conf_key; do
	[[ -z "$conf_key" ]] && continue
	case " $KNOWN_KEYS " in
		*" $conf_key "*) ;;
		*)
			echo "ERROR: unknown key '$conf_key' on line $conf_line of $CONF." >&2
			echo "       required: $REQUIRED_KEYS" >&2
			echo "       optional: $OPTIONAL_KEYS" >&2
			exit 2
			;;
	esac
done < <(LC_ALL=C awk '
	match($0, /^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=/) {
		key = $0
		sub(/^[[:space:]]*(export[[:space:]]+)?/, "", key)
		sub(/=.*$/, "", key)
		printf "%d\t%s\n", NR, key
	}' "$CONF")
# shellcheck disable=SC1090
source "$CONF"

# A yes/no key with any other value takes the else branch and scaffolds a mod
# that is quietly missing a feature, or a server that is never installed.
for flag in csharp assets clone; do
	case "${!flag}" in
		yes|no) ;;
		*)
			echo "ERROR: $flag must be 'yes' or 'no' in $CONF, got '${!flag}'." >&2
			exit 2
			;;
	esac
done

ask() { # ask <varname> <prompt> [problem]
	local var="$1" prompt="$2" problem="${3:-}" value
	value="${!var}"
	if [[ -z "$value" ]]; then
		if [[ -t 0 ]]; then
			# a closed stdin is a half-answered form, not an empty answer: it
			# exits 2 with what was still missing rather than looping or dying
			# on the read's status
			if ! read -r -p "$prompt: " value; then
				echo >&2
				echo "ERROR: no answer read for '$var'; nothing was written." >&2
				exit 2
			fi
			printf -v "$var" '%s' "$value"
		else
			# the same shape of answer the interactive re-ask spells out, so a
			# CI log names what the key owes instead of only that it is absent
			echo "ERROR: '$var' missing in $CONF and not running interactively." >&2
			[[ -n "$problem" ]] && echo "       $problem" >&2
			exit 2
		fi
	fi
}

# ask_checked <varname> <prompt> <check> <problem> [default]
# One bad answer used to end the run, before anything was written, with a
# message that named the rule but not the shape of a good answer. On a tty the
# question is asked again with that shape spelled out; an answer that came from
# the config file is the user's own text to fix, so it stays a hard error naming
# the key. A [default] stands in for an empty typed answer.
ask_checked() {
	local var="$1" prompt="$2" check="$3" problem="$4" default="${5:-}"
	local from_config=1
	[[ -z "${!var}" ]] && from_config=0
	while :; do
		ask "$var" "$prompt" "$problem"
		if [[ -z "${!var}" && -n "$default" ]]; then
			printf -v "$var" '%s' "$default"
		fi
		"$check" "${!var}" && return 0
		if ((from_config)); then
			echo "ERROR: $var in $CONF: $problem" >&2
			exit 2
		fi
		if [[ -n "${!var}" ]]; then
			printf "       rejected: %s\n" "${!var}" >&2
			fi
			echo "       $problem" >&2
		printf -v "$var" '%s' ''
	done
}

is_mod_name() { [[ $1 =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; }
is_filled() { [[ -n "$1" ]]; }

ask_checked name "Mod name (modlet id, e.g. MyMod)" is_mod_name \
	"a mod name starts with a letter and holds only letters, digits and underscores (it is the modlet id and the folder name), e.g. MyMod"
[[ -z "$display_name" ]] && display_name="$name"
ask_checked author "Author" is_filled \
	"an author is required: it names the mod's author field and its initial commit"
ask_checked purpose "Purpose (a sentence or paragraph: what this mod is for)" is_filled \
	"a purpose is required: it is seeded into the mod's README, design notes and TODO"
ask_checked target_dir "Directory to create the mod in (empty for the current directory, $PWD)" is_filled \
	"a target directory is required: the mod is created as <target_dir>/<name>" "$PWD"
target_dir="${target_dir/#\~/$HOME}"
MOD_FINAL="$target_dir/$name"
if [[ -e "$MOD_FINAL" ]]; then
	echo "ERROR: $MOD_FINAL already exists." >&2
	echo "       pick a different target_dir in $CONF, or move the existing one aside." >&2
	exit 2
fi

# The scaffold is built in a staging directory beside the target and moved
# into place as the last step, so an interrupted run (a full disk, a Ctrl-C,
# a failing git commit) leaves no half-written mod behind. A partial mod dir
# is worse than no mod dir: every later run refuses a target that exists, so
# one interrupted run would need a hand-rolled cleanup before any rerun could
# work at all.
mkdir -p "$target_dir"
STAGE="$(mktemp -d "$target_dir/.anvil-stage-XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT INT TERM HUP
# mktemp creates 0700; a mod dir is ordinary content and must not inherit it.
chmod 0755 "$STAGE"
# Every step below builds here; the last step is the move into MOD_FINAL.
MOD_DIR="$STAGE/$name"

# --- hordeforge tool checkouts -------------------------------------------
if [[ -z "$hordeforge_root" ]]; then
	ask_checked hordeforge_root "Directory holding (or to hold) the hordeforge tool checkouts" is_filled \
		"a hordeforge_root is required: it is the parent directory of the tool checkouts" "$PWD"
fi
hordeforge_root="${hordeforge_root/#\~/$HOME}"

if [[ "$clone" == "yes" ]]; then
	mkdir -p "$hordeforge_root"
	for repo in 7dtd-playtest 7dtd-asset-pipeline 7dtd-engine-research; do
		if [[ -d "$hordeforge_root/$repo" ]]; then
			echo "Found $repo."
		elif command -v gh >/dev/null 2>&1; then
			echo "Cloning hordeforge/$repo ..."
			gh repo clone "hordeforge/$repo" "$hordeforge_root/$repo" -- --quiet ||
				warn "could not clone $repo into $hordeforge_root/$repo; clone it later"
		else
			git clone --quiet "https://github.com/hordeforge/$repo" "$hordeforge_root/$repo" ||
				warn "could not clone $repo into $hordeforge_root/$repo; clone it later"
		fi
	done
fi

# --- game install (for .local.env) ---------------------------------------
if [[ -z "$game_dir" ]]; then
	default_install="$HOME/.local/share/Steam/steamapps/common/7 Days To Die"
	if [[ -f "$default_install/Data/Config/items.xml" ]]; then
		game_dir="$default_install"
		echo "Detected game install: $game_dir"
	elif [[ -t 0 ]]; then
		# ask, not a bare read: a closed stdin here used to end the run under
		# set -e with no message at all, after four answers the user had given
		# and before anything was written.
		ask game_dir "7 Days To Die client install dir (empty to configure later)"
	fi
fi
# Every path the config may carry, expanded the same way before anything
# reads it: a literal "~" written into .local.env is a directory that does not
# exist, and the failure surfaces later as a missing DLL, not as a bad path.
game_dir="${game_dir/#\~/$HOME}"
server_dir="${server_dir/#\~/$HOME}"
unity_editor="${unity_editor/#\~/$HOME}"
if [[ -n "$game_dir" && ! -f "$game_dir/Data/Config/items.xml" ]]; then
	warn "$game_dir has no Data/Config/items.xml; recorded in .local.env anyway, fix it before make build"
fi

# --- create the mod directory --------------------------------------------
mkdir -p "$MOD_DIR"
cp -R "$ANVIL/template/." "$MOD_DIR/"
# A plain copy ignores .gitignore, so a developer's own build output in the
# template tree (a stale __pycache__ from running the gates, a leftover dist/,
# the .ruff_cache ruff writes when the gate runs here) would ship inside the
# new mod. None of it is source. The names are the gitignore rules of
# template/ and this repo, so a cache the gates can create is one this drops.
find "$MOD_DIR" \( -name '__pycache__' -o -name '*.pyc' -o -name 'dist' \
	-o -name '.ruff_cache' -o -name '.shamway' -o -name '.local' \) \
	-prune -exec rm -rf {} +
mkdir -p "$MOD_DIR/docs/reference"
cp -R "$ANVIL/docs/." "$MOD_DIR/docs/reference/"

if [[ "$csharp" == "yes" ]]; then
	mv "$MOD_DIR/src/__MOD_NAME__/__MOD_NAME__.csproj" "$MOD_DIR/src/__MOD_NAME__/$name.csproj"
	mv "$MOD_DIR/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs" "$MOD_DIR/src/__MOD_NAME__/ConsoleCmd$name.cs"
	mv "$MOD_DIR/src/__MOD_NAME__" "$MOD_DIR/src/$name"
	mv "$MOD_DIR/Config/__MOD_NAME__.toml" "$MOD_DIR/Config/$name.toml"
	skip_eac="true"
else
	rm -rf "$MOD_DIR/src"
	# no DLL, so nothing reads the TOML settings file or its contract gate
	rm -f "$MOD_DIR/Config/__MOD_NAME__.toml" "$MOD_DIR/scripts/test_settings_reload.py"
	skip_eac="false"
fi
if [[ "$assets" == "yes" ]]; then
	mkdir -p "$MOD_DIR/assets-src"
	note "run 'shamway init' in the mod to set up the asset pipeline (.shamway.toml + its AGENTS contract)"
fi

# The optional-feature blocks this template marks (the shamway targets and the
# prose that tells an agent to run them, the C# settings contract) are stripped
# in the same python pass as the token substitution: `sed -i` is GNU-only, and
# BSD sed (macOS) demands a backup-suffix argument, taking the scaffolder down
# on any non-GNU host. The markers always go; the block between them only when
# the feature it documents is off.
export ANVIL_NAME="$name" ANVIL_DISPLAY="$display_name" ANVIL_AUTHOR="$author" \
	ANVIL_PURPOSE="$purpose" ANVIL_SKIP_EAC="$skip_eac" \
	ANVIL_CSHARP="$csharp" ANVIL_ASSETS="$assets"
python3 - "$MOD_DIR" <<'PYEOF'
import datetime, html, os, re, sys, unicodedata
import xml.etree.ElementTree as ET
mod_dir = sys.argv[1]

def from_shell(name):
    """A value the shell exported, as text this program can write back out.

    A shell variable is a byte string, and `os.environ` decodes one that is
    not UTF-8 with `surrogateescape`, so a `newmod.conf` holding `author=Jos<e9>`
    in latin-1 (any editor still saving that encoding) arrived here as
    'Jos<udce9>'. Every write below is `encoding="utf-8"`, so the substituted
    token raised UnicodeEncodeError out of the scaffolder with a traceback and
    no mod, over a name the user had typed.

    The bytes go back through `surrogateescape` and are then decoded as UTF-8
    with `replace`: text that was already UTF-8 comes back unchanged, and a
    byte that is not becomes U+FFFD, which is a substitution a reader can see
    rather than a crash. The modlet is never handed a lone surrogate.
    """
    raw = os.environ[name]
    return raw.encode("utf-8", "surrogateescape").decode("utf-8", "replace")

purpose = from_shell("ANVIL_PURPOSE").strip()

# Characters that draw nothing and, worse, reorder what sits around them: the
# bidi overrides and isolates, the soft hyphen, the zero-width space, the word
# joiner, the BOM, and any control character. A display name or an author
# carrying one is a second string that reads as the first, and those two
# fields are how a player tells one mod from another, so the run stops rather
# than seed a look-alike into the mod browser. The zero-width joiner and
# non-joiner are not in this set: they are how an emoji sequence and a
# Persian word are written, and they attach to a neighbouring character
# rather than reorder the line.
INVISIBLE = frozenset(
    "\u00ad\u200b\u2060\ufeff"
    "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069")

def readable(label, text):
    """`text` as the config reader saw it, or exit 2 naming what is in it.

    Exit 2 is the config's own status: a name carrying a character that draws
    nothing is a value the user has to fix, not a step that failed part way.
    """
    found = sorted({char for char in text
                    if char in INVISIBLE or unicodedata.category(char) == "Cc"})
    if found:
        listed = ", ".join("U+%04X" % ord(char) for char in found)
        print("ERROR: %s in the config holds a character that draws nothing: %s."
              % (label, listed), file=sys.stderr)
        print("       A mod name that is not the name a player reads is not this mod's name.",
              file=sys.stderr)
        raise SystemExit(2)
    return text

display = readable("display_name", from_shell("ANVIL_DISPLAY"))
the_author = readable("author", from_shell("ANVIL_AUTHOR"))
purpose = readable("purpose", purpose)
# ModInfo.xml is the mod's single source of truth for its version: the game
# reads that field and nothing else, and the release readme's first line has
# to name the same version. Reading it here keeps the two in step at scaffold
# time; the static-check gate keeps them in step afterwards.
version = ""
for field in ET.parse(os.path.join(mod_dir, "ModInfo.xml")).getroot():
    if field.tag == "Version":
        version = (field.get("value") or "").strip()
if not version:
    sys.exit("ERROR: ModInfo.xml has no Version value; the mod's version is undeclared.")

ZWJ = "\u200d"
# A code point that can only follow another one: a zero-width joiner or space,
# a BOM, a variation selector, an emoji skin-tone modifier, or a mark in any
# script (a combining accent, a Devanagari matra, a Thai vowel sign, a
# keycap's enclosing mark). Cutting the description between one of these and
# the character it belongs to leaves it stranded, and ModInfo.xml's
# Description is rendered by the game, so the truncation has to end on a whole
# character.
#
# The mark test is the Unicode property, not a list of ranges: a list of
# combining marks needs an entry per script, and every script left out of it
# truncates mid-word. Marks are the Mn, Mc and Me categories, and the ranges
# below are the non-marks that attach the same way.
ATTACHING = re.compile("[\u200d\u200c\ufeff\ufe00-\ufe0f\ufe20-\ufe2f"
                       "\U0001f3fb-\U0001f3ff]")
REGIONAL_INDICATOR = (0x1F1E6, 0x1F1FF)

def attaches(char):
    """Whether `char` belongs to the character before it, not after it."""
    if ATTACHING.match(char):
        return True
    return unicodedata.category(char) in ("Mn", "Mc", "Me")

def ends_mid_cluster(text):
    """Whether `text` stops inside a character, so a cut there strands half of one.

    Three ways a fixed code-point limit lands inside one: on a mark, on the
    base of a ZWJ sequence whose joiner is already behind it, and on the
    first of a flag's two regional indicators.
    """
    if not text:
        return False
    if attaches(text[-1]):
        return True
    if len(text) > 1 and text[-2] == ZWJ:
        return True
    run = 0
    for char in reversed(text):
        if REGIONAL_INDICATOR[0] <= ord(char) <= REGIONAL_INDICATOR[1]:
            run += 1
        else:
            break
    return run % 2 == 1

def to_clusters(text, limit):
    """`text` cut to at most `limit` code points, ending on a whole character."""
    cut = text[:limit]
    while cut and ends_mid_cluster(cut):
        cut = cut[:-1]
    return cut

# Where a sentence ends, per script. A Latin sentence closes on `.`, `!` or
# `?` and writes whitespace or nothing after it; a CJK, Devanagari, Khmer,
# Mongolian, Ethiopic, Burmese or Tibetan one closes on its own stop
# character and writes nothing after it at all, so an ASCII-only rule reads
# a Japanese purpose as one long sentence and leaves the mod browser's
# description holding two of them, cut mid-phrase.
ASCII_STOP = ".!?"
OTHER_STOP = "。！？．｡؟۔।॥።᠃᠉။ႁႂႃႄႅႆႇႈႉႊႋႌႍႎႏ។៕៿"


def first_sentence(text):
    """`text` up to its first sentence end, or all of it when it has none.

    A stop is not an end where a digit (`v1.2`) or a lone capital (the `J.` of
    an initial) ends the word before it, and an ASCII stop is one only where
    whitespace or the end of the text follows it. The unit is the last word,
    not the whole prefix: `J` alone in "A mod about J. R. R. Tolkien" is an
    initial, while a single-character *prefix* is only the first word of the
    purpose, so measuring the prefix cut the description at the first
    middle initial and left the browser showing "A mod about J.".
    """
    for index, char in enumerate(text):
        if char not in ASCII_STOP + OTHER_STOP:
            continue
        if char in ASCII_STOP and index + 1 < len(text) and not text[index + 1].isspace():
            continue
        words = text[:index].split()
        if words and char in ASCII_STOP:
            # The last character, not the whole word: `v1.2` ends the word in
            # a digit while the word itself is `v1`, and a plain isdigit() on
            # it never fires.
            word = words[-1]
            if word[-1].isdigit() or (word.isupper() and len(word) == 1):
                continue
        return text[:index + 1]
    return text

# The description is the mod browser's one line: 200 code points, whatever
# the script, not bytes and not grapheme clusters, and the cut lands on a
# whole character in that script.
DESCRIPTION_LIMIT = 200
short = to_clusters(first_sentence(purpose), DESCRIPTION_LIMIT)

# The author token names the Harmony id, a lowercase ASCII string. Decomposing
# first turns an accented name into its base letters, so Müller and its
# decomposed spelling both reduce to muller rather than mller. Folding rather
# than lowering is what keeps one author's name from reaching another's id:
# lower() maps a German ß to nothing, so "Weiß" and "Wei" both reduced to
# "wei", and two different authors were given one Harmony id.
author_id = re.sub(r"[^a-z0-9]", "",
                   unicodedata.normalize("NFKD", the_author).casefold())
tokens = {
    "__MOD_NAME__": from_shell("ANVIL_NAME"),
    "__MOD_NAME_LOWER__": from_shell("ANVIL_NAME").lower(),
    "__MOD_DISPLAY_NAME__": display,
    "__MOD_AUTHOR__": the_author,
    "__MOD_AUTHOR_LOWER__": author_id or "author",
    "__MOD_PURPOSE__": purpose,
    "__MOD_PURPOSE_SHORT__": short,
    "__MOD_VERSION__": version,
    # The date this mod's first release section carries. A changelog entry
    # with no date is a version a reader cannot place in time, and the one
    # every mod starts with is the one a mod author copies when they cut
    # their next release.
    "__MOD_RELEASE_DATE__": datetime.date.today().isoformat(),
    "__SKIP_WITH_ANTI_CHEAT__": from_shell("ANVIL_SKIP_EAC"),
}
xml_tokens = {token: html.escape(value, quote=True)
              for token, value in tokens.items()}

CSHARP = ("<!-- ANVIL:CSHARP-BEGIN -->", "<!-- ANVIL:CSHARP-END -->")
ASSETS_MAKE = ("# ANVIL:ASSETS-BEGIN", "# ANVIL:ASSETS-END")
ASSETS_HTML = ("<!-- ANVIL:ASSETS-BEGIN -->", "<!-- ANVIL:ASSETS-END -->")
# file -> {marker pair: the feature it documents}. A block whose feature is off
# loses everything between the markers, so neither the Makefile nor the prose
# names a target that is gone; the two marker lines go either way. A pair may
# appear more than once in one file: the Makefile marks the asset help text
# and the asset .PHONY line separately.
marked = {
    "Makefile": {ASSETS_MAKE: "assets"},
    "README.md": {CSHARP: "csharp"},
    "AGENTS.md": {CSHARP: "csharp", ASSETS_HTML: "assets"},
}

def strip_marked(text, blocks):
    """Take the marker lines out of `text`, and a block whose feature is off.

    One pass over the lines, whatever the blocks: a marker opens a block and
    the next marker of the same pair closes it, and a block never closed runs
    to the end of the file. A block whose feature is on is entered too, and
    only its content kept, or its closing marker would survive into the mod.
    Both are whole-line matches, so a marker inside a paragraph of prose is
    not one.
    """
    drop_when_off = {markers[0]: os.environ["ANVIL_" + feature.upper()] != "yes"
                     for markers, feature in blocks.items()}
    closers = {markers[1] for markers in blocks}
    kept, inside, dropping = [], False, False
    for line in text.splitlines(keepends=True):
        marker = line.strip()
        if not inside and marker in drop_when_off:
            inside, dropping = True, drop_when_off[marker]
        elif inside and marker in closers:
            inside = dropping = False
        elif not inside or not dropping:
            kept.append(line)
    return "".join(kept)

for base, dirs, files in os.walk(mod_dir):
    dirs[:] = [d for d in dirs if d != ".git"]
    for f in files:
        path = os.path.join(base, f)
        try:
            # newline="" on both ends: a CRLF source file must survive the
            # round trip byte for byte, and an LF file must not be rewritten
            # to CRLF by a Windows scaffolder.
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (UnicodeDecodeError, OSError):
            continue
        out = strip_marked(text, marked[f]) if base == mod_dir and f in marked else text
        # ModInfo.xml is the one file here whose values land in an XML
        # attribute, where a bare `&`, `<` or `"` ends the attribute and
        # leaves the file the game cannot parse. Every other consumer (a C#
        # string, a markdown file) takes the text as it stands, so escaping
        # belongs to that one file, applied to every value alike.
        here = xml_tokens if base == mod_dir and f == "ModInfo.xml" else tokens
        for token, value in here.items():
            out = out.replace(token, value)
        if out != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(out)
PYEOF

# --- machine-local .local.env --------------------------------------------
# per-repo roots are always derived from hordeforge_root, cloned yet or not
for repo_var in PLAYTEST_ROOT:7dtd-playtest CONNECT_ROOT:7dtd-fastconnect ASSET_PIPELINE_ROOT:7dtd-asset-pipeline; do
	printf -v "${repo_var%%:*}" '%s' "$hordeforge_root/${repo_var#*:}"
done
# The targets source this file, so a value carrying a quote, a dollar or a
# backtick would be re-interpreted as shell rather than read back as the path
# the user gave.
local_env_value() { # local_env_value <value>
	local v="$1"
	v="${v//\\/\\\\}"
	v="${v//\"/\\\"}"
	v="${v//\$/\\\$}"
	v="${v//\`/\\\`}"
	printf '%s' "$v"
}
cat > "$MOD_DIR/.local.env" <<LOCALEOF
# Machine-local path inventory (never commit; format: .local.env.example).
SEVEN_DAYS_TO_DIE_DIR="$(local_env_value "$game_dir")"
SEVEN_DAYS_TO_DIE_SERVER_DIR="$(local_env_value "$server_dir")"
HORDEFORGE_ROOT="$(local_env_value "$hordeforge_root")"
PLAYTEST_ROOT="$(local_env_value "$PLAYTEST_ROOT")"
CONNECT_ROOT="$(local_env_value "$CONNECT_ROOT")"
ASSET_PIPELINE_ROOT="$(local_env_value "$ASSET_PIPELINE_ROOT")"
DOTNET_ROOT=""
ILSPYCMD="$(local_env_value "$(command -v ilspycmd || true)")"
UNITY_EDITOR="$(local_env_value "$unity_editor")"
LOCALEOF
# 0600: the file names this account's home and install directories, which the
# default 0644 would leave readable by every other account on the machine.
chmod 600 "$MOD_DIR/.local.env"

# --- git ------------------------------------------------------------------
git -C "$MOD_DIR" init -q -b main
if ! git -C "$MOD_DIR" config user.email >/dev/null; then
	# no global identity on this machine; a repo-local one keeps the
	# initial commit from failing
	git -C "$MOD_DIR" config user.name "$author"
	git -C "$MOD_DIR" config user.email "$author@users.noreply.github.com"
fi
git -C "$MOD_DIR" add -A
git -C "$MOD_DIR" commit -q -m "Scaffold $name from hordeforge/7dtd-mod-template"

# The mod exists at its real path only now, and whole. The stage directory is
# left to the EXIT trap.
mv "$MOD_DIR" "$MOD_FINAL"

echo
echo "OK -> $MOD_FINAL"
# What the run decided, in the terms the config file uses for it. A first-time
# user who left csharp and assets empty has a mod with no DLL and no asset
# targets, and the only other place that shows up is the absence of files.
printf '  mod          %s ("%s")\n' "$name" "$display_name"
printf '  csharp       %s\n' "$csharp"
printf '  assets       %s\n' "$assets"
printf '  tool repos   %s (clone=%s)\n' "$hordeforge_root" "$clone"
printf '  game dir     %s\n' "${game_dir:-(not set: make build and the install-dependent gates need it in .local.env)}"
if ((${#WARNINGS[@]})); then
	echo "Warnings:"
	for warning in "${WARNINGS[@]}"; do
		printf '  WARN: %s\n' "$warning"
	done
fi
if ((${#NOTES[@]})); then
	echo "Next steps:"
	for next_step in "${NOTES[@]}"; do
		printf '  NOTE: %s\n' "$next_step"
	done
fi
printf 'Next: cd %q && make test && make lint-shell && make lint-py\n' "$MOD_FINAL"
echo "      (make help lists every target; make build needs the game install in .local.env)"
echo "Start with TODO.md (the purpose is seeded there); AGENTS.md has the working rules."

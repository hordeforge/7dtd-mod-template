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

usage() {
	cat <<USAGE
usage: $SELF <config-file>

Scaffold a new 7 Days To Die mod from template/.

arguments:
  <config-file>  shell key=value config, see newmod.conf.example. Missing
                 required keys are prompted for on a tty and fail the run
                 without one.

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
KNOWN_KEYS="name display_name author purpose target_dir hordeforge_root csharp assets clone game_dir server_dir unity_editor"
while read -r conf_key; do
	[[ -z "$conf_key" ]] && continue
	case " $KNOWN_KEYS " in
		*" $conf_key "*) ;;
		*)
			echo "ERROR: unknown key '$conf_key' in $CONF; known keys: $KNOWN_KEYS" >&2
			exit 2
			;;
	esac
done < <(sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' "$CONF")
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

ask() { # ask <varname> <prompt>
	local var="$1" prompt="$2" value
	value="${!var}"
	if [[ -z "$value" ]]; then
		if [[ -t 0 ]]; then
			read -r -p "$prompt: " value
			printf -v "$var" '%s' "$value"
		else
			echo "ERROR: '$var' missing in $CONF and not running interactively." >&2
			exit 2
		fi
	fi
}

ask name "Mod name (modlet id, e.g. MyMod)"
[[ "$name" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]] || { echo "ERROR: name must be alphanumeric (ModInfo Name = folder name)." >&2; exit 2; }
[[ -z "$display_name" ]] && display_name="$name"
ask author "Author"
ask purpose "Purpose (what this mod is for — a sentence or paragraph)"
ask target_dir "Directory to create the mod in"
target_dir="${target_dir/#\~/$HOME}"
MOD_FINAL="$target_dir/$name"
[[ -e "$MOD_FINAL" ]] && { echo "ERROR: $MOD_FINAL already exists." >&2; exit 2; }

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
	ask hordeforge_root "Directory holding (or to hold) the hordeforge tool checkouts"
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
				echo "WARN: could not clone $repo; clone it later." >&2
		else
			git clone --quiet "https://github.com/hordeforge/$repo" "$hordeforge_root/$repo" ||
				echo "WARN: could not clone $repo; clone it later." >&2
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
		read -r -p "7 Days To Die client install dir (empty to configure later): " game_dir
	fi
fi
# Every path the config may carry, expanded the same way before anything
# reads it: a literal "~" written into .local.env is a directory that does not
# exist, and the failure surfaces later as a missing DLL, not as a bad path.
game_dir="${game_dir/#\~/$HOME}"
server_dir="${server_dir/#\~/$HOME}"
unity_editor="${unity_editor/#\~/$HOME}"
if [[ -n "$game_dir" && ! -f "$game_dir/Data/Config/items.xml" ]]; then
	echo "WARN: $game_dir has no Data/Config/items.xml; recorded anyway — fix .local.env before building." >&2
fi

# --- create the mod directory --------------------------------------------
mkdir -p "$MOD_DIR"
cp -R "$ANVIL/template/." "$MOD_DIR/"
# A plain copy ignores .gitignore, so a developer's own build output in the
# template tree (a stale __pycache__ from running the gates, a leftover dist/)
# would ship inside the new mod. None of it is source.
find "$MOD_DIR" \( -name '__pycache__' -o -name '*.pyc' -o -name 'dist' \) \
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
	echo "NOTE: run 'shamway init' in the mod to set up the asset pipeline (.shamway.toml + its AGENTS contract)."
else
	# strip the shamway targets from the Makefile, and the prose that tells an
	# agent to run them from the docs, so neither names a target that is gone
	sed -i '/^# ANVIL:ASSETS-BEGIN$/,/^# ANVIL:ASSETS-END$/d' "$MOD_DIR/Makefile"
	sed -i '/<!-- ANVIL:ASSETS-BEGIN -->/,/<!-- ANVIL:ASSETS-END -->/d' \
		"$MOD_DIR/README.md" "$MOD_DIR/AGENTS.md"
fi

# The optional-feature blocks this template marks go in the same python pass
# as the token substitution below: `sed -i` is GNU-only, and BSD sed (macOS)
# demands a backup-suffix argument, taking the scaffolder down on any non-GNU
# host. The markers always go; the block between them only when the feature it
# documents is off.
export ANVIL_NAME="$name" ANVIL_DISPLAY="$display_name" ANVIL_AUTHOR="$author" \
	ANVIL_PURPOSE="$purpose" ANVIL_SKIP_EAC="$skip_eac" \
	ANVIL_CSHARP="$csharp" ANVIL_ASSETS="$assets"
python3 - "$MOD_DIR" <<'PYEOF'
import html, os, re, sys
import xml.etree.ElementTree as ET
mod_dir = sys.argv[1]
purpose = os.environ["ANVIL_PURPOSE"].strip()
short = re.split(r"(?<=[.!?])\s", purpose)[0][:200]
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
tokens = {
    "__MOD_NAME__": os.environ["ANVIL_NAME"],
    "__MOD_NAME_LOWER__": os.environ["ANVIL_NAME"].lower(),
    "__MOD_DISPLAY_NAME__": os.environ["ANVIL_DISPLAY"],
    "__MOD_AUTHOR__": os.environ["ANVIL_AUTHOR"],
    "__MOD_AUTHOR_LOWER__": re.sub(r"[^a-z0-9]", "", os.environ["ANVIL_AUTHOR"].lower()) or "author",
    "__MOD_PURPOSE__": purpose,
    "__MOD_PURPOSE_SHORT__": html.escape(short, quote=True),
    "__MOD_VERSION__": version,
    "__SKIP_WITH_ANTI_CHEAT__": os.environ["ANVIL_SKIP_EAC"],
}

CSHARP = ("<!-- ANVIL:CSHARP-BEGIN -->", "<!-- ANVIL:CSHARP-END -->")
ASSETS = ("# ANVIL:ASSETS-BEGIN", "# ANVIL:ASSETS-END")
# file -> (markers, drop the block between them too?)
marked = {
    "Makefile": (ASSETS, os.environ["ANVIL_ASSETS"] != "yes"),
    "README.md": (CSHARP, os.environ["ANVIL_CSHARP"] != "yes"),
    "AGENTS.md": (CSHARP, os.environ["ANVIL_CSHARP"] != "yes"),
}

def strip_block(text, begin, end):
    """Drop every whole-line begin..end block; an unterminated one runs to EOF."""
    lines = text.splitlines(keepends=True)
    kept, inside = [], False
    for line in lines:
        marker = line.strip()
        if not inside and marker == begin:
            inside = True
        elif inside and marker == end:
            inside = False
        elif not inside:
            kept.append(line)
    return "".join(kept)

def strip_markers(text, begin, end):
    markers = {begin, end}
    return "".join(
        line for line in text.splitlines(keepends=True) if line.strip() not in markers
    )

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
        out = text
        if base == mod_dir and f in marked:
            (begin, end), drop_block = marked[f]
            if drop_block:
                out = strip_block(out, begin, end)
            out = strip_markers(out, begin, end)
        for token, value in tokens.items():
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
echo "Next: cd $MOD_FINAL && make test && make lint-shell && make lint-py"
echo "      (make help lists every target; make build needs the game install in .local.env)"
echo "Start with TODO.md (the purpose is seeded there); AGENTS.md has the working rules."

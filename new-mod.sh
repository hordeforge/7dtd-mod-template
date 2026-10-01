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
for flag_default in csharp:no assets:no clone:yes; do
	flag="${flag_default%%:*}"
	# An empty yes/no key is "not set", the reading every other optional key
	# here gets: newmod.conf.example writes display_name="" to say "default
	# to name", and a config that blanks a key to say so must not be refused.
	if [[ -z "${!flag}" ]]; then
		printf -v "$flag" '%s' "${flag_default#*:}"
		continue
	fi
	case "${!flag}" in
		yes|no) ;;
		*)
			echo "ERROR: $flag must be 'yes', 'no' or empty in $CONF, got '${!flag}'." >&2
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
# EXIT alone, plus signal traps that end the run. One trap covering all four
# removes the stage and then lets the run carry on writing into a directory
# that no longer exists: a Ctrl-C at the git step below deleted STAGE and the
# next `cp` recreated it, so the run finished "OK" over a mod built across
# two unrelated directories. Same split verify-reproducible.sh and
# run-offline-tests.sh use, for the same reason.
trap 'rm -rf "$STAGE"' EXIT
trap 'rm -rf "$STAGE"; exit 129' HUP
trap 'rm -rf "$STAGE"; exit 130' INT
trap 'rm -rf "$STAGE"; exit 143' TERM
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
		if [[ -e "$hordeforge_root/$repo" && ! -e "$hordeforge_root/$repo/.git" ]]; then
			# A directory without a .git is what an interrupted clone leaves
			# behind, and a second run used to report "Found" for it and move
			# on, leaving every later gate pointed at a checkout that has
			# none of the tools in it. Said out loud instead, because the
			# directory is the user's and removing it is not this run's call.
			warn "$hordeforge_root/$repo exists but is not a git checkout; remove or finish it, or the mod's tooling cannot run"
		elif [[ -d "$hordeforge_root/$repo" ]]; then
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
# in the same pass as the token substitution, scripts/substitute-tokens.py:
# `sed -i` is GNU-only, and BSD sed (macOS) demands a backup-suffix argument,
# taking the scaffolder down on any non-GNU host. The markers always go; the
# block between them only when the feature it documents is off.
export ANVIL_NAME="$name" ANVIL_DISPLAY="$display_name" ANVIL_AUTHOR="$author" \
	ANVIL_PURPOSE="$purpose" ANVIL_SKIP_EAC="$skip_eac" \
	ANVIL_CSHARP="$csharp" ANVIL_ASSETS="$assets"
python3 "$ANVIL/scripts/substitute-tokens.py" "$MOD_DIR"

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
# One KEY="value" line per call, appended to local_env_lines. Every value is
# collected before the file is opened, so a value the run refuses leaves no
# half-written .local.env behind.
#
# A control character is refused, and a line break is the reason: the escaping
# above spells a quote, a dollar and a backtick, but no escaping can put a line
# break inside a quoted assignment. One ends the KEY="..." line, and the rest
# of the value is then the next line of a file every server target sources
# (`scripts/lib/server-common.sh`), so a path the config carried is read as shell.
# A path is the one value here that cannot hold a line break for any reason a
# user would want, so the run stops and says so rather than writing it.
local_env_line() { # local_env_line <key> <value> [config-key]
	local key="$1" value="$2" from="${3:-$1}"
	case "$value" in
	*[[:cntrl:]]*)
		echo "ERROR: $key (from $from) holds a control character, which a KEY=\"value\" line cannot carry." >&2
		echo "       .local.env is sourced by the mod's targets, so a line break in a" >&2
		echo "       path would be read as the start of another shell command." >&2
		exit 2
		;;
	esac
	local_env_lines+=("$key=\"$(local_env_value "$value")\"")
}
local_env_lines=(
	'# Machine-local path inventory (never commit; format: .local.env.example).'
)
local_env_line SEVEN_DAYS_TO_DIE_DIR "$game_dir" game_dir
local_env_line SEVEN_DAYS_TO_DIE_SERVER_DIR "$server_dir" server_dir
local_env_line HORDEFORGE_ROOT "$hordeforge_root" hordeforge_root
local_env_line PLAYTEST_ROOT "$PLAYTEST_ROOT"
local_env_line CONNECT_ROOT "$CONNECT_ROOT"
local_env_line ASSET_PIPELINE_ROOT "$ASSET_PIPELINE_ROOT"
local_env_lines+=('DOTNET_ROOT=""')
local_env_line ILSPYCMD "$(command -v ilspycmd || true)"
local_env_line UNITY_EDITOR "$unity_editor" unity_editor
printf '%s\n' "${local_env_lines[@]}" > "$MOD_DIR/.local.env"
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
#
# The target is re-checked here, and the outcome of the move is verified, not
# just attempted. The existence test above ran before the clone, the
# substitution pass and the commit, so a second run started in that window
# passed it too: `mv src dst` with an existing directory dst moves src
# *inside* it, and the loser of that race would report OK over a mod nested
# one level down that the game never loads and no later run can clean up.
# Both runs now end the same way: the winner's mod is where it belongs, and
# the loser puts its own copy back in the stage and names the collision.
if [[ -e "$MOD_FINAL" ]]; then
	echo "ERROR: $MOD_FINAL was created while this run was scaffolding." >&2
	echo "       move it aside, or pick a different target_dir in $CONF." >&2
	exit 2
fi
mv "$MOD_DIR" "$MOD_FINAL"
if [[ -d "$MOD_FINAL/$name" ]]; then
	# The move nested rather than placed, so the target existed after all and
	# a concurrent run got there first. Put this copy back where the EXIT
	# trap deletes it and leave the other run's mod untouched.
	# ${name:?} in both: an empty one would make this an rm -rf of the target
	# itself, and name is checked for emptiness long before here.
	mv "${MOD_FINAL:?}/${name:?}" "$MOD_DIR" 2>/dev/null ||
		rm -rf "${MOD_FINAL:?}/${name:?}"
	echo "ERROR: $MOD_FINAL already exists; nothing was written." >&2
	echo "       pick a different target_dir in $CONF, or move the existing one aside." >&2
	exit 2
fi

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

#!/usr/bin/env bash
# Scaffold a new 7DTD mod from template/ — the full setup in one run.
#
# Usage: ./new-mod.sh <config-file>
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
set -euo pipefail

ANVIL="$(cd "$(dirname "$0")" && pwd)"

if (($# != 1)); then
	echo "usage: $0 <config-file>   (see newmod.conf.example)" >&2
	exit 2
fi
CONF="$1"
[[ -f "$CONF" ]] || { echo "ERROR: config file not found: $CONF" >&2; exit 2; }

# defaults, then the config overrides
name="" display_name="" author="" purpose="" target_dir=""
hordeforge_root="" csharp="no" assets="no" clone="yes"
game_dir="" server_dir="" unity_editor=""
# shellcheck disable=SC1090
source "$CONF"

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
MOD_DIR="$target_dir/$name"
[[ -e "$MOD_DIR" ]] && { echo "ERROR: $MOD_DIR already exists." >&2; exit 2; }

# --- hordeforge tool checkouts -------------------------------------------
if [[ -z "$hordeforge_root" ]]; then
	if [[ -d "$HOME/code/hordeforge" ]]; then
		hordeforge_root="$HOME/code/hordeforge"
		echo "Using existing hordeforge checkout dir: $hordeforge_root"
	else
		ask hordeforge_root "Directory for hordeforge tool checkouts (created if missing)"
	fi
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
if [[ -n "$game_dir" && ! -f "$game_dir/Data/Config/items.xml" ]]; then
	echo "WARN: $game_dir has no Data/Config/items.xml; recorded anyway — fix .local.env before building." >&2
fi

# --- create the mod directory --------------------------------------------
mkdir -p "$MOD_DIR"
cp -R "$ANVIL/template/." "$MOD_DIR/"
mkdir -p "$MOD_DIR/docs/reference"
cp -R "$ANVIL/docs/." "$MOD_DIR/docs/reference/"

if [[ "$csharp" == "yes" ]]; then
	mv "$MOD_DIR/src/__MOD_NAME__/__MOD_NAME__.csproj" "$MOD_DIR/src/__MOD_NAME__/$name.csproj"
	mv "$MOD_DIR/src/__MOD_NAME__" "$MOD_DIR/src/$name"
	skip_eac="true"
else
	rm -rf "$MOD_DIR/src"
	skip_eac="false"
fi
if [[ "$assets" == "yes" ]]; then
	mkdir -p "$MOD_DIR/assets-src"
	echo "NOTE: run 'shamway init' in the mod to set up the asset pipeline (.shamway.toml + its AGENTS contract)."
else
	# strip the shamway targets from the Makefile
	sed -i '/^# ANVIL:ASSETS-BEGIN$/,/^# ANVIL:ASSETS-END$/d' "$MOD_DIR/Makefile"
fi
sed -i '/^# ANVIL:ASSETS-BEGIN$/d; /^# ANVIL:ASSETS-END$/d' "$MOD_DIR/Makefile"

# token substitution across every tracked text file (python: purpose text
# may contain any character sed's delimiter escaping would mangle)
export ANVIL_NAME="$name" ANVIL_DISPLAY="$display_name" ANVIL_AUTHOR="$author" \
	ANVIL_PURPOSE="$purpose" ANVIL_SKIP_EAC="$skip_eac"
python3 - "$MOD_DIR" <<'PYEOF'
import html, os, re, sys
mod_dir = sys.argv[1]
purpose = os.environ["ANVIL_PURPOSE"].strip()
short = re.split(r"(?<=[.!?])\s", purpose)[0][:200]
tokens = {
    "__MOD_NAME__": os.environ["ANVIL_NAME"],
    "__MOD_NAME_LOWER__": os.environ["ANVIL_NAME"].lower(),
    "__MOD_DISPLAY_NAME__": os.environ["ANVIL_DISPLAY"],
    "__MOD_AUTHOR__": os.environ["ANVIL_AUTHOR"],
    "__MOD_AUTHOR_LOWER__": re.sub(r"[^a-z0-9]", "", os.environ["ANVIL_AUTHOR"].lower()) or "author",
    "__MOD_PURPOSE__": purpose,
    "__MOD_PURPOSE_SHORT__": html.escape(short, quote=True),
    "__SKIP_WITH_ANTI_CHEAT__": os.environ["ANVIL_SKIP_EAC"],
}
for base, dirs, files in os.walk(mod_dir):
    dirs[:] = [d for d in dirs if d != ".git"]
    for f in files:
        path = os.path.join(base, f)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (UnicodeDecodeError, OSError):
            continue
        out = text
        for token, value in tokens.items():
            out = out.replace(token, value)
        if out != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(out)
PYEOF

# --- machine-local .local.env --------------------------------------------
cat > "$MOD_DIR/.local.env" <<LOCALEOF
# Machine-local paths (never commit; format: .local.env.example).
SEVEN_DAYS_TO_DIE_DIR="$game_dir"
SEVEN_DAYS_TO_DIE_SERVER_DIR="$server_dir"
UNITY_EDITOR="$unity_editor"
HORDEFORGE_ROOT="$hordeforge_root"
LOCALEOF

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

echo
echo "OK -> $MOD_DIR"
echo "Next: cd $MOD_DIR && make test && make lint-shell"
echo "Start with TODO.md (the purpose is seeded there); AGENTS.md has the working rules."

#!/usr/bin/env bash
# Stage the deployable modlet under dist/<Name>/. Compiles the C# DLL first
# when src/ exists (requires SEVEN_DAYS_TO_DIE_DIR via env or .local.env).
set -euo pipefail

# Sorting and any date formatting in staging and packaging must not follow
# the builder's locale or timezone.
export LC_ALL=C
export TZ=UTC

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
	cat <<'HELP'
Stage the deployable modlet under dist/<Name>/.

USAGE
  scripts/build.sh

OPTIONS
  -h, --help  show this help and exit

EXIT STATUS
  0  dist/<Name>/ is staged
  1  the build failed
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

MOD_NAME="__MOD_NAME__"
OUT="$ROOT/dist/$MOD_NAME"
SRC="$ROOT/src/$MOD_NAME"

rm -rf "$OUT"
mkdir -p "$OUT"

if [[ -d "$SRC" ]]; then
	# The ignored file is the documented machine-local game reference. It is
	# loaded whether or not the environment already names a game dir:
	# load_local_env keeps a key the environment set, and skipping the file
	# when it was set threw away the rest of it.
	# shellcheck source=server-common.sh
	source "$SCRIPT_DIR/server-common.sh"
	load_local_env "$ROOT"
	GAME_DIR="${SEVEN_DAYS_TO_DIE_DIR:-}"
	if [[ -z "$GAME_DIR" ]]; then
		echo "ERROR: set SEVEN_DAYS_TO_DIE_DIR or create .local.env with the client game-install directory before building." >&2
		exit 1
	fi
	MANAGED="$GAME_DIR/7DaysToDie_Data/Managed"
	HARMONY="$GAME_DIR/Mods/0_TFP_Harmony/0Harmony.dll"
	[[ -f "$MANAGED/Assembly-CSharp.dll" ]] || { echo "ERROR: Assembly-CSharp.dll not found under $MANAGED." >&2; exit 1; }
	[[ -f "$HARMONY" ]] || { echo "ERROR: stock 0_TFP_Harmony/0Harmony.dll not found in the game install." >&2; exit 1; }
	command -v dotnet >/dev/null 2>&1 || { echo "ERROR: dotnet not found; required to build the net48 mod DLL." >&2; exit 1; }
	# `dotnet` on PATH is not a build: a runtime-only or SDK-less install
	# resolves the command and then fails deep inside dotnet's own output.
	# Probe for a usable SDK here and name the fix.
	dotnet --list-sdks 2>/dev/null | grep -q . || {
		echo "ERROR: dotnet is on PATH but no .NET SDK is installed ('dotnet --list-sdks' is empty), so the mod DLL cannot be built." >&2
		echo "       Install an SDK, or point DOTNET_ROOT in .local.env at one (an SDK-less" >&2
		echo "       install, including a dotnet under ~/.dotnet, shows up here)." >&2
		exit 1
	}
	# The pin has to be a pin. global.json's rollForward is what decides how
	# far the host may drift from it, so the pin is resolved here, from the
	# mod root, and the answer is checked: a host carrying only a newer
	# feature band then says which band was wanted instead of compiling the
	# DLL with whatever it has and calling it the same source.
	#
	# `dotnet --version` is the resolver itself, so there is no second
	# implementation of what rollForward means to drift away from the tool's.
	sdk_pinned="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([0-9][0-9.]*\)".*/\1/p' "$ROOT/global.json")"
	[[ -n "$sdk_pinned" ]] || {
		echo "ERROR: no sdk.version in $ROOT/global.json, so the pinned SDK could" >&2
		echo "       not be read and the build would silently use whatever the host" >&2
		echo "       has newest. Restore the line." >&2
		exit 1
	}
	sdk_resolved=''
	sdk_resolved="$(cd "$ROOT" && dotnet --version 2>&1)" || {
		echo "ERROR: no .NET SDK that global.json's pin (version $sdk_pinned," >&2
		echo "       rollForward latestPatch) resolves to. The host has:" >&2
		dotnet --list-sdks 2>/dev/null | sed 's/^/         /' >&2
		echo "       dotnet said: $sdk_resolved" >&2
		echo "       Install the pinned band, or bump global.json together with" >&2
		echo "       LangVersion in $MOD_NAME.csproj: a different SDK compiles this" >&2
		echo "       source to a different DLL." >&2
		exit 1
	}
	# dotnet resolves global.json (the SDK pin) from the working directory,
	# not from the project path it was handed: run from anywhere else and the
	# pin is skipped and whatever SDK the host has newest is used instead.
	(
		cd "$ROOT"
		dotnet build "$SRC/$MOD_NAME.csproj" -c Release -o "$OUT" \
			-p:GameManagedDir="$MANAGED" -p:HarmonyPath="$HARMONY"
	)
fi

cp "$ROOT/ModInfo.xml" "$OUT/ModInfo.xml"
# the player-facing release readme (game version, EAC, Harmony, install)
cp "$ROOT/README.txt" "$OUT/README.txt"
# the release notes, so the shipped zip says what this version changed
# (scripts/test_static_checks.py gates that the mod keeps one CHANGELOG.md
# with a section for the version ModInfo.xml declares)
cp "$ROOT/CHANGELOG.md" "$OUT/CHANGELOG.md"
# Localization ships inside Config/: the engine reads a mod's localization
# only from <mod>/Config/Localization.csv (ModManager passes mod.Path +
# "/Config" to Localization.LoadPatchDictionaries).
for entry in Config Prefabs Resources UI UIAtlases WebMod; do
	if [[ -e "$ROOT/$entry" ]]; then
		cp -R "$ROOT/$entry" "$OUT/$entry"
	fi
done

echo "OK -> $OUT"

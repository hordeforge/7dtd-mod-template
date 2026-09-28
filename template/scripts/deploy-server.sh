#!/usr/bin/env bash
# Replace only the server install's Mods/__MOD_NAME__/ with the staged package.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi

"$ROOT/scripts/build.sh"

SOURCE="$ROOT/dist/__MOD_NAME__"
TARGET="$SERVER_DIR/Mods/__MOD_NAME__"
if [[ -d "$ROOT/src" && ! -f "$SOURCE/__MOD_NAME__.dll" ]]; then
	echo "ERROR: expected packaged DLL missing from $SOURCE." >&2
	exit 1
fi

mkdir -p "$SERVER_DIR/Mods"
# Stage outside Mods/ and swap, so a failed copy, a full disk, or an interrupt
# leaves the previously deployed mod in place instead of a half-copied one.
# Nothing may sit under Mods/ between the two steps: the game loads every
# mod folder it finds there, so a leftover stage would load a second copy.
STAGE="$SERVER_DIR/.deploy-stage/__MOD_NAME__"
PREVIOUS="$SERVER_DIR/.deploy-stage/__MOD_NAME__.previous"
mkdir -p "$SERVER_DIR/.deploy-stage"
rm -rf "$STAGE" "$PREVIOUS"
cp -R "$SOURCE" "$STAGE"
if [[ -d "$TARGET" ]]; then
	mv "$TARGET" "$PREVIOUS"
fi
if ! mv "$STAGE" "$TARGET"; then
	if [[ -d "$PREVIOUS" ]]; then
		mv "$PREVIOUS" "$TARGET"
	fi
	echo "ERROR: deploy failed; a previously deployed mod has been put back." >&2
	exit 1
fi
rm -rf "$PREVIOUS"

echo "OK: deployed $SOURCE to $TARGET"

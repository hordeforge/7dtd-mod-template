#!/usr/bin/env bash
# Replace only the server install's Mods/__MOD_NAME__/ with the staged package.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
	cat <<'HELP'
Replace the server install's Mods/__MOD_NAME__/ with the staged package.

USAGE
  scripts/deploy-server.sh

OPTIONS
  -h, --help  show this help and exit

ENVIRONMENT
  SEVEN_DAYS_TO_DIE_SERVER_DIR  the server install to deploy into

EXIT STATUS
  0  the modlet is deployed
  1  the server install is unusable, or the deploy failed
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

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
# swap_into_place restores the previous copy when the run is interrupted between
# its two moves, which is the one window a rerun does not cover: the run that
# was interrupted is the one that has to leave the deployment intact.
swap_into_place "$STAGE" "$TARGET" "$PREVIOUS"

echo "OK: deployed $SOURCE to $TARGET"

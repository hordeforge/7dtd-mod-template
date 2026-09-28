#!/usr/bin/env bash
# Deploy, boot the dedicated server for a bounded window, and prove this mod
# loaded from the log — no client involved.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
	cat <<'HELP'
Deploy, boot the dedicated server briefly, and prove the mod loaded from its log.

USAGE
  scripts/server-smoke.sh

OPTIONS
  -h, --help  show this help and exit

ENVIRONMENT
  SEVEN_DAYS_TO_DIE_SERVER_DIR        the server install to boot
  SEVEN_DAYS_TO_DIE_SERVER_CONFIG      serverconfig to boot; defaults to
                                       <SERVER_DIR>/serverconfig.__MOD_NAME_LOWER__.xml
  SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS  boot window, 90 by default
  SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS    smoke logs kept, 5 by default

EXIT STATUS
  0  the server booted and reported the mod loaded
  1  the run or one of its prerequisites failed
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment

SERVER_BIN="$SERVER_DIR/7DaysToDieServer.x86_64"
LOG_DIR="$SERVER_DIR/logs"

RUN_FOR_SECONDS_RAW="${SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS:-90}"
KEEP_LOGS_RAW="${SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS:-5}"
# Through decimal_uint, not a ^[0-9]+$ match: a leading zero is an octal prefix
# to `$(( ))`, so a `RUN_FOR_SECONDS` of `090` is a syntax error the run dies
# on, and a `KEEP_LOGS` of `08` is one that prunes nothing at all.
RUN_FOR_SECONDS="$(decimal_uint "$RUN_FOR_SECONDS_RAW")" || RUN_FOR_SECONDS=""
if [[ -z "$RUN_FOR_SECONDS" ]] || (( RUN_FOR_SECONDS < 1 )); then
	echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS must be a positive integer, got '$RUN_FOR_SECONDS_RAW'." >&2
	exit 1
fi
# Checked here, not only inside prune_smoke_logs: a typo'd value is a no-op
# there, and the run it fails to prune is the one that grows logs/ without
# bound, once per smoke run, forever.
KEEP_LOGS="$(decimal_uint "$KEEP_LOGS_RAW")" || KEEP_LOGS=""
if [[ -z "$KEEP_LOGS" ]]; then
	echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS must be a non-negative integer, got '$KEEP_LOGS_RAW'." >&2
	exit 1
fi
command -v timeout >/dev/null 2>&1 || { echo "ERROR: timeout is required." >&2; exit 1; }
if [[ ! -x "$SERVER_BIN" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi
if [[ ! -f "$SERVER_CONFIG" ]]; then
	echo "ERROR: server configuration not found at $SERVER_CONFIG." >&2
	exit 1
fi
if ! grep -iq '<property[[:space:]]\+name="EACEnabled"[[:space:]]\+value="false"' "$SERVER_CONFIG"; then
	echo "ERROR: set EACEnabled=false in $SERVER_CONFIG before Harmony/DLL server testing." >&2
	exit 1
fi

"$SCRIPT_DIR/deploy-server.sh"
mkdir -p "$LOG_DIR"
# Named after the deploy, not before it: a run that takes longer than a second
# to reach the server would otherwise pick the name a later run is about to
# claim.
LOG_FILE="$(smoke_log_path "$LOG_DIR" "__MOD_NAME_LOWER__-server-smoke-")"

echo "Launching dedicated server for ${RUN_FOR_SECONDS}s."
set +e
timeout --signal=TERM --kill-after=10 "$RUN_FOR_SECONDS" \
	"$SERVER_BIN" -configfile="$SERVER_CONFIG" >"$LOG_FILE" 2>&1
SERVER_STATUS=$?
set -e

# Every run writes its own log and nothing else removes them, so the server
# install's logs/ would grow by one file per smoke run forever. Keep the newest
# KEEP_LOGS and drop the rest; the game's own logs are a different prefix and
# are never touched. Pruned after the boot so this run's log counts toward the
# quota: pruning first left KEEP_LOGS+1 behind every time.
prune_smoke_logs "$LOG_DIR" "$KEEP_LOGS"

if (( SERVER_STATUS != 124 )); then
	echo "ERROR: dedicated server exited before the ${RUN_FOR_SECONDS}s smoke-test timeout (status $SERVER_STATUS)." >&2
	tail -n 80 "$LOG_FILE" >&2
	exit 1
fi

echo "SERVER LOG"
echo "  $LOG_FILE"

if ! grep -Fq "Loaded Mod: __MOD_NAME__" "$LOG_FILE"; then
	echo "ERROR: server log has no 'Loaded Mod: __MOD_NAME__' line." >&2
	grep -n -i '__MOD_NAME__\|\[MODS\]' "$LOG_FILE" >&2 || true
	exit 1
fi
if [[ -d "$ROOT/src" ]] && ! grep -Fq "[__MOD_NAME__] InitMod" "$LOG_FILE"; then
	echo "ERROR: the mod DLL did not report InitMod on the server." >&2
	grep -n -F "[__MOD_NAME__]" "$LOG_FILE" >&2 || true
	exit 1
fi

echo "RESULT"
echo "  PASS: __MOD_NAME__ loaded on the dedicated server."

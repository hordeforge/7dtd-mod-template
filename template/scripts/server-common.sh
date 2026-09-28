#!/usr/bin/env bash
# Shared helpers for the dedicated-server targets. Sourced, not executed.

load_server_environment() {
	ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
	SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"

	if [[ -z "$SERVER_DIR" && -f "$ROOT/.local.env" ]]; then
		set -a
		# shellcheck disable=SC1090,SC1091
		source "$ROOT/.local.env"
		set +a
		SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"
	fi

	if [[ -z "$SERVER_DIR" ]]; then
		echo "ERROR: set SEVEN_DAYS_TO_DIE_SERVER_DIR or add it to .local.env." >&2
		exit 1
	fi
	if [[ "$SERVER_DIR" != /* ]]; then
		echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_DIR must be an absolute path." >&2
		exit 1
	fi

	# Consumed by the sourcing server-*.sh callers, not by this library.
	# shellcheck disable=SC2034
	SERVER_CONFIG="${SEVEN_DAYS_TO_DIE_SERVER_CONFIG:-$SERVER_DIR/serverconfig.__MOD_NAME_LOWER__.xml}"
}

resolve_steamcmd() {
	if [[ -n "${SEVEN_DAYS_TO_DIE_STEAMCMD:-}" && -x "$SEVEN_DAYS_TO_DIE_STEAMCMD" ]]; then
		STEAMCMD_BIN="$SEVEN_DAYS_TO_DIE_STEAMCMD"
		return
	fi
	if command -v steamcmd >/dev/null 2>&1; then
		STEAMCMD_BIN="$(command -v steamcmd)"
		return
	fi
	STEAMCMD_BIN="${SEVEN_DAYS_TO_DIE_STEAMCMD_DIR:-$HOME/.local/share/steamcmd}/steamcmd.sh"
	if [[ ! -x "$STEAMCMD_BIN" ]]; then
		echo "ERROR: SteamCMD not found; install it or set SEVEN_DAYS_TO_DIE_STEAMCMD." >&2
		exit 1
	fi
}

# prune_smoke_logs <log-dir> <keep>
#
# Keep the newest <keep> server-smoke logs and drop the rest. A smoke log is
# named <prefix>-server-smoke-<YYYYMMDD-HHMMSS>.log, and that timestamp is
# fixed width, so a reverse byte sort of the names is a reverse time sort.
# Globbing keeps paths with spaces in them intact, and it needs no GNU find:
# -printf is GNU-only and absent on the BSD find in macOS.
prune_smoke_logs() {
	local log_dir="$1" keep="$2" log candidate
	local -a logs=() stale=()

	[[ "$keep" =~ ^[0-9]+$ ]] || return 0
	shopt -s nullglob
	# -f, because `find -type f` was what this replaced: a directory that
	# happens to carry a log name is not a log and must not use up a slot.
	for candidate in "$log_dir"/__MOD_NAME_LOWER__-server-smoke-*.log; do
		[[ -f "$candidate" ]] && logs+=("$candidate")
	done
	shopt -u nullglob
	((${#logs[@]})) || return 0

	while IFS= read -r log; do
		stale+=("$log")
	done < <(printf '%s\n' "${logs[@]}" | LC_ALL=C sort -r | tail -n "+$((keep + 1))")
	if ((${#stale[@]})); then
		rm -f -- "${stale[@]}"
	fi
	return 0
}

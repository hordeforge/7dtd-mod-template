#!/usr/bin/env bash
# Shared helpers for the dedicated-server targets. Sourced, not executed.

# load_local_env <mod-root>
#
# Export every key of the ignored <mod-root>/.local.env into the environment.
# A key already set in the environment is left alone, so the precedence is
# one rule for every caller: a one-off `SEVEN_DAYS_TO_DIE_DIR=... make ...`
# overrides the file without editing it. A missing file is the normal case
# for a fresh checkout, not an error.
#
# A file that cannot be parsed is fatal and names itself: sourcing it under
# `set -e` otherwise dies on a /dev/fd path that says nothing about which file
# the reader has to fix.
load_local_env() {
	local env_file="$1/.local.env"
	[[ -f "$env_file" ]] || return 0
	local -a from_file=() preset=() was_set=()
	local key
	# Through sed, not `source "$env_file"`: a CRLF file (any edit from a
	# Windows editor leaves one) turns every KEY="v" into KEY="v"\r, which
	# bash reports as a command-not-found on the value rather than as a
	# malformed line. The same pass names the keys, which is how the
	# environment keeps precedence after the source overwrites them.
	while IFS= read -r key; do
		from_file+=("$key")
		if [[ -v "$key" ]]; then
			preset+=("${!key}")
			was_set+=(1)
		else
			preset+=("")
			was_set+=(0)
		fi
	done < <(sed -n -e 's/\r$//' \
		-e 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\).*/\2/p' \
		"$env_file")
	((${#from_file[@]})) || return 0

	set -a
	# shellcheck disable=SC1090,SC1091
	if ! source <(sed -e 's/\r$//' "$env_file"); then
		set +a
		echo "ERROR: cannot parse $env_file; it must hold KEY=\"value\" lines (see .local.env.example)." >&2
		exit 1
	fi
	set +a

	# The source has now run every assignment; put back the ones the caller
	# already had, which is the whole of the environment-wins rule.
	for key in "${!from_file[@]}"; do
		if ((was_set[key])); then
			printf -v "${from_file[key]}" '%s' "${preset[key]}"
			export "${from_file[key]}"
		fi
	done
}

load_server_environment() {
	ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
	SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"

	if [[ -z "$SERVER_DIR" ]]; then
		load_local_env "$ROOT"
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
	# Every server-lane target deletes or writes below $SERVER_DIR, so a
	# one-level value ("/", "/srv") turns those into machine-wide deletes.
	depth="${SERVER_DIR//[!\/]/}"
	if ((${#depth} < 2)); then
		echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_DIR must be at least two levels deep (e.g. /srv/7dtd-server); '$SERVER_DIR' is too shallow to deploy into safely." >&2
		exit 1
	fi

	# Consumed by the sourcing server-*.sh callers, not by this library.
	# shellcheck disable=SC2034
	SERVER_CONFIG="${SEVEN_DAYS_TO_DIE_SERVER_CONFIG:-$SERVER_DIR/serverconfig.__MOD_NAME_LOWER__.xml}"
	# Relative to what? The server binary runs from wherever the caller was
	# started, so a relative value passes the existence check from the mod
	# directory and then fails to be found by the game.
	if [[ "$SERVER_CONFIG" != /* ]]; then
		echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_CONFIG must be an absolute path, got '$SERVER_CONFIG'." >&2
		exit 1
	fi
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

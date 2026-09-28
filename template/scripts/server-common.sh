#!/usr/bin/env bash
# Shared helpers for the dedicated-server targets. Sourced, not executed.

# shellcheck source=lib/require-bash.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/require-bash.sh"
require_bash

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

# decimal_uint <value>
#
# Print <value> as the plain decimal integer it spells, and succeed; fail when
# it is not a decimal integer or is too long for the shell's arithmetic.
#
# Every caller of this takes a number a person typed into .local.env and feeds
# it to `$(( ))`, and `$(( ))` is not a decimal parser. A leading zero is an
# octal prefix, so a KEEP_LOGS of `08` is not eight: the expansion fails, the
# quota it was meant to enforce is silently never applied, and under `set -e`
# the run dies on a value that was never wrong. A digit run longer than 64 bits
# wraps instead, so `18446744073709551616` reads as `0` and a SOURCE_DATE_EPOCH
# just past 2107 is accepted as one just after 1970. Both are wrong answers to
# a value nobody mistyped, so the digits are normalized once, here, and every
# caller compares the result.
decimal_uint() {
	local value="$1"
	[[ "$value" =~ ^0*([0-9]{1,19})$ ]] || return 1
	printf '%s\n' "${BASH_REMATCH[1]}"
}

# load_server_environment
#
# Set the globals the server-*.sh callers read ($ROOT, $SERVER_DIR,
# $SERVER_CONFIG) from SEVEN_DAYS_TO_DIE_SERVER_DIR, loading .local.env
# first when the environment has no value. Sets them in the caller's shell
# rather than exporting them: they are the caller's own names, not the
# process environment's. Exits 1 naming the offending value when the server
# directory is missing, relative, or too shallow to deploy into.
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

# resolve_steamcmd
#
# Set $STEAMCMD_BIN to the first SteamCMD that exists, in this order:
# SEVEN_DAYS_TO_DIE_STEAMCMD, `steamcmd` on PATH, then steamcmd.sh under
# SEVEN_DAYS_TO_DIE_STEAMCMD_DIR (default ~/.local/share/steamcmd). A
# SEVEN_DAYS_TO_DIE_STEAMCMD that is set but not executable is skipped like
# a missing one, so the next tier can still answer; the failure it was
# meant to be is reported only when no tier produces a binary. Exits 1 when
# none does.
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

# smoke_log_path <log-dir> <prefix>
#
# Print a log name no earlier run has used. A stamp one second wide repeats:
# a rerun inside the same second opens the previous run's name with `>` and
# replaces the evidence that run left, and the two runs then count as one
# against the quota prune_smoke_logs keeps. The stamp keeps its width, so the
# name sort stays a time sort; the _2, _3 suffixes only ever sit inside one
# second, and `_` sorts above `.`, so the reverse name sort the pruning does
# reads the later of the two as the newer one, which is the order it wants.
smoke_log_path() {
	local log_dir="$1" prefix="$2" stamp candidate n
	stamp="$(date -u +%Y%m%d-%H%M%S)"
	candidate="$log_dir/$prefix$stamp.log"
	n=1
	while [[ -e "$candidate" ]]; do
		n=$((n + 1))
		candidate="$log_dir/$prefix${stamp}_$n.log"
	done
	printf '%s\n' "$candidate"
}

# swap_into_place <source> <target> <previous>
#
# Put <source> where <target> is, holding the copy that is already there until
# the new one is in place. The two moves cannot be one: between them the target
# does not exist, and a Ctrl-C, a SIGTERM or a failed second move in that
# window leaves the deployment gone rather than half-updated. So the previous
# copy goes back where it was on any exit before the swap completes, and only
# the new copy survives. <previous> is removed once the swap is done; a
# leftover under Mods/ would be a second mod the game loads.
swap_into_place() {
	local source="$1" target="$2" previous="$3"
	local held=0 swapped=0

	put_previous_back() {
		if (( held )) && [[ -d "$previous" && ! -e "$target" ]]; then
			mv "$previous" "$target" || true
		fi
		held=0
	}
	# `swapped` rather than a plain clear: the restore has to be inert once the
	# new copy is in place, or the EXIT trap would take the deployment down on
	# the way out.
	trap '(( swapped )) || put_previous_back' EXIT
	trap 'put_previous_back; exit 129' HUP
	trap 'put_previous_back; exit 130' INT
	trap 'put_previous_back; exit 143' TERM

	if [[ -d "$target" ]]; then
		# Set before the move, not after: a signal delivered while the move is
		# running is exactly the case the restore exists for, and by then the
		# target may already be the one name that is missing.
		held=1
		mv "$target" "$previous"
	fi
	if ! mv "$source" "$target"; then
		put_previous_back
		echo "ERROR: could not put $source in place at $target; a previously deployed copy has been put back." >&2
		return 1
	fi
	# Read by the trap strings above, which shellcheck does not parse as code.
	# shellcheck disable=SC2034
	swapped=1
	trap - EXIT HUP INT TERM
	rm -rf "$previous"
}

# prune_smoke_logs <log-dir> <keep>
#
# Keep the newest <keep> server-smoke logs and drop the rest. A smoke log is
# named <prefix>-server-smoke-<YYYYMMDD-HHMMSS>.log, and that timestamp is
# fixed width, so a reverse byte sort of the names is a reverse time sort.
# Globbing keeps paths with spaces in them intact, and it needs no GNU find:
# -printf is GNU-only and absent on the BSD find in macOS.
#
# <keep> goes through decimal_uint: `$((keep + 1))` reads a leading zero as an
# octal prefix, so a quota of `08` failed the expansion and pruned nothing at
# all rather than keeping eight.
prune_smoke_logs() {
	local log_dir="$1" keep="$2" log candidate
	local -a logs=() stale=()

	keep="$(decimal_uint "$keep")" || return 0
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

#!/usr/bin/env bash
# Run the offline contract/unit suite: every scripts/test_*.py must exit 0.
#
# Each test script is standalone (see its own docstring) and needs no live
# client or server, so the shared live-playtest lock is not involved. Live
# behaviour is covered by the live suites the mod runs through
# hordeforge/7dtd-playtest instead.
#
# The tests are independent processes writing only into their own temporary
# directories, so they are run concurrently; results are collected and
# reported in glob order either way, with each test's own output replayed
# after its PASS/FAIL line. OFFLINE_TEST_JOBS=1 restores the serial walk,
# which reports the same lines in the same order (same knob
# scripts/test_rules_have_gates.py honours).
#
# The report carries no wall-clock reading, so two runs over an unchanged tree
# print byte-identical stdout — the property AGENTS.md requires of a gate, and
# the one scripts/test_run_offline_tests.py asserts. OFFLINE_TEST_TIMINGS=1
# appends per-test elapsed seconds for a human, and is therefore the one mode
# whose output is not reproducible.
#
# An interrupted run owns nothing when it exits: the signal traps release the
# scratch directory and the workers, because a shell killed by a signal never
# runs its EXIT trap.
#
# Usage:
#   scripts/run-offline-tests.sh              # run every test
#   scripts/run-offline-tests.sh nuke fuse    # run tests whose name matches any substring
#   OFFLINE_TEST_TIMINGS=1 scripts/run-offline-tests.sh   # add elapsed seconds
set -uo pipefail

# shellcheck source=lib/require-bash.sh
source "$(dirname "$0")/lib/require-bash.sh"
require_bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
	cat <<'HELP'
Run every scripts/test_*.py; each must exit 0.

USAGE
  scripts/run-offline-tests.sh [filter ...]
  make test [TF=<filter ...>]

ARGUMENTS
  [filter ...]       run only the tests whose file name contains one of these
                     substrings, e.g. telnet

OPTIONS
  -h, --help         show this help and exit

ENVIRONMENT
  OFFLINE_TEST_JOBS=1     run serially instead of concurrently
  OFFLINE_TEST_TIMINGS=1 append per-test elapsed seconds (not reproducible)

EXIT STATUS
  0  every test that ran passed
  1  a test failed, or no test matched the filters
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
help_only usage "$@"

# Read one key out of .local.env without exporting it. OFFLINE_TEST_JOBS and
# OFFLINE_TEST_TIMINGS are documented .local.env keys, so they have to be
# settable there, but this runner spawns every gate: load_local_env would put
# the modlet's whole machine-local configuration into the environment of each
# one, so a gate that deliberately reads an unset key would see it set by its
# own caller. Two keys read narrowly instead of a whole file exported wide.
local_env_value() { # local_env_value <key>
	local file value
	file="$MOD_DIR/.local.env"
	[[ -f "$file" ]] || return 0
	value="$(sed -n -e 's/\r$//' -e "s/^[[:space:]]*${1}=//p" "$file" | tail -n 1)"
	[[ "$value" == \"*\" ]] && value="${value:1:${#value} - 2}"
	printf '%s' "$value"
}

# Elapsed time is measured on a monotonic clock. `date +%s` is the wall
# clock: an NTP step or a manual clock change during a run reports a negative
# or wildly inflated duration for a test that took a moment. /proc/uptime is
# the only monotonic reading a POSIX shell can get without another process;
# where it is absent the wall clock is the fallback, and no worse than before.
now_seconds() {
	local uptime
	if [[ -r /proc/uptime ]]; then
		read -r uptime _ < /proc/uptime || uptime=""
		if [[ "$uptime" == *.* ]]; then
			printf '%s\n' "${uptime%%.*}"
			return
		fi
	fi
	date +%s
}

filters=("$@")
failed=()
ran=0
overall_start=$(now_seconds)

tests=()
for test_script in "$SCRIPT_DIR"/test_*.py; do
	name="$(basename "$test_script")"
	if (( ${#filters[@]} )); then
		skip=1
		for needle in "${filters[@]}"; do
			if [[ "$name" == *"$needle"* ]]; then
				skip=0
				break
			fi
		done
		if (( skip )); then
			continue
		fi
	fi
	tests+=("$test_script")
done

max_jobs=${OFFLINE_TEST_JOBS:-}
if [[ -z "$max_jobs" ]]; then
	max_jobs="$(local_env_value OFFLINE_TEST_JOBS)"
fi
# `[1-9][0-9]{0,18}` rather than `[1-9][0-9]*`: a 19-digit-plus value wraps in
# `$(( ))` rather than failing, so a run count of 18446744073709551616 came
# back as 0 and silently ran the whole suite serially. Past 18 digits the value
# is not a job count, and falling through to the nproc default is the answer.
if [[ ! "$max_jobs" =~ ^[1-9][0-9]{0,18}$ ]]; then
	max_jobs=$(nproc 2>/dev/null || printf '8')
	(( max_jobs > 8 )) && max_jobs=8
fi

# Elapsed seconds are the one value in the report that cannot replay, so they
# are opt-in rather than always printed.
timings=${OFFLINE_TEST_TIMINGS:-}
if [[ -z "$timings" ]]; then
	timings="$(local_env_value OFFLINE_TEST_TIMINGS)"
fi
[[ "$timings" == 1 ]] || timings=0

# Global, not local: the EXIT trap must still see it after run_parallel returns.
tmpdir=""

# Release everything this run holds: the workers, then the temp directory
# holding their output. Called from the EXIT trap and from each signal trap,
# because a non-interactive shell killed by a signal never runs its EXIT trap,
# so an EXIT trap alone leaves a whole temp directory behind on every
# interrupt, once per interrupted run, forever.
cleanup() {
	local worker child
	# The shell's own job table, not a list of PIDs collected at launch: a
	# worker `wait -n` already reaped is gone from it, and its PID is free for
	# the kernel to hand to some unrelated process, which a recorded PID
	# would then kill.
	while read -r worker; do
		[[ -n "$worker" ]] || continue
		# A worker is a subshell whose own child is the test process, so
		# signalling the subshell alone orphans that child: it keeps running,
		# writing into a directory that is about to be removed, until the
		# test finishes on its own. The children are collected first,
		# because once the subshell is gone they are reparented and this
		# cannot find them again.
		while read -r child; do
			[[ -n "$child" ]] && kill "$child" 2>/dev/null || true
		done < <(ps -o pid= --ppid "$worker" 2>/dev/null)
		kill "$worker" 2>/dev/null || true
	done < <(jobs -pr)
	if [[ -n "$tmpdir" && -d "$tmpdir" ]]; then
		rm -rf "$tmpdir"
	fi
	tmpdir=""
	return 0
}

# make_tmpdir: the scratch directory both modes capture into, with the traps
# that release it installed once.
make_tmpdir() {
	tmpdir="$(mktemp -d)"
	trap cleanup EXIT
	trap 'cleanup; exit 129' HUP
	trap 'cleanup; exit 130' INT
	trap 'cleanup; exit 143' TERM
}

run_serial() {
	local test_script name start status elapsed out err
	make_tmpdir
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		out="$tmpdir/$name.out"
		err="$tmpdir/$name.err"
		start=$(now_seconds)
		status=0
		python3 "$test_script" >"$out" 2>"$err" || status=$?
		elapsed=""
		(( timings )) && elapsed=" ($(( $(now_seconds) - start ))s)"
		if (( status == 0 )); then
			printf 'PASS %s%s\n' "$name" "$elapsed"
		else
			printf 'FAIL %s (exit %s)%s\n' "$name" "$status" "$elapsed"
			failed+=("$name")
		fi
		# Captured and replayed, exactly as run_parallel does, so a serial run
		# reports the same lines in the same order as a parallel one. Sent
		# straight to the terminal instead, a test's own output landed ahead of
		# its PASS line and only in this mode.
		cat "$out"
		cat "$err" >&2
		ran=$((ran + 1))
	done
}

run_parallel() {
	local active test_script name start status secs elapsed out err
	make_tmpdir
	active=0
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		out="$tmpdir/$name.out"
		err="$tmpdir/$name.err"
		(
			start=$(now_seconds)
			status=0
			python3 "$test_script" >"$out" 2>"$err" || status=$?
			# The report is read back in glob order, so which worker finished
			# first must not reach the output: the status file is keyed by
			# name, never appended to.
			printf '%s %s\n' "$status" "$(( $(now_seconds) - start ))" \
				> "$tmpdir/$name.status"
		) &
		active=$((active + 1))
		if (( active >= max_jobs )); then
			wait -n
			active=$((active - 1))
		fi
	done
	wait
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		# A worker killed outright (OOM, a signal) never writes its status
		# file. An unset `status` would abort the whole report under `set -u`
		# and lose the results of every test that did run, so the missing
		# file is itself the failure.
		status=125
		secs=0
		if ! read -r status secs < "$tmpdir/$name.status"; then
			printf 'FAIL %s (no status file: the worker exited before reporting)\n' "$name"
			failed+=("$name")
			ran=$((ran + 1))
			continue
		fi
		ran=$((ran + 1))
		elapsed=""
		(( timings )) && elapsed=" (${secs}s)"
		if (( status == 0 )); then
			printf 'PASS %s%s\n' "$name" "$elapsed"
		else
			printf 'FAIL %s (exit %s)%s\n' "$name" "$status" "$elapsed"
			failed+=("$name")
		fi
		cat "$tmpdir/$name.out"
		cat "$tmpdir/$name.err" >&2
	done
}

if (( max_jobs > 1 )); then
	run_parallel
else
	run_serial
fi

if (( timings )); then
	printf '%s offline tests run in %ss.\n' "$ran" "$(( $(now_seconds) - overall_start ))"
else
	printf '%s offline tests run.\n' "$ran"
fi
if (( ${#filters[@]} && ran == 0 )); then
	# A filter matching nothing must not read as a green run.
	printf 'ERROR: no test_*.py matches filter(s): %s\n' "${filters[*]}" >&2
	exit 1
fi
if (( ${#failed[@]} )); then
	printf 'FAILED: %s\n' "${failed[*]}"
	exit 1
fi

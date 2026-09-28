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
# reported in glob order either way. OFFLINE_TEST_JOBS=1 restores the serial
# walk (same knob scripts/test_rules_have_gates.py honours).
#
# The report carries no wall-clock reading, so two runs over an unchanged tree
# print byte-identical stdout — the property AGENTS.md requires of a gate, and
# the one scripts/test_run_offline_tests.py asserts. OFFLINE_TEST_TIMINGS=1
# appends per-test elapsed seconds for a human, and is therefore the one mode
# whose output is not reproducible.
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
if [[ ! "$max_jobs" =~ ^[1-9][0-9]*$ ]]; then
	max_jobs=$(nproc 2>/dev/null || printf '8')
	(( max_jobs > 8 )) && max_jobs=8
fi

# Elapsed seconds are the one value in the report that cannot replay, so they
# are opt-in rather than always printed.
timings=${OFFLINE_TEST_TIMINGS:-0}
[[ "$timings" == 1 ]] || timings=0

# Global, not local: the EXIT trap must still see it after run_parallel returns.
tmpdir=""

run_serial() {
	local test_script name start status elapsed
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		start=$(now_seconds)
		if python3 "$test_script"; then
			status=0
		else
			status=$?
		fi
		elapsed=""
		(( timings )) && elapsed=" ($(( $(now_seconds) - start ))s)"
		if (( status == 0 )); then
			printf 'PASS %s%s\n' "$name" "$elapsed"
		else
			printf 'FAIL %s (exit %s)%s\n' "$name" "$status" "$elapsed"
			failed+=("$name")
		fi
		ran=$((ran + 1))
	done
}

run_parallel() {
	local active test_script name start status secs elapsed out err
	tmpdir="$(mktemp -d)"
	trap 'rm -rf "$tmpdir"' EXIT
	active=0
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		out="$tmpdir/$name.out"
		err="$tmpdir/$name.err"
		(
			start=$(now_seconds)
			if python3 "$test_script" >"$out" 2>"$err"; then
				status=0
			else
				status=$?
			fi
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

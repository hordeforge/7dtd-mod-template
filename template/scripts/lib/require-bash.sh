# shellcheck shell=bash
# The bash version this mod's scripts assume, checked in one place. Sourced,
# never executed.
#
# Bash 3.2 is still the system bash on macOS, and it is the version a plain
# `#!/usr/bin/env bash` picks up there. Every feature below fails on it in its
# own way and none of them says why: `mapfile -d` (scripts/package.sh) rejects
# the option, `wait -n` (scripts/run-offline-tests.sh) is an unknown operand,
# and `[[ -v var ]]` (scripts/lib/server-common.sh) is a syntax error. A script
# that uses one of those sources this file and calls require_bash first, so the
# floor is reported once, in one message, before any work starts.
#
# Keeping the features to 3.2 is the alternative, and it is not free: `wait -n`
# is what bounds the offline suite's parallelism, and the null-delimited
# mapfile is what keeps a staged path with a space or a newline in it intact.
BASH_FLOOR_MAJOR=4
BASH_FLOOR_MINOR=4

require_bash() {
	if ((BASH_VERSINFO[0] > BASH_FLOOR_MAJOR)); then
		return 0
	fi
	if ((BASH_VERSINFO[0] == BASH_FLOOR_MAJOR && BASH_VERSINFO[1] >= BASH_FLOOR_MINOR)); then
		return 0
	fi
	echo "ERROR: bash ${BASH_FLOOR_MAJOR}.${BASH_FLOOR_MINOR}+ is required; this is ${BASH_VERSION}." >&2
	echo "       On macOS: brew install bash, or run the scripts under Homebrew's bash." >&2
	exit 1
}

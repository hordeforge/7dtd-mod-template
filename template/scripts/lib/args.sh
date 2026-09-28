# shellcheck shell=bash
# The command line every script in this directory answers to: -h and --help
# print the script's usage on stdout and exit 0, and an argument the script
# does not take is a usage error (usage on stderr, exit 2). Sourced, never
# executed.
#
# A script that ignores its arguments cannot answer a question about them:
# `scripts/build.sh --help` staged a modlet instead of printing help, and
# `scripts/build.sh --dry-run` ran the full build and looked accepted. A
# mistyped flag that a tool silently drops is worse than one it refuses,
# because the run reports success over work nobody asked for.
#
# Exit 2 is reserved for the command line, exit 1 for a step that ran and
# failed, so a caller can tell "I asked wrongly" from "the work failed"
# without parsing a message.
#
# Usage: help_only <usage-fn> [args...]        # -h/--help only
#        parse_no_args <usage-fn> [args...]    # -h/--help, and refuse the rest

# help_only <usage-fn> [args...]
# Handles -h and --help and leaves every other argument to the caller, which
# is the script that knows what its own arguments mean.
help_only() {
	local usage_fn="$1"
	shift
	case "${1:-}" in
	-h | --help)
		"$usage_fn"
		exit 0
		;;
	esac
}

# parse_no_args <usage-fn> [args...]
# For a script whose whole command line is "run it". The error names the
# argument that was not taken, so the caller does not have to guess which of
# the three it was.
parse_no_args() {
	local usage_fn="$1"
	shift
	case "${1:-}" in
	-h | --help)
		"$usage_fn"
		exit 0
		;;
	"") return 0 ;;
	esac
	echo "ERROR: $(basename "${0##*/}") takes no arguments; got '$1'." >&2
	"$usage_fn" >&2
	exit 2
}

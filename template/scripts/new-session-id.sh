#!/usr/bin/env bash
# Generate a unique parallel-session ID: PREFIX-UTC_TIMESTAMP-RANDOM_SUFFIX.
#
# Usage: scripts/new-session-id.sh PREFIX
#        scripts/new-session-id.sh --help
set -euo pipefail

usage() {
	cat <<'HELP'
Generate a unique parallel-session ID.

USAGE
  scripts/new-session-id.sh PREFIX
  scripts/new-session-id.sh --help

PREFIX
  Lowercase agent-family name: e.g. claude, codex.

OUTPUT
  PREFIX-UTC_TIMESTAMP-RANDOM_SUFFIX, on stdout.

EXIT STATUS
  0  the id was printed, or usage was shown
  2  wrong arguments, or PREFIX is not a lowercase word

Use the generated value when claiming a TODO task. The ID records the active
session; it does not replace the task's [-] ownership marker.
HELP
}

case "${1:-}" in
-h | --help)
	usage
	exit 0
	;;
esac

if (($# != 1)); then
	usage >&2
	exit 2
fi

prefix="$1"
if [[ ! "$prefix" =~ ^[a-z][a-z0-9]*$ ]]; then
	echo "ERROR: PREFIX must start with a lowercase letter and contain only lowercase letters and digits." >&2
	exit 2
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
suffix="$(od -vAn -N6 -tx1 /dev/urandom | tr -d '[:space:]')"
printf '%s-%s-%s\n' "$prefix" "$timestamp" "$suffix"

#!/usr/bin/env bash
# Shellcheck gate over every tracked shell script in this mod.
#
# README's "Host tools" lists shellcheck as required; this script is where
# that requirement is actually enforced. Runs at full severity (style
# included).
#
# Usage: scripts/lint-shell.sh [--help]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
	cat <<'HELP'
Run shellcheck at full severity over every tracked shell script.

USAGE
  scripts/lint-shell.sh

OPTIONS
  -h, --help  show this help and exit

EXIT STATUS
  0  shellcheck found nothing
  1  shellcheck reported findings, or it is not installed
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

# shellcheck source=lib/lint-gate.sh
source "$SCRIPT_DIR/lib/lint-gate.sh"

# SCRIPTDIR lets each script's `source=` directives resolve against its own
# directory while -x follows them, so cross-file variables are visible.
lint_gate shellcheck '*.sh' "shell scripts" -x --severity=style --source-path=SCRIPTDIR

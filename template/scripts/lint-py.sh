#!/usr/bin/env bash
# Ruff gate over every tracked Python script in this mod.
#
# README's "Host tools" lists ruff as required; this script is where that
# requirement is actually enforced. The rule set lives in ruff.toml at the
# mod root, so the gate and the config cannot drift apart.
#
# Usage: scripts/lint-py.sh [--help]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
	cat <<'HELP'
Run ruff over every tracked Python script, under the mod's own ruff.toml.

USAGE
  scripts/lint-py.sh

OPTIONS
  -h, --help  show this help and exit

EXIT STATUS
  0  ruff found nothing
  1  ruff reported findings, or it is not installed
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

# shellcheck source=lib/lint-gate.sh
source "$SCRIPT_DIR/lib/lint-gate.sh"

# --config points at the mod's own ruff.toml explicitly so the gate runs the
# checked-in rule set even when invoked from another directory.
lint_gate ruff '*.py' "Python scripts" check --config "$MOD_DIR/ruff.toml"

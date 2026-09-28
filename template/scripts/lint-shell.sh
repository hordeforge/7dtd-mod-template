#!/usr/bin/env bash
# Shellcheck gate over every tracked shell script in this mod.
#
# README's "Host tools" lists shellcheck as required; this script is where
# that requirement is actually enforced. Runs at full severity (style
# included).
#
# Usage: scripts/lint-shell.sh
set -euo pipefail

# shellcheck source=lib/lint-gate.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/lint-gate.sh"

# SCRIPTDIR lets each script's `source=` directives resolve against its own
# directory while -x follows them, so cross-file variables are visible.
lint_gate shellcheck '*.sh' "shell scripts" -x --severity=style --source-path=SCRIPTDIR

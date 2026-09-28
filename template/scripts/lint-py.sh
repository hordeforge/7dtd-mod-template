#!/usr/bin/env bash
# Ruff gate over every tracked Python script in this mod.
#
# README's "Host tools" lists ruff as required; this script is where that
# requirement is actually enforced. The rule set lives in ruff.toml at the
# mod root, so the gate and the config cannot drift apart.
#
# Usage: scripts/lint-py.sh
set -euo pipefail

# shellcheck source=lib/lint-gate.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/lint-gate.sh"

# --config points at the mod's own ruff.toml explicitly so the gate runs the
# checked-in rule set even when invoked from another directory.
lint_gate ruff '*.py' "Python scripts" check --config "$MOD_DIR/ruff.toml"

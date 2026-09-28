#!/usr/bin/env bash
# Run one live suite through hordeforge/7dtd-playtest. A thin wrapper: the
# orchestrator, the machine-wide client lock, and the suite JSON contract all
# live upstream (docs/reference/sibling-tooling.md); this file only resolves
# the upstream checkout from .local.env and forwards the suite id.
#
# One invocation is one concern. A comma-list is refused upstream unless it is
# declared with PLAYTEST_CONCERN_SUITES holding exactly the same tokens, so
# unrelated features are separate runs.
#
# Usage: make playtest SUITE=<one-id> [EXTRA_ARGS=<playtest_run.py flags>]
#        scripts/playtest.sh <one-id> [extra playtest_run.py flags]
#
# Exit status: 0 the suite passed, 1 the run or its prerequisites failed,
# 2 no suite was named.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# .local.env holds PLAYTEST_ROOT, PLAYTEST_SUITE and PLAYTEST_SUITE_FILE, so
# it is loaded before any of them is read and unconditionally: loading is
# skipped for a key already in the environment, and loading it only when
# PLAYTEST_ROOT happened to be unset left the other two documented keys
# unreachable from the file. Nothing here needs a suite to be named, so a
# `.local.env` that cannot be parsed is still reported.
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"
load_local_env "$ROOT"

suite="${1:-${SUITE:-${PLAYTEST_SUITE:-}}}"
if (($#)); then
	shift
fi
if [[ -z "$suite" ]]; then
	echo "usage: make playtest SUITE=<one-id> [EXTRA_ARGS=<playtest_run.py flags>]" >&2
	exit 2
fi

if [[ -z "${PLAYTEST_ROOT:-}" ]]; then
	echo "ERROR: set PLAYTEST_ROOT in .local.env (or the environment)." >&2
	exit 1
fi

runner="$PLAYTEST_ROOT/scripts/playtest_run.py"
if [[ ! -f "$runner" ]]; then
	echo "ERROR: no 7dtd-playtest checkout at $PLAYTEST_ROOT." >&2
	exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
	echo "ERROR: uv is required to run 7dtd-playtest (its own toolchain)." >&2
	exit 1
fi

args=(--suite "$suite")
# A suite of this mod's own is a JSON file beside it; without this the run
# would fall back to the upstream built-ins and report a suite it never ran.
if [[ -z "${PLAYTEST_SUITE_FILE:-}" && -f "$ROOT/suites/$suite.json" ]]; then
	args+=(--suite-file "$ROOT/suites/$suite.json")
fi

cd "$PLAYTEST_ROOT"
exec uv run --locked --project . python scripts/playtest_run.py "${args[@]}" "$@"

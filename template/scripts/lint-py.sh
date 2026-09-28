#!/usr/bin/env bash
# Ruff gate over every tracked Python script in this mod.
#
# README's "Host tools" lists ruff as required; this script is where that
# requirement is actually enforced. The rule set lives in ruff.toml at the
# mod root, so the gate and the config cannot drift apart. Tracked files
# only: untracked scratch under .local/, dist/, etc. never blocks the gate.
#
# Usage: scripts/lint-py.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

command -v ruff >/dev/null 2>&1 || {
	echo "ERROR: ruff not found; run your package manager." >&2
	exit 1
}
command -v git >/dev/null 2>&1 || {
	echo "ERROR: git not found; it is required to enumerate tracked scripts." >&2
	exit 1
}

cd "$MOD_DIR"
scripts=()
while IFS= read -r file; do
	[[ -n "$file" ]] && scripts+=("$file")
done < <(git ls-files '*.py')

if (( ${#scripts[@]} == 0 )); then
	echo "ERROR: no tracked Python scripts found under $MOD_DIR." >&2
	exit 1
fi

echo "ruff over ${#scripts[@]} tracked scripts"
# --config points at the mod's own ruff.toml explicitly so the gate runs the
# checked-in rule set even when invoked from another directory.
exec ruff check --config "$MOD_DIR/ruff.toml" "${scripts[@]}"

# shellcheck shell=bash
# The shared body of the lint gates (scripts/lint-shell.sh, scripts/lint-py.sh):
# require the tool, enumerate tracked files by extension, fail loud when that
# list is empty, and exec the tool over it. Sourced, never executed.
#
# Both checks live here because every gate needs them, and a gate that skips
# one is wrong in a way that reads as a pass: without the git check a clone
# that has no git reports "no tracked scripts" instead of "install git", and
# without the empty-list check an linter reports success over zero files, a
# green gate that checked nothing.
#
# Tracked files only, so untracked scratch under .local/, dist/, etc. never
# blocks a gate.
#
# Usage: lint_gate TOOL GIT_GLOB NOUN [TOOL_ARGS...]

# The mod root, for the callers' tool_args and the error message below.
MOD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

lint_gate() {
	local tool="$1" git_glob="$2" noun="$3"
	shift 3

	command -v "$tool" >/dev/null 2>&1 || {
		echo "ERROR: $tool not found; run your package manager." >&2
		exit 1
	}
	command -v git >/dev/null 2>&1 || {
		echo "ERROR: git not found; it is required to enumerate tracked scripts." >&2
		exit 1
	}

	# `set -e` lives in the caller, not here, so the cd carries its own guard.
	cd "$MOD_DIR" || exit 1
	local scripts=()
	while IFS= read -r file; do
		[[ -n "$file" ]] && scripts+=("$file")
	done < <(git ls-files "$git_glob")

	if (( ${#scripts[@]} == 0 )); then
		echo "ERROR: no tracked $noun found under $MOD_DIR." >&2
		exit 1
	fi

	echo "$tool over ${#scripts[@]} tracked $noun"
	exec "$tool" "$@" "${scripts[@]}"
}

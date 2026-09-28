#!/usr/bin/env bash
# Prove the package is reproducible instead of asserting it: build and zip the
# modlet three times and require the three archives to be byte-identical.
#
#   1. in place, no SOURCE_DATE_EPOCH -> package.sh falls back to the last commit
#   2. in place, that commit time     -> the fallback is the value it claims to be
#   3. a copy at a different absolute path, no git, a Turkish locale and a
#      Tokyo clock, that same epoch  -> nothing about where or who built it
#      reaches the archive
#
# Run 1 vs 2 fails when the git fallback drifts. Run 2 vs 3 fails when a build
# path, the caller's locale, or the caller's timezone reaches the artifact, and
# it is the pass that covers the DLL (`PathMap`) rather than believing it. A
# mismatch names the differing hashes and, when diffoscope is installed, what
# differs inside the two archives.
#
# Usage: scripts/verify-reproducible.sh [--help]
set -euo pipefail

export LC_ALL=C
export TZ=UTC

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
	cat <<'HELP'
Build and zip the modlet three times and require byte-identical archives.

USAGE
  scripts/verify-reproducible.sh

OPTIONS
  -h, --help  show this help and exit

EXIT STATUS
  0  the three archives are byte-identical
  1  a packaging pass failed, or the archives differ
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

MOD_NAME="__MOD_NAME__"
ARCHIVE="$ROOT/dist/$MOD_NAME.zip"
KEPT="$ROOT/dist/$MOD_NAME.pinned.zip"

# what build.sh stages, plus the scripts that stage it, the sources, and the
# machine-local path inventory the C# build reads. .git and dist are left out
# on purpose: the third pass must be a tree with no commit to read a timestamp
# from, which is what an exported source tree looks like.
TREE=(ModInfo.xml README.txt CHANGELOG.md .local.env Config Prefabs Resources
	UIAtlases WebMod src scripts)

if command -v sha256sum >/dev/null 2>&1; then
	digest() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
	digest() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
	echo "ERROR: neither sha256sum nor shasum found; a hash is how two archives are compared." >&2
	exit 1
fi

if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
	COMMIT_EPOCH="$(git -C "$ROOT" log -1 --pretty=%ct)"
else
	echo "ERROR: $ROOT is not a git checkout; the package has no timestamp source." >&2
	exit 1
fi

# One staging + zip pass in the environment the caller set. The environment is
# never defaulted here: pass 1 has to see SOURCE_DATE_EPOCH unset. Each step is
# checked rather than left to errexit, which a command substitution does not
# carry into the subshell this runs in: an unchecked failure would go on to
# hash an archive that was never written.
variant() { # variant <mod-root> <label>
	# stderr: the return value is the hash, captured by a command substitution
	echo "-- packaging ($2)" >&2
	"$1/scripts/build.sh" >/dev/null || return 1
	"$1/scripts/package.sh" >/dev/null || return 1
	digest "$1/dist/$MOD_NAME.zip" || return 1
}

# A second tree at a different absolute path, with no .git, built by a caller
# whose locale and timezone are neither C nor UTC.
elsewhere="$(mktemp -d)"
# The scratch tree never outlives this script, so the machine-local path
# inventory copied into it is removed with it.
trap 'rm -rf "$elsewhere"' EXIT
mkdir -p "$elsewhere/$MOD_NAME"
for entry in "${TREE[@]}"; do
	if [[ -e "$ROOT/$entry" ]]; then
		cp -R "$ROOT/$entry" "$elsewhere/$MOD_NAME/$entry"
	fi
done

from_git="$(variant "$ROOT" 'SOURCE_DATE_EPOCH unset, git fallback')" ||
	{ echo "ERROR: a packaging pass failed; nothing was compared." >&2; exit 1; }

from_pinned="$(SOURCE_DATE_EPOCH="$COMMIT_EPOCH" variant "$ROOT" "SOURCE_DATE_EPOCH=$COMMIT_EPOCH")" ||
	{ echo "ERROR: a packaging pass failed; nothing was compared." >&2; exit 1; }
# Kept for diffoscope, and so a failing run leaves the two archives to look at.
cp "$ARCHIVE" "$KEPT"

# A locale whose collation is not C's ('I' and 'ı' sort apart in tr_TR) and a
# timezone that puts DOS timestamps a day off UTC. The locale is whichever of
# the candidates the host actually has, so the pass never warns about a locale
# that is not installed; C.UTF-8 is the honest last resort and the label says
# which one ran. The subshell keeps both off the later steps.
FOREIGN_LOCALE=''
for candidate in tr_TR.UTF-8 tr_TR.utf8 de_DE.UTF-8 de_DE.utf8 C.UTF-8 C.utf8; do
	if locale -a 2>/dev/null | grep -qixF "$candidate"; then
		FOREIGN_LOCALE="$candidate"
		break
	fi
done
: "${FOREIGN_LOCALE:=C}"
FOREIGN_TZ=Asia/Tokyo

from_elsewhere="$(
	export LC_ALL="$FOREIGN_LOCALE" TZ="$FOREIGN_TZ" SOURCE_DATE_EPOCH="$COMMIT_EPOCH"
	variant "$elsewhere/$MOD_NAME" "$elsewhere, no git, $FOREIGN_LOCALE / $FOREIGN_TZ"
)" ||
	{ echo "ERROR: a packaging pass failed; nothing was compared." >&2; exit 1; }

fail=0
if [[ "$from_git" != "$from_pinned" ]]; then
	echo "FAIL: the git timestamp fallback does not match SOURCE_DATE_EPOCH=$COMMIT_EPOCH" >&2
	echo "      git fallback: $from_git" >&2
	echo "      explicit:     $from_pinned" >&2
	fail=1
fi
if [[ "$from_pinned" != "$from_elsewhere" ]]; then
	echo "FAIL: the archive depends on the build path, the locale, or the timezone" >&2
	echo "      in place:                 $from_pinned" >&2
	echo "      $FOREIGN_LOCALE / $FOREIGN_TZ: $from_elsewhere" >&2
	fail=1
fi

if (( fail )); then
	if command -v diffoscope >/dev/null 2>&1; then
		# "-" is diffoscope's stdout report; as a file name it eats path2.
		diffoscope --text - "$KEPT" "$elsewhere/$MOD_NAME/dist/$MOD_NAME.zip" || true
	fi
	echo "Kept $KEPT for comparison." >&2
	exit 1
fi

rm -f "$KEPT"
echo "OK -> $ARCHIVE is byte-identical across the git fallback, an explicit epoch, and a foreign path, locale, and timezone"

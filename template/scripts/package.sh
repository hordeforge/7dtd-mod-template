#!/usr/bin/env bash
# Zip dist/<Name>/ into dist/<Name>.zip, byte-for-byte reproducible.
#
# Info-ZIP's recursive mode (`zip -r`) walks the tree in readdir order, stores
# each entry's own mtime, the staging user's uid/gid, and whatever permission
# bits the staging umask produced. Two builds of the same source then differ.
# This script fixes all four: entries are added in LC_ALL=C sorted order, every
# mtime is pinned to SOURCE_DATE_EPOCH, permissions are normalized, and -X drops
# the extra fields carrying uid/gid.
#
# SOURCE_DATE_EPOCH: taken from the environment when set, otherwise .local.env,
# otherwise the last commit's timestamp, otherwise a fixed constant (a copy
# outside git).
#
# Usage: scripts/package.sh   (after scripts/build.sh staged dist/<Name>/)
set -euo pipefail

# shellcheck source=lib/require-bash.sh
source "$(dirname "$0")/lib/require-bash.sh"
require_bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
	cat <<'HELP'
Zip dist/<Name>/ into dist/<Name>.zip, byte for byte reproducible.

USAGE
  scripts/package.sh

OPTIONS
  -h, --help  show this help and exit

EXIT STATUS
  0  the archive is written
  1  packaging failed, or the timestamp source is unusable
  2  wrong arguments
HELP
}

# shellcheck source=lib/args.sh
source "$SCRIPT_DIR/lib/args.sh"
parse_no_args usage "$@"

MOD_NAME="__MOD_NAME__"
STAGE="$ROOT/dist/$MOD_NAME"
ARCHIVE="$ROOT/dist/$MOD_NAME.zip"
# 2016-01-01T00:00:00Z, used when neither the environment nor git supplies a time.
FALLBACK_EPOCH=1451606400
# The zip entry timestamp is a 32-bit DOS date: 7 bits of year counted from
# 1980, so it cannot express 1980-01-01T00:00:00Z (315532800) or
# 2107-12-31T23:59:58Z (4354819198) and anything after. Info-ZIP does not
# reject an out-of-range mtime, it wraps it: 2107-12-31T23:59:59Z and
# 1970-01-01T00:00:01Z both land in the archive as 1980-01-01, and every
# epoch past the wrap lands on some other wrong date. A SOURCE_DATE_EPOCH
# outside the range therefore produces a reproducible but silently wrong
# archive, so it is rejected here rather than written.
MIN_DOS_EPOCH=315532800
MAX_DOS_EPOCH=4354819198

# shellcheck source=lib/server-common.sh
source "$ROOT/scripts/lib/server-common.sh"
# SOURCE_DATE_EPOCH is a documented .local.env key, so the file is read before
# the timestamp is resolved; an already-set value in the environment wins.
load_local_env "$ROOT"

# Info-ZIP writes DOS timestamps in local time and sorts in collation order,
# so a non-UTC or non-C environment alone changes the archive bytes.
export LC_ALL=C
export TZ=UTC

command -v zip >/dev/null 2>&1 || {
	echo "ERROR: zip not found; it is required to package the modlet." >&2
	exit 1
}
[[ -d "$STAGE" ]] || {
	echo "ERROR: $STAGE not staged; run 'make build' first." >&2
	exit 1
}
[[ -f "$STAGE/ModInfo.xml" ]] || {
	echo "ERROR: $STAGE/ModInfo.xml missing; a modlet without it does not load." >&2
	exit 1
}

if [[ -z "${SOURCE_DATE_EPOCH:-}" ]]; then
	if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
		SOURCE_DATE_EPOCH="$(git -C "$ROOT" log -1 --pretty=%ct)"
	else
		SOURCE_DATE_EPOCH="$FALLBACK_EPOCH"
	fi
fi
SOURCE_DATE_EPOCH_RAW="$SOURCE_DATE_EPOCH"
# decimal_uint, not a ^[0-9]+$ match: a leading zero is an octal prefix to the
# range check below, so `020260101` is read as octal and compared as a
# different date, and a digit run past 64 bits wraps into the range instead of
# being rejected.
SOURCE_DATE_EPOCH="$(decimal_uint "$SOURCE_DATE_EPOCH_RAW")" || SOURCE_DATE_EPOCH=""
[[ -n "$SOURCE_DATE_EPOCH" ]] || {
	echo "ERROR: SOURCE_DATE_EPOCH must be seconds since the epoch, got '$SOURCE_DATE_EPOCH_RAW'." >&2
	exit 1
}
if (( SOURCE_DATE_EPOCH < MIN_DOS_EPOCH || SOURCE_DATE_EPOCH > MAX_DOS_EPOCH )); then
	echo "ERROR: SOURCE_DATE_EPOCH $SOURCE_DATE_EPOCH is outside the range a zip entry can hold." >&2
	echo "       Use $MIN_DOS_EPOCH (1980-01-01T00:00:00Z) through $MAX_DOS_EPOCH (2107-12-31T23:59:58Z);" >&2
	echo "       past that the archive stores a wrapped, wrong timestamp without saying so." >&2
	exit 1
fi

# the archive is the only output: a stale entry can never survive a rebuild.
rm -f "$ARCHIVE"

# directories before files, both sorted: empty directories are entries too, and
# a fixed order removes the readdir dependence.
mapfile -d '' -t DIRS < <(cd "$STAGE" && find . -mindepth 1 -type d -print0 | sort -z)
mapfile -d '' -t FILES < <(cd "$STAGE" && find . -mindepth 1 -type f -print0 | sort -z)

# A symlink is neither a directory nor a file, so it is in neither list and
# was never named to zip: the archive silently shipped a smaller modlet than
# the one just built. Resolving links at staging time would follow one, so the
# link is refused here instead, where the report can name it.
LINK="$(cd "$STAGE" && find . -mindepth 1 -type l -print -quit)"
if [[ -n "$LINK" ]]; then
	echo "ERROR: $STAGE/${LINK#./} is a symlink; zip would leave it out of $ARCHIVE." >&2
	echo "       Replace it with the file it points at, then re-run." >&2
	exit 1
fi

set_mtime() { # set_mtime <epoch>; GNU touch first, BSD date -r after
	local epoch="$1" stamp
	if find . -mindepth 1 -exec touch -h -d "@$epoch" -- {} + 2>/dev/null; then
		return
	fi
	stamp="$(date -u -r "$epoch" +%Y%m%d%H%M.%S)"
	find . -mindepth 1 -exec touch -h -t "$stamp" -- {} +
}

(
	# zip runs from dist/ with the mod directory as the entry prefix, so the
	# archive extracts to Mods/__MOD_NAME__/ModInfo.xml rather than to
	# Mods/ModInfo.xml.
	cd "$STAGE"
	# Permissions and timestamps are set by one batched find per mode rather
	# than a chmod and a touch spawned per entry: the per-entry form costs two
	# process launches per staged file, and a mod shipping assets stages
	# thousands of them, which is minutes of fork/exec for a build step that
	# otherwise takes seconds. The archive bytes are the same either way (same
	# modes, same mtimes); only the number of processes differs.
	find . -mindepth 1 -type d -exec chmod 0755 -- {} +
	find . -mindepth 1 -type f -exec chmod 0644 -- {} +
	set_mtime "$SOURCE_DATE_EPOCH"

	cd "$ROOT/dist"
	entries=()
	for entry in ${DIRS[@]+"${DIRS[@]}"} ${FILES[@]+"${FILES[@]}"}; do
		entries+=("$MOD_NAME/${entry#./}")
	done
	# entries are listed explicitly, in the order fixed above; zip never
	# recurses, so nothing readdir-shaped reaches the archive.
	zip -X -q "$ARCHIVE" "${entries[@]}"
)

echo "OK -> $ARCHIVE"

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

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOD_NAME="__MOD_NAME__"
STAGE="$ROOT/dist/$MOD_NAME"
ARCHIVE="$ROOT/dist/$MOD_NAME.zip"
# 2016-01-01T00:00:00Z, used when neither the environment nor git supplies a time.
FALLBACK_EPOCH=1451606400

# shellcheck source=server-common.sh
source "$ROOT/scripts/server-common.sh"
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
[[ "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]] || {
	echo "ERROR: SOURCE_DATE_EPOCH must be seconds since the epoch, got '$SOURCE_DATE_EPOCH'." >&2
	exit 1
}

# the archive is the only output: a stale entry can never survive a rebuild.
rm -f "$ARCHIVE"

# directories before files, both sorted: empty directories are entries too, and
# a fixed order removes the readdir dependence.
mapfile -d '' -t DIRS < <(cd "$STAGE" && find . -mindepth 1 -type d -print0 | sort -z)
mapfile -d '' -t FILES < <(cd "$STAGE" && find . -mindepth 1 -type f -print0 | sort -z)

set_mtime() { # set_mtime <path> <epoch>; GNU touch first, BSD date -r after
	local path="$1" epoch="$2" stamp
	if touch -h -d "@$epoch" -- "$path" 2>/dev/null; then
		return
	fi
	stamp="$(date -u -r "$epoch" +%Y%m%d%H%M.%S)"
	touch -h -t "$stamp" -- "$path"
}

(
	# zip runs from dist/ with the mod directory as the entry prefix, so the
	# archive extracts to Mods/__MOD_NAME__/ModInfo.xml rather than to
	# Mods/ModInfo.xml.
	cd "$ROOT/dist"
	entries=()
	for entry in ${DIRS[@]+"${DIRS[@]}"} ${FILES[@]+"${FILES[@]}"}; do
		rel="${entry#./}"
		if [[ -d "$STAGE/$rel" ]]; then
			chmod 0755 -- "$STAGE/$rel"
		else
			chmod 0644 -- "$STAGE/$rel"
		fi
		set_mtime "$STAGE/$rel" "$SOURCE_DATE_EPOCH"
		entries+=("$MOD_NAME/$rel")
	done
	# entries are listed explicitly, in the order fixed above; zip never
	# recurses, so nothing readdir-shaped reaches the archive.
	zip -X -q "$ARCHIVE" "${entries[@]}"
)

echo "OK -> $ARCHIVE"

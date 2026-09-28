#!/usr/bin/env bash
# A second new-mod.sh run must converge, not nest a mod inside a mod.
#
# The scaffolder refuses a target that exists when it starts, but a run takes
# long enough (clone, substitution, git commit) that a second run started in
# that window passed the same check. `mv src dst` with an existing directory
# dst moves src *inside* it, so the second run reported OK over
# <target>/<Name>/<Name>/ModInfo.xml: a mod the game never loads, which no
# later run can clean up, and which reads as a finished scaffold.
#
# Three cases are pinned, because the fix has two parts and the sequential
# rerun alone only reaches the first:
#   1. a plain rerun onto a finished mod, refused before any work
#   2. a run whose target appears after that check, so only the verification
#      of the move itself can catch it (a stub `mv` stands in for the other
#      run and creates the target at the moment the real move would land)
#   3. a tool checkout interrupted mid-clone, which leaves a directory with
#      no .git in it that the run used to report as "Found"
#
# Usage: ci/scaffolder-rerun.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/.scratch/anvil-rerun"
MOD_NAME="RerunSmoke"

rm -rf "$WORK"
mkdir -p "$WORK/bin"

CONF="$WORK/rerun.conf"
{
	printf 'name="%s"\n' "$MOD_NAME"
	printf 'author="Rerun Smoke"\n'
	printf 'display_name="Rerun Smoke"\n'
	printf 'purpose="A mod scaffolded twice, to prove the second run changes nothing."\n'
	printf 'target_dir="%s/mod"\n' "$WORK"
	printf 'hordeforge_root="%s/hordeforge"\n' "$WORK"
	printf 'csharp="no"\n'
	printf 'assets="no"\n'
	printf 'clone="no"\n'
} > "$CONF"

MOD="$WORK/mod/$MOD_NAME"

fail() { # fail <message>
	echo "FAIL $1" >&2
	exit 1
}

# Contents, not mtimes: the point is that the rerun changed nothing.
fingerprint() { # fingerprint <dir>
	(cd "$1" && find . -path ./.git -prune -o -type f -print0 |
		LC_ALL=C sort -z | xargs -0 sha256sum) | sha256sum
}

# Any staging directory left in the tree is a rerun that did not clean up.
assert_no_stage() { # assert_no_stage <target-dir>
	local leftovers
	leftovers=$(find "$1" -maxdepth 1 -name '.anvil-stage-*' -print)
	[[ -z "$leftovers" ]] || fail "a staging directory was left behind: $leftovers"
}

if [[ -d "$MOD" ]]; then
	fail "$MOD already exists before the first run"
fi
"$ROOT/new-mod.sh" "$CONF" > "$WORK/first.log" 2>&1 ||
	{ tail -n 20 "$WORK/first.log" >&2; fail "the first scaffold did not succeed"; }
[[ -f "$MOD/ModInfo.xml" ]] || fail "the first run produced no $MOD/ModInfo.xml"
first_print=$(fingerprint "$MOD")

# 1. The sequential rerun, refused before any work is done.
set +e
"$ROOT/new-mod.sh" "$CONF" > "$WORK/second.log" 2>&1
second_status=$?
set -e
if (( second_status != 2 )); then
	tail -n 20 "$WORK/second.log" >&2
	fail "a rerun onto an existing target must exit 2, got $second_status"
fi
if [[ -d "$MOD/$MOD_NAME" ]]; then
	fail "the rerun nested a $MOD_NAME inside the mod"
fi
if [[ "$(fingerprint "$MOD")" != "$first_print" ]]; then
	fail "the refused rerun changed the mod's contents"
fi
assert_no_stage "$WORK/mod"

# 2. The race. The target does not exist when the run starts and appears at
# the moment the move would land, so the check before the move passes and
# only the verification after it can catch the other run.
RACE_CONF="$WORK/race.conf"
sed "s#^target_dir=.*#target_dir=\"$WORK/race\"#" "$CONF" > "$RACE_CONF"
RACE_TARGET="$WORK/race/$MOD_NAME"
# Resolved before this directory goes on PATH: inside the stub, PATH already
# leads with the stub, so looking `mv` up there finds the stub and execs it
# forever.
REAL_MV=$(command -v mv)
cat > "$WORK/bin/mv" <<STUB
#!/usr/bin/env bash
# Stand in for a concurrent scaffolder finishing first: create the target
# directory, with a marker a reader can tell apart from ours, immediately
# before the move that would have claimed it. Then do the real move.
set -e
for arg in "\$@"; do
	if [[ "\$arg" == "\$RACE_TARGET" ]]; then
		mkdir -p "\$RACE_TARGET"
		printf 'the other run\n' > "\$RACE_TARGET/MODINFO_MARKER"
		break
	fi
done
exec "$REAL_MV" "\$@"
STUB
chmod +x "$WORK/bin/mv"

set +e
PATH="$WORK/bin:$PATH" RACE_TARGET="$RACE_TARGET" \
	"$ROOT/new-mod.sh" "$RACE_CONF" > "$WORK/race.log" 2>&1
race_status=$?
set -e
if (( race_status != 2 )); then
	tail -n 20 "$WORK/race.log" >&2
	fail "a run that loses the race must exit 2, got $race_status"
fi
if [[ -d "$RACE_TARGET/$MOD_NAME" ]]; then
	fail "the losing run nested a $MOD_NAME inside the existing mod"
fi
if [[ "$(cat "$RACE_TARGET/MODINFO_MARKER" 2>/dev/null)" != "the other run" ]]; then
	fail "the losing run did not leave the mod that was already there"
fi
assert_no_stage "$WORK/race"
if ! grep -q 'already exists' "$WORK/race.log"; then
	fail "the losing run did not say the target already exists"
fi

# 3. A clone interrupted before it wrote .git leaves a bare directory. Every
# later gate reads PLAYTEST_ROOT and the other keys from it, so a run that
# reports "Found" for it leaves the mod pointed at a checkout with no tools
# in it and says nothing.
PARTIAL_CONF="$WORK/partial.conf"
sed -e "s#^target_dir=.*#target_dir=\"$WORK/partial-mod\"#" \
	-e "s#^hordeforge_root=.*#hordeforge_root=\"$WORK/partial\"#" \
	-e "s#^clone=.*#clone=\"yes\"#" "$CONF" > "$PARTIAL_CONF"
# The two healthy checkouts get a .git so the run finds them and stops; only
# 7dtd-playtest is the bare directory. Any other shape would send this gate
# to the network, which is not where a test of a directory's contents
# belongs.
mkdir -p "$WORK/partial/7dtd-asset-pipeline/.git"
mkdir -p "$WORK/partial/7dtd-engine-research/.git"
mkdir -p "$WORK/partial/7dtd-playtest"

"$ROOT/new-mod.sh" "$PARTIAL_CONF" > "$WORK/partial.log" 2>&1 ||
	{ tail -n 20 "$WORK/partial.log" >&2; fail "the partial-checkout run did not succeed"; }
if ! grep -q 'is not a git checkout' "$WORK/partial.log"; then
	fail "a directory with no .git was not reported as unusable"
fi
if grep -q 'Found 7dtd-playtest' "$WORK/partial.log"; then
	fail "a partial clone directory was reported as a checkout"
fi

rm -rf "$WORK"
echo "PASS a second new-mod.sh run converges: it refuses, nests nothing, and leaves the existing mod untouched"

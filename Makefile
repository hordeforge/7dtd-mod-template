# Verification for the template repo itself. A change to new-mod.sh or
# template/ is proven by scaffolding a modlet and running its gates, which is
# exactly what .github/workflows/ci.yml does. `make check` is that workflow,
# step for step, so a green run locally means green CI.
#
# The generated mod has its own Makefile (`make help` inside it); this one only
# covers Anvil.

ROOT := $(CURDIR)

# ci/smoke.conf is the one committed smoke config: clone=no, so no network and
# no sibling checkout, and it lands in the gitignored .scratch/.
SMOKE_CONF := ci/smoke.conf
SMOKE_MOD := .scratch/anvil-smoke/CiSmoke

# Bare `make` lists the targets instead of scaffolding.
.DEFAULT_GOAL := help

.DELETE_ON_ERROR:

.PHONY: help check preflight scaffold clean

help:
	@echo "Changing Anvil (the template repo, not a scaffolded mod):"
	@echo "  make check                   everything CI runs, in CI's order"
	@echo "  make preflight               report the missing host tools and stop"
	@echo "  make scaffold                re-scaffold the smoke mod into .scratch/"
	@echo "  make clean                   remove the scaffolded smoke mod and its zip"
	@echo ""
	@echo "Host tools: bash, make, git, python3, shellcheck, ruff, zip, unzip."
	@echo "In the scaffolded mod, make help lists that mod's own targets."

# Every host tool the workflow below shells out to. A tool missing here is the
# one thing CI installs for you and a clean clone does not, so it is named here
# rather than surfacing as a missing-binary error from a script three steps in.
preflight:
	@missing=; \
	for tool in bash make git python3 shellcheck ruff zip unzip; do \
		command -v "$$tool" >/dev/null 2>&1 || missing="$$missing $$tool"; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "ERROR: host tools not found on PATH:$$missing" >&2; \
		echo "       install them with your package manager, then re-run." >&2; \
		exit 1; \
	fi; \
	pinned="$$(sed -n 's/.*RUFF_VERSION: *"\(.*\)".*/\1/p' "$(ROOT)/.github/workflows/ci.yml")"; \
	if [ -z "$$pinned" ]; then \
		echo "ERROR: no RUFF_VERSION: \"...\" line in .github/workflows/ci.yml, so the" >&2; \
		echo "       pin this compares against could not be read and a local run" >&2; \
		echo "       would silently claim to match CI. Restore the line." >&2; \
		exit 1; \
	fi; \
	local="$$(ruff --version | sed 's/^ruff //')"; \
	if [ "$$pinned" != "$$local" ]; then \
		echo "WARNING: local ruff $$local, CI pins $$pinned; a rule the" >&2; \
		echo "         mod's ruff.toml selects can resolve differently, so a" >&2; \
		echo "         green local run is not the CI verdict." >&2; \
	fi

# A fresh tree every run: a stale .scratch/anvil-smoke must never be what makes
# the gates pass.
scaffold: preflight
	rm -rf "$(SMOKE_MOD)" "$(SMOKE_MOD).zip"
	./new-mod.sh "$(SMOKE_CONF)"

# Step-for-step .github/workflows/ci.yml. The env is set here, not only on the
# runner, so a local run is held to the same locale and timezone contract.
check: preflight scaffold
	# What the scaffolder made of the smoke config's text: XML-hostile
	# characters, an accented author name, a CJK sentence end. CI runs this
	# step first, before anything executes inside the mod, and so does this:
	# the mod's own gates write their caches into it, so a check that read
	# the tree afterwards could not tell a cache the scaffolder shipped from
	# one the run just made.
	LC_ALL=C TZ=UTC python3 ci/check-smoke-mod.py "$(SMOKE_MOD)" "$(SMOKE_CONF)"
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" test
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" lint-shell
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" lint-py
	# the release contract of this repo's own notes, which no scaffolded mod
	# can check: the file a tag is cut from
	LC_ALL=C TZ=UTC python3 ci/check-changelog.py CHANGELOG.md
	# new-mod.sh and ci/*.sh are not copied into the modlet, so the mod's own
	# lint-shell never sees them; they are this repo's unchecked shell scripts.
	shellcheck -x --severity=style new-mod.sh ci/*.sh
	# likewise ci/: the mod's lint-py runs over the mod's scripts, not over
	# this repo's. The modlet's rule set is the one this repo writes against.
	ruff check --config template/ruff.toml ci/
	# The packaging path without a game install: the DLL build needs one, so
	# drop src/ and prove dist/<Name>.zip still extracts to Mods/<Name>/.
	rm -rf "$(SMOKE_MOD)/src"
	$(MAKE) -C "$(SMOKE_MOD)" package
	unzip -l "$(SMOKE_MOD)/dist/CiSmoke.zip" | grep -q "CiSmoke/ModInfo.xml"
	# The last CI step, in the tree the step above leaves: no src/, so this
	# proves the archive the packaging path really builds is byte-identical
	# across a foreign path, locale, and timezone.
	$(MAKE) -C "$(SMOKE_MOD)" verify-reproducible
	# and the last one after it: a config value in an encoding that is not
	# UTF-8 has to scaffold as valid UTF-8.
	ci/scaffolder-encoding.sh
	# and the one after that: a purpose the 200 code-point description limit
	# cuts inside a character, a name that draws nothing, an author name
	# reaching the Harmony id.
	LC_ALL=C TZ=UTC python3 ci/scaffold-text.py
	@echo "OK -> every CI step passed locally."

clean:
	rm -rf "$(SMOKE_MOD)" "$(SMOKE_MOD).zip"

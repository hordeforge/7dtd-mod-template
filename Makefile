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
	@echo "  make clean                   remove the scaffolded smoke mod"
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
	fi

# A fresh tree every run: a stale .scratch/anvil-smoke must never be what makes
# the gates pass.
scaffold: preflight
	rm -rf "$(SMOKE_MOD)" "$(SMOKE_MOD).zip"
	./new-mod.sh "$(SMOKE_CONF)"

# Step-for-step .github/workflows/ci.yml. The env is set here, not only on the
# runner, so a local run is held to the same locale and timezone contract.
check: preflight scaffold
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" test
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" lint-shell
	LC_ALL=C TZ=UTC make -C "$(SMOKE_MOD)" lint-py
	# new-mod.sh is not copied into the modlet, so the mod's own lint-shell
	# never sees it; it is the one unchecked shell script in this repo.
	shellcheck -x --severity=style new-mod.sh
	# The packaging path without a game install: the DLL build needs one, so
	# drop src/ and prove dist/<Name>.zip still extracts to Mods/<Name>/.
	rm -rf "$(SMOKE_MOD)/src"
	$(MAKE) -C "$(SMOKE_MOD)" package
	unzip -l "$(SMOKE_MOD)/dist/CiSmoke.zip" | grep -q "CiSmoke/ModInfo.xml"
	@echo "OK -> every CI step passed locally."

clean:
	rm -rf .scratch/anvil-smoke

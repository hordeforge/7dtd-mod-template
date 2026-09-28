ROOT := $(CURDIR)

# Bare `make` lists the targets instead of starting a build that fails on
# a machine without a game install or a dotnet SDK.
.DEFAULT_GOAL := help

# a recipe that dies mid-way must not leave a half-written target behind
.DELETE_ON_ERROR:

.PHONY: help build package test lint-shell lint-py validate-xml verify-patched-config validate-patch-targets install-server deploy-server server-smoke clean build-assets validate-assets playtest

help:
	@echo "Offline gates (no game install needed; run these before every commit):"
	@echo "  make test                   every scripts/test_*.py must exit 0"
	@echo "  make test TF=<substring>    only the tests whose name matches (e.g. make test TF=telnet)"
	@echo "  make lint-shell             shellcheck, full severity"
	@echo "  make lint-py                ruff over every tracked Python script"
	@echo ""
	@echo "Modlet build (needs the game install in .local.env, plus a dotnet SDK for C#):"
	@echo "  make build                   stage dist/__MOD_NAME__/"
	@echo "  make package                 dist/__MOD_NAME__.zip, extracts to Mods/__MOD_NAME__/ModInfo.xml"
	@echo ""
	@echo "Install-dependent gates (need .local.env):"
	@echo "  make validate-xml            every Config xpath against the installed game"
	@echo "  make verify-patched-config   every patch element proven applied, from a save's ConfigsDump"
	@echo "  make validate-patch-targets  every [HarmonyPatch] target against Assembly-CSharp (ilspycmd)"
	@echo ""
	@echo "Dedicated-server lane (needs SEVEN_DAYS_TO_DIE_SERVER_DIR in .local.env):"
	@echo "  make install-server          provision the server via SteamCMD (EAC off)"
	@echo "  make deploy-server           stage the package into the server's Mods/"
	@echo "  make server-smoke            boot it briefly and prove the mod loaded from its log"
	@echo ""
	@echo "Live playtest (needs PLAYTEST_ROOT in .local.env; one run is one concern):"
	@echo "  make playtest SUITE=<id>     run one hordeforge/7dtd-playtest suite; EXTRA_ARGS=<flags>"
	@echo "                              adds playtest_run.py flags, e.g. --headed"
	@echo ""
	@echo "  make clean                   remove dist/ and the C# bin/ obj/"

# ANVIL:ASSETS-BEGIN
# help lines for the asset targets live in their own recipe so the whole
# block (markers included) is stripped from a mod without assets.
	@echo ""
	@echo "Asset bundles (shamway):"
	@echo "  make build-assets            build the asset bundles"
	@echo "  make validate-assets         validate bundles and icon sizes"
# ANVIL:ASSETS-END

# Offline contract/unit suite: every scripts/test_*.py must exit 0.
# Optional substring filters: make test TF="xml layout"
TF ?=
test:
	$(ROOT)/scripts/run-offline-tests.sh $(TF)

# Shellcheck over every tracked shell script (full severity).
lint-shell:
	$(ROOT)/scripts/lint-shell.sh

# Ruff over every tracked Python script, under the mod's own ruff.toml.
lint-py:
	$(ROOT)/scripts/lint-py.sh

# Stage the deployable modlet under dist/__MOD_NAME__/ (compiles the DLL
# when src/ exists; needs .local.env for the game install).
build:
	$(ROOT)/scripts/build.sh

# Zip dist/__MOD_NAME__/ so extracting into Mods/ yields
# Mods/__MOD_NAME__/ModInfo.xml immediately. Reproducible: sorted entry order,
# SOURCE_DATE_EPOCH timestamps, no uid/gid extra fields.
package: build
	$(ROOT)/scripts/package.sh

# Every Config/**/*.xml xpath checked against the installed game's vanilla
# files (needs .local.env; not part of the offline suite).
validate-xml:
	python3 $(ROOT)/scripts/validate-xml-targets.py

# Prove every shipped XPath actually applied, from a loaded world's own
# ConfigsDump (a patch matching nothing applies silently, log clean).
verify-patched-config:
	python3 $(ROOT)/scripts/verify-patched-config.py

# Every [HarmonyPatch] target re-checked against the installed
# Assembly-CSharp (needs .local.env and ilspycmd).
validate-patch-targets:
	python3 $(ROOT)/scripts/verify-patch-targets.py

# Dedicated-server lane (needs SEVEN_DAYS_TO_DIE_SERVER_DIR in .local.env):
# provision via SteamCMD with a mod-owned EAC-off serverconfig, stage the
# package into the server's Mods/, boot it briefly and prove the mod loaded.
install-server:
	$(ROOT)/scripts/install-server.sh

deploy-server:
	$(ROOT)/scripts/deploy-server.sh

server-smoke:
	$(ROOT)/scripts/server-smoke.sh

# One live suite through hordeforge/7dtd-playtest. One invocation is one
# concern: SUITE takes a single id, never a comma-list of unrelated features.
# PLAYTEST_ROOT comes from the ignored .local.env.
SUITE ?=
playtest:
	$(ROOT)/scripts/playtest.sh "$(SUITE)" $(EXTRA_ARGS)

# ANVIL:ASSETS-BEGIN
# Asset bundle build/validation via shamway (hordeforge/7dtd-asset-pipeline).
build-assets:
	cd $(ROOT) && shamway build

validate-assets:
	cd $(ROOT) && shamway validate
	cd $(ROOT) && shamway check-icons
# ANVIL:ASSETS-END

clean:
	rm -rf $(ROOT)/dist $(ROOT)/src/__MOD_NAME__/bin $(ROOT)/src/__MOD_NAME__/obj

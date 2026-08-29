ROOT := $(CURDIR)

.PHONY: build package test lint-shell validate-xml verify-patched-config validate-patch-targets install-server deploy-server server-smoke clean build-assets validate-assets

# Offline contract/unit suite: every scripts/test_*.py must exit 0.
# Optional substring filters: make test TF="xml layout"
TF ?=
test:
	$(ROOT)/scripts/run-offline-tests.sh $(TF)

# Shellcheck over every tracked shell script (full severity).
lint-shell:
	$(ROOT)/scripts/lint-shell.sh

# Stage the deployable modlet under dist/__MOD_NAME__/ (compiles the DLL
# when src/ exists; needs .local.env for the game install).
build:
	$(ROOT)/scripts/build.sh

# Zip dist/__MOD_NAME__/ so extracting into Mods/ yields
# Mods/__MOD_NAME__/ModInfo.xml immediately.
package: build
	cd $(ROOT)/dist && rm -f __MOD_NAME__.zip && zip -qr __MOD_NAME__.zip __MOD_NAME__
	@echo "OK -> dist/__MOD_NAME__.zip"

# Every Config/*.xml xpath checked against the installed game's vanilla
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

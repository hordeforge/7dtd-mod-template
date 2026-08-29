# 🔨 Anvil (7DTD Mod Template)

> **Part of [HordeForge](https://github.com/hordeforge)**: High-Performance Systems Engineering for 7 Days to Die.

![CI](https://github.com/hordeforge/7dtd-mod-template/actions/workflows/ci.yml/badge.svg)
![license](https://img.shields.io/github/license/hordeforge/7dtd-mod-template)

The forge tool every mod gets shaped on: a template for new 7 Days to Die
mods (XML/XPath modlets, optionally with a C#/Harmony DLL and custom asset
bundles). A mod scaffolded from Anvil starts with the full structure,
tooling, offline gates, documentation discipline, and agent working rules
that the HordeForge modding workspace converged on — with none of any
specific mod's content.

Scope is standard 7DTD mods only. ZDTD mods are templated separately;
WASM-plugin mods (`hordeforge/7dtd-wasm`) are out of scope while that ABI is
experimental.

## Scaffolding a new mod

```bash
cp newmod.conf.example mymod.conf   # fill in name, purpose, paths
./new-mod.sh mymod.conf
```

One run does the whole setup:

1. Resolves your local hordeforge checkout directory (or asks for one) and
   clones the missing tool repos the workflow needs — `7dtd-playtest`,
   `7dtd-asset-pipeline`, and optionally `7dtd-engine-research`.
2. Creates the mod directory from [`template/`](template/) with every
   name/author placeholder substituted. `csharp=yes` includes the net48
   Harmony DLL project; `assets=yes` includes the shamway asset targets.
3. Seeds the mod's stated purpose into its `README.md`, `docs/design.md`,
   and first `TODO.md` section, so an agent session can start from files
   alone.
4. Writes the resolved machine-local paths into the mod's ignored
   `.local.env` — tracked files never carry absolute paths.
5. `git init` + initial commit.

The config file is always passed as an argument — nothing is hardcoded, so
several configs can coexist (a committed `configs/` presets directory is the
natural later addition). Missing keys are prompted for interactively.

The generated mod passes its own `make test` and `make lint-shell` out of
the box; `make build` needs a configured game install in `.local.env`.

## Layout

```
7dtd-mod-template/
├── docs/            # shared, mod-agnostic 7DTD modding reference (vendored + generalized)
├── template/        # the modlet skeleton new-mod.sh instantiates
├── new-mod.sh       # the scaffolder
└── newmod.conf.example
```

Start at [`docs/README.md`](docs/README.md) for the reference material a
scaffolded mod indexes into; [`docs/best-practices.md`](docs/best-practices.md)
is the vendored canonical guide (sync it manually from
`hordeforge/.github/MODDING_BEST_PRACTICES.md` when upstream changes) and
[`docs/agent-rules.md`](docs/agent-rules.md) is its distilled, enforceable
core.

## What a scaffolded mod gets

- **Modlet shape** per the best-practices guide: `ModInfo.xml` at the mod
  root, `Config/` XPath patches (V3 `XUi_InGame` paths,
  `Config/Localization.csv`), a player-facing `README.txt`, optional
  `src/<Name>/` net48 C#, optional shamway-built assets, `dist/` packaging
  that extracts to `Mods/<Name>/ModInfo.xml`.
- **Offline gates**: `make test` runs every `scripts/test_*.py` — XML
  well-formedness and patch conventions, packaging layout, a stdlib Python
  defect-class gate over the mod's own scripts, the rules-have-gates
  meta-gate (incident rules name their gate; every gate runs twice,
  byte-identical), the session-id gate, and the upstream-tooling scan that
  stops the mod re-implementing what sibling hordeforge repos own.
  `make lint-shell` is full-severity shellcheck.
- **Install-dependent checks**: `make validate-xml` (every Config xpath
  against the installed game), `make verify-patched-config` (every shipped
  patch element proven applied from a loaded save's `ConfigsDump` — a patch
  matching nothing applies silently), `make validate-patch-targets` (every
  `[HarmonyPatch]` target and injected parameter against the installed
  Assembly-CSharp via ilspycmd), and a dedicated-server lane
  (`make install-server` / `deploy-server` / `server-smoke`: SteamCMD
  provision with a mod-owned EAC-off serverconfig, deploy, bounded boot,
  log proof the mod loaded).
- **Docs-as-memory**: `TODO.md` task queue with claim markers,
  `docs/design.md` / `docs/architecture.md` / `docs/adr/` decision records,
  and an `AGENTS.md` (+ `CLAUDE.md` importing it) carrying the working
  discipline — a fresh agent session resumes from files alone.
- **Tool integration by reference**: playtesting via `hordeforge/7dtd-playtest`
  (including its machine-wide client lock), asset builds via `shamway`
  (`hordeforge/7dtd-asset-pipeline`), engine facts via
  `hordeforge/7dtd-engine-research` — never vendored, never a required
  relative path.

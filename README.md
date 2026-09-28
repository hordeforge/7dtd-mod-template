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

## Quick start

```bash
gh repo clone hordeforge/7dtd-mod-template
cd 7dtd-mod-template
cp newmod.conf.example mymod.conf   # fill in name, purpose, target_dir
./new-mod.sh mymod.conf
```

`./new-mod.sh --help` lists what the config file may hold and what each
exit status means.

Then, in the generated mod: `make test`, `make lint-shell` and `make lint-py`
are green out of the box, and `make help` lists every target. `make build` / `make package`
produce the deployable modlet; they need the game install recorded in
`.local.env` and, for a C# mod, a .NET SDK on `PATH`.

One run does the whole setup:

1. Resolves your local hordeforge checkout directory (or asks for one) and
   clones the missing tool repos the workflow needs — `7dtd-playtest`,
   `7dtd-asset-pipeline`, and `7dtd-engine-research` (set `clone="no"` to
   skip this).
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
natural later addition). Missing keys are prompted for interactively, and a
prompt is asked again until the answer is usable.

## Changing Anvil

This repo has no build of its own: a change to `new-mod.sh` or `template/` is
proven by scaffolding a throwaway mod and running that mod's gates, which is
exactly what CI does. `make check` is that workflow, step for step, so a green
local run is a green CI run.

```bash
make check      # scaffold + every gate + the package layout check (~10s)
make help       # the targets above, and what they need
```

`make check` needs `bash`, `make`, `git`, `python3`, `shellcheck`, `ruff`,
`zip` and `unzip` on `PATH`; `make preflight` names whichever is missing before
the first step runs. Nothing is installed for you and no game install or .NET SDK is
needed, because the smoke config ([`ci/smoke.conf`](ci/smoke.conf)) sets
`clone="no"` and the package step proves the XML-only path. That config also
carries a display name and author full of `&`, `<` and quotes, an accented
letter and a Japanese first sentence, so
[`ci/check-smoke-mod.py`](ci/check-smoke-mod.py) proves the scaffold writes
them into `ModInfo.xml` intact on every run. To iterate on a
single gate, `make scaffold` once and then work inside
`.scratch/anvil-smoke/CiSmoke` with its own `make help` (`make test TF=<substring>`
runs one test).

## Versions and releases

Anvil's version is a git tag on `main`, and
[`CHANGELOG.md`](CHANGELOG.md) records what each one changed for a mod
scaffolded from an older tag. Cutting a tag moves what landed under
`Unreleased` into a dated `## [version]` section and leaves `Unreleased`
empty for the next change; `ci/check-changelog.py` holds the notes to that
shape and `make check` runs it. The template is `0.y.z` while the modlet's
interfaces still move; `1.0.0` is when they stop. Fixes land on `main`
through the normal branch-and-PR flow and are not backported, so a mod
scaffolded from a tag tracks that tag, not `main`.

Re-scaffolding a mod from a newer tag keeps the mod's own content, so the
changes that move its contract are the ones to read. They open with the
same marker, so the upgrade between two tags is one search:

```console
$ rg -F '**Breaking for a mod' CHANGELOG.md
```

A generated mod versions itself. `ModInfo.xml` is the single source of the
version, the first line of the mod's `README.txt` has to name the same value,
and both are gated against the mod's `CHANGELOG.md` by `make test`.

## Layout

```
7dtd-mod-template/
├── docs/            # shared, mod-agnostic 7DTD modding reference (vendored + generalized)
├── template/        # the modlet skeleton new-mod.sh instantiates
├── new-mod.sh       # the scaffolder
├── newmod.conf.example
├── Makefile         # `make check`: this repo's gates, which are CI's
└── CHANGELOG.md     # what each tag changed for a mod scaffolded from an older one
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
  byte-identical), the session-id gate, the decision-record gate behind
  `docs/adr/`, and the upstream-tooling scan that
  stops the mod re-implementing what sibling hordeforge repos own.
  `make lint-shell` is full-severity shellcheck, `make lint-py` is ruff
  over the mod's Python under the shipped `ruff.toml`.
- **Install-dependent checks**: `make validate-xml` (every Config xpath
  against the installed game), `make verify-patched-config` (every element
  the mod's `Config/` *inserts* counted in a loaded save's `ConfigsDump` — a
  patch matching nothing applies silently; `set`/`remove`/`csv` change a
  matched node and contribute no new element, so prove those in game),
  `make validate-patch-targets` (every
  `[HarmonyPatch]` target and injected parameter against the installed
  Assembly-CSharp via ilspycmd), and a dedicated-server lane
  (`make install-server` / `deploy-server` / `server-smoke`: SteamCMD
  provision with a mod-owned EAC-off serverconfig, deploy, bounded boot,
  log proof the mod loaded).
- **TOML runtime settings** (C# mods): `Config/<Name>.toml` read by the
  DLL from the installed mod folder through a shipped fail-loud TOML
  subset parser — hot-reloaded on save (debounced UnityUpdate watch,
  reset-to-defaults-then-apply, broken save keeps current values), with a
  console command (`settings|set|reload`) sharing one value grammar, and
  an `Applied` event for synced values or a future settings UI.
- **Docs-as-memory**: `TODO.md` task queue with claim markers,
  `docs/design.md` / `docs/architecture.md` / `docs/adr/` decision records,
  and an `AGENTS.md` (+ `CLAUDE.md` importing it) carrying the working
  discipline — a fresh agent session resumes from files alone.
- **Tool integration by reference**: playtesting via `hordeforge/7dtd-playtest`
  (including its machine-wide client lock), asset builds via `shamway`
  (`hordeforge/7dtd-asset-pipeline`), engine facts via
  `hordeforge/7dtd-engine-research` — never vendored, never a required
  relative path.

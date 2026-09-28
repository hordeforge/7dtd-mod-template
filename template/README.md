# __MOD_DISPLAY_NAME__

__MOD_PURPOSE__

A 7 Days to Die mod. Scaffolded from
[Anvil](https://github.com/hordeforge/7dtd-mod-template); the modlet is this
directory itself — `make build` stages the deployable copy under
`dist/__MOD_NAME__/`, `make package` zips it for release.

## Build and test

```bash
make test                   # offline gates (scripts/test_*.py)
make lint-shell             # shellcheck, full severity
make lint-py                # ruff over every tracked Python script
make build                  # stage dist/__MOD_NAME__/ (a DLL build needs .local.env, see below)
make package                # dist/__MOD_NAME__.zip — extracts to Mods/__MOD_NAME__/
make validate-xml           # every Config xpath against the installed game
make verify-patched-config  # every patch element proven applied, from a save's ConfigsDump
make validate-patch-targets # every [HarmonyPatch] target against Assembly-CSharp (ilspycmd)
make install-server         # provision the dedicated server via SteamCMD (EAC off)
make server-smoke           # deploy + boot the server briefly, prove the mod loaded
```

Host tools: `python3`, `git`, `make`, `shellcheck`, `ruff`, `zip`; a .NET SDK (`dotnet`
on PATH, `dotnet --list-sdks` prints one) for C# mods, `ilspycmd`
(`dotnet tool install -g ilspycmd`) for patch-target validation, `steamcmd`
for the dedicated-server lane. `make help` lists every target.

`make package` is reproducible: entries go in sorted order with
`SOURCE_DATE_EPOCH` timestamps, so the same source yields the same bytes
regardless of build path, locale, or timezone. Export `SOURCE_DATE_EPOCH` to
override the default (last git commit, else a fixed constant). The C# project
pins the SDK floor in `global.json` and maps build paths out of the DLL
(`PathMap`), so the DLL does not change with the build directory.

Machine-local paths (game install, hordeforge tool checkouts) live in the
ignored `.local.env` — copy `.local.env.example` and fill it in.

<!-- ANVIL:CSHARP-BEGIN -->
Runtime settings live in `Config/__MOD_NAME__.toml` in the installed mod
folder; saving it applies without a restart, and the in-game/telnet
command `__MOD_NAME_LOWER__` lists, changes, and reloads them.
<!-- ANVIL:CSHARP-END -->

## Live playtest

Live suites, when this mod has them, go through
[hordeforge/7dtd-playtest](https://github.com/hordeforge/7dtd-playtest).
One invocation is one concern: one suite id. The template ships no
playtest target, so the mod adds `playtest` to its `Makefile` as a thin
wrapper over the sibling tool (`PLAYTEST_ROOT` in `.local.env`).

```bash
make playtest SUITE=<one-id>
```

`playtest` is a target this mod adds to its Makefile together with its first
live suite (a thin wrapper over the runner in `$PLAYTEST_ROOT`, with this
mod's suite file — see [`AGENTS.md`](AGENTS.md) "One concern per playtest
run"). A mod with no live suite yet has no such target.

Do not comma-list unrelated ids on `SUITE=` / `PLAYTEST_SUITE`. Several
features are several invocations. A prefab in the camera (`*_look`) and
a block on a voxel (`*_block_*`) are never one run. See `AGENTS.md`
"One concern per playtest run" and the playtest README.

## Docs

- [`TODO.md`](TODO.md) — what's next
- [`docs/design.md`](docs/design.md) — gameplay decisions
- [`docs/architecture.md`](docs/architecture.md) — technical decisions ([`docs/adr/`](docs/adr/) for formal records)
- [`docs/reference/`](docs/reference/) — general 7DTD modding reference and best practices (binding)
- [`AGENTS.md`](AGENTS.md) — working instructions for agent sessions

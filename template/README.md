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
make build                  # stage dist/__MOD_NAME__/ (needs .local.env, see below)
make package                # dist/__MOD_NAME__.zip — extracts to Mods/__MOD_NAME__/
make validate-xml           # every Config xpath against the installed game
make verify-patched-config  # every patch element proven applied, from a save's ConfigsDump
make validate-patch-targets # every [HarmonyPatch] target against Assembly-CSharp (ilspycmd)
make install-server         # provision the dedicated server via SteamCMD (EAC off)
make server-smoke           # deploy + boot the server briefly, prove the mod loaded
```

Host tools: `python3`, `git`, `make`, `shellcheck`, `zip`; `dotnet` (net48
build) for C# mods, `ilspycmd` (`dotnet tool install -g ilspycmd`) for
patch-target validation, `steamcmd` for the dedicated-server lane.

Machine-local paths (game install, hordeforge tool checkouts) live in the
ignored `.local.env` — copy `.local.env.example` and fill it in.

Runtime settings live in `Config/__MOD_NAME__.toml` in the installed mod
folder; saving it applies without a restart, and the in-game/telnet
command `__MOD_NAME_LOWER__` lists, changes, and reloads them.

## Docs

- [`TODO.md`](TODO.md) — what's next
- [`docs/design.md`](docs/design.md) — gameplay decisions
- [`docs/architecture.md`](docs/architecture.md) — technical decisions ([`docs/adr/`](docs/adr/) for formal records)
- [`docs/reference/`](docs/reference/) — general 7DTD modding reference and best practices (binding)
- [`AGENTS.md`](AGENTS.md) — working instructions for agent sessions

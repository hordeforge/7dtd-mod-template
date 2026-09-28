# Threat Model: 7dtd-mod-template

Last reviewed: 2026-09-28
Owner: unassigned
Scope: this repository (the scaffolder and the template it instantiates). Generated
mods get their own model; every entry point below is reachable from a checkout here.

Nothing in this repository listens on a network socket. The interesting surface is
the other way round: shell and Python tooling that runs with the developer's own
authority, sources files as code, fetches and executes third-party checkouts, and
produces a DLL that is loaded with full process privileges inside a game client or
a dedicated server.

## Risk-ranked summary

| # | Threat | Boundary | Where | Severity |
|---|--------|----------|-------|----------|
| 1 | Config file is `source`d as shell, so a conf from anywhere is arbitrary code execution as the developer | operator to scaffolder | `new-mod.sh:31` | High |
| 2 | `.local.env` is `source`d as shell under `set -a`; anything that can write it runs as code on the next `make` | machine to build | `template/scripts/build.sh:20`, `template/scripts/server-common.sh:11` | High |
| 3 | Mod DLL executes with full game/server process authority, and a server config with EAC off is the shipped lane | build to runtime | `template/src/__MOD_NAME__/ModApi.cs:10`, `template/scripts/server-smoke.sh:30` | High |
| 4 | Sibling tool checkouts are cloned and then executed by `make` targets | tool chain to build | `new-mod.sh:65-76`, `template/Makefile:57-68` | Medium-High |
| 5 | Mod console command is admin-level and server-side; a player's own in-game console still runs it locally, mutating that client's copy of the settings | player to client process | `template/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs:25` | Low |
| 6 | Telnet console client has no peer authentication; the console password and every command go in cleartext to whatever answers on the port | network to tooling | `template/scripts/lib/game_telnet.py:60`, `:83` | Medium |
| 7 | `.local.env` is gitignored, and the scaffolder's `git add -A` runs after it is written, so machine paths and any future secret stay out of history | build to VCS | `new-mod.sh:192`, `template/.gitignore:5` | Controlled |
| 8 | `deploy-server.sh` runs `rm -rf` on a path built from an env-sourced directory; a wrong or hostile `SEVEN_DAYS_TO_DIE_SERVER_DIR` destroys a server tree | env to filesystem | `template/scripts/deploy-server.sh:30-45` | Medium |
| 9 | NuGet audit is switched off and no lockfile is committed, so restore-time dependency substitution is unobserved | build to dependency feed | `template/src/__MOD_NAME__/__MOD_NAME__.csproj:10` | Medium |
| 10 | CI checks out `actions/checkout` by mutable tag, and a pull request runs the PR's copy of the scaffolder | VCS to CI | `.github/workflows/ci.yml:23` | Low-Medium |
| 11 | Unvalidated `author`, `display_name` and `purpose` strings are written into tracked docs and the player-facing `README.txt` | operator to artifact | `new-mod.sh:126-156` | Low |
| 12 | Offline suite executes every `scripts/test_*.py` present, so a file dropped into the mod's scripts directory runs on `make test` | filesystem to build | `template/scripts/run-offline-tests.sh:31` | Low |

Nothing here is remotely exploitable without a position on the developer's machine
or a foothold in the mod folder. That is the honest blast radius: this is a
developer-workstation and server-hosting toolchain, not a service.

## 1. Attack surface inventory

Entry points, all with the file that creates them.

**Command line arguments**

- `new-mod.sh <config-file>`: the file is the first and only argument
  (`new-mod.sh:19-24`).
- `make` targets in `template/Makefile`: `build`, `package`, `test`, `lint-shell`,
  `lint-py`, `validate-xml`, `verify-patched-config`, `validate-patch-targets`,
  `install-server`, `deploy-server`, `server-smoke`, and the shamway asset targets
  behind the `ANVIL:ASSETS` markers.

**Sourced files (code, not data)**

- the operator-supplied conf (`new-mod.sh:31`).
- `.local.env` from the mod root, under `set -a` (`template/scripts/build.sh:20`,
  `template/scripts/server-common.sh:11`), written by `new-mod.sh:199-210`.

**Environment variables**

- `SEVEN_DAYS_TO_DIE_DIR`, `SEVEN_DAYS_TO_DIE_SERVER_DIR`,
  `SEVEN_DAYS_TO_DIE_SERVER_CONFIG` (`server-common.sh:4-34`).
- `SEVEN_DAYS_TO_DIE_STEAMCMD`, `SEVEN_DAYS_TO_DIE_STEAMCMD_DIR`
  (`server-common.sh:37-51`), `SEVEN_DAYS_TO_DIE_SERVER_APP_ID`
  (`install-server.sh:14`).
- `SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS`, the server-smoke window
  (`server-smoke.sh:12`).
- `OFFLINE_TEST_JOBS` (parallelism cap, `run-offline-tests.sh:51` and
  `scripts/test_rules_have_gates.py`, which re-runs every gate twice).
- `ANVIL_NAME`, `ANVIL_DISPLAY`, `ANVIL_AUTHOR`, `ANVIL_PURPOSE`,
  `ANVIL_SKIP_EAC`, `ANVIL_CSHARP`, `ANVIL_ASSETS` (`new-mod.sh:121-123`),
  consumed by the embedded substitution program.

**Network**

- outbound `git clone` / `gh repo clone` of three `hordeforge/*` repositories
  (`new-mod.sh:65-76`).
- outbound SteamCMD `+app_update` (anonymous login, `install-server.sh:17`), with
  the app id overridable from the environment.
- outbound NuGet restore during `dotnet build` (`build.sh:33`).
- outbound TCP to a dedicated server's telnet console, default `127.0.0.1:8081`
  (`game_telnet.py:28-29`, `:68`).
- inbound `pull_request` GitHub Actions runs, which execute this repository's
  shell scripts on a hosted runner (`.github/workflows/ci.yml:14-41`).

**Files parsed as input**

- `serverconfig.xml` from the server install (`configure-server-config.py:14`).
- every `Config/*.xml` and `ModInfo.xml` in the mod
  (`test_static_checks.py:22`, `validate-xml-targets.py:44`).
- `Config/<Mod>.toml` inside the installed mod folder, re-read on a 0.25 s poll
  (`ModSettings.cs:37`, `:66`).
- console command arguments (`ConsoleCmd__MOD_NAME__.cs:65`).
- the game install's managed assemblies, decompiled during target validation
  (`verify-patch-targets.py:203`).

**Deployment artifacts**

- `dist/<Mod>.zip` is extracted into the server's `Mods/` directory
  (`deploy-server.sh:18-45`), where the game loads every DLL it finds.
- the mod DLL is loaded into the client or dedicated server process
  (`ModApi.cs:10-23`).

## 2. Trust boundaries

**Operator to scaffolder.** The conf file crosses this boundary as an argument and
is then executed, not parsed (`new-mod.sh:31`). A conf is trusted exactly as much
as the shell that runs it.

**Machine state to build.** `.local.env` is documented as an ignored, machine-local
file, but it is `source`d. Writing to it is code execution on the next build.

**Build to runtime.** Everything in `dist/` is loaded into a game process with the
process's full authority. The DLL is not sandboxed and Harmony rewrites other
mods' code paths (`ModApi.cs:22`). Anything that can write to `dist/` or to the
installed `Mods/` folder controls a running client or server.

**Build to dependency feed.** The game install's `Assembly-CSharp.dll` and
`0Harmony.dll` are the compile-time reference set (`build.sh:28-34`); NuGet
supplies the rest. A tampered game install yields a tampered mod with no signal,
because audit is disabled (`__MOD_NAME__.csproj:10`).

**Tool chain to build.** `PLAYTEST_ROOT`, `CONNECT_ROOT` and
`ASSET_PIPELINE_ROOT` point at sibling checkouts whose scripts the `make` targets
invoke. They are trusted code with no pinning.

**Player to server process.** The console command surface is reachable by any
client that can issue a command, and the engine decides which of those
callers are allowed: `ConnectionManager.ServerConsoleCommand` applies
`AdminTools.CommandAllowedFor` before dispatch, and the template's command
states the admin level (0) itself rather than inheriting one, so a connected
player is refused. Telnet, stdin and the local in-game console skip that
gate by design, so what is left is a player running the command in their own
client process.

**Developer to network.** SteamCMD, GitHub and NuGet see the developer's IP and
credentials; the telnet client sends a console password in cleartext.

**VCS to CI.** A pull request runs the pull request's copy of `new-mod.sh` and the
generated mod's `make test` on a GitHub-hosted runner with no repository secrets
(the workflow uses `pull_request`, not `pull_request_target`).

## 3. Assets and impact

- **The dedicated server process.** A hostile mod DLL in `Mods/` owns the server:
  world state, player inventory, and every connected client's view. The shipped
  server lane also requires `EACEnabled=false` (`install-server.sh:31`,
  `server-smoke.sh:30`), so the process is explicitly not running the
  anti-cheat that would otherwise detect a modified client or server binary.
- **Server world saves and player data** under `SEVEN_DAYS_TO_DIE_SERVER_DIR`.
  `deploy-server.sh:30-45` deletes a subtree of that path, and
  `server-smoke.sh:15` writes a log into it. A wrong directory is unrecoverable.
- **Developer workstation filesystem**, reachable through the sourced conf, the
  sourced `.local.env`, and the cloned tool repos.
- **Build integrity.** The mod DLL players install. `Config/` XML patches alter
  item recipes, loot tables and crafting on every client that loads the mod, and
  ship to end users through the zip.
- **Reputation of the mod.** Every scaffolded mod inherits this template's
  defaults, so a defect here is copied into every generated repository.
- **Machine path inventory.** `.local.env` holds local filesystem layout. It is
  not a secret, but it is a reconnaissance aid, so it stays ignored
  (`template/.gitignore:5`).

## 4. Threats per boundary

**Operator to scaffolder (STRIDE)**
- *Elevation of privilege:* a conf file obtained from a colleague, a gist, or a
  chat message executes as the developer. `new-mod.sh:31` performs no validation
  before `source`.
- *Tampering:* `author` from the conf becomes the generated repository's
  `user.name` and `user.email` (`new-mod.sh:178-183`), attributing commits to
  the wrong identity.
- *Repudiation:* the initial scaffold commit is unsigned (`new-mod.sh:185`).

**Machine state to build (STRIDE)**
- *Elevation of privilege:* any process that can append one line to `.local.env`
  inherits execution on the next `make build`, `make deploy-server`, or
  `make server-smoke`.
- *Tampering:* `SEVEN_DAYS_TO_DIE_SERVER_DIR` decides what
  `deploy-server.sh:33-45` deletes and what `server-smoke.sh:41` executes.
- *Information disclosure:* `set -a` exports every value in `.local.env` into the
  environment of the build, where it reaches any child process.

**Build to runtime (STRIDE)**
- *Elevation of privilege:* a mod DLL runs with the game process's authority; on a
  dedicated server that is the whole server.
- *Tampering:* the TOML settings file is re-read live from the mod folder
  (`ModSettings.cs:37-42`), so write access to the install changes running server
  behavior without a restart and without a log line naming the writer.
- *Information disclosure:* `Describe()` prints every setting and current value
  to the console (`ConsoleCmd__MOD_NAME__.cs:69-74`). The operator channels
  (telnet, stdin) return it, and so does a player's own in-game console, which
  runs the command in that client's process with no level check; a client
  arriving over the network is refused by the permission level.

**Player to server process (STRIDE)**
- *Elevation of privilege:* the engine's permission check runs before a
  networked client's command is dispatched, and the command declares the admin
  level, so `set` and `reload` are refused for a connected player. The
  command is not client-executable (`:34`), so an admin who runs it from a
  client gets the server's values back rather than editing their own. The
  remaining path is the client's own local console, where the same command
  edits that client's copy of the settings; that reaches server behavior only
  through a mod whose own code reads the settings on the client. The shipped
  setting is a boolean and no shipped patch reads it, so today's impact is
  low; the class ships into every generated mod, where settings are likely to
  be more sensitive and client-side readers more likely.
- *Repudiation:* a settings change made through the console is not attributable to
  a player; the log line the mod emits carries the value, not the sender.

**Developer to network (STRIDE)**
- *Spoofing:* the telnet client connects to `host:port` with no peer identity
  check (`game_telnet.py:68`). Anything that answers on that port receives the
  console password (`:83-84`) and every subsequent command, and can return output
  the tooling treats as ground truth for the screenshot-driven checks. The
  docstring at `:15-18` accurately describes the game's loopback binding; it does
  not authenticate the client side of the connection.
- *Information disclosure:* the telnet password and the console session are
  cleartext whenever the host is not loopback.
- *Tampering:* the SteamCMD app id comes from the environment
  (`install-server.sh:14`), so a modified environment installs a different
  payload into `SEVEN_DAYS_TO_DIE_SERVER_DIR`.
- *Denial of service:* `dotnet restore` and the clone loop depend on reachability
  of third-party services with no retry ceiling other than the clone fallback
  warnings (`new-mod.sh:70-75`).

**VCS to CI (STRIDE)**
- *Tampering:* the workflow depends on `actions/checkout@v4` by tag
  (`.github/workflows/ci.yml:23`); a moved tag changes what runs.
- *Elevation of privilege:* a pull request executes the PR's own copy of
  `new-mod.sh` and the mod's test suite. The workflow uses `pull_request`, so no
  repository secrets are exposed, which bounds this to runner compute and
  runner egress.

**Parser boundary (STRIDE)**
- *Denial of service:* `xml.etree.ElementTree` expands internal entities without a
  limit, so a crafted `serverconfig.xml` (`configure-server-config.py:14`) or
  `Config/*.xml` (`test_static_checks.py:22`) is a memory-amplification vector.
  The reach is limited: these files come from a local install the developer
  already trusts, or from the mod's own tracked tree.

## 5. Mitigations mapping

Controls that exist in the code, with what each one actually covers.

| Control | Location | Covers |
|---------|----------|--------|
| Mod name restricted to `[A-Za-z][A-Za-z0-9_]*` before use | `new-mod.sh:48` | Closes shell injection through the one token that reaches `Makefile`, `build.sh:7` and `deploy-server.sh:18-19`. `display_name`, `author` and `purpose` are unvalidated but only reach docs and `README.txt`. |
| Existing mod directory refused | `new-mod.sh:55` | Prevents clobbering an existing tree by a mistyped name. |
| `SEVEN_DAYS_TO_DIE_SERVER_DIR` must be absolute and at least two levels deep | `server-common.sh:20-30` | Catches a relative path resolving somewhere unexpected, and a value like `/` or `/srv` that would make the server lane's deletes machine-wide. |
| `SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS` must be a positive integer, and the server runs under `timeout` with a kill-after | `server-smoke.sh:17-21`, `:40` | Bounds the server process; a runaway or hung server cannot outlive the target. |
| SteamCMD result verified (binary and `serverconfig.xml` present) | `install-server.sh:19-26` | A failed or partial download does not read as a good install. |
| `.local.env` gitignored, and the scaffolder's `git add -A` runs after the file is written | `template/.gitignore:5`, `new-mod.sh:192` | Keeps machine paths and anything later added there out of generated history. |
| `pull_request` rather than `pull_request_target` | `.github/workflows/ci.yml:5` | Keeps repository secrets out of pull-request CI. |
| `EACEnabled=false` required before server testing | `install-server.sh:31`, `server-smoke.sh:30` | A config that would keep the anti-cheat on is caught before a Harmony mod is loaded into it. It also *is* the reason the server lane has no anti-cheat; see threat 3. |
| `TreatWarningsAsErrors`, analyzers on, `DebugType=none` | `__MOD_NAME__.csproj:9-12` | No symbols shipped with the mod. |
| shellcheck over every tracked script, and the incident-to-gate harness | `lint-shell.sh`, `test_rules_have_gates.py` | Catches shell defects and rules that were written as prose only. |
| ruff over every tracked Python script under the shipped `ruff.toml`, blocking in CI | `lint-py.sh`, `ruff.toml` | Catches Python defects in the mod's own build-time tooling, which is the only code a mod author edits before any game code exists. |
| Deterministic gate harness: every AGENTS.md incident names a `test_*.py` | `test_rules_have_gates.py:29-35` | Keeps written rules from rotting into unenforceable prose. |
| Mod console command states the admin level and is not client-executable, with a gate over both | `ConsoleCmd__MOD_NAME__.cs:25`, `:34`, `test_console_command_permissions.py` | `AdminTools.CommandAllowedFor` refuses a connected player before dispatch, and an admin's run edits the server's settings rather than their own. |

Gaps, ranked by exploitability then impact. These are recorded here; the fixes
belong to code review, not to this document.

1. **Sourced-as-code conf and `.local.env`** (`new-mod.sh:31`, `build.sh:20`,
   `server-common.sh:11`). No format validation, no ownership or mode check on
   `.local.env`, no warning that it is executed rather than parsed.
2. **No peer authentication or TLS in the telnet client** (`game_telnet.py:60`,
   `:83`). The password is sent to whoever answered the port, and the returned
   text is trusted as game truth.
3. **Dependency substitution is unobserved**: `NuGetAudit=false`
   (`__MOD_NAME__.csproj:10`), no `packages.lock.json`, and the compile-time
   reference set is DLLs read out of a game install (`build.sh:28-34`).
5. **Destructive delete on an env-derived path** (`deploy-server.sh:30-45`). The path
   is only checked for being absolute, never for being a server directory that
   contains `7DaysToDieServer.x86_64` under the target `Mods/` subpath.
5. **Sibling checkouts execute without pinning** (`new-mod.sh:65-76`,
   `Makefile:56-60`). A moved branch or a compromised repository runs on the
   developer's machine.
7. **CI action not pinned to a commit** (`.github/workflows/ci.yml:23`).
8. **Unbounded XML entity expansion** on locally trusted files
   (`configure-server-config.py:14`, `test_static_checks.py:22`).
8. **A player's own in-game console runs any console command in their client
   process** (`ConsoleCmd__MOD_NAME__.cs:65`). The engine's level check covers
   the networked and web paths only; telnet, stdin and the local console are
   operator channels by design. A player can therefore rewrite their own
   copy of a mod's settings, which reaches server behavior only through a mod
   that reads them on the client.
9. **No audit trail for security-relevant events.** `server-smoke.sh` writes a
   server log, and the mod writes `[<Mod>] InitMod` to the game log
   (`ModApi.cs:15`), but there is no record of who deployed a package
   (`deploy-server.sh`), which conf produced a scaffold, or which console sender
   changed a setting.

Single points of failure worth naming: the shell execution of `.local.env`
carries threats 1, 4 and 7 at once, and one line there reaches every `make`
target. The mod DLL is the single artifact whose compromise yields full server
control.

## 6. Abuse cases

Scenarios, each with the enabling code path. None of these were executed; all are
read from the source.

- **A conf file shared in chat or a ticket runs on the next machine that uses
  it.** `new-mod.sh:31` sources whatever path was passed as `$1`, with no
  content check.
- **Anything that can append a line to `.local.env` owns the build.** A Makefile
  target, a test, a sibling tool, or a compromised editor plugin that writes once
  gets shell execution on the next `make build`, `make package` or
  `make deploy-server` (`build.sh:20`, `server-common.sh:11`).
- **A mis-set `SEVEN_DAYS_TO_DIE_SERVER_DIR` deletes the wrong tree.**
  `deploy-server.sh:30-45` removes and replaces `$SERVER_DIR/Mods/$MOD` on a path the
  environment supplies; the checks are that it is absolute and at least two
  levels deep (`server-common.sh:20-30`). The deploy itself is a staged swap
  from `$SERVER_DIR/.deploy-stage/`, never an in-place copy, and a failed swap
  puts the previous mod back.
- **A hostile client on a public server flips a mod setting and reloads.**
  `ConsoleCmd__MOD_NAME__.cs:40` accepts `set` and `reload` from any sender, and
  the resulting value is echoed back into the console for that client.
- **A process squatting on the console port harvests the password and forges
  output.** `game_telnet.py:68` connects to whatever is listening; `:83-84` sends
  the password; the screenshot checks consume the returned text as the game's
  answer, so forged output reads as a passing check.
- **A PR author's template change runs in CI.** `.github/workflows/ci.yml:24-31`
  scaffolds and tests the PR's own `template/`. No secrets are in scope, so the
  realistic abuse is runner compute and network egress from the runner.
- **A dropped `scripts/test_*.py` runs on `make test`.** The suite is a glob over
  the scripts directory (`run-offline-tests.sh:31`), so the test lane executes
  every Python file present in a mod that was cloned or copied from elsewhere.

## 7. Model and disclosure state

- This is the threat model. It has no risk ranking outside section 5's gap list
  and no owner; both need a person to fill in.
- **No `SECURITY.md` exists.** There is no disclosure contact, no supported
  versions list, and no documented path from "a vulnerability was reported" to
  "a fix shipped". `SECURITY.md` in this repository states that gap rather than
  inventing a contact.
- The model has no scheduled review cadence. Nothing in the repository triggers a
  re-read, and the entry points above will drift as templates gain targets; a
  re-read is needed whenever `new-mod.sh`, the `Makefile` targets, or
  `template/scripts/` change.

## 8. Response readiness

Not built, recorded so it is not mistaken for covered.

- The server log is the only artifact an incident can be reconstructed from
  (`server-smoke.sh:15`). There is no record of the conf that produced a
  scaffold, of who deployed a package (`deploy-server.sh`), or of the git
  identity a scaffold was committed under.
- There is no disclosure contact and no triage path, so a report has nowhere
  defined to go.
- No incident in this repository's history has yet produced a dated entry in
  `template/AGENTS.md`, so `test_rules_have_gates.py` has no security incident
  to enforce today. The gate exists and will fail if such a section is added
  without a deterministic check behind it.

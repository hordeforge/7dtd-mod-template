# Threat Model: 7dtd-mod-template

Last reviewed: 2026-09-28
Reference paths and parser controls refreshed: 2026-10-01. References name files and functions so code movement does not invalidate them.
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
| 1 | Config file is `source`d as shell, so a conf from anywhere is arbitrary code execution as the developer | operator to scaffolder | `new-mod.sh` | High |
| 2 | `.local.env` is `source`d as shell under `set -a`; anything that can write it runs as code on the next `make` | machine to build | `template/scripts/build.sh`, `template/scripts/lib/server-common.sh` | High |
| 3 | Mod DLL executes with full game/server process authority, and a server config with EAC off is the shipped lane | build to runtime | `template/src/__MOD_NAME__/ModApi.cs`, `template/scripts/server-smoke.sh` | High |
| 4 | Sibling tool checkouts are cloned and then executed by `make` targets | tool chain to build | `new-mod.sh`, `template/Makefile` | Medium-High |
| 5 | A player's own in-game console runs the admin-level, server-side console command in their own client process, mutating that client's copy of the settings | player to client process | `template/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs` | Low |
| 6 | Telnet console client has no peer authentication; the console password and every command go in cleartext to whatever answers on the port | network to tooling | `template/scripts/lib/game_telnet.py` | Medium |
| 7 | `.local.env` is gitignored and written `0600`, and the scaffolder's `git add -A` runs after it is written, so machine paths stay out of history and out of other accounts' reach | build to VCS | `new-mod.sh`, `template/.gitignore` | Controlled |
| 8 | `deploy-server.sh` derives its delete and swap target from an env-sourced `SEVEN_DAYS_TO_DIE_SERVER_DIR`; a wrong value reaches a real server tree's `Mods/` and `.deploy-stage/` | env to filesystem | `template/scripts/deploy-server.sh` | Low |
| 9 | NuGet audit is switched off and no lockfile is committed, so restore-time dependency substitution is unobserved | build to dependency feed | `template/src/__MOD_NAME__/__MOD_NAME__.csproj` | Medium |
| 10 | CI runs a pull request's own copy of the scaffolder, on runner compute and runner egress | VCS to CI | `.github/workflows/ci.yml` | Low |
| 11 | Unvalidated `author`, `display_name` and `purpose` strings are written into tracked docs and the player-facing `README.txt` | operator to artifact | `new-mod.sh` | Low |
| 12 | Offline suite executes every `scripts/test_*.py` present, so a file dropped into the mod's scripts directory runs on `make test` | filesystem to build | `template/scripts/run-offline-tests.sh` | Low |

Nothing here is remotely exploitable without a position on the developer's machine
or a foothold in the mod folder. That is the honest blast radius: this is a
developer-workstation and server-hosting toolchain, not a service.

## 1. Attack surface inventory

Entry points, all with the file that creates them.

**Command line arguments**

- `new-mod.sh <config-file>`: the file is the first and only argument
  (`new-mod.sh`).
- `make` targets in `template/Makefile`: `build`, `package`, `test`, `lint-shell`,
  `lint-py`, `validate-xml`, `verify-patched-config`, `validate-patch-targets`,
  `install-server`, `deploy-server`, `server-smoke`, and the shamway asset targets
  behind the `ANVIL:ASSETS` markers (`template/Makefile`).

**Sourced files (code, not data)**

- the operator-supplied conf, after its keys are checked against the known-key
  list (`new-mod.sh`, `new-mod.sh`).
- `.local.env` from the mod root, under `set -a`
  (`template/scripts/build.sh`, `template/scripts/lib/server-common.sh`),
  written by `new-mod.sh`.

**Environment variables**

- `SEVEN_DAYS_TO_DIE_DIR` (`build.sh`),
  `SEVEN_DAYS_TO_DIE_SERVER_DIR` and `SEVEN_DAYS_TO_DIE_SERVER_CONFIG`
  (`server-common.sh`).
- `SEVEN_DAYS_TO_DIE_STEAMCMD`, `SEVEN_DAYS_TO_DIE_STEAMCMD_DIR`
  (`server-common.sh`), `SEVEN_DAYS_TO_DIE_SERVER_APP_ID`
  (`install-server.sh`).
- `SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS`, the server-smoke window
  (`server-smoke.sh`).
- `OFFLINE_TEST_JOBS` (parallelism cap, `run-offline-tests.sh` and
  `scripts/test_rules_have_gates.py`, which re-runs every gate twice).
- `ANVIL_NAME`, `ANVIL_DISPLAY`, `ANVIL_AUTHOR`, `ANVIL_PURPOSE`,
  `ANVIL_SKIP_EAC`, `ANVIL_CSHARP`, `ANVIL_ASSETS` (`new-mod.sh`),
  consumed by the embedded substitution program.

**Network**

- outbound `git clone` / `gh repo clone` of three `hordeforge/*` repositories
  (`new-mod.sh`).
- outbound SteamCMD `+app_update` (anonymous login, `install-server.sh`),
  with the app id taken from the environment after a digits-only check
  (`install-server.sh`).
- outbound NuGet restore during `dotnet build` (`build.sh`).
- outbound TCP to a dedicated server's telnet console, default `127.0.0.1`
  (`game_telnet.py`).
- inbound `pull_request` GitHub Actions runs, which execute this repository's
  shell scripts on a hosted runner (`.github/workflows/ci.yml`).

**Files parsed as input**

- `serverconfig.xml` from the server install (`configure-server-config.py`).
- every `Config/*.xml` and `ModInfo.xml` in the mod
  (`test_static_checks.py`, `validate-xml-targets.py`).
- `Config/<Mod>.toml` inside the installed mod folder, re-read on a 0.25 s poll
  (`ModSettings.cs`).
- console command arguments (`ConsoleCmd__MOD_NAME__.cs`).
- the game install's managed assemblies, decompiled during target validation
  (`verify-patch-targets.py`).

**Deployment artifacts**

- `dist/<Mod>.zip` is extracted into the server's `Mods/` directory
  (`deploy-server.sh`), where the game loads every DLL it finds.
- the mod DLL is loaded into the client or dedicated server process
  (`ModApi.cs`).

## 2. Trust boundaries

**Operator to scaffolder.** The conf file crosses this boundary as an argument and
is then executed, not parsed (`new-mod.sh`). A conf is trusted exactly as much
as the shell that runs it. Unknown keys and a `csharp`/`assets`/`clone` value
outside `yes`/`no` are rejected first (`new-mod.sh`), which catches a typo
and nothing else.

**Machine state to build.** `.local.env` is documented as an ignored, machine-local
file, but it is `source`d. Writing to it is code execution on the next build. It is
written `0600` (`new-mod.sh`) and an unparseable read fails loud naming the
file (`server-common.sh`), so another local account cannot quietly edit it.

**Build to runtime.** Everything in `dist/` is loaded into a game process with the
process's full authority. The DLL is not sandboxed and Harmony rewrites other
mods' code paths (`ModApi.cs`). Anything that can write to `dist/` or to the
installed `Mods/` folder controls a running client or server.

**Build to dependency feed.** The game install's `Assembly-CSharp.dll` and
`0Harmony.dll` are the compile-time reference set (`build.sh`); NuGet
supplies the rest. A tampered game install yields a tampered mod with no signal,
because audit is disabled (`__MOD_NAME__.csproj`).

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
credentials; the telnet client sends a console password in cleartext and says so
on the wire's terminal when the host is not loopback (`game_telnet.py`).
A passwordless console is bound to loopback; setting a password moves the game's
listener to every interface (`game_telnet.py`), which is the configuration
where the cleartext warning matters.

**VCS to CI.** A pull request runs the pull request's copy of `new-mod.sh` and the
generated mod's `make test` on a GitHub-hosted runner with no repository secrets
(the workflow uses `pull_request`, not `pull_request_target`). The job holds
`contents: read`, drops the checkout token afterwards, and is capped at 20 minutes
(`.github/workflows/ci.yml`).

## 3. Assets and impact

- **The dedicated server process.** A hostile mod DLL in `Mods/` owns the server:
  world state, player inventory, and every connected client's view. The shipped
  server lane also requires `EACEnabled=false` (`install-server.sh`,
  `server-smoke.sh`), so the process is explicitly not running the
  anti-cheat that would otherwise detect a modified client or server binary.
- **Server world saves and player data** under `SEVEN_DAYS_TO_DIE_SERVER_DIR`.
  `deploy-server.sh` deletes a subtree of that path, and
  `server-smoke.sh` writes a log into it. A wrong directory is unrecoverable.
- **Developer workstation filesystem**, reachable through the sourced conf, the
  sourced `.local.env`, and the cloned tool repos.
- **Build integrity.** The mod DLL players install. `Config/` XML patches alter
  item recipes, loot tables and crafting on every client that loads the mod, and
  ship to end users through the zip.
- **Reputation of the mod.** Every scaffolded mod inherits this template's
  defaults, so a defect here is copied into every generated repository.
- **Machine path inventory.** `.local.env` holds local filesystem layout. It is
  not a secret, but it is a reconnaissance aid, so it stays ignored
  (`template/.gitignore`) and is written `0600` (`new-mod.sh`).

## 4. Threats per boundary

**Operator to scaffolder (STRIDE)**
- *Elevation of privilege:* a conf file obtained from a colleague, a gist, or a
  chat message executes as the developer. The key and flag checks at
  `new-mod.sh` run before the `source` at `new-mod.sh` and reject an
  unknown key or a non-`yes`/`no` flag, but a file whose every key is known and
  whose body is otherwise shell still runs as shell.
- *Tampering:* `author` from the conf becomes the generated repository's
  `user.name` and `user.email` when the machine has no global git identity
  (`new-mod.sh`), attributing commits to the wrong identity.
- *Repudiation:* the initial scaffold commit is unsigned (`new-mod.sh`).

**Machine state to build (STRIDE)**
- *Elevation of privilege:* any process that can append one line to `.local.env`
  inherits execution on the next `make build`, `make deploy-server`, or
  `make server-smoke`. The file's own `0600` mode (`new-mod.sh`) bounds that
  to the account and to anything already running as it.
- *Tampering:* `SEVEN_DAYS_TO_DIE_SERVER_DIR` decides what
  `deploy-server.sh` deletes and what `server-smoke.sh` runs under
  `timeout`.
- *Information disclosure:* `set -a` exports every value in `.local.env` into the
  environment of the build, where it reaches any child process.

**Build to runtime (STRIDE)**
- *Elevation of privilege:* a mod DLL runs with the game process's authority; on a
  dedicated server that is the whole server.
- *Tampering:* the TOML settings file is re-read live from the mod folder
  (`ModSettings.cs`), so write access to the install changes running
  server behavior without a restart and without a log line naming the writer.
- *Information disclosure:* `Describe()` prints every setting and current value
  to the console (`ConsoleCmd__MOD_NAME__.cs`). The operator channels
  (telnet, stdin) return it, and so does a player's own in-game console, which
  runs the command in that client's process with no level check; a client
  arriving over the network is refused by the permission level.

**Player to server process (STRIDE)**
- *Elevation of privilege:* the engine's permission check runs before a
  networked client's command is dispatched, and the command declares the admin
  level (`ConsoleCmd__MOD_NAME__.cs`), so `set` and `reload` are refused for a
  connected player. The command is not client-executable (that file), so an admin who
  runs it from a client gets the server's values back rather than editing their
  own. The remaining path is the client's own local console, where the same command
  edits that client's copy of the settings; that reaches server behavior only
  through a mod whose own code reads the settings on the client. The shipped
  setting is a boolean and no shipped patch reads it, so today's impact is
  low; the class ships into every generated mod, where settings are likely to
  be more sensitive and client-side readers more likely.
- *Repudiation:* a settings change made through the console is not attributable to
  a player; the log line the mod emits carries the value, not the sender.

**Developer to network (STRIDE)**
- *Spoofing:* the telnet client connects to `host:port` with no peer identity
  check (`game_telnet.py`). Anything that answers on that port receives the
  console password (that file) and every subsequent command, and can return output
  the tooling treats as ground truth for the screenshot-driven checks. The
  docstring at that file accurately describes the game's loopback binding; it does
  not authenticate the client side of the connection.
- *Information disclosure:* the telnet password and the console session are
  cleartext whenever the host is not loopback. The client resolves the host and
  warns once when it is not loopback (`game_telnet.py`); it
  sends the password anyway.
- *Tampering:* the SteamCMD app id comes from the environment and must be a
  positive integer (`install-server.sh`), so a modified environment
  installs a different app than intended into `SEVEN_DAYS_TO_DIE_SERVER_DIR`.
- *Denial of service:* `dotnet restore` and the clone loop depend on reachability
  of third-party services with no retry ceiling other than the clone fallback
  warnings (`new-mod.sh`).

**VCS to CI (STRIDE)**
- *Tampering:* the workflow's one action is pinned by commit rather than by tag
  (`.github/workflows/ci.yml`), and Dependabot (`.github/dependabot.yml`)
  opens the PR that carries a new tag's commit, so the pin is not a manual chore
  left to rot. The runner image itself is not pinned to a digest.
- *Elevation of privilege:* a pull request executes the PR's own copy of
  `new-mod.sh` and the mod's test suite. The workflow uses `pull_request`, so no
  repository secrets are exposed, and the job's grant is `contents: read` with
  `persist-credentials: false` (`.github/workflows/ci.yml`), which bounds this to runner compute and runner egress.

**Parser boundary (STRIDE)**
- *Denial of service:* all XML readers use `template/scripts/lib/safe_xml.py`
  (`parse` / `fromstring`), which rejects DTD and entity declarations before
  `xml.etree.ElementTree` parses a document. A crafted `serverconfig.xml` or
  `Config/*.xml` cannot reach entity expansion. `test_safe_xml.py` pins this
  refusal and the shared-parser use; the resolver fuzz gates independently
  bound the `Extends` chain, Harmony prefix parser and XPath resolver.

## 5. Mitigations mapping

Controls that exist in the code, with what each one actually covers.

| Control | Location | Covers |
|---------|----------|--------|
| Mod name restricted to `[A-Za-z][A-Za-z0-9_]*` before use | `new-mod.sh` | Closes shell injection through the one token that reaches `Makefile`, `build.sh` and `deploy-server.sh`. `display_name`, `author` and `purpose` are unvalidated but only reach docs and `README.txt`. |
| Conf keys checked against a known-key allowlist, and `csharp`/`assets`/`clone` must be `yes` or `no`, before the conf is sourced | `new-mod.sh` | Catches the misspelled key that would otherwise be set, read by nothing, and silently take the default. It does not make the conf data; the `source` at `new-mod.sh` still runs it. |
| Existing mod directory refused, and the tree is built in a staging directory then moved | `new-mod.sh` | Prevents clobbering an existing tree by a mistyped name, and leaves no half-written mod after an interrupted run. |
| `SEVEN_DAYS_TO_DIE_SERVER_DIR` must be absolute and at least two levels deep | `server-common.sh` | Catches a relative path resolving somewhere unexpected, and a value like `/` or `/srv` that would make the server lane's deletes machine-wide. |
| Deploy refuses a target that holds no `7DaysToDieServer.x86_64`, stages outside `Mods/`, and swaps with the previous copy restored on an interrupted run | `deploy-server.sh` | Bounds the delete to `$SERVER_DIR/.deploy-stage/<Mod>`, keeps a leftover stage from being loaded as a second mod, and leaves the previous deployment in place when the run dies between its two moves. The check is a file test, not an identity test; see gap 4. |
| `SEVEN_DAYS_TO_DIE_SERVER_APP_ID` must be a positive integer | `install-server.sh` | The value goes onto the SteamCMD command line, so anything but digits fails here rather than as an opaque SteamCMD error. |
| `SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS` must be a positive integer, and the server runs under `timeout` with a kill-after | `server-smoke.sh` | Bounds the server process; a runaway or hung server cannot outlive the target. |
| SteamCMD result verified (binary and `serverconfig.xml` present) | `install-server.sh` | A failed or partial download does not read as a good install. |
| `.local.env` written `0600`, gitignored, and the scaffolder's `git add -A` runs after the file is written | `new-mod.sh`, `template/.gitignore` | Keeps machine paths out of generated history and out of reach of other local accounts. |
| An unparseable `.local.env` read fails loud, naming the file | `server-common.sh` | A corrupt or hand-mangled file stops the build instead of exporting half its keys. |
| `pull_request` rather than `pull_request_target`, `contents: read`, `persist-credentials: false`, 20-minute cap | `.github/workflows/ci.yml` | Keeps repository secrets and the checkout token out of pull-request CI and bounds what a hung run costs. |
| `EACEnabled=false` required before server testing | `install-server.sh`, `server-smoke.sh` | A config that would keep the anti-cheat on is caught before a Harmony mod is loaded into it. It also *is* the reason the server lane has no anti-cheat; see threat 3. |
| `TreatWarningsAsErrors`, analyzers on, `DebugType=none` | `__MOD_NAME__.csproj` | No symbols shipped with the mod. |
| shellcheck over every tracked script, and the incident-to-gate harness | `lint-shell.sh`, `test_rules_have_gates.py` | Catches shell defects and rules that were written as prose only. |
| ruff over every tracked Python script under the shipped `ruff.toml`, blocking in CI | `lint-py.sh`, `ruff.toml` | Catches Python defects in the mod's own build-time tooling, which is the only code a mod author edits before any game code exists. |
| Deterministic gate harness: every AGENTS.md incident names a `test_*.py` | `test_rules_have_gates.py` | Keeps written rules from rotting into unenforceable prose. |
| Mod console command states the admin level and is not client-executable, with a gate over both that resolves the class through the mod's own intermediate bases and exempts only the settings members it names read-only | `ConsoleCmd__MOD_NAME__.cs`, `test_console_command_permissions.py` | `AdminTools.CommandAllowedFor` refuses a connected player before dispatch, and an admin's run edits the server's settings rather than their own. |
| Telnet password redacted from anything the client prints, and a warning before it goes to a non-loopback host | `game_telnet.py` | Keeps the console password out of CI logs and terminal output, and makes the cleartext exposure explicit. Neither authenticates the peer. |
| XML declarations rejected before parsing | `template/scripts/lib/safe_xml.py` (`parse`, `fromstring`), `template/scripts/test_safe_xml.py` | Prevents entity expansion in every XML-reading gate and server-config reader. |
| Telnet drain byte cap | `template/scripts/lib/game_telnet.py` (`_drain`) | Bounds the bytes one drain keeps from a flooding console peer. |
| Fuzz gates over the `Extends` resolver, the Harmony prefix parser and the XPath resolver | `test_fuzz_extends_chain.py`, `test_fuzz_harmony_parsers.py`, `test_fuzz_xpath_targets.py` | Bounds the three recursive, prefix-driven or dialect-driven parsers a mod author feeds from `Config/*.xml` and mod source. Each asserts totality and known answers, so a wrong verdict fails the gate rather than only a crash. The XML entity layer is separately guarded by `safe_xml.py` and `test_safe_xml.py`. |

Gaps, ranked by exploitability then impact. These are recorded here; the fixes
belong to code review, not to this document.

1. **Sourced-as-code conf and `.local.env`** (`new-mod.sh`, `build.sh`,
   `server-common.sh`). The key and flag checks and the `0600` mode close the
   accidental cases; a conf or a hand-edited `.local.env` from another machine is
   still executed, and no line of the toolchain says so at the point of reading.
2. **No peer authentication or TLS in the telnet client** (`game_telnet.py`). The password is sent to whoever answered the port, and the returned
   text is trusted as game truth. The client warns on a non-loopback host; it does
   not refuse.
3. **Dependency substitution is unobserved**: `NuGetAudit=false`
   (`__MOD_NAME__.csproj`), no `packages.lock.json`, and the compile-time
   reference set is DLLs read out of a game install (`build.sh`).
4. **Destructive delete on an env-derived path** (`deploy-server.sh`). The
   delete is bounded: it runs only after the target holds an executable
   `7DaysToDieServer.x86_64` (`deploy-server.sh`), it removes only
   `$SERVER_DIR/.deploy-stage/<Mod>` and its `.previous` sibling (that file), and the
   directory itself is checked for being absolute and two levels deep
   (`server-common.sh`). What is left is that the depth check is a
   shape test, not an identity test: a path that is a valid, deep directory
   holding an unrelated `7DaysToDieServer.x86_64` still has a `.deploy-stage/`
   subtree removed from it.
5. **Sibling checkouts execute without pinning** (`new-mod.sh`,
   `Makefile`). A moved branch or a compromised repository runs on the
   developer's machine.
6. **CI runner image is not pinned to a digest** (`.github/workflows/ci.yml`).
   The one action the workflow uses is pinned by commit (that file) and Dependabot
   carries the bump, but the image behind `runs-on: ubuntu-24.04` is whatever
   the runner label resolves to on the day.
7. **A player's own in-game console runs any console command in their client
   process** (`ConsoleCmd__MOD_NAME__.cs`). The engine's level check covers
   the networked and web paths only; telnet, stdin and the local console are
   operator channels by design. A player can therefore rewrite their own
   copy of a mod's settings, which reaches server behavior only through a mod
   that reads them on the client.
8. **No audit trail for security-relevant events.** `server-smoke.sh` writes a
   server log, and the mod writes `[<Mod>] InitMod` to the game log
   (`ModApi.cs`), but there is no record of who deployed a package
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
  it.** `new-mod.sh` sources whatever path was passed as `$1`. A file whose
  keys are all known passes the check at `new-mod.sh` and then runs.
- **Anything that can append a line to `.local.env` owns the build.** A Makefile
  target, a test, a sibling tool, or a compromised editor plugin that writes once
  gets shell execution on the next `make build`, `make package` or
  `make deploy-server` (`build.sh`, `server-common.sh`).
- **A mis-set `SEVEN_DAYS_TO_DIE_SERVER_DIR` deploys into the wrong tree.**
  `deploy-server.sh` removes and replaces `$SERVER_DIR/Mods/$MOD` on a path the
  environment supplies. Three checks stand in the way: the path must be absolute
  and at least two levels deep (`server-common.sh`), the target must hold
  an executable `7DaysToDieServer.x86_64` (`deploy-server.sh`), and the
  deploy is a staged swap out of `$SERVER_DIR/.deploy-stage/`, never an in-place
  copy, with the previous mod restored when the run is interrupted. A path that
  satisfies all three is a real server install, and the mod lands in it.
- **A player rewrites their own copy of a mod's settings from the in-game console.**
  `ConsoleCmd__MOD_NAME__.cs` runs the command for whoever the engine dispatches
  it to. A client arriving over the network is stopped by the permission level
  (that file), and the local console is an operator channel that skips that gate by
  design. The shipped setting is a boolean no shipped patch reads, so the value
  of this depends on a generated mod's own client-side readers.
- **A process squatting on the console port harvests the password and forges
  output.** `game_telnet.py` connects to whatever is listening; that file sends
  the password; the screenshot checks consume the returned text as the game's
  answer, so forged output reads as a passing check.
- **A PR author's template change runs in CI.** `.github/workflows/ci.yml`
  scaffolds and tests the PR's own `template/`. No secrets are in scope and the
  grant is `contents: read`, so the realistic abuse is runner compute and
  network egress from the runner.
- **A dropped `scripts/test_*.py` runs on `make test`.** The suite is a glob over
  the scripts directory (`run-offline-tests.sh`), so the test lane executes
  every Python file present in a mod that was cloned or copied from elsewhere.

## 7. Model and disclosure state

- This is the threat model. It carries a risk ranking in the summary table and
  section 5's gap list; it has no owner, and an unassigned owner is stated
  rather than filled with a name.
- `SECURITY.md` exists and states the two facts that are true today: there is no
  disclosure contact and no triage path, and nothing is backported. A report has
  no defined destination, and the model does not invent one.
- The model has no scheduled review cadence. Nothing in the repository triggers a
  re-read, and the entry points above will drift as templates gain targets; a
  re-read is needed whenever `new-mod.sh`, the `Makefile` targets, or
  `template/scripts/` change.

## 8. Response readiness

Not built, recorded so it is not mistaken for covered.

- The server log is the only artifact an incident can be reconstructed from
  (`server-smoke.sh`). There is no record of the conf that produced a
  scaffold, of who deployed a package (`deploy-server.sh`), or of the git
  identity a scaffold was committed under.
- There is no disclosure contact and no triage path, so a report has nowhere
  defined to go.
- No incident in this repository's history has yet produced a dated entry in
  `template/AGENTS.md`, so `test_rules_have_gates.py` has no security incident
  to enforce today. The gate exists and will fail if such a section is added
  without a deterministic check behind it.

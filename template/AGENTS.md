# Agent Instructions — __MOD_DISPLAY_NAME__

Working instructions for implementing this mod. This file is *how to work*;
what was decided lives in `docs/`, and how 7DTD modding works in general
lives in `docs/reference/`.

## Starting a session

On "continue" or any vague/no-context start: read `TODO.md` first (next
unchecked item under the earliest unfinished section is the next task), then
skim `docs/design.md` (gameplay decisions) and `docs/architecture.md`
(technical decisions) for what's already locked in — don't re-litigate
anything already marked "Decided"/"Resolved", and don't re-derive facts
already recorded. Only ask the user what to do if `TODO.md` has nothing
actionable or the design genuinely isn't decided yet.

If you are unfamiliar with 7DTD modding, read `docs/reference/README.md`
first. `docs/reference/best-practices.md` is **binding** when authoring;
`docs/reference/agent-rules.md` is its enforceable core — layer discipline
(shallowest layer that solves the problem), XPath conventions, Harmony
hygiene, packaging.

## Keep docs and TODO current — as you go, not after

The point of this doc structure is that a fresh session with zero
conversation history can resume correctly from files alone. Any decision or
progress that exists only in chat scrollback is lost.

- **Claim before work:** before researching, editing, or testing a
  TODO-tracked task, change its marker from `[ ]` to `[-]` and append
  `in progress — <agent>, YYYY-MM-DD; session: <id>`. That is the exclusive
  ownership signal for other agents. Only then begin.
- The moment a **gameplay** decision is made, record it in `docs/design.md`
  under a dated heading (`Decided YYYY-MM-DD: …`).
- The moment a **technical** decision is made, record it in
  `docs/architecture.md` the same way — and write an ADR in `docs/adr/`
  when it is significant and hard to reverse (see `docs/adr/README.md`).
  Gameplay/balance decisions are never ADRs.
- The moment a task completes, mark it `[x]` in the same turn and remove
  the in-progress text. Released or blocked: restore `[ ]` with the reason.
  Never leave a stale `[-]`.
- New follow-up work or open questions go into `TODO.md` immediately.
- If a decision changes course, fix the now-stale statements in the same
  edit.
- A change a player can notice gets a line under `## [Unreleased]` in
  `CHANGELOG.md` in the same edit, in the user's terms, not the diff's.
  Releasing moves those lines to `## [<version>] - <date>` and sets
  `<version>` in `ModInfo.xml` and on the `README.txt` first line; those
  three have to move together, because `make test` gates them against each
  other. A published version is spent: bump, never re-edit.

## Parallel sessions

When multiple agent sessions work here concurrently, each generates a
durable ID before claiming anything:

```bash
scripts/new-session-id.sh <agent-family>   # e.g. claude, codex
```

The ID identifies the session; the `[-]` marker remains the ownership
claim. Never reuse an ID. Expect other agents' edits in the tree: stage
commits by explicit path only — never `git add -A` / `git add .` /
`git commit -a`.

## Playtest / live-client exclusivity

There is one shared 7 Days to Die client (and dedicated-server runtime) on
this machine, coordinated by the lock owned by `hordeforge/7dtd-playtest`
(`scripts/playtest_lock.py`), at its default path
`~/.cache/7dtd-playtest/playtest_running`. Before any exclusive live-client
work: read the lock (missing file = free); a fresh `running=yes` for
another session means **do not start**; acquire with your session id before
launching; refresh `heartbeat` (~30s, 120s stale window); release
(`running=no`) when done if you own it. A stale lock may be reclaimed only
when no live client/server process exists — and a sandboxed empty `ps` is
not evidence of that. **Never invent a second lock or a second lock path.**

## Gates are not negotiable

A gate is any check that fails a change: an offline `scripts/test_*.py`
assertion, an XML validator, a live case's assert. **When a gate rejects
your change, change the change.** Never relax, narrow, or delete an
assertion so work fits through — the gate is the accumulated memory of a
defect somebody already shipped. If a gate is genuinely wrong (asserts
something the design has since changed), say so in the commit message and
the deciding doc, and make it *stricter about the new truth*, never looser.

The first two corollaries below are each enforced by
`scripts/test_rules_have_gates.py`; the last two are the discipline that
gate cannot check for you.

- A rule that has been broken gets a **gate**, not a paragraph: every
  AGENTS.md section that records a dated incident names the
  `scripts/test_*.py` that enforces it (or declares, by name, what enforces
  it instead).
- Every gate is **deterministic** — no clock, iteration-order, or
  random-seed dependence; the meta-gate runs each gate twice and requires
  byte-identical output.

The parsers that read hand-written input have fuzz gates, seeded so the run
is reproducible and lengthened with `HARMONY_FUZZ_ITERS` /
`EXTENDS_FUZZ_ITERS` / `XPATH_FUZZ_ITERS` / `TELNET_FUZZ_ITERS`:
`scripts/test_fuzz_harmony_parsers.py` over the C# attribute and signature
splitting in `scripts/verify-patch-targets.py`,
`scripts/test_fuzz_extends_chain.py` over the `Extends` walk in
`scripts/lib/xml_extends.py`,
`scripts/test_fuzz_xpath_targets.py` over the xpath resolver in
`scripts/validate-xml-targets.py`, and
`scripts/test_fuzz_telnet_stream.py` over the console byte stream in
`scripts/lib/game_telnet.py` (the one input here that is neither a file nor
mod-authored: another machine's console, read a byte at a time through the
real `_recv`). A new parser takes a
gate in the same pass that adds it: malformed input must come back as a named
error or a resolved entry, never as a traceback that kills the gate before it
can report. A parser is total over its own input grammar, not only
crash-free: `ElementTree`'s `find` answers `text()` with a `KeyError` and an
unclosed predicate with a `TypeError`, so a gate that catches only
`SyntaxError` does not hold. A gate that only proves the parser does not
crash holds half the contract: assert the answer too (a chunked decode equals
the whole-stream decode, a line ends where the protocol says), or a parser
returning the wrong text is indistinguishable from a correct one.
- **Prove a gate can fail** before trusting it — against a fixture or a
  scratchpad copy, never by breaking the shared tree.

## Sibling tooling is mandatory; do not recreate it

Playtesting, the client lock, launch, mute, capture, asset builds, and
engine research belong to the `hordeforge/7dtd-*` repositories — the map is
`docs/reference/sibling-tooling.md`, and `scripts/test_upstream_tooling.py`
scans script content for the banned tool calls. If a capability is general
and missing, add it upstream first (worktree → branch → PR → merge in the
owning repo), then consume it; a local substitute "until upstream exists"
is the defect. Sibling repos are separate checkouts found via
`HORDEFORGE_ROOT` in `.local.env` — never a build input or required
relative path of this repo.

<!-- ANVIL:ASSETS-BEGIN -->
## Asset bundles (when this mod ships them)

The bundle is built by **shamway** (`hordeforge/7dtd-asset-pipeline`); this
mod owns only its assets, generators, and provenance. **No Unity editor is
required**: the default synthesized lane builds complete bundles —
textures, audio, text, meshes, materials, prefabs — with no editor at all;
`bundle_source = "unity"` (with `UNITY_EDITOR`) is an opt-in lane, and
where an editor exists it is a checker, not a requirement. Start with
`shamway init` (it generates `.shamway.toml` and the pipeline's own
`tools/shamway/AGENTS.md` contract), orient with `shamway status --json`,
and gate every rebuild with `make validate-assets` **before** any client
launch — a bundle without a class-142 `AssetBundle` object is always
rejected at runtime, and a matching UnityFS header is *not* acceptance
evidence. Acceptance is a fresh client loading the bundle. If a build fails
a shamway gate, fix the cause — never downgrade the gate.
<!-- ANVIL:ASSETS-END -->

<!-- ANVIL:CSHARP-BEGIN -->
## Runtime settings are TOML

This mod's own tunables live in `Config/__MOD_NAME__.toml`, read by the
DLL from the installed mod folder — see the settings section of
`docs/reference/csharp-harmony.md` for the full contract (hot reload on
save, reset-then-apply, broken save keeps current values, console
`settings|set|reload`). Add a setting in `ModSettings.cs` (its header
comment lists the steps) and mirror it, commented, in the shipped TOML.
`scripts/test_settings_reload.py` holds the contract offline.

The command is admin-only (`DefaultPermissionLevel => 0`) and server-side
(`IsExecuteOnClient => false`): it edits the server's copy of the settings,
so a client-executable one would edit the caller's instead. Any new
`ConsoleCmdAbstract` class states its own level rather than inheriting the
game base class's, states it as a number the gate can resolve, and if it
calls a settings member that changes state holds that admin-and-server-side
contract wherever it is declared.
`scripts/test_console_command_permissions.py` holds all of it, finding
commands by their base type anywhere under `src/` rather than by file
name, so a class in an unexpected file is not a class nobody checked, and
through any intermediate base the mod declares, so a command the engine
registers is never one the gate cannot see. Only the settings members it
names read-only are exempt, so a new one is admin-bound by default.
"Who may run a console command" in
`docs/reference/csharp-harmony.md` has the engine's side.

The TOML's comments are player-facing: Wrench
(`hordeforge/7dtd-mod-settings`) renders this file in the options menu,
shows the comment block directly above each key as its help text, and an
optional final `# ui: flags|enum|range ...` line in that block turns the
raw text field into checkboxes/choices/bounds — see "Comments are the
settings UI" in `docs/reference/csharp-harmony.md`. Write each key's
comment as help a player will read, and keep any `# ui:` token list in
sync with the values `TrySet` accepts.
<!-- ANVIL:CSHARP-END -->

## Local path inventory

All machine-specific paths live in the ignored `.local.env` (format:
`.local.env.example`); see `docs/reference/environment.md`. **Read it
before searching the host** for tools or installations, and when a user
supplies a machine path — or setup discovers one — record it there
immediately. Keep the complete inventory together, including these keys
when their targets exist:

```dotenv
SEVEN_DAYS_TO_DIE_DIR="/absolute/client/install"
SEVEN_DAYS_TO_DIE_SERVER_DIR="/absolute/dedicated/server/install"
HORDEFORGE_ROOT="/absolute/dir/of/hordeforge/checkouts"
PLAYTEST_ROOT="/absolute/checkout/7dtd-playtest"
CONNECT_ROOT="/absolute/checkout/7dtd-fastconnect"
ASSET_PIPELINE_ROOT="/absolute/checkout/7dtd-asset-pipeline"
DOTNET_ROOT="/absolute/dotnet/sdk"
ILSPYCMD="/absolute/ilspycmd"
UNITY_EDITOR="/absolute/Unity"
SEVEN_DAYS_TO_DIE_SAVES_DIR="/absolute/proton/saves"
```

`.local.env.example` is the full inventory: these path keys plus every
non-path knob the scripts read, each with its valid values. A key already set
in the environment wins over the file.

Never commit the file or copy its absolute values into tracked files;
`scripts/test_local_path_inventory.py` enforces the documented keys and the
ignore rule. If a needed key is missing or invalid, **ask the user for the
path** — never guess or reuse one from docs or history. The game install is
**read-only reference**: read `Data/Config/*.xml` freely, never write under
the install directory.

## Repo layout

This directory itself is the modlet — the deployable unit. Mod content
(`ModInfo.xml`, `Config/`, `Resources/`, `UIAtlases/`, …) sits at the root;
`src/` (C# source), `scripts/`, `docs/`, `AGENTS.md`, `CLAUDE.md`,
`TODO.md` are build-time only and excluded from the package. `make build`
stages the deployable modlet under `dist/__MOD_NAME__/`; `make package`
zips it with `scripts/package.sh`, which fixes entry order, timestamps
(`SOURCE_DATE_EPOCH`, else the last commit), and permissions, so the same
source always produces the same archive. `make verify-reproducible`
(`scripts/verify-reproducible.sh`) is the proof: it zips the mod three
times, the last one from a copy at another absolute path under a foreign
locale and timezone, and fails unless all three archives are byte-identical.
Never nest deployable content under a further subfolder.

## XML conventions

- Prefer XPath patches over full-file overrides
  (`docs/reference/xml-patching.md`); use a `<configs>` root in every patch
  file.
- Prefer `Extends` on an existing vanilla entry over defining from scratch.
- Match vanilla indentation/style (tabs, one `<property>` per line).
- Localization ships at `Config/Localization.csv` (the engine only reads a
  mod's localization from `<mod>/Config/` — see
  `docs/reference/agent-rules.md`).

Corrected 2026-09-28: `make validate-xml` listed `Config/` flat, so every
patch under `Config/XUi_InGame/` was never opened and the target reported a
clean run over a set it had not read. It now walks `Config/` the way the
engine loads it, and `scripts/test_xml_gates.py` holds that. The walk itself
is `scripts/lib/config_files.py`, shared with `make verify-patched-config`
rather than copied into it (the `Extends` walk in
`scripts/lib/xml_extends.py`, whose only callers are the offline gates, is
beside it: a chain that re-enters a name now raises rather than recursing
to the interpreter limit).

## Text conventions

- Text is read and written as `utf-8-sig` (`encoding="utf-8-sig"`): a file a
  Windows editor saved opens with a BOM, and as a bare U+FEFF it broke the
  first line of a `.cs`, `.py`, `.md` or `.local.env` file rather than being
  stripped. Never decode with the locale encoding: `text=True` on
  `subprocess.run` is ASCII under `LC_ALL=C` (which `scripts/build.sh` and
  `scripts/package.sh` both export), and one non-ASCII character in a
  tool's output raised out of a gate.
- A byte stream is decoded once across its chunks, not once per chunk. TCP
  splits a character anywhere, so `scripts/lib/game_telnet.py` decodes with an
  incremental decoder; a per-chunk decode turned every split into U+FFFD.
- A record ends where the format says it ends, and nowhere else. Python's
  `str.splitlines()` also ends one at NEL, LINE SEPARATOR and PARAGRAPH
  SEPARATOR, each of which is a legal byte inside a path or a printed line:
  `scripts/lib/game_telnet.py` splits the console stream on the protocol's CR,
  LF and CRLF, and `scripts/lib/local_env.py` splits `.local.env` the way the
  shell's own `source` reads it (`scripts/test_telnet_text_decoding.py` and
  `scripts/test_local_env_reader.py` hold both).
- Text arriving from the shell is decoded with a stated policy, not left to
  the default. A shell variable is a byte string, and `os.environ` decodes one
  that is not UTF-8 with `surrogateescape`, so the value carries a lone
  surrogate that any UTF-8 write rejects.
- Truncate text on a character boundary, never at a code point that only
  completes the one before it (combining mark, zero-width joiner, variation
  selector, emoji modifier, regional indicator). Test for the mark by its
  Unicode category, not by a list of ranges: every script a list does not
  name truncates mid-word. `new-mod.sh` does this for the `ModInfo.xml`
  description, which the game renders.
- A name is identity, so it carries nothing that draws nothing. A display
  name or an author with a bidi override, a zero-width space or a BOM in it
  is a second string that reads as the first; the scaffolder stops on such a
  config (`ci/scaffold-text.py` holds it). The zero-width joiner is not in
  that set: it is how an emoji sequence is written.
- Compare identifiers with `Ordinal` / `OrdinalIgnoreCase`
  (`StringComparer`, `StringComparison`), never with `ToLower()`: the game's
  item and setting names are keys, and a lowercase copy is a second spelling
  of them.

## Testing

Offline gates: `make test` (every `scripts/test_*.py`), `make lint-shell`
(shellcheck, full severity) and `make lint-py` (ruff under the mod's
`ruff.toml`) must pass before any commit. A suppression is a comment or a
`# noqa: RULE` naming the rule and the reason; a bare `# noqa` never
silences a line.
The suite's report carries no elapsed time, so two runs over an unchanged
tree print byte-identical output; `OFFLINE_TEST_TIMINGS=1` adds the seconds
for a human and is the one non-reproducible mode
(`scripts/test_run_offline_tests.py` holds the contract, including that an
interrupted run leaves no scratch directory and no worker behind). Both the suite
and the determinism gate that re-runs every gate twice take their
parallelism from `OFFLINE_TEST_JOBS` (`1` runs them serially).
Install-dependent checks: `make validate-xml` (every Config xpath against
vanilla), `make verify-patched-config` (after loading a world: every element the
mod's `Config/` inserts counted in the save's own `ConfigsDump`, attributed
to this mod, in its intended parent — the positive proof a clean log cannot
give, since a patch matching nothing applies silently. It counts inserted
elements only: `set`/`remove`/`csv` change a matched node and contribute
none, so prove those in game) and, for C# mods,
`make validate-patch-targets` (every `[HarmonyPatch]` target against the
installed Assembly-CSharp) — run them after any config/patch change and
after every game update. `scripts/lib/game_telnet.py` is the stdlib client
for dedicated-server console oracles when a check needs to ask the running
game what is true. Take its password from the environment: the console is
plaintext telnet, and setting a password moves the engine's listener from
loopback to every interface. Dedicated
server: `make install-server` / `deploy-server` / `server-smoke` boot the
configured server briefly and prove the mod loaded from its log. Each smoke
run writes one log into the server install's `logs/` and keeps the newest
`SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS` (default 5); the game's own logs are
never touched.

A number typed into `.local.env` is parsed as a decimal integer before any
`$(( ))` sees it (`decimal_uint` in `scripts/server-common.sh`), never with a
`^[0-9]+$` match. A leading zero is an octal prefix to shell arithmetic, so
`KEEP_LOGS=08` used to fail the expansion and prune nothing, and a digit run
past 64 bits wraps rather than failing, so an epoch just over 2^64 was
compared as a wrapped one inside the accepted range. `SOURCE_DATE_EPOCH`,
`SEVEN_DAYS_TO_DIE_SERVER_{APP_ID,RUN_SECONDS,KEEP_LOGS}` and
`OFFLINE_TEST_JOBS` all go through it, and
`scripts/test_package_epoch.py` plus `scripts/test_smoke_log_pruning.py` hold
the outcomes.

Live behavior: deploy per `docs/reference/environment.md` and check the
game log — a clean log alone does not prove an XPath matched; verify in
game. Live suites, when this mod grows them, go through
`hordeforge/7dtd-playtest` (an `IScenarioProvider` + thin wrapper), never a
private launcher.

## Every script answers --help and refuses what it does not take

`scripts/` is this mod's CLI, and one command line covers all of it:
`-h`/`--help` prints the script's usage on stdout and exits 0 without
starting any work, and an argument the script does not take is a usage
error on stderr with exit 2. A script that ignores its arguments cannot
answer a question about them: `scripts/build.sh --help` staged a modlet
instead of printing help, and `scripts/playtest.sh --help` forwarded the
flag to the upstream runner as a suite id. A mistyped flag a tool
silently drops is worse than one it refuses, because the run then reports
success over work nobody asked for.

Exit 2 is reserved for the command line, exit 1 for a step that ran and
failed, so a caller can tell "I asked wrongly" from "the work failed"
without parsing a message. Status lines go to stdout, diagnostics and
usage errors to stderr, so a redirected run keeps its output.

A script with no arguments of its own calls `parse_no_args usage "$@"`
from `scripts/lib/args.sh`; one that takes positionals calls
`help_only usage "$@"` and validates the rest itself. A new executable
script in `scripts/` is added to `NO_ARGUMENT_SCRIPTS` or
`POSITIONAL_SCRIPTS` in `scripts/test_script_cli.py`, which holds the
contract for every one of them.

Corrected 2026-09-28: nine scripts under `scripts/` took no arguments at
all and dropped every one of them.

## Setup and deploy targets are re-runnable

A setup or deploy target runs again whenever a step failed, a lane was
interrupted, or the same target is invoked twice in one session. It must
converge: a rerun either reaches the same state as one run or changes nothing
at all. Concretely, `make install-server` re-installs over an existing server
install and derives the mod's `serverconfig` only when it is missing, so that
config is written to a staging name and renamed into place (a write cut
halfway would otherwise leave a truncated file that no rerun regenerates, and
the lane would keep trusting it). `make deploy-server` stages the modlet
outside `Mods/` and swaps it, so an interrupted copy leaves the previously
deployed mod loaded rather than two. `make server-smoke` writes one log per
run and prunes to `SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS` after the boot, so the
directory cannot grow with repeated runs.
`scripts/test_configure_server_config.py` (the derived config: a rerun is
byte-identical, a failed run writes nothing and leaves no residue),
`scripts/test_smoke_log_pruning.py` (the log quota),
`scripts/test_deploy_swap.py` (the deploy swap) and
`scripts/test_verify_reproducible.py` (an interrupted `make
verify-reproducible` leaves no scratch tree) hold that.

Corrected 2026-09-28: the deploy swap moved the deployed copy aside and then
moved the new one in, with nothing between the two moves: a Ctrl-C, a SIGTERM
or a failed second move in that window left no deployed mod at all, and a
rerun is not the recovery the interrupted run can count on. The swap is now
`swap_into_place` in `scripts/server-common.sh`, which puts the previous copy
back on any exit before it completes.
`scripts/test_deploy_swap.py` drives it, including a signal delivered between
the two moves.

Corrected 2026-09-28: a smoke log was named after the second it started, so
a rerun inside one second opened the previous run's log with `>` and replaced
it, and the two runs then counted as one against the quota. The name comes
from `smoke_log_path` instead, which never reuses one, and it is taken after
the deploy so a slow run cannot hand its name to a later one.

A target that fails on a second run, or that a rerun performs twice, is a
defect in the target: fix the script, not the caller's cleanup.

## One concern per playtest run

Written 2026-08-30.

A case belongs to the suite whose feature it proves, never dropped into
another feature's fixture (shared world/inventory state makes a borrowed
case change every case after it). Do not comma-list unrelated suites on
`PLAYTEST_SUITE`; the harness refuses an undeclared list. Consecutive
actions of one feature (equip, then use, then capture) belong in that
feature's suite. A particle system that is already part of a built prefab
is not a second suite. Unrelated features are separate invocations (a
matrix), not one comma-list. `scripts/test_one_concern.py` gates this.

When this mod has live suites, run **one id** per invocation through
hordeforge/7dtd-playtest (see that repo's README "one concern"):

```bash
make playtest SUITE=<one-id>
```

That target is a thin wrapper that execs the hordeforge/7dtd-playtest
runner from `$PLAYTEST_ROOT`, passing this mod's own suite file
(`suites/<id>.json`, when it exists) so a run cannot silently fall back to
an upstream built-in (`docs/reference/sibling-tooling.md`). It ships with
the template, so it is there before the mod has any live suite; adding a
suite means adding the JSON, not a new Makefile rule.

Several unrelated features: separate invocations, not
`SUITE=a,b`. `PLAYTEST_SUITE` comma-lists are refused unless declared
as consecutive steps of one feature (`--concern-suites` /
`PLAYTEST_CONCERN_SUITES`, exact same tokens). A `*_look` suite and a
`*_block_*` suite cannot share a list even if declared.

## Git workflow

This is a standalone hordeforge repository and the clone may be shared by
concurrent sessions: never `git checkout` / `git switch` / `git branch -D`
in it — take a worktree per unit of work
(`git worktree add /tmp/__MOD_NAME__-<topic> -b <branch> origin/main`).
Complete the full lifecycle autonomously when unblocked: branch → commit →
push → PR → merge; never commit directly to the default branch. Stage by
explicit path. No `Co-Authored-By` or other attribution trailers in commits
or PRs. If another session is working on something — a dirty file, a live
branch, an open PR — do not touch it at all.

## Scope

Only build what's decided in `docs/design.md`, `docs/architecture.md`, or
`TODO.md`. If the design isn't decided yet, that's a question for the user,
not something to invent mid-implementation.

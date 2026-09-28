# Changelog

All notable changes to Anvil, the 7DTD mod template, are recorded here. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
versions follow [SemVer](https://semver.org/spec/v2.0.0.html) for the
template itself: `0.y.z` while the modlet's own interfaces move, and the
version goes `1.0.0` when they stop.

A version is a git tag on `main`. `Unreleased` holds everything landed since
the last tag, so an older template can be diffed against a newer one without
reading the commit log. Generated mods are versioned separately, in their own
`ModInfo.xml`; nothing here is a mod's release.

A mod scaffolded from an older tag and re-scaffolded from a newer one keeps
its own content: the notes below mark the changes that move the generated
modlet's contract rather than add to it, and every one of them opens with
`**Breaking for a mod <what the mod did>:**`, so
`rg -F '**Breaking for a mod' CHANGELOG.md` is the whole upgrade between
two tags. `ci/check-changelog.py` holds that spelling, and the rest of the
shape above, so the search cannot quietly stop matching.

## [Unreleased]

### Added

- `CONTRIBUTING.md` for the human contributor: the `make preflight` setup
  step and the host tools it needs, the single-gate edit loop
  (`make scaffold`, then `make test TF=<substring>` inside the smoke mod),
  what a pull request has to carry, and how `RUFF_VERSION` is bumped
  (Dependabot does not cover it; `actions/checkout` is bumped by tag commit).
- `scripts/verify-patch-targets.py` parses its own command line with
  `argparse`, as `verify-patched-config.py` already did, instead of a
  hand-rolled `usage()` and argument loop that reimplemented it.
- `ci/scaffold-text.py` pins the text boundaries `ci/check-smoke-mod.py`
  does not reach: a purpose the 200 code-point description limit cuts inside
  a character (a ZWJ emoji sequence, a flag, a Devanagari matra), a display
  name or author carrying a character that draws nothing, and an author name
  folding into the Harmony id. `make check` and CI both run it.
- `ci/check-smoke-mod.py` pins what the scaffolder makes of the smoke
  config's text: the ModInfo fields a reader of `ci/smoke.conf` expects, the
  full purpose still reaching the mod, and the Harmony id the author name
  produces. `ci/smoke.conf` carries text hostile on purpose (`&`, `<`, a
  quote, an accented letter, a CJK sentence end) so the check is a real one.
  `make check` and CI both run it, and CI also runs the modlet's ruff rules
  over `ci/`.
- A fuzz pass over the XPath resolver in `validate-xml-targets.py`, which
  turned a malformed `xpath=` on a patch operation into a traceback that
  killed `make validate-xml` partway through its target list.
- The Harmony parser fuzz gate now asserts `argument_list` and
  `strip_namespace` on their own, rather than only reaching them through
  `parameter_names` and `parameter_types`.
- `make lint-py` gates the modlet's Python under the shipped `ruff.toml`, and
  CI installs ruff and runs it as a blocking step. **Breaking for a mod
  scaffolded before this:** that mod has no `lint-py` target and no
  `ruff.toml`, so it has to take both from here to run the same gate.
- `make help` lists every target, and `new-mod.sh --help` documents the
  config file and the meaning of each exit status.
- A fuzz pass over the C# signature and `Extends`-chain parsers, which
  crashed on malformed input the offline gates feed them.
- `THREAT_MODEL.md` and a security posture page, with the file reference
  behind each claim.
- A generated mod gets a `CHANGELOG.md`, an `Unreleased` section, and a
  release procedure: `ModInfo.xml` is the single source of the version, the
  first line of `README.txt` has to name the same value, and
  `scripts/test_static_checks.py` fails the offline gates when the three
  disagree. The changelog ships in the package next to `README.txt`.
  **Breaking for a mod scaffolded before this:** its own `CHANGELOG.md` and
  the release procedure in its header are what it has to take from here.
- `make verify-reproducible` packages the modlet three times, the last from a
  copy at another absolute path with no git checkout, under a locale and
  timezone that are not C/UTC, and fails unless the three archives are
  byte-identical. CI runs it, so the reproducibility the docs claim is checked
  rather than asserted.
- The dedicated-server lane provisions with a mod-owned EAC-off
  `serverconfig`, and the server smoke boot is bounded.
- A `Makefile` at the template repo root: `make check` runs the whole CI
  workflow locally, step for step, after a `make preflight` that names any
  missing host tool. It proves a change to `new-mod.sh` or `template/` without
  a contributor having to reconstruct the CI job by hand. The last CI step is
  the reproducible package, and `make check` runs it too, on the tree the
  package step leaves.
- The host floors the scripts assume are declared and checked:
  `scripts/lib/require-bash.sh` fails with one message on the bash 3.2 that
  macOS still ships as its system bash, where `mapfile -d`, `wait -n` and
  `[[ -v ]]` each fail differently and none says why, and the README states
  bash 4.4+ and Python 3.9+. **Breaking for a mod scaffolded before this:**
  that mod has no `scripts/lib/require-bash.sh`, so take it with the three
  scripts that source it.
- `scripts/test_adr_records.py` holds the decision-record lifecycle
  `docs/adr/README.md` states: sequential `NNNN-title.md` numbering, a status
  from the documented vocabulary on every record (never `Proposed`, an ADR is
  a decision made), a supersession that names the record it replaces, one
  index row per record whose status matches, and dated
  `Decided`/`Resolved` entries in `docs/design.md` and
  `docs/architecture.md`.
- `test_settings_reload.py` proves the settings contract at the source level
  and computes, in float32, the uptime at which each deadline below is lost,
  so the constants cannot go back to a float without the gate saying why.
- `ci/check-changelog.py` holds this file to the release contract its own
  header states: `Unreleased` first and always present, a dated
  `## [version]` section per released version, Keep a Changelog's group
  names, a section with at least one entry, versions that only go down the
  file, and the `**Breaking for a mod` marker the README tells an upgrading
  mod author to search for. The generated mod's `test_static_checks.py` holds the same
  contract for a mod's `ModInfo.xml` and `README.txt`; nothing held the
  template's own notes, which are the file a tag is cut from. `make check`
  and CI both run it.

### Changed

- `global.json` pins the SDK with `rollForward: latestPatch` instead of
  `latestFeature`, so the build stays in the 8.0.1xx feature band the README
  already claimed and a host with only a newer band installed no longer
  compiles the DLL with whatever it has. `scripts/build.sh` resolves the pin
  from the mod root (`dotnet --version`) and fails there naming the wanted
  version and the ones the host has, instead of leaving it to dotnet's
  resolver output. **Breaking for a mod scaffolded before this:** it now
  needs an SDK in the pinned band, not any 8.0.x.
- `make check` runs `ci/check-smoke-mod.py` right after the scaffold, which
  is where `.github/workflows/ci.yml` runs it. The mod's own gates write
  their caches into the mod, so a check reading the tree afterwards could
  not tell a cache the scaffolder shipped from one the run just made.

- The shipped `ruff.toml` selects seven more defect groups the tree
  already passes: `ARG`, `DTZ`, `ERA`, `G`, `PGH`, `RSE` and `TID`
  alongside the existing set, so a parameter nobody reads, a naive
  datetime, a commented-out block, a malformed logging call, a blanket
  `# noqa` or `# type: ignore`, a redundant parenthesised `raise` and a
  relative import all fail `make lint-py` instead of passing unnoticed.
- `scripts/test_ruff_rule_set.py` fails the offline gates when a group is
  dropped from `select`, re-disabled through `[lint] ignore`, or when the
  `line-length` cap, the `target-version` floor, or the gate's use of the
  shipped config go missing. Deleting a line of the rule set used to
  silence a class of defects with a still-green gate.
- The console-command permission gate finds commands by their
  `ConsoleCmdAbstract` base type anywhere under `src/`, so a command
  declared in a file other than `ConsoleCmd<Mod>.cs` is held to the same
  contract as the settings command, and a second class in a file is held
  separately from the first. A stated level must also resolve to a number,
  and any command that writes the settings is held to the admin level in
  the server process. **Breaking for a mod that has added a command:** it
  now needs its own stated, resolvable level, which is the level it should
  have been stating.
- **An `Extends` cycle raises `ExtendsCycle` instead of resolving.** A mod
  whose config closes an `Extends` chain (`a` extends `b`, `b` extends `a`)
  used to have the chain cut silently, which reported a broken patch as a
  working one; `make test` now walks the mod's own `Config/` with the shared
  model and fails with the chain named. An entry that extends *itself* still
  resolves, as the engine reads it.
- `make lint-py` and `make lint-shell` share one body, `scripts/lib/lint-gate.sh`
  (and the offline gates share `scripts/lib/gate.py`), so the two lint targets
  cannot drift on which files they cover or how they report. A mod carrying its
  own copy of either should take the shared one.
- `deploy-server.sh` stages into a `.deploy-stage` directory and swaps it into
  place, rolling back when the swap fails, so a failed deploy no longer leaves
  a half-written server. `server-common.sh` refuses a
  `SEVEN_DAYS_TO_DIE_SERVER_DIR` less than two levels deep, where a wrong path
  would have deployed over the wrong tree. **Breaking for a mod whose
  `.local.env` sets that key to a shallower path:** it has to name the game's
  server directory.
- One `.local.env` reader for the shell lanes (`load_local_env` in
  `scripts/server-common.sh`), with a Python counterpart in
  `scripts/lib/local_env.py` for the targets written in Python. It tolerates
  CRLF files and fails on a file it cannot parse, naming itself, where a
  `source` died on a `/dev/fd` path.
  A mod carrying its own copy of a reader should take this one.
- Settings hot-reload detects a change by file content, not by mtime and
  length, so an edit that preserves both applies.
- The modlet package is reproducible: entries in `LC_ALL=C` sorted order,
  `SOURCE_DATE_EPOCH` timestamps, normalized permissions, no extra fields.
  The same source yields the same bytes on any host, so a rebuild no longer
  changes a published zip's checksum. Export `SOURCE_DATE_EPOCH` to pin the
  time yourself. `global.json` pins the SDK to the 8.0.1xx feature band and
  `PathMap` keeps the DLL independent of the build directory. The C#
  `LangVersion` is a version rather than `latest`, which moved with the SDK
  major, and `scripts/build.sh` builds from the mod root so `dotnet` finds
  that pin whatever directory it was invoked from.
- A scaffolded mod's first changelog section is dated
  `## [<version>] - <today>`, the version `ModInfo.xml` already declares, and
  `test_static_checks.py` fails a released section with no date. The section
  read `- scaffold` before, so the file's own release procedure asked for
  something the shipped file did not do, and the mod author's next release
  copied the exception. **Breaking for a mod scaffolded before this:** its
  `CHANGELOG.md` has to carry a date on each released section.
- A rerun of `new-mod.sh` over the same target is safe: the mod is built in a
  staging directory and moved into place as the last step, so an interrupted
  run leaves nothing half-written for the next one to refuse.
- The README says how a mod reads what a newer tag changes for it: one
  fixed-string search over this file for the `**Breaking for a mod` marker,
  which `ci/check-changelog.py` holds in place. Before, the only path from
  "I am re-scaffolding from a newer tag" to the changes that move my mod's
  contract was reading the whole file.

### Fixed

- The scaffolder cut the mod browser's 200 code-point description inside a
  character whenever the purpose was written in a script where one character
  is several code points: a Devanagari matra, a Thai vowel sign or a flag's
  regional indicator landed in `ModInfo.xml` on its own, and an emoji ZWJ
  sequence was left holding the first of its elements. The cut now walks back
  to a whole character in any script, and the mark test is the Unicode
  category rather than a list of ranges, so a script the list did not name
  truncates with it. The sentence-end set covers Khmer, Mongolian, Ethiopic,
  Burmese and Tibetan stops, and not only CJK and Devanagari.
- The author name reached the Harmony id through `lower()`, which maps a
  German sharp s to nothing: "Weiß" and "Wei" both reduced to `wei` and two
  authors were given one id. It is case-folded now.
- A display name or an author carrying a character that draws nothing (a
  bidi override, a zero-width space, a BOM) scaffolded as a second string
  that reads as the first, in the two fields a player tells one mod from
  another by. The run stops on such a config with exit 2 and the code
  points it found.
- Nine scripts under `template/scripts/` dropped every argument they were
  given: `scripts/build.sh --help` staged a modlet, `--dry-run` ran the full
  build and looked accepted, and `scripts/playtest.sh --help` forwarded the
  flag to the upstream runner as a suite id. Every script in that directory
  now answers `-h`/`--help` with its usage on stdout and exit 0, and refuses
  an argument it does not take with the usage on stderr and exit 2
  (reserved for the command line, so a caller can tell "I asked wrongly"
  from "the work failed"). `scripts/lib/args.sh` holds the two shared
  entry points and `scripts/test_script_cli.py` holds the contract for every
  script that has a command line.
- `validate-xml-targets.py` read no argument of its own, so a mistyped flag
  ran the whole check over a tree the caller believed they had narrowed
  down. It now takes `--help` and refuses anything else with exit 2.
- `configure-server-config.py` printed a lowercase two-line `usage:` on
  stderr, where every other entry point prints the same `USAGE` /
  `OPTIONS` / `EXIT STATUS` block its siblings do.
- The scaffolder's optional-feature markers never reach the generated mod.
  A block kept because its feature is on kept its closing marker too, so a
  mod scaffolded with assets off shipped two `ANVIL:ASSETS` lines in its
  `AGENTS.md`; a mod scaffolded with C# off did the same with the
  `ANVIL:CSHARP` pair in `README.md` and `AGENTS.md`. The stripping of those
  blocks and the token substitution are one pass now, and
  `ci/check-smoke-mod.py` fails when any marker survives.
- A mod without asset bundles no longer declares `build-assets` and
  `validate-assets` phony while defining neither, so `make build-assets` in
  one reported success and did nothing.
- The scaffolder copies `template/` with a plain `cp -R`, which ignores
  `.gitignore`, and pruned only `__pycache__`, `*.pyc` and `dist`. A
  developer who had run the gates in the template tree shipped
  `.ruff_cache/` (and `.shamway/`, `.local/`) inside every mod the
  scaffolder produced. `ci/check-smoke-mod.py` now fails on any of them.
- A number typed into `.local.env` is read as the decimal integer it spells.
  A leading zero is an octal prefix to shell arithmetic, so
  `SEVEN_DAYS_TO_DIE_SERVER_KEEP_LOGS=08` failed the `$((keep + 1))` in
  `prune_smoke_logs`, printed `value too great for base`, and pruned nothing
  at all, leaving `logs/` to grow by one file per smoke run; the same value
  for `RUN_FOR_SECONDS` or `APP_ID` ended the run. Past 64 bits the
  arithmetic wraps rather than failing, so a `SOURCE_DATE_EPOCH` just over
  2^64 passed the 1980-2107 range check as a wrapped value inside it, and
  `OFFLINE_TEST_JOBS=18446744073709551616` came back as 0 and ran the whole
  suite serially. `decimal_uint` in `scripts/server-common.sh` normalizes
  once and every reader of a number from `.local.env` goes through it;
  `scripts/test_package_epoch.py` and `scripts/test_smoke_log_pruning.py`
  hold the outcomes.
- `validate-xml-targets.py` caught only `SyntaxError` around
  `ElementTree`'s `find`, which answers `text()` and a bare `()` with a
  `KeyError` and an unclosed predicate with a `TypeError`. Both are the same
  answer the caller already had for an unparseable xpath: a SKIP.
- A trailing separator in a C# parameter list no longer reports a phantom
  parameter, so `Patch(string sep = "),(",)` is one parameter rather than two.
- The telnet client keeps no transcript. `GameTelnet` concatenated every
  chunk it drained into a `_buffer` field that nothing read, so a long oracle
  session held its whole output in memory for the length of the session.
  `scripts/test_telnet_no_retention.py` drives a session over a real socket
  pair and fails if any per-instance state grows with it.
- A scaffold writes `ModInfo.xml`'s free text as XML. A display name or
  author holding `&`, `<` or a quote (a typographic name, an ampersand, a
  name in a non-Latin script) went into the attribute raw and left a file
  the game cannot parse, and the generated mod's own xml-parses gate red.
- A purpose is cut at the sentence end its script writes. Only `.!?`
  counted, and only where whitespace followed, so a Japanese or Devanagari
  purpose was one long sentence and the mod-browser description held two
  of them, cut mid-phrase. A digit or a lone capital before a stop is an
  initial or a version, not an end.
- The author token behind the Harmony id is normalized before it is
  reduced to lowercase ASCII, so an accented name keeps its base letters
  (`Müller` becomes `muller`, not `mller`) whether it is stored composed or
  decomposed.
- A scaffolder prompt is asked again until the answer is usable, and the
  re-ask spells out what a usable answer looks like. An empty or malformed
  answer used to end the run with a message naming the rule but not its
  shape; a closed stdin, which used to kill the script on `read`'s status,
  now says which key went unanswered and that nothing was written. An empty
  `target_dir` or `hordeforge_root` takes the current directory.
- An interrupted `make deploy-server` leaves the previously deployed mod in
  place. The swap held the old copy aside and moved the new one in with
  nothing between the two moves, so a Ctrl-C, a SIGTERM or a failed second
  move in that window took the deployment down with it; the swap is
  `swap_into_place` now, and it puts the previous copy back on any exit
  before it completes.
- A smoke rerun inside the same second no longer overwrites the log of the
  run before it, and the two no longer count as one against the log quota.
- `make lint-py` passes on a current ruff. Three test scripts carried
  `# noqa: E402` directives ruff no longer needs, and RUF100 failed every
  scaffold; the two that did need it now put their path constants after the
  import block instead of suppressing the rule.
- `make lint-py` no longer turns red on an unrelated ruff release: CI pins
  the version it installs (`RUFF_VERSION`) instead of taking the newest one
  from PyPI, and the stale `# noqa: E402` that made the pinned ruff reject
  `scripts/test_telnet_text_decoding.py` is gone.
- The telnet console password no longer appears in error messages or logs.
- The telnet socket is released on every close path, and the server smoke
  logs are bounded.
- A read or decompile failure in the offline gates is reported instead of
  being swallowed into a passing result.
- The offline gate report is byte-identical across runs, and the gates run
  their subprocesses concurrently with the elapsed time read from a
  monotonic clock.
- Nested `Config` patch files are validated, `param1` exclusions resolve
  correctly against inherited scalars and class blocks, and the XPath-patch
  checkers and the `playtest` target are wired as documented.
- Harmony targets resolve per class, and the `.local.env` lookup is the same
  in every script.
- The scaffolder and the log pruning no longer need GNU-only `sed` or `date`,
  and preserve line endings.
- A `dotnet` on `PATH` with no SDK installed now names the fix instead of
  failing deep inside the build output.
- The settings poll interval and reload debounce run on
  `Time.unscaledTimeAsDouble` and are `double` constants. Both are differences
  of clock readings, and a `float` there loses the sub-second resolution they
  need once a long-running server's uptime makes the quantum larger than the
  interval itself (0.25s at about 60 days, 1.0s at about 120). Past that the
  poll collapsed to "every frame" and the debounce delta read 0.0, so a saved
  file was never applied and the reload the console command promises stopped
  working.
- `make package` rejects a `SOURCE_DATE_EPOCH` outside 315532800
  (1980-01-01T00:00:00Z) through 4354819198 (2107-12-31T23:59:58Z), the range
  a zip entry's 32-bit DOS date can hold. Info-ZIP wraps an out-of-range mtime
  silently rather than rejecting it, so a mistyped epoch produced an archive
  that was reproducible and stamped with a date nobody asked for, and the only
  sign was a wrong `unzip -l`. `test_package_epoch.py` drives the real script
  and reads the real archive back.
- Settings floats stay exact, and SDK fallbacks order numerically.
- Settings keys in `.local.env` are validated against the documented set.
- `verify-patch-targets.py` postpones its annotations, so it imports on the
  Python 3.9 floor `ruff.toml` pins instead of raising `TypeError` on
  `str | None`; `test_python_defects.py` fails any script that reintroduces a
  PEP 604 union without the future import.
- Text is intact at the boundaries that used to mangle it: the telnet client
  decodes incrementally, so a multi-byte character split across two reads is no
  longer three `U+FFFD`; the local-env and patch-verifier readers take
  `utf-8-sig`; `ilspycmd` output is decoded as UTF-8 rather than the caller's
  locale, which raised `UnicodeDecodeError` under `LC_ALL=C`; and `new-mod.sh`
  truncates an over-long `ModInfo.xml` description on a character boundary
  rather than mid-codepoint. `test_telnet_text_decoding.py` gates it.
- The derived `serverconfig.xml` is written atomically, so a run interrupted
  mid-write no longer leaves a file the next run refuses to parse, and a
  `serverconfig.xml` that will not parse exits 1 with the error instead of a
  traceback.
- The Python entry points document themselves: `configure-server-config.py`,
  `validate-xml-targets.py`, `verify-patched-config.py` and
  `verify-patch-targets.py` take `--help`, say what each exit status means, and
  send diagnostics to stderr, so a failing lane is distinguishable from a
  passing one by its status alone.
- `make preflight` warns when the local ruff differs from the `RUFF_VERSION` CI
  pins, because a rule the mod's `ruff.toml` selects can resolve differently
  there and a green local run is then not the CI verdict.

## [0.1.0] - 2026-09-11

### Added

- Initial release: the `new-mod.sh` scaffolder, the `template/` modlet
  skeleton, the mod-agnostic reference in `docs/`, and the CI smoke that
  scaffolds a throwaway mod and runs its offline gates.

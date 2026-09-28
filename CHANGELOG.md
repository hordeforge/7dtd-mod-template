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
modlet's contract rather than add to it.

## [Unreleased]

### Added

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
  a contributor having to reconstruct the CI job by hand.
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

### Changed

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
  working one; it now fails the gate with the chain named. An entry that
  extends *itself* still resolves, as the engine reads it.
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
- A rerun of `new-mod.sh` over the same target is safe: the mod is built in a
  staging directory and moved into place as the last step, so an interrupted
  run leaves nothing half-written for the next one to refuse.

### Fixed

- The telnet client keeps no transcript. `GameTelnet` concatenated every
  chunk it drained into a `_buffer` field that nothing read, so a long oracle
  session held its whole output in memory for the length of the session.
  `scripts/test_telnet_no_retention.py` drives a session over a real socket
  pair and fails if any per-instance state grows with it.
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
- Settings floats stay exact, and SDK fallbacks order numerically.
- Settings keys in `.local.env` are validated against the documented set.
- `verify-patch-targets.py` postpones its annotations, so it imports on the
  Python 3.9 floor `ruff.toml` pins instead of raising `TypeError` on
  `str | None`; `test_python_defects.py` fails any script that reintroduces a
  PEP 604 union without the future import.

## [0.1.0] - 2026-09-11

### Added

- Initial release: the `new-mod.sh` scaffolder, the `template/` modlet
  skeleton, the mod-agnostic reference in `docs/`, and the CI smoke that
  scaffolds a throwaway mod and runs its offline gates.

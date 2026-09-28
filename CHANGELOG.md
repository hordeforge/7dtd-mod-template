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
- The dedicated-server lane provisions with a mod-owned EAC-off
  `serverconfig`, and the server smoke boot is bounded.
- A `Makefile` at the template repo root: `make check` runs the whole CI
  workflow locally, step for step, after a `make preflight` that names any
  missing host tool. It proves a change to `new-mod.sh` or `template/` without
  a contributor having to reconstruct the CI job by hand.

### Changed

- **An `Extends` cycle raises `ExtendsCycle` instead of resolving.** A mod
  whose config closes an `Extends` chain (`a` extends `b`, `b` extends `a`)
  used to have the chain cut silently, which reported a broken patch as a
  working one; it now fails the gate with the chain named. An entry that
  extends *itself* still resolves, as the engine reads it.
- One `.local.env` reader for the whole modlet (`load_local_env` in
  `scripts/server-common.sh`). It tolerates CRLF files and fails on a file it
  cannot parse, naming itself, where a `source` died on a `/dev/fd` path.
  A mod carrying its own copy of a reader should take this one.
- Settings hot-reload detects a change by file content, not by mtime and
  length, so an edit that preserves both applies.
- The modlet package is reproducible: entries in `LC_ALL=C` sorted order,
  `SOURCE_DATE_EPOCH` timestamps, normalized permissions, no extra fields.
  The same source yields the same bytes on any host, so a rebuild no longer
  changes a published zip's checksum. Export `SOURCE_DATE_EPOCH` to pin the
  time yourself. `global.json` pins the SDK floor and `PathMap` keeps the DLL
  independent of the build directory.
- A rerun of `new-mod.sh` over the same target is safe: the mod is built in a
  staging directory and moved into place as the last step, so an interrupted
  run leaves nothing half-written for the next one to refuse.

### Fixed

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

## [0.1.0] - 2026-09-11

### Added

- Initial release: the `new-mod.sh` scaffolder, the `template/` modlet
  skeleton, the mod-agnostic reference in `docs/`, and the CI smoke that
  scaffolds a throwaway mod and runs its offline gates.

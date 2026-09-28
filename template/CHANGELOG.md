# Changelog

All notable changes to __MOD_DISPLAY_NAME__ are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [SemVer](https://semver.org/spec/v2.0.0.html) with the
four-segment form the game expects in `ModInfo.xml` (`major.minor.patch.build`).

`ModInfo.xml` is the single source of truth for the version: the first line of
`README.txt` has to name the same value, and `make test` fails when the two
disagree. Release a change like this:

1. Move what you wrote under `## [Unreleased]` into a new
   `## [<version>] - <YYYY-MM-DD>` section, and put `<version>` in
   `ModInfo.xml` and on the `README.txt` first line.
2. Group the entries under `Added`, `Changed`, `Fixed`, `Removed`, and put a
   breaking change first under `Changed` with a `**Breaking:**` prefix
   saying what a user has to do, not what moved in the source.
3. Leave `## [Unreleased]` present and empty, so the next change has a home.

A version already in a published zip is spent: bump the version rather than
editing the entry.

## [Unreleased]

## [__MOD_VERSION__] - __MOD_RELEASE_DATE__

### Added

- Initial scaffolded modlet from [Anvil](https://github.com/hordeforge/7dtd-mod-template).

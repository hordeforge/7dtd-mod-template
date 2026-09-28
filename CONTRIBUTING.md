# Contributing

Anvil is a scaffolder plus a template, so a change to `new-mod.sh`, to
`template/`, or to `ci/` is proven by scaffolding a throwaway mod and running
that mod's gates. `make check` does exactly that, step for step in the order
`.github/workflows/ci.yml` runs them, and takes well under two minutes on a
warm tree with nothing else competing for the CPU.

## Before you start

```bash
make preflight   # report the missing host tools and stop
make check       # everything CI runs, in CI's order
```

`make preflight` is the setup step. It needs `bash`, `make`, `git`, `python3`,
`shellcheck`, `ruff`, `zip` and `unzip` on `PATH`, and it compares your local
`ruff --version` against the `RUFF_VERSION` pinned in
`.github/workflows/ci.yml`, warning when they differ. A rule the modlet's
`ruff.toml` selects can resolve differently between the two, so a green local
run is not the CI verdict while they are apart. Nothing is installed for you:
put ruff where your shell already looks for tools rather than globally.

There is no game install, no .NET SDK and no network in the loop.
[`ci/smoke.conf`](ci/smoke.conf) sets `clone="no"` and the package step proves
the XML-only path, so `make check` is the whole local gate.

## The edit loop

`make check` re-scaffolds from scratch every run. To iterate on one gate, that
is too coarse:

```bash
make scaffold                        # one smoke mod in .scratch/anvil-smoke/CiSmoke
cd .scratch/anvil-smoke/CiSmoke
make help                            # that mod's own targets
make test TF=<substring>             # one test, e.g. make test TF=telnet
```

The mod's `make help` is the entry point for everything downstream of the
scaffold. When the change is in the modlet rather than the scaffolder, edit
`template/` and re-run `make scaffold`; the smoke mod is disposable, so never
carry a fix you made inside `.scratch/` back to `template/` by hand.

## Opening a pull request

- This clone is shared between sessions, so branch from `origin/main` on a
  worktree outside it (`git worktree add <dir> -b <topic> origin/main`),
  never in the tree you are sitting in. Never commit directly to `main`;
  fixes land there by merge.
- `make check` is green before you push. It is the same set of steps as the
  `scaffold-smoke` job, so nothing new can fail only in CI.
- Add the change under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md),
  in the section it belongs to. A mod scaffolded from an older tag reads that
  file to learn what moved, so an entry that says what changed beats an entry
  that says which files moved.
- No attribution trailers. A `Co-authored-by: Name <email>` for a real person
  is fine; a generated one is not.

## Bumping a pinned version

`RUFF_VERSION` in `.github/workflows/ci.yml` is the one pin a bump tool will
not open for you. Raise it, run `make lint-py` inside a scaffolded mod, and
say in the changelog which findings moved. `actions/checkout` is pinned by
commit, not by tag, and Dependabot bumps it monthly carrying that tag's commit;
do not hand-edit the SHA.

`docs/best-practices.md` is vendored from
`hordeforge/.github/MODDING_BEST_PRACTICES.md`. Do not edit it here; re-sync
it from upstream and update the date in its provenance header. Anything
Anvil-specific belongs in the other `docs/` files.

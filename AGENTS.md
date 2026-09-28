# Agent Instructions — Anvil (7dtd-mod-template)

Rules for working on the template repo itself. A mod *generated* from this
template carries its own `AGENTS.md` (see `template/AGENTS.md`).

## What this repo is

Everything under `template/` is scaffolding that `new-mod.sh` instantiates:
`__MOD_NAME__`, `__MOD_DISPLAY_NAME__`, `__MOD_AUTHOR__`, and
`__MOD_PURPOSE__` are substitution tokens, and the `src/__MOD_NAME__/`
directory is renamed at scaffold time. Keep tokens intact; never replace one
with a concrete value inside `template/`.

## Editing rules

- **Nothing mod-specific.** The template must contain only structure,
  tooling, and discipline that any 7DTD mod needs. If a change only makes
  sense for one mod, it belongs in that mod, not here.
- **No absolute or machine-local paths in tracked files.** Machine paths
  live in a generated mod's ignored `.local.env`; this repo's docs refer to
  those keys, never to concrete paths.
- **No required paths into sibling checkouts.** Tool repos
  (`7dtd-playtest`, `7dtd-asset-pipeline`, …) are referenced by their
  installed CLIs or via `.local.env` keys, and their absence degrades
  gracefully (a skipped target, not a broken build).
- **`docs/best-practices.md` is vendored**, from
  `hordeforge/.github/MODDING_BEST_PRACTICES.md`. Do not edit its content
  except to re-sync from upstream (update the provenance header's date when
  you do). Anything Anvil-specific goes in the other docs.
- **Template CLAUDE.md stays exactly `@AGENTS.md`.** All instructions live
  in AGENTS.md; CLAUDE.md is only the import.

## Testing a change

Any change to `template/` or `new-mod.sh` is proven by scaffolding:

```bash
make check                  # scaffolds and runs every gate CI runs
```

`make check` is `.github/workflows/ci.yml` step for step: it re-scaffolds
`ci/smoke.conf` into the gitignored `.scratch/` (so a stale tree never makes
the gates pass), then runs the generated mod's `make test`, `make lint-shell`
and `make lint-py`, asserts what the scaffold made of that config's text with
`ci/check-smoke-mod.py`, shellchecks `new-mod.sh` itself, runs the modlet's
ruff rules over `ci/`, and proves `make package`
produces a zip that extracts to `Mods/<Name>/ModInfo.xml`. `make preflight`
names any missing host tool first. `make scaffold` alone, then working inside
`.scratch/anvil-smoke/CiSmoke`, is the loop for iterating on one gate. Never
mark template work done on inspection alone.

`ci/smoke.conf` carries text that is hostile on purpose (`&`, `<`, a quote in
the display name and author, an accented letter, a CJK sentence end), and
`ci/check-smoke-mod.py` pins what the substitution owes ModInfo.xml. Change
either and the checker fails, by design.

`new-mod.sh` is re-runnable in the same sense: it builds the mod in a staging
directory and moves it into place as its last step, so an interrupted run
leaves no half-written mod that the next run would refuse. Proving that means
scaffolding, killing the run, and scaffolding again.

## Git workflow

Standard hordeforge lifecycle: this clone is shared, so never
`git checkout` / `git switch` / `git branch -D` in it — take a worktree per
unit of work (`git worktree add /tmp/7dtd-mod-template-<topic> -b <branch>
origin/main`), then branch → commit → push → PR → merge. Never commit
directly to `main`. No `Co-Authored-By` or other attribution trailers in
commits or PRs.

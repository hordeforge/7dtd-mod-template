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
./new-mod.sh ci/smoke.conf   # points target_dir at a temp dir, clone=no
```

Then, in the generated mod: `make test` and `make lint-shell` must pass, and
`make package` must produce a zip that extracts to
`Mods/<Name>/ModInfo.xml`. CI runs exactly this. Never mark template work
done on inspection alone.

## Git workflow

Standard hordeforge lifecycle: this clone is shared, so never
`git checkout` / `git switch` / `git branch -D` in it — take a worktree per
unit of work (`git worktree add /tmp/7dtd-mod-template-<topic> -b <branch>
origin/main`), then branch → commit → push → PR → merge. Never commit
directly to `main`. No `Co-Authored-By` or other attribution trailers in
commits or PRs.

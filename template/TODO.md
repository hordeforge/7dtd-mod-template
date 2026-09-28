# TODO — __MOD_DISPLAY_NAME__

Task queue. Claim a task by changing `[ ]` to `[-]` with
`in progress — <agent>, YYYY-MM-DD; session: <id>` (see AGENTS.md); mark it
`[x]` the moment it completes. Next task = first unchecked item under the
earliest unfinished section.

## Purpose

__MOD_PURPOSE__

## Design

- [ ] Break the purpose above into concrete gameplay decisions in
      `docs/design.md` (dated `Decided YYYY-MM-DD:` entries); raise open
      questions for the user instead of inventing answers.

## Implementation

- [ ] (add tasks as the design firms up)

## Testing

- [ ] Keep `make test`, `make lint-shell` and `make lint-py` green on every change.
- [ ] First in-game validation: `make build`, deploy per
      `docs/reference/environment.md`, verify the log is clean of XPath
      errors AND the change is visible in game.

## Open questions

- (none yet)

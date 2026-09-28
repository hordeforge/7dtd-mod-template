# Architecture Decision Records

One file per significant, hard-to-reverse **technical** decision for this
mod: the chosen approach, alternatives considered, and consequences — a
permanent record of *why*, not just *what*. Not for gameplay/balance
decisions (those go in [`../design.md`](../design.md)) and not for routine
implementation notes without a real fork in approach (those go in
[`../architecture.md`](../architecture.md)). See `../../AGENTS.md` for when
a decision warrants an ADR.

Numbered sequentially with a zero-padded 4-digit filename prefix (`0001-`,
`0002-`, …), never renumbered or deleted — a superseded decision gets a
**new** ADR that names the record it replaces, with the old one's `Status`
updated to `Superseded by [NNNN](NNNN-title.md)` and the index row below
changed to `Superseded by NNNN`.

An ADR records a decision that has been made, so a record here is never
`Proposed`. A choice still open for comment belongs to an RFC, under
`docs/rfcs/` (numbered and indexed the same way, created with its first
proposal): the ADR is written once the decision lands, and the RFC's
`Status` updated to point at it.

For a new decision: copy [`template.md`](template.md) into the next unused
number, fill it in, then add it to the index below.
`scripts/test_adr_records.py` holds all of the above: the numbering, the
status vocabulary, the supersession link, the index, and the dated entries
in [`../design.md`](../design.md) and
[`../architecture.md`](../architecture.md).

## Index

| # | Title | Status |
|---|---|---|

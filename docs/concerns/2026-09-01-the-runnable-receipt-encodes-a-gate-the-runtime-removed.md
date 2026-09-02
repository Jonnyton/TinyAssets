# The `runnable` receipt encodes a gate the runtime removed

**Filed:** 2026-09-01, from the founder's universe planning around a receipt
that was wrong.
**Severity:** P2 — nothing fails, but the universe's agent plans from a false
signal: it avoided code nodes, built prompt-node workarounds, and only learned
the truth by running anyway.

## The finding

Two definitions of one fact.

* The **runtime** (`tinyassets/graph_compiler.py`, `_validate_source_code`)
  says, in its own docstring: *"there is no host-approval check here any more:
  `approved` / `approved_source_hash` are provenance, not a gate."* The OS
  sandbox is the authority boundary (change `sandboxed-code-node`). What
  remains is a pattern scan, a size cap and a syntax check.
* The **receipt** (`tinyassets/api/branches.py`) still computes
  `runnable = not errors and not unapproved_sc` at four sites — `get_branch`,
  `validate`, `describe`, and the authoring receipt's
  `source_code_approval.runnable` — from `_approval_provenance_valid`, whose
  docstring says it mirrors *"the fail-closed runtime gate"* that no longer
  exists.

Tiny, live 2026-09-01, on the branch it then ran successfully:

> `runnable: false` on code-node authoring receipts is misleading. My code
> nodes do run; the receipt is not reliable enough to plan from.

## Also stale

`docs/concerns/README.md` row for the outbound-proxy concern (2026-08-27)
says *"`source_code` nodes are still unrunnable: `mark_approved` has zero
non-test callers"*. Inverted by the same change: they run; the zero callers
mean approval is simply no longer consulted.

## The fix

`runnable` reports what the runtime checks: validation errors (and, ideally,
the compiler's own source checks). `unapproved_source_code_nodes` may stay as
a provenance list, but nothing derives runnability from it. About twenty
assertions in `tests/test_describe_branch_approval.py` and
`tests/test_composite_branch_actions.py` pin the retired design and flip with
it — they are not to be quarantined.

# Async sub-branch sessions have no aggregate provider budget

**Filed:** 2026-08-27
**Severity:** P2 — no observed abuse; the shape allows unbounded fan-out spend

## The finding

Cross-family review of PR #2586, finding (b), `DISAGREE_CONCERN`.

`prepare_foreground_run_provider` mints a **sibling session** for an async
sub-branch whose run id differs from the parent's. That fix is correct — before
it, the child run was created FAILED before executing a node — but it does not
bound how many siblings a subtree may mint.

- Every call with a different valid run id constructs another session. There is
  no sibling count and no parent/child lineage check
  (`tinyassets/foreground_run_provider.py`, the different-run branch).
- Durable exhaustion is computed **per receipt**, and receipts are keyed by
  work-item / run id (`tinyassets/storage/provider_work_authority.py`). Reusing
  the same child run does not reset its budget — but minting a *distinct* child
  run gets a fresh one.
- `graph_compiler` enforces an invocation **depth** limit. That bounds chain
  length, not breadth, and it is not an aggregate provider budget.

So a branch that fans out wide enough spends N budgets where the operator
reasonably expects one.

## Why it is not fixed in #2586

#2586 restores a run path that was broken outright — every async sub-branch
failed before executing a node. Adding a subtree budget in the same change
would put an unreviewed accounting model on the critical path of a fix that is
already overdue.

More to the point, the fix is a **design decision, not a patch**, and
`AGENTS.md` puts money and authority shape in the "spec what is hard to
reverse" set. At least three shapes are defensible:

1. **Subtree budget.** The root run's receipt carries the whole subtree; each
   sibling draws from it. Correct accounting; needs a lineage column and a
   contention story for concurrent siblings.
2. **Explicit bounded delegation.** The parent declares how much it may hand
   down, and a child cannot exceed its grant. Fits the existing receipt/claim
   vocabulary; more moving parts.
3. **Breadth cap.** A ceiling on siblings per parent, mirroring the existing
   depth limit. Cheapest, and the least principled — it bounds the blast radius
   without making the accounting true.

## What is true today, and what would change it

No observed abuse: fan-out is authored by the universe owner, whose own
subscription pays for it, so there is no cross-tenant exposure. The concern
becomes urgent the moment a branch is **shared, remixed, or run on someone
else's compute** — a goal on the roadmap — because then the author of the
fan-out is not the payer.

Prerequisite for any option: a run needs durable parent lineage. Confirm
whether the run row already carries one before designing against option 1.

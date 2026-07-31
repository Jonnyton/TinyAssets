## Context

`worktree_status.py` currently builds a full status for every git worktree and
only then applies `--provider`. Each build can run multiple git subprocesses,
so hundreds of historical lanes make a logically narrow query exceed the
drain's 90-second allowance. The drain brief therefore places a global
operator diagnostic on every disposable worker's startup path.

After PR #1979 merged, a fresh foldback worker was told that the implementation
was already merged and also that it could own at most one PR. It treated the
old implementation PR as that PR, returned the same `PARTIAL` receipt, and
caused `partial-stalled`.

## Goals / Non-Goals

**Goals**

- Make an identity-scoped worktree query proportional to matching entries.
- Keep global inventory available for session/operator diagnosis.
- Make a foldback continuation produce one new durable PR and return its URL.
- Preserve every existing claim, review, CI, merge, and result-validation gate.

**Non-goals**

- Building the cloud drain or a new queue/refinery authority.
- Removing worktree inventory from the session-start ritual.
- Adding a local durable attempt-receipt domain.
- Parallel drain workers or market compute.

## Decisions

### Filter entries before status construction

Add a pure matching helper over `WorktreeEntry` identity fields and apply it to
`collect_worktrees(repo)` before `build_status`. Filtering uses the same
case-insensitive slug/branch/path substring rule as the existing post-build
filter, so matching output remains compatible while nonmatching entries invoke
no per-entry git probes.

A zero-match result is never proof that a lane is clean and never authorizes
editing. The worker independently verifies its exact prepared worktree and
STATUS claim through the existing gates before changing files.

### Use the exact drain identity on the worker hot path

The worker brief invokes `worktree_status.py --provider <exact identity>` and
caps that scoped diagnostic at 15 seconds. A timeout remains non-authorizing:
the worker may continue only from its clean exact lane and must still run
claim, collision, OpenSpec, and provider-context gates.

### Make foldback PR ownership explicit

When the persisted prior result is `PARTIAL`, the brief says:

- the implementation PR belongs to a previous worker and does not consume this
  worker's PR budget;
- this worker must create at most one new foldback PR after restacking;
- a successful terminal marker cites the new foldback PR, never the prior
  implementation PR.

The general one-PR rule is restated as per disposable worker attempt.

### Keep the implementation clean-room

Implementation and tests use only TinyAssets-local code, tests, requirements,
and independently stated orchestration properties. This change adds no Ringer
dependency and does not copy or adapt Ringer code, tests, fixtures, prompts,
data formats, command structure, or implementation structure.

## Risks / Trade-offs

- A provider substring may match more than one worktree. This is existing
  behavior and remains intentionally visible.
- A 15-second scoped timeout could still fire on a pathological matching lane;
  exact authority checks remain mandatory and the timeout is recorded.
- Prompt enforcement cannot prove a PR exists by itself. Existing GitHub merge
  verification and repeated-partial failure handling remain the enforcement
  boundary.

## Verification

- Unit proof that nonmatching worktrees never reach `build_status`.
- Equivalence proof for matching provider-filter output.
- Prompt proof for identity-scoped 15-second inspection.
- Prompt proof that partial resume requires a fresh foldback PR and states the
  per-worker-attempt budget.
- Zero-match proof that scoped inventory grants no clean-lane or edit
  authority.
- Diff/dependency review proving no Ringer source, fixture, prompt, test, or
  package entered the change.
- Focused pytest, Ruff, strict OpenSpec validation, diff check, and independent
  exact-head review.

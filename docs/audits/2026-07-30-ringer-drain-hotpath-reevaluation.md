# Ringer Drain Hot-Path Re-evaluation

Date: 2026-07-30
Initial provider: Codex (`codex-gpt5-desktop`)
TinyAssets base: `00ade586c80ab96fd228419b959a8244a7b9dfb9`
Review gate: no implementation based on this re-evaluation until the required
independent review is recorded in
`docs/audits/2026-07-30-ringer-drain-hotpath-review.md`.

## Executive Judgment

The earlier Ringer diagnosis remains directionally correct, and its authority,
isolation, review, and durable-delivery adaptations are producing useful work.
The live local drain is no longer primarily failing at implementation. It is
losing throughput at two harness boundaries:

1. every disposable worker can spend up to 90 seconds globally probing hundreds
   of unrelated historical worktrees before touching its packet; and
2. a foldback worker was told both to finish a merged slice and to own at most
   one PR, without being told that the one-PR budget is per disposable worker.
   It reused the implementation PR in a second `PARTIAL` result, producing
   `partial-stalled` instead of a foldback PR.

Ringer's applicable invariant is narrower than “add more agents”: an executor
starts from an explicit task packet, performs only packet-local preparation,
executes verification, and records an attempt result. Global inventory and
historical cleanup are supervisor/operator diagnostics, not per-task hot-path
work.

## Canonical Source Re-check

| Field | Value |
|---|---|
| Repository | `NateBJones-Projects/ringer` |
| URL | <https://github.com/NateBJones-Projects/ringer> |
| Default branch | `main` |
| Inspected commit | `a1a91b8b384a90dcca379e1cb9ab91405275ac46` |
| Commit date | `2026-07-28T22:48:00Z` |
| Re-checked | 2026-07-30 America/Los_Angeles |
| License | PolyForm Shield 1.0.0 |

The source head is unchanged from the earlier audit. TinyAssets continues to
use only independently restated orchestration properties. It does not copy,
adapt, vendor, or derive Ringer code, tests, templates, command structure, or
internal data formats.

## Source-to-System Map

| Ringer property | Current TinyAssets bridge | Current gap | Adaptation |
|---|---|---|---|
| `TaskSpec` requires a spec, check, timeout, attempts, and expected artifacts | STATUS admission + worker brief + one-PR contract | A zero-hint worker may refine and deliver, but its local startup still includes a global repository-history scan | Keep exact claim/context checks; make worktree inspection identity-scoped before expensive probes |
| One task workspace; retry reuses the task workspace | Controller admission worktree or worker-created exact lane | Foldback continuation language did not distinguish the prior implementation PR from the fresh worker's PR budget | State explicitly that the limit is per worker and require one new foldback PR whose URL is returned |
| Executed verifier and bounded retry context | Tests, exact-head independent review, CI, merge verification | Correctness boundary is sound; #1979 passed 171 focused tests and review | Preserve; do not weaken review or CI for speed |
| Eval log records each attempt | Supervisor log/state and result artifacts | Sufficient to diagnose this bridge incident; cloud receipts remain task 2.2 | Do not add a second local receipt authority; cloud automation owns durable user-visible receipts |
| Manifest lint detects structurally wasteful work | OpenSpec/claim checks and prompt contract | `--provider` filtering currently occurs after every worktree has been probed | Move filtering before `build_status`; prove output equivalence for matching entries |

## Runtime Evidence

Freshness: 2026-07-30, Windows local bridge,
`output/openspec-drain-auto-20260730-182443`.

- Attempt 1 delivered implementation PR #1975 as `PARTIAL`.
- Attempt 2 delivered foldback PR #1977 as `MERGED`.
- Attempt 3 returned `NO_CANDIDATE` after 5 minutes while no admitted row was
  available.
- Attempt 4 refined and delivered task 2.4 as PR #1979 in about 22 minutes;
  171 focused tests, strict OpenSpec validation, mirror parity, CI, and
  independent review passed.
- Attempt 5 verified #1979 but refused to create a foldback PR, repeated the
  same PR in `PARTIAL`, and moved the controller to `partial-stalled`.
- A fresh global `python scripts/worktree_status.py --json` diagnostic did not
  finish within 59 seconds and was terminated. Code inspection confirmed that
  `--provider` filtering occurs only after `build_status` probes every listed
  worktree.
- The controller was stopped between workers, and PR #1980 retired the exact
  stranded task-2.4 claim before this lane was admitted.

The evidence changes one earlier emphasis: zero-hint refinement is not itself
the dominant failure. Attempt 4 successfully fused refinement and delivery.
The immediate defects are unbounded unrelated startup inspection and ambiguous
foldback continuation.

## Adopt / Adapt / Avoid / Defer

### Adopt now

- Filter the worktree inventory before per-entry git probes.
- Require controller workers to run the identity-scoped inventory with a short
  finite cap; retain exact claim and provider-context gates.
- Say explicitly that one PR means one PR per disposable worker attempt.
- On a merged implementation continuation, require one new foldback PR and
  require the terminal result to cite that foldback PR.

### Preserve

- Sequential delivery in the local bridge.
- Exact STATUS identity and write-set claims.
- Test-first implementation, exact-head independent review, CI, merge
  verification, and OpenSpec foldback.
- A fused refine-and-deliver worker when no row is safely pre-admitted; the
  worker must still create a concrete STATUS packet before implementation.

### Avoid

- Removing global worktree inventory entirely; it remains useful outside the
  task hot path.
- Counting repeated verification of the same merged PR as useful progress.
- Treating the local controller as the target cloud architecture.
- Copying Ringer implementation under its current license.

### Defer to the cloud owner

- Durable user-visible attempt/health receipts:
  `activate-main-universe-spec-drain` task 2.2.
- Dependency-aware waves and backlog-refinery automation until the generic
  single-packet cloud path conforms.
- Market compute until requester-owned BYOC runs end to end.

## Smallest Implementation Slice

One OpenSpec change modifies `development-coordination-runtime`:

1. prefilter `worktree_status.py --provider` entries before `build_status`;
2. change the drain brief to use the exact identity-scoped diagnostic with a
   15-second cap;
3. make partial-resume text require a fresh foldback PR, clarify that the
   one-PR limit is per worker attempt, and require the terminal URL to name the
   foldback PR;
4. add focused regression tests and keep all authority/review gates unchanged.

The implementation is clean-room at the repository boundary: use only
TinyAssets-local code, tests, requirements, and independently stated
properties. Add no Ringer dependency and do not copy or adapt a Ringer fixture,
prompt, test shape, data format, or implementation structure.

An empty identity-scoped worktree result is diagnostic only. It is not evidence
that a lane is clean or authority to edit; a worker must independently verify
the exact prepared worktree and STATUS claim before changing files.

## Pickup Packet

- Branch: `codex/ringer-drain-hotpath-20260730`
- Worktree:
  `C:/Users/Jonathan/Projects/wf-ringer-drain-hotpath-20260730`
- OpenSpec owner:
  `openspec/changes/optimize-openspec-drain-hotpath/`
- Changed capability: `development-coordination-runtime`
- Files:
  `scripts/worktree_status.py`, `scripts/openspec_drain_supervisor.py`, focused
  tests, this audit/review, and coordination foldback
- Gate: research review first; TDD; strict OpenSpec; independent exact-head code
  review; one PR; restart the local bridge from updated main
- Next cloud task after landing: `harden-background-branch-execution-authority`
  task 2.5, then the activation/BYOC critical path already recorded in
  `activate-main-universe-spec-drain`.

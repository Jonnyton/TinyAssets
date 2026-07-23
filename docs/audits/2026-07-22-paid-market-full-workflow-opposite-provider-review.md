# Paid-market full-workflow opposite-provider review

- **Date/environment:** 2026-07-22 PT / 2026-07-23 UTC, Windows worktree `codex/paid-market-track-e-wave2-spec`
- **Reviewed state:** tracked working-tree amendment over `56681dbe`
- **Reviewer:** Claude Sonnet, invoked read-only as the opposite-provider architecture-to-requirement gate
- **Final verdict:** **APPROVE**
- **Scope:** target group 5 from `2026-07-22-openspec-full-coverage-audit.md`: production realtime paid-market inbox, atomic bid matching, claims, and delivery

## Result

The first review returned `NEEDS_CHANGES` despite strict OpenSpec validation. It
found four semantic blockers:

1. price discovery and Wave 2 both appeared to own ranking, while domain versus
   market acceptance ownership disagreed;
2. the request state machine raced a claim from `pending` despite declaring
   claims only after `bidding`, and “correction” had no defined edge;
3. snapshot-plus-tail reconnect did not state an ordering invariant strong
   enough to prevent a gap;
4. new request/bid/match/delivery tables lacked a spec-level deny-by-default
   authority boundary.

The corrected contract:

- makes price discovery the cross-lane quote evaluator and Wave 2 the
  intra-request bid/host/fan-out allocator;
- binds native firm quote id/version/digest to a request-scoped persistent bid,
  which maps one-to-one to the pure matcher’s `BookOffer`;
- leaves the semantic completion verdict with the domain owner while
  `paid-market-economy` owns only the bound request-lifecycle transition and
  accounting handoff;
- races cancellation and claim from `bidding` and defines correction as a new
  fenced `disputed -> running -> completed` attempt;
- uses a same-transaction durable per-shard outbox plus
  subscribe-and-buffer → repeatable-read snapshot/watermark → durable catch-up
  → live-tail ordering, with no correctness reliance on Supabase replay;
- adds deny-by-default workflow DML, least-privilege/RLS reads,
  fixed-search-path non-login-owner command functions, and independent
  locked-row positive-authority rechecks even for internal roles;
- names exact test outputs, cites distributed-execution S14/B36 to
  `docs/exec-plans/active/2026-07-18-distributed-execution-platform.md`, and
  uses persistent `bid` versus pure `BookOffer` terminology consistently.

The final foreground re-review independently inspected the corrected diffs and
returned `APPROVE`, finding all four blockers resolved and no new owner
collision. It explicitly did not delegate to a background process.

## Evidence

- `openspec validate paid-market-track-e-wave-2-transport --strict` — valid
- `openspec validate paid-market-live-price-discovery --strict` — valid
- `openspec validate --all --strict` — 36 passed, 0 failed
- `git diff --check` — clean
- Wave 2 delta — 14 requirement headings, 76 scenarios after correction
- Live-price delta — 16 requirement headings, 49 scenarios after correction
- Review was read-only; no edit, commit, push, or PR mutation occurred.
- `tests/test_uptime_canary_layer2.py` was not run.

## Non-blocking follow-up

- The distributed-execution active delta does not yet carry the
  `job_id:lease_fence:accepted_result_sha256` identity as its own requirement;
  this market contract therefore cites the owning execution plan rather than
  claiming that missing requirement has landed.
- This approval covers the Wave 2 full-workflow amendment and its composition
  with live-price discovery. The separate live-price task requiring review of
  PR #1574 source context remains unchecked until that source-specific gate is
  completed.

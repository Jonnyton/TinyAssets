## Context

Workspace create and checkout use one initial admission probe, one reconciliation
sweep after a busy refusal, and one bounded retry through `workspace_pool.admit`.
Its job-lock retry loop observes conflicts but discards that information. Receipts
currently contain storage and generation facts only. The owner-reported September
8 retest cannot distinguish successful serial admission from successful contention.

PLAN's evidence boundary justifies this addition: a user graph cannot inspect the
private scheduler database, and trust-critical effects should expose their own
evidence. This does not add a tool, a queue, a test-specific path or an evaluator.
Both browser-only and local clients read the same existing run/effect results.

## Goals / Non-Goals

Goals: expose accurate per-operation admission facts on success and refusal;
preserve the existing execution policy; keep old results honestly unknown.

Non-goals: FIFO fairness, new queue policy, changing timeout clocks, lock lifetime,
quota limits, cancellation, private workflow editing, refreshing webhooks, declaring
the checklist passed, or reconstructing historical admission behavior.

## Decisions

1. **Local observation value, not stored lease shape.** An optional mutable
   admission-observation object is passed to the pool by create/checkout. It is
   local to that effect invocation and shared across the initial probe and retry.
   It accumulates `attempts`, `lock_conflicts` and `retry_sleep_seconds`. Each
   attempted transaction increments attempts; only caught `REFUSED_BUSY` increments
   lock conflicts. Actual time in retry sleep is measured with a monotonic clock.
   The existing wall-clock deadline policy is unchanged. No callback, new storage
   table, process-global counter, or per-tenant metrics collector is introduced.

2. **An additive `workspace_admission` receipt.** Every result after at least one
   observed transaction attempt, including failures after admission, contains a
   snapshot with the three numeric fields above. The existing
   `error_kind` retains outcome authority: exhausted lock wait remains
   `workspace_busy`; success means admission succeeded, not necessarily later work.
   A positive conflict count is evidence of encountering a lock row, not proof
   the holder was still active: the following sweep may repair a stale row.
   Sleep duration is not total latency, FIFO order or a fairness score.

3. **No observations before admission.** Authority/schema/provision checks that
   reject before reaching the pool do not receive fabricated zero counters.
   Historical results remain unchanged; missing receipt means unobserved.
   The receipt is persisted through the existing effect-result path, under the
   same universe custody and read authority as the rest of that result.

4. **Keep data minimal.** No run/holder identity, universe ID, database/host path,
   lock key, queue position, credentials or user content enters the new fields.
   Existing refusal details are not expanded by this work. Observation survives
   a quota refusal after a previous lock conflict without relabeling the quota.

Alternatives rejected: infer contention from generation numbers or elapsed run
time (not evidence); force a long-running private probe (changes acceptance
workflows); add FIFO scheduling (unrequested policy); expose a lock-table reader
(new surface and disclosure); label every retry 'queued' (no queue exists).

## Risks / Trade-offs

- Consumers might read success as fairness proof: use factual counters only and
  document the limit; do not insert checklist-specific coaching in tool results.
- Synthetic tests could miss propagation: test both pool observation and actual
  effect receipt/readback, including a coordinated real lock holder/release.
- Reconciliation can clear a stale lock: count a conflict, not an active holder.
- Instrumentation could alter timing: use a passive observation object; preserve
  current sleep values, admission ordering and errors in differential tests.
- Exact-time assertions are flaky: inject monotonic time in pool tests and assert
  semantic bounds for real-thread tests.

## Migration Plan

No schema migration or backfill. Independent shape/basic-safety review, focused
tests, Linux oracle and CI, then normal reviewed image deploy and authenticated
canary/revision check. Send only `Retest your workflow checklist` in the existing
app. Its answer is acceptance evidence, not something the receipt pre-decides.
Rollback to the previous immutable image if admission behavior or health changes;
old readers can ignore the additive JSON and old receipts remain valid.

## Open Questions

The app may still require a deadline-exhaustion proof or a stronger contention
test after receiving evidence. Let its uncoached retest decide; do not manufacture
acceptance. The expired destination requires owner action independently.

## Pre-build evidence, 2026-09-08

Source comparison after `git fetch origin main`: workspace pool, adapter and tests
are unchanged between this worktree and origin/main; the whole committed trees
also compare equal. Existing evidence-doc edits were preserved on the new branch.

Windows baseline: `python -m pytest -q tests/test_workspace_pool.py
tests/test_workspace_effector.py tests/test_effects_at_node_time.py` => 243 passed,
3 skipped, 44 dependency deprecation warnings. No runtime edits made yet.
`python scripts/linux_oracle.py -- -q tests/test_workspace_pool.py -k bounded_wait`
could not start: Docker Desktop's Linux engine pipe is absent. Linux CI remains
required, and this Windows baseline is not a claim about POSIX isolation.

Persistence trace: `_fire_node_effects` preserves workspace results unchanged;
`runs.py` stores chain evidence under system-authoritative `external_write_results`;
the API run snapshot carries that mapping without a nested-field allowlist. Add
regression coverage for this path; do not expose a separate status API.

## Implementation verification, 2026-09-08

Windows working-tree focused suite: `python -m pytest -q
tests/test_workspace_pool.py tests/test_workspace_effector.py
tests/test_effects_at_node_time.py tests/test_run_snapshot_phase.py` =>
261 passed, 3 skipped, 44 dependency deprecation warnings in 14.92 seconds.
Includes coordinated real SQLite lock release for create and checkout, a
policy-differential observation test, and receipt persistence/readback.
`python packaging/claude-plugin/build_plugin.py` staged 393 files and passed
the import probe. Ruff passed on the two canonical runtime and four test files.
These results do not prove Linux isolation, live deployment, or app acceptance.

## Linux and deploy evidence, 2026-09-08

PR #3442 merged as `0e485ba0add1b852d712b4c5d349e542a4131268` after
exact-head Claude approval and required CI run 34204412801. The gate reports
no new failures (the broad suite retains known failures). Its JUnit artifact
10047675276 contains all four changed files: pool 71/0 skipped, effector 144/2
skipped, effects-at-node-time 40/0 skipped, run-snapshot 9/0 skipped; zero
failures/errors in all four. Thus 262 passed and 2 skipped on Linux, not a claim
that the entire repository suite is green.

Image build 34205838812 succeeded; production deploy 34206123316 succeeded,
including authenticated public `--assert-handles` canary and protected
`deployed_sha.py --assert-contains` for the immutable target. Local canary bearer
is absent; these commands ran in the authorized CI environment holding it.
Rendered app acceptance is recorded below, separately from these deployment gates.

## Rendered acceptance, 2026-09-08 08:48 UTC

After the protected deploy gate, sent exactly `Retest your workflow checklist`
through the existing Chrome conversation at `https://tinyassets.io/mcp/app`.
The app read deploy `0e485ba0add1` and marked contention recovery **PASS**: the
second workspace run observed two lock conflicts, retried and completed.
It also passed sequential, parallel, heartbeat, preflight, workspace+code and
read-only repository access. Busy retry-exhaustion refusal remained OPEN and
the stale exact webhook destination remained FAIL 404. No private workflow,
automation, connection or destination was edited by this task. This is live
test acceptance for the additive evidence capability, not completion of the
whole checklist. No post-fix organic receipt use is visible yet; retained in
the workspace-admission concern. Full rendered trace: `output/user_sim_session.md`.

# Pre-build shape review

September22,2026 UTC. Independent Claude Fable subscription review13185 finished
exit0 after210s on tree f2b3fc00b92f5515b07118b07605ee527a2a4a2c, identical to
deployed cad07bd0. Read-only, no tests. Verdict READY_TO_PROPOSE, not exact-head
implementation approval. Brief/result remain in root output/run-diagnostics-shape-*
and this record preserves the decision that gates building/push/rollout.

Reviewer supports adding typed metadata to existing target=run instead of a new
event target, preserving existing scope/ACL/envelope and reusing stored events.
Required holes: no raw detail copying, distinguish local start from provider
acknowledgment, do not treat terminal-row timestamp span as execution duration.
Suggested tests: completed evidence after later failure, payload allowlist,
unknown evidence, timing, scope and unchanged status/adapter behavior.

Lead source verification/dispositions:

- AGREE: api/runs.py1523 loads events, snapshot1341 loses useful metadata;
  runs.py3832-3841 records local start,3892-3893 stamps terminal observation;
  graph_compiler.py1487 emits returned-call detail.
- Refine timing wording: the terminal timestamps are separate clock calls, so
  their span is not literally guaranteed zero; it is not execution duration.
- Confirm returned does not mean validated: graph_compiler.py1504 onward parses
  the JSON contract after the ran event. Reviewer did not inspect that tail.
- Adapt: prefer strict normalized execution receipts from
  providers/execution_receipt.py; do not omit actual answering-model evidence
  while promoting legacy configured-model fields instead.
- Adapt: omit free-form failure_message rather than truncating arbitrary event
  exceptions into newly exposed metadata. Raw data remains under existing reads.
- Adapt: local start count is not provider attempt count; loop-return receipts
  need their own step/time to avoid attribution to a later attempt.
- Scope correction: _run_matches_scope compares the resolved universe, not the
  actor; canonical read ACL permits visibility/grant-authorized readers, while
  served graph selection stays pinned. This patch changes no grant policy.
- A bounded metadata projection is not a new telemetry producer or proof of the
  historical stall cause. Broader runtime reliability remains open.

Before ready/merge: independent exact-head review of implementation and test
evidence is still required. No implementation verdict is inferred from this
pre-build recommendation.

## Implementation verification (not release approval)

September22,2026 around01:38UTC, Windows Python3.14: base cad07bd0 tree
(frozen node-stream-budget worktree) selected snapshot/graph-receipt/engine
tests: 93 passed, 3 skipped. Candidate with tests/test_run_activity.py and
tests/test_run_activity_surface.py added: 216 passed, the same 3 skipped.
Command: `python -m pytest -q tests/test_run_activity.py
tests/test_run_activity_surface.py tests/test_run_snapshot_phase.py
tests/test_graph_answer_execution.py tests/test_engine_mcp_server.py`;
baseline omits the two new files. No new failure or skip.

Opus test builder46287 wrote tests/test_run_activity.py within its sole file
ownership, then exceeded420s and was killed by the wrapper (exit1). No passing
result or release approval is attributed to that peer. Lead read its entire
test file, retained it, and ran the tests above. Lead owns the integration tests.
Initial integration setup used legacy OAuth scopes incorrectly; corrected to
explicit extensions.read for canonical OAuth and the serving resolve-always
founder mode for engine reads. Actual private-universe ACLs and pinned selectors
are tested before events load; no runtime authorization policy was changed.

Plugin build completed497files/import probe-ok. Linux baseline:96passed/no skips.
First Linux candidate:219passed/no skips, but plugin rebuilding overlapped its
archive capture and emitted changed-file warnings. Do not treat that copy as
frozen-tree release proof; a clean candidate rerun is required before freeze.

Clean candidate rerun46537 completed exit0 after archive capture with no changed
file warnings: Linux Python3.11.15/git2.47.3/bwrap0.12.0,219passed in5.07s,
no skips (baseline96passed in6.89s). Command: `python scripts/linux_oracle.py
-- -q tests/test_run_activity.py tests/test_run_activity_surface.py
tests/test_run_snapshot_phase.py tests/test_graph_answer_execution.py
tests/test_engine_mcp_server.py`. Ruff, `git diff --check`, seven pre-commit
invariants and strict change validation also passed before release-review freeze.

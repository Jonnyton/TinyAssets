# Bounded workspace resource-policy correction

2026-09-08 PDT. Wider Patches, resource-policy simplification and owner acceptance
remain OPEN. This report concerns removal of the duplicate ten-workspace-start
gate and the new authorized usage projection, not all workflow capabilities.

## Change and review

[PR #3560](https://github.com/Jonnyton/TinyAssets/pull/3560) merged as
`0eb1388f354de6052fae51d4aacd1aa813fa3681` at 2026-09-09 02:51:06 UTC.
Both jobs/hour refusals were removed; job observations and existing transfer,
lease/pool/storage/lock/outbox safeguards remain. No private workflow was edited.
Status exposes admin-only observations with actual units, limits, allocations,
transfer reservations and honest unavailability for unmeasured total storage.

Independent Claude shape review ADAPT removed the first draft's new ledger and
epoch/migration machinery. Code round 1 ADAPT caught a real quiescent-WAL reader
failure. The corrected reader uses normal read-only SQLite isolation, allowing
its coordination sidecars without creating databases, schemas or records.
The suggested immutable fallback was rejected because it could ignore a
concurrent ACL change. Independent round 2 reproduced and approved the correction
at exact source head `79a4f7650f1c3307af76ecb522819b0c3212a9b7`:
[full approval](https://github.com/Jonnyton/TinyAssets/pull/3560#issuecomment-5594942162).

## Verification

- Windows/Python 3.14, focused eight-file suite: **393 passed, 9 skipped**.
  Command: `python -m pytest -q tests/test_resource_usage_status.py tests/test_engine_mcp_hardening.py tests/test_engine_mcp_server.py tests/test_api_status.py tests/test_get_status_primitive.py tests/test_workspace_pool.py tests/test_workspace_effector.py tests/test_run_usage_budgets.py`.
- Ruff, import smoke, OpenSpec strict validation and generated plugin parity passed.
- Linux/Ubuntu/Python 3.11 required PR run
  [34303597592](https://github.com/Jonnyton/TinyAssets/actions/runs/34303597592):
  **400 relevant passed, 2 unchanged Windows-only skips**, including all 31
  resource-status tests. Checked its actual checkout commit, not only metadata:
  `18443d16050715cfa352e4b04b89704d509909cc` has an identical complete source tree
  to the approved head (`git diff --exit-code` returned 0).
- Baseline: initial-attempt JUnit from main run 34301938622. No added relevant
  failure or skip. The old jobs-refusal assertion is intentionally replaced by
  eleven-lease and eleven-zero-byte-operation regressions.
- Local Docker crashed before tests. Commander authorized the existing Linux CI
  route; no host repair, weakened tests or production test workload. This proves
  affected POSIX/symlink behavior, not sandbox-jail coverage.
- Extended-suite differences were checked against historical evidence. The
  additional intermittent missing-provider-receipt load failure predates this
  patch; it is retained in
  [its concern](../concerns/2026-09-08-provider-receipt-intermittent-load-failure.md).
  [Detailed Linux reconciliation](https://github.com/Jonnyton/TinyAssets/pull/3560#issuecomment-5595029846).

## Deployment and app proof

Image build 34304843917 succeeded. Production deploy
[34305023434](https://github.com/Jonnyton/TinyAssets/actions/runs/34305023434)
completed successfully at **2026-09-09 02:55:19 UTC** (September 8, 19:55 PDT).
Inspected its actual job steps and logs with `gh run view 34305023434 --json
status,conclusion,headSha,jobs` and `gh run view 34305023434 --log`:

- Immutable image resolution, fail-safe deploy and health verification passed.
- Authenticated `python scripts/mcp_public_canary.py --url
  https://tinyassets.io/mcp --assert-handles` passed; rollback was not needed.
- Authenticated `python scripts/deployed_sha.py --url https://tinyassets.io/mcp
  --assert-contains 0eb1388f354de6052fae51d4aacd1aa813fa3681` reported
  `SHIPPED (per receipt)` at 02:55:17 UTC. Credentials stayed in CI.

This is **deployed and ready for owner testing**, not rendered acceptance.
Commander relayed the owner's standing boundary after deployment: live testing
belongs to the user; report readiness only, and do not send an app retest or ask
its agent to run workflows without a fresh explicit request. No app prompt,
workflow repair, duplicate deploy or post-fix organic-use claim was made.
The final rendered acceptance task remains unchecked; specs are synchronized
to the shipped implementation without representing that task as complete.

## Remaining limits

Unknown failed transfers still retain conservative byte reservations. Aggregate
retained-storage accounting, host-global capacity, other policy consolidation,
tool parity and owner acceptance remain open. Passing this bounded correction
does not establish that every arbitrary workflow or provider is supported.

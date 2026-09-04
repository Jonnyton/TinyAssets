# Workflow checklist deployment loop

## Founder direction, 2026-09-04

Deploy the current round of generic platform fixes, then send the existing
TinyAssets webapp conversation exactly:

> Retest your workflow checklist

Use the bound agent's rendered response to identify the next platform fix;
review, merge, deploy, and repeat until its checklist passes. Do not add
coaching or directly manage the user's workflow definitions or universe state.
This supersedes the previous instruction to stop before sending a live retest.

Founder clarification, 2026-09-04: success is the app agent reporting that it
can build the workflows it wants using reusable platform capabilities. Never
build, repair, or edit its private workflows to manufacture passing probes.
Continue the exact-prompt loop; its independent checklist is the acceptance
criterion, not platform-side test results alone.

## Current round

The workspace effect dispatcher did not forward the node timeout into pool
admission, leaving both create and checkout on the zero-wait default.
The fix forwards that budget into one retry after the initial admission probe
and reconciliation sweep. The existing transactional pool waits only on locks.

Windows Python 3.14 verification, 2026-09-04:

- `python -m pytest -q tests/test_effects_at_node_time.py tests/test_workspace_effector.py tests/test_workspace_pool.py`: 243 passed, 3 skipped.
- Broader workspace/runtime selection: 194 passed, 22 skipped.
- Ruff, plugin import probe and mirror parity passed.
- `python scripts/linux_oracle.py -- -q tests/test_effects_at_node_time.py tests/test_workspace_effector.py tests/test_workspace_pool.py`: could not start because Docker Desktop's Linux engine was unavailable. Startup then failed at its inference socket. Linux CI remains the landing gate.
- Claude review: APPROVE; recovered from its completed transcript because the wrapper retained only a closing message. Reviewer independently ran 140 tests (2 skipped).

Latest user checklist evidence was against `b1ec544c` around 21:29 UTC,
before terminal lock release deployed as `2102d630` at 21:33 UTC:
heartbeat, missing-input preflight and workspace happy path passed;
sequential and parallel probes were running; concurrent workspace refused;
external delivery reached a stale destination and received HTTP 404.
The intentional failure probe v3 is excluded.

## Deployed round, 2026-09-04 22:26 UTC

PR #2951 merged as `0512f3353bd5721c6bfa36b37e45eafeeb66e635`.
Linux required and slow tests passed in run `33924110227`. Linux, macOS and
Windows builds plus the Windows install test passed. Image build `33925175365`
published the exact revision; automatic deploy `33925440487` succeeded.
Its authenticated `python scripts/mcp_public_canary.py --url
https://tinyassets.io/mcp --assert-handles` and protected
`python scripts/deployed_sha.py --url https://tinyassets.io/mcp
--assert-contains 0512f3353bd5721c6bfa36b37e45eafeeb66e635` both passed.

The rendered app requested sign-in before the retest was sent. Sign-in opened
the existing AuthKit page; the browser integration then reinitialized and the
mission tab disappeared. No checklist prompt was sent and no private workflow
was modified. Asked the founder to restore the signed-in existing conversation;
the exact-prompt acceptance loop remains incomplete.

## Restored app, 2026-09-04 22:57–22:59 UTC

Founder restored the tab and explicitly told this task to proceed. Sent exactly
`Retest your workflow checklist`; the user message rendered verbatim, but the
app reported an unknown turn failure. One unchanged retry after the provider's
120-second cooldown failed identically. The bounded server log showed the
model subprocess exiting before a turn, and double truncation of the provider's
error hid its terminal cause. See the new checklist-turn concern; no checklist
row has been newly accepted, and no private workflow state was edited.

Next round preserves the head and tail of already-scrubbed provider failure
details within the same 200-character server-log budget. Independent review
caught seven earlier router cuts, now replaced with the same scrub-before-cut
helper. No diagnostic fields, authority, routing, or workflow shape changes.
Focused Windows tests: 116 passed across failure notices and provider routing;
the real-router regression was first demonstrated red against the old router.

Rollback for this diagnostic-only round: deploy the last healthy immutable
image through the normal fail-safe release workflow if startup or connector
health regresses. No storage migration or private-state rollback is involved.

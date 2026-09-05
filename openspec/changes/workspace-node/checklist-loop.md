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

## Diagnostic round deployed, 2026-09-04 23:32 UTC

PR #2959 merged as `97da0eadc3d3ca0bf6edee81394aaf922582978a`.
Image build `33929636420` and deploy `33929823161` passed, including the
authenticated public canary and protected deployed-SHA assertion. Retried the
unchanged exact prompt in the existing app at 23:34 UTC; it still rendered an
unknown turn failure. No checklist row is newly accepted.

Stopped blind retries after the third failed attempt and obtained independent
Claude diagnosis. Subsequent read-only metadata narrowed one confirmed defect:
live catalogue HTTP 200 declares `max`, which deployed Codex CLI 0.135.0 cannot
deserialize. The next generic compatibility round is isolated on
`codex/provider-catalogue-compat`; no workflow, provider binding, credential, or
user state is altered. See the checklist-turn concern for evidence and limits.

## Compatibility round verification, 2026-09-04 23:56 UTC

CLI pin 0.153.4 and explicit workspace-write launch replace the removed flag;
the platform keepalive job receives the same flag repair. The shape reviewer
required a real launch check, feature-default comparison, and preserving
scrubbed JSON error messages. Implemented all three; remote-plugin loading is
now explicitly disabled with account apps and shell tools. No private workflow
definitions, connection state, credentials, or model selections were changed.

Windows Python 3.14 baseline: 173 passed, 3 skipped. Changed focused selection
(`tests/test_codex_cli_compat.py`, providers, served_router, stream_watchdog,
dockerfile_shape, provider_sandbox): 189 passed, 3 skipped. Ruff and actionlint
passed; plugin import probe and mirror build passed. `python
scripts/codex_cli_smoke.py npm.cmd exec --yes --package=@openai/codex@0.153.4
-- codex` passed with an empty home, allowlisted environment, real required-MCP
startup, disabled account/plugin/shell features, and a fake loopback HTTP 401.
Docker image construction runs the same credential-free check on Linux.

`python scripts/linux_oracle.py -- -q tests/test_codex_cli_compat.py
tests/test_provider_served_router.py` could not start: local Docker Desktop's
Linux engine remains unavailable. Linux CI and Docker build must pass before
landing. Independent implementation review is running; no deployment claimed.

Rollback: normal fail-safe deploy of prior immutable image if startup or public
connector health regresses. No migration or user-state rollback is needed.

Final independent review approved 2026-09-05 00:10 UTC; durable artifact:
`docs/reviews/2026-09-05-codex-catalogue-compat-claude.md`. The strengthened smoke
inspects actual model tool specs and MCP bearer headers. Both old and new CLI
pass; native file patching is explicitly reported as unchanged baseline,
contained by the existing read-only mounts. Keepalive and both non-served
launch tests now also pin account/plugin restrictions. Follow-up tests: 83
passed. Final Linux CI and live deploy/retest remain outstanding.

Linux required run `33932155764` completed 2026-09-05 00:25 UTC with 14,618
passing tests and two new ratchet failures: the new structured-error helper's
vendor-prefixed identifier increased the provider-name count from 75 to 76.
Mechanically renamed that generic JSON helper to `_structured_failure_excerpt`
and updated its references; no behavior, guard, or baseline change. Local
ratchet plus focused suite: 204 passed, 3 skipped. Final container build
`33932130912` had already passed the strengthened bearer/tool-spec smoke on
Linux CLI 0.153.4. CI must rerun on the naming-only follow-up before landing.

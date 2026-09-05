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

## Compatibility round landed, 2026-09-05 00:44 UTC

PR #2964 merged as `c30daa8f5ee86f8db64f6bf7c2ea7b1a7b94396b` after required
Linux run `33933159500`: 14,620 passed, 54 skipped, nine failed and two collection
errors all covered by the existing quarantine; zero new failures and zero stale
quarantine entries. The gate passed, not an entirely failure-free suite.
Production image build `33933967217` is in progress; merge is not live proof.

Founder separately requires compatibility with providers unknown to TinyAssets
without routine platform patches. The pinned CLI/catalogue repair does not meet
that architectural outcome; the verified execution/registration gap is recorded
in `docs/concerns/2026-09-04-provider-compatibility-is-not-open.md`.

Deploy `33934197685` completed 2026-09-05 00:50 UTC. Its authenticated
`python scripts/deployed_sha.py --url https://tinyassets.io/mcp --assert-contains
c30daa8f5ee86f8db64f6bf7c2ea7b1a7b94396b` gate confirms production contains
the fix; `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
--assert-handles` passed. At 00:51 UTC the existing browser conversation received
exactly `Retest your workflow checklist`; the message rendered verbatim and the
app is thinking. The previous retry button targets a different user message and
was not used. Checklist acceptance remains pending.

The 00:51 UTC app turn failed before a checklist reply. Retained diagnostics
prove HTTP 400 rejection of the implicit platform model, not provider absence:
`gpt-5.4` is unsupported for the connected ChatGPT account. A model-only
production `printenv TINYASSETS_CODEX_MODEL` read returned exit 1/unset.

## Native model recovery, 2026-09-05 01:05 UTC

Work continues on `codex/provider-native-model-defaults`. Removing the implicit
model argv pin preserves explicit operator overrides and all isolation flags;
outcome and runtime labels say `provider-default`, not an invented model name.
The founder clarified the durable target: provider default initially, user-saved
defaults and choice from all models available through their connection. PLAN and
the compatibility concern record that target; ignored connection-local model
selection remains open, not silently activated by this patch.

Independent shape review ADAPT supported the change and required label/document
alignment plus coverage. Baseline Windows selection: 153 passed, 3 skipped.
New native-default tests failed on the old forced model (3 failed, 2 explicit
override cases passed). Changed expanded selection: 183 passed, 3 skipped; Ruff
and plugin mirror import probe passed. Local Linux oracle could not start
because Docker Desktop's Linux engine is unavailable; Linux CI remains required.

Initial hold: credential-free real CLI smoke, now omitting the model flag,
resolved `gpt-6-astra` but omitted tools from outgoing model requests. The fake
required MCP initialized/listed tools; even advertising `read_graph` did not
produce a tools field. Three attempts failed the same inspection invariant;
stopped retries and dispatched independent round-2 diagnosis/review (peer output
`output/provider-native-model-review.md`, completed execution handle 67648).

Round 2 returned ADAPT at 01:14 UTC: implementation supported, fixture must
understand Responses-lite additional_tools input items and deferred MCP discovery.
After those corrections the native-default real CLI smoke passed; it still
requires nonempty tool specs and applies the forbidden-name walk. It explicitly
reports code-mode deferred engine visibility as unobserved, not a proven tool
call. This unauthenticated custom-provider run uses the bundled default, not the
account default. App retest remains the final proof; no checklist row is closed.

Release queue, 2026-09-05 02:12 UTC: PR #2977 merged as
`9d361262896519c1ab3c05c4154d6aac0a151588` at 02:08:56 UTC. Final independent
round-3 review APPROVE is recorded in
`docs/reviews/2026-09-05-provider-native-model-defaults-claude.md`; no fourth round.
The first Linux run found two new failures (concern index entry and static command
shape parsing); mechanical corrections are pushed and 242 focused local tests
pass, 3 skip. Fresh required Linux run 33937064317 passed: 14,642 tests passed,
54 skipped, 9 failed and 2 collection errors matched the existing quarantine,
zero new failures and zero stale quarantine entries. This is a green baseline
comparison, not a failure-free suite. Both image smoke checks passed. Production
image publication 33938244843 is active. Production remains c30daa8f, and no app
prompt has been sent since its 00:51 UTC failure. Verify the actual deployed
target plus authenticated public canary, then send only the exact
retest request in the existing app conversation. Never claim this PR closes the
broader provider/model-selection gap or any checklist row before rendered proof.

Deployment verified at 2026-09-05 02:15 UTC: image build 33938244843 succeeded;
deploy 33938479563 passed authenticated `mcp_public_canary.py --assert-handles`
and protected `deployed_sha.py --assert-contains` for
`9d361262896519c1ab3c05c4154d6aac0a151588`. Exact retest request sent and rendered
in the existing app at 02:15 UTC; app is thinking. No private workflow, binding,
credential, model preference, or external destination was changed.

Rendered result at 02:17 UTC: the app reports all fresh runs settled. Sequential
`23afa7e5342146b3`, parallel `dda972835cc149f4`, heartbeat `675c4f54d8634185`
completed with provider-call evidence. Missing `context` was refused preflight.
Workspace `1c34376d6b9b498d` and overlapping `228acaa65de54cc3` completed; the
agent qualifies contention as smoke evidence, not fairness proof. External run
`6df9005077324601` still received HTTP 404 for the expired webhook destination.
The agent explicitly says the full nine-row checklist is NOT cleared and only
enumerates seven previously exercised lanes. The other two rows remain
unidentified/unverified; do not substitute these six PASS rows for full success.

Next: the existing host-action row for the expired exact delivery destination is
still needed; asked the founder asynchronously to restore/choose it through the
app's owner-controlled setup, without pasting credentials. No platform defect is
established merely by that third-party 404. No workflow/connection repair or
coaching is authorized. Preserve the full acceptance scope and obtain actual
rendered evidence for the omitted lanes as well. Native-default startup recovery
is verified; broader provider portability/model choice remains open separately.

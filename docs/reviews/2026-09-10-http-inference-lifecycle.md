# HTTP inference lifecycle: bounded shipping slice

September 10, 2026. Base b801ef11503223975c2e78cb1a8b62f280130a7c.
Branch codex/nonblocking-http-inference, extracted from the unshipped model
selection work. No model selector, discovery, pricing or preference changes
are included. No workflow, grant, secret, API or storage shape changes.

## Behavior and safety

The legacy HTTP executor called synchronous SQLite lookup, broker startup and
network request directly on its event loop, and never closed its owned proxy.
Move the existing operation into one executor Future with copied request context.
Keep the router on its loop. Shield and drain that same Future on cancellation,
including repeated cancellation and asyncio.run teardown. Cancellation wins over
late success or failure; it cannot start another attempt. The router holds its
slot/reservation until completion, then conservatively settles cancellation.
Close only an owned proxy, on the worker thread, in finally. Preserve the original
outcome if cleanup fails and emit only a fixed, secret-free warning. Reported
inference latency excludes cleanup.

This is not remote cancellation or exactly-once delivery. Existing broker IPC has
no independent total receive deadline: a wedged broker can delay draining. Never
release a still-running request merely because an observation timeout expired.
The change does not claim to fix that separate deadline limitation.

## Independent review before extraction

Claude shape review: ADAPT, 210 seconds. Preserved pre-cleanup latency, dominant
cancellation, broad cleanup Exception guard and no uncancel. Applied before
implementation review. Author changed the initial to_thread Task to a private
executor Future: asyncio.run directly cancels all Tasks, even shielded children.
An actual runner-shutdown regression covers the distinction.

Claude implementation review: APPROVE, 224 seconds. Independently ran all 14
initial lifecycle tests and checked CPython teardown, request context, cleanup
ownership and selected-model router reservation retention. Nonblocking concerns:
Python 3.14 shield may emit a sanitized error log for a late failed cancelled
request despite correct cancellation; and an owned test double lacked close.
The fixture now has close. No log-suppression workaround is included. Production
Python 3.11 does not have that 3.14 shield callback. The isolated shipping slice
adds a fifteenth regression through the existing legacy HTTP serving authority.
Final unchanged-head approval is recorded externally in the PR, not self-attested
inside the commit it approves.

## Local proof

September 10, 01:09 UTC, Windows Python 3.14:

`python -m pytest -q tests/test_http_inference_lifecycle.py tests/test_api_key_http_provider.py tests/test_provider_served_router.py tests/test_provider_admission.py tests/test_run_provider_session.py tests/test_mirror_parity_gate.py --tb=short -rs`

133 passed, 3 skipped, 13.53 seconds. Skips: Windows same-universe shared-reader
locking; POSIX bubblewrap; optional real-Codex fixture. Existing LangGraph Python
3.14 deprecations remain. Ruff and diff-check pass. Plugin build:396 mirrored
runtime files and successful import probe. Focused lifecycle file:15 passed.

Final actual Docker Linux run including the fifteenth test:135 passed, 1 skipped,
9.19 seconds (Python3.11.16, Git2.47.3, bubblewrap0.12.0). The single skip requires
an optional real-Codex fixture. Uses the already-reviewed oracle fixes from feature commit558b94a3
and image tinyassets-linux-oracle:ce0e83fb15a8 against this shipping working tree,
not the feature runtime. pyproject.toml SHA256 matches both trees:
0b058bf8e49288897131edc760a3f9d292be1336844f4f21d24d8004a099f143.
No Docker Desktop or host configuration changes. This test harness is not shipped.

## Release and rollback

Draft PR until exact-head independent approval; then all required CI checks,
normal merge and authenticated deployed-sha/public canary gates. Fresh rendered
app context precedes the exact owner-authorized message:
`Retest your workflow checklist`. Do not edit the user's workflows directly.
Do not count text-only HTTP completion as full model-picker/agent-tool support.

If HTTP error rates newly exceed twice baseline, shared-loop responsiveness
regresses, cleanup leaks grow, or accounting releases live attempts, revert this
isolated merge through a reviewed follow-up and deploy the prior runtime. There
is no data migration to reverse. Reverify deployed SHA and canary after rollback.
Keep model-selection work unactivated. No post-fix organic user proof yet.

## Landing receipt

PR3718 exact-head approval on a15d608c22c0789bdddc348f3185eacfd2b7b52f:
https://github.com/Jonnyton/TinyAssets/pull/3718#issuecomment-5611165147
Claude APPROVE141s;15 lifecycle tests independently passed. Final local proof:
https://github.com/Jonnyton/TinyAssets/pull/3718#issuecomment-5611228657

All required checks passed. Tests run34424623467 required-tests finished in14m28s:
14903 passed,54 skipped,10 deselected,9 known failures and2 known errors;
the gate reported zero new failures and zero stale quarantine entries. Slow
tests:10 passed,1 skipped. No quarantine or gate edits in this release.

Normal squash merge at2026-09-10T01:28:43Z:
b9d642646c8d0918c36bb640c470b34123824e15. Its tree equals the reviewed head.
Build34425633001 is the production image pipeline; deployment is not inferred
from merge or build alone. The new provider-routing requirement records only
this lifecycle behavior. No broader model-selection spec is synced as shipped.

## Authenticated deployment

Build34425633001 succeeded. Deploy34425981123 succeeded; public MCP canary
`python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
passed, and its constrained service-principal check at2026-09-10T01:35:00Z ran
`python scripts/deployed_sha.py --assert-contains b9d642646c8d0918c36bb640c470b34123824e15`.
Result: production reportsb9d642646c8d, containing the intended merge revision.
Evidence: https://github.com/Jonnyton/TinyAssets/actions/runs/34425981123
No local credential was read or substituted for that authenticated verifier.

Owned Chrome-extension app tab1346517848 was freshly reread after deployment.
The latest prior conversation still ended with the16:43PDT completed CSV export.
At18:35PDT the operator sent and verified exactly “Retest your workflow checklist”.
At18:38PDT the app reported releaseb9d642646c8d and five fresh passes: single-node
model (pong), sequential fixture handoff, parallel synthesis, workspace+HTTP
README read, and contention/recovery. Runsf74df08d9da04576 /8560d3c5974542bf are
its contention/recovery evidence. Webhook returned404 because its receiver had
been deleted. It opened “Reusable webhook checklist receivers”, asking to extend
the existing key to POST webhook.site/{receiver} and DELETE
webhook.site/token/{receiver}; the visible explanation explicitly covers any
matching UUID receiver the key can reach. Operator inspected but did not accept,
deny, clear, mute or answer the request. This is new owner authority, not a
platform guard to bypass.

The refreshed history also revealed two earlier16:38PDT owner approvals and app
answers that were absent from the long-lived tab's prior rendering: webhook run
1fb7cf62e27044ef had delivered200, cleaned up204 and closed the original checklist.
The app acknowledged the duplicate approval without repeating the run. Therefore
the original six-check checklist did complete; the latest repeatability failure
is a deleted receiver plus fixed-ID grant, not proof that delivery never worked.

Existing signed-in app session, not first-contact proof. No operator changes to
owner workflows, grants, keys or model selection. The five fresh passes are
rendered app evidence, not specific proof of live HTTP-executor cancellation,
full HTTP agent tools, model-picker behavior or new organic post-fix user use.
Those remain unproven; the lifecycle guarantees have the targeted regression
and cross-family evidence above. No blanket completion claim for select-agent-models.

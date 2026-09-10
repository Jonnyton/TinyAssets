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

Initial actual Docker Linux run before the fifteenth test:134 passed, 1 skipped,
9.77 seconds (Python3.11.16, Git2.47.3, bubblewrap0.12.0). Final run pending at
this commit. Uses the already-reviewed oracle fixes from feature commit558b94a3
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
Keep model-selection work unactivated. No live or post-fix user proof yet.

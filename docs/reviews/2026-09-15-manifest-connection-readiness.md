# Manifest connection readiness repair

Intent: show the Connect-model request only when the current owner lacks a
current serving connection, including accepted multi-provider assignments.

Production46647117, September15 UTC: the original subscription user's selected
Codex reply succeeded while Connect-model remained visible. The free-only
second user's actual lack of a connection is a separate condition.

Pre-build Claude Fable diagnostic/shape review83064 (343s, exit0) confirmed the
cause: the request rail calls a legacy-only authority resolver which rejects
all manifest assignments. It recommended a manifest-aware readiness path while
preserving execution fences. Terminal Claude failure diagnostics are a separate
lane; this patch does not claim to repair that underlying provider failure.

Approach: add a boolean local readiness projection under assignment admission.
Require one exact-owner serving enrollment and current accepted member custody.
Any independent live member suffices, even when the anchor is revoked. No model
discovery, executor probing, grants, preferences or launch permissions change.
Keep the legacy execution resolver and its capability/voice callers untouched.
No public API/schema/storage changes; this is a request-rail bug fix in the
existing model-selection lane, not a new authority primitive or project.

Reproduction: tests/test_pending_requests_power.py's four new manifest cases
failed before runtime edits. After repair, the combined five-file Windows run
passes88 tests, zero skips (September15 UTC):

    python -m pytest -q tests/test_pending_requests_power.py tests/test_model_access_requests.py tests/test_pending_requests.py tests/test_provider_serving_binding.py tests/test_model_options_composition.py

Coverage includes wrong owner/universe, pause, stale binding reference, loss of
all credentials, surviving independent member, unchanged strict execution
resolver, legacy HTTP grant revocation and credential rotation. The fixture
refuses any executor lookup after setup. No real credential/provider call.

Exact-head independent review, CI, deployment and rendered app proof remain
required. After shipping, reload the subscription user's conversation, check
the false request disappears, and send the exact workflow retest prompt. Check
the free-only user's genuine request remains, without granting new access.
Write as-built spec after live proof. No completion claim yet.

Rollback: redeploy previously healthy46647117 image using the existing release
workflow if connection prompts disappear for genuinely unpowered users or live
health regresses. No migration or data cleanup is involved. Preserve all user
workflows and credentials; rollback restores the prior false-prompt behavior.

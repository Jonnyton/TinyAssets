# Candidate verification — 2026-09-18 UTC

Environment: Windows host, isolated codex/portable-app-layout-mvp, integrated
base 3c4b011f. No private project changes, live writes, merge or deployment.

- `python -m pytest -q tests/test_app_layout_controller.py tests/test_app_layout_bindings.py tests/test_onboarding_model_setup.py`: 12 passed. Executes actual JavaScript parser, owner/status/home/provider fences, saturated/ambiguous refusal, private-config update preservation, wrong-owner readback refusal, no uncertain retry, successful application, portable-envelope retention, node identity and unsent-draft restoration. Real store tests retain conversations, memory and serving authority. Self endpoint tests cover connected, empty and degraded self identity.
- `python -m pytest -q tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_app_hosted_model_connect.py tests/test_onboarding_connection_progress.py tests/test_onboarding_app.py tests/test_onboarding_auth_boundary.py tests/test_onboarding_model_preferences.py`: 273 passed, one existing Starlette deprecation warning.
- Ruff on changed Python/test files passed.
- `python packaging/claude-plugin/build_plugin.py`: 453 files, import probe passed.

Initial independent Fable shape verdict: ADAPT. Its proposed collaborator
selection escape was rejected by lead/reviewer; caller identity and complete-list
fences now replace that escape. Exact-head cross-family release approval, hosted
CI, desktop/phone visual proof, deployed SHA, canary and ordinary two-user live
acceptance remain outstanding. The local minimal DOM test is not live proof.

Scope: consumed first-party declarative layouts only; not arbitrary executable
UI, complete portable harness/setup, provider authority or private app workflows.

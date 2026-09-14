# Served model setup: implementation checkpoint

September14 2026, local WindowsPython3.14. Worktree served-model-setup,
branch codex/served-model-setup, based on the unchanged PR3843 candidate.
Pre-code Fable5.1 shape review and proposal are in this branch. This checkpoint
is NOT exact-code review, Linux proof, a release candidate or live acceptance.

Implemented: pinned model_options/agent_bindings/agent_binding reads; catalogue
read admission and untrusted envelope; scoped preference save reusing the strict
parser/current-home CAS store; discovery-only metadata configuration through the
existing owner/grant validator. No broad binding/connection mutation forwarded.

Initial tests reproduced five missing-surface failures and one unbound pass.
After implementation and updating the intentional old refusal assertions:

`python -m pytest -q tests/test_served_model_setup.py tests/test_engine_mcp_server.py tests/test_model_options_api.py tests/test_onboarding_model_preferences.py tests/test_model_discovery_capability.py --tb=short`

194passed,3Windows skips,13.79seconds. Real storage cases cover own/foreign
binding reads, preference generation conflict, changed home and no provider-work
binding created by saving a preference. This is not real-account discovery.
Ruff and git diff --check pass.442-file plugin rebuild/import probe passes.

Remaining: typed bind_model_access owner request/answer/rendering and partial
failure semantics; coherent canonical connector preference path; expanded real
discovery/permission/admission tests; fresh head review, CI, deploy and rendered
app acceptance. Do not present preference save as inference authority or turn
this checkpoint into a final narrower feature. Private workflows remain untouched.

# OpenRouter onboarding MVP integration

September18,2026 UTC. Lane: `codex/automatic-model-bootstrap`, draft PR3853.
Integrated deployed main `64e29743b3836f92b077875ffc987c72f6300917` into the
existing isolated implementation. The only merge conflict was the generated
app checksum; the canonical generator regenerated it. App model-picker,
connection-copy and failure-history changes merged without conflict.

No authentication, storage or API design was changed in this integration.
The existing owner/home-bound hosted PKCE flow, exact endpoint grants,
account-filtered catalogue and separate free-only owner approval remain the
implementation. Existing setup stays recovery, never automatically empty.
The browser recovery guidance from the prior integration already distinguishes
missing free models, expired authorization, changed setup and uncertain results.

## Verification

Windows, Python3.14, September18 03:19–03:23UTC:

```text
python -m pytest -q tests/test_hosted_model_auth.py tests/test_onboarding_model_connect.py tests/test_model_bootstrap.py tests/test_model_bootstrap_binding.py tests/test_model_bootstrap_candidate.py tests/test_onboarding_model_setup.py tests/test_app_hosted_model_connect.py
106 passed in 10.46s (pre-integration baseline), zero skips

python -m pytest -q tests/test_hosted_model_auth.py tests/test_onboarding_model_connect.py tests/test_model_bootstrap.py tests/test_model_bootstrap_binding.py tests/test_model_bootstrap_candidate.py tests/test_onboarding_model_setup.py tests/test_app_hosted_model_connect.py tests/test_onboarding_app.py tests/test_discovery_http.py tests/test_pending_requests.py tests/test_pending_requests_power.py tests/test_onboarding_serving.py tests/test_onboarding_openai_device.py tests/test_app_model_picker.py
472 passed in 59.72s, zero skips

python -m pytest -q tests/test_app_failure_history.py tests/test_model_options.py tests/test_model_options_api.py tests/test_native_model_options_api.py tests/test_served_model_preferences.py
102 passed in 32.89s, zero skips; two upstream deprecation warnings
```

Ruff passed for the six new onboarding modules and seven new test files.
`python WebSite/brand/render_marks.py` regenerated provenance;
`python packaging/claude-plugin/build_plugin.py` staged452 files, import probe OK.
`openspec validate select-agent-models --strict` and
`git diff origin/main --check` passed. A cached merge diff reports an existing
blank EOF line in main's conversation-failure-history spec; the PR diff adds
no whitespace error. No Linux claim is made for these local Windows runs.

The documented provider contract was rechecked September18:
[OpenRouter OAuth PKCE](https://openrouter.ai/docs/guides/overview/auth/oauth)
still documents S256 authorization via `/auth`, returning a code to the callback,
and server exchange via `POST /api/v1/auth/keys`.

## Remaining release and acceptance gates

- Fresh independent approval must cover the eventual integration head. The
  September15 approval for `c9c8bb277db5b098e3d1a2fd02967723535dcd86` does not.
- Required CI must run for that head; the earlier draft's required tests passed,
  while its scope gate correctly failed without current approval.
- Lead owns deployment, protected deployed-revision/canary checks and rendered
  app acceptance. This lane does not merge, deploy or operate live browsers.
- A separate free-only owner must complete their own provider signup/consent,
  see the account-filtered catalogue and one model-access approval, then get a
  real free-model answer which survives refresh. No such proof exists yet.
- No account, credential, model grant or private workflow was changed here.
  Native hosted callback remains outside this web-first MVP.

The in-flight OpenSpec delta remains the requirement contract. Do not mark the
capability complete or sync it as shipped before live acceptance.

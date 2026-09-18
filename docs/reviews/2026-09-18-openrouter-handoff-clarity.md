# OpenRouter signup handoff clarity

User-reported live issue: a new account saw OpenRouter's starter-key overlay
before the actual TinyAssets authorization screen. After copying that key and
opening a fresh app tab, the existing secure deposit box was hard to find.

## Bounded correction

The hosted free-model card explains Continue, TinyAssets authorization,
possible return, and subsequent free-model approval in the original tab.
Copying a starter key is not required for that guided flow. A prominent
existing-key button scrolls to and focuses the single existing paste box;
it reads no key, submits nothing, and grants no authority.

The manual form is explicitly credential storage, not model activation. Its
existing resolveConnection/connectHTTP path does not bind serving or approve
free models. An unpowered user may not have inference available for generic
connection resolution; this patch does not claim otherwise or invent a bypass.
The guided authorization flow remains unchanged.

Follow-up live evidence at04:36UTC: signup can land on OpenRouter's workspace
instead of continuing authorization; a new explicitly approved ceremony also
returned an authorization error. The copy now gives dashboard recovery and
does not guarantee automatic return. Callback diagnosis belongs to the other
builder. Manual model activation is a separate gated addition in
`recover-openrouter-key-handoff`; this storage-only shortcut is not a completed
onboarding recovery and must not be shipped or reported as one.

## Verification — Windows, 2026-09-18 04:32–04:34 UTC

- `python -m pytest -q tests/test_app_hosted_model_connect.py
  tests/test_onboarding_connection_progress.py tests/test_onboarding_model_connect.py
  tests/test_onboarding_app.py`: 182 passed,31.21s.
- After harness formatting, hosted-controller suite:29 passed,4.27s.
- Actual shipped controller tests click the wired shortcut; assert original
  field/intent preservation, focus/reveal, no credential-value read, duplicate
  IDs, requests, navigation, approval, storage or credential output.
- Offline actual Chromium DOM at390px and1280px: original field focused,
  instruction shown, one paste box, no network/log activity or horizontal
  overflow. Local `output/probe_openrouter_handoff.py` uses rendered markup
  and the shipped controller, blocks all network, and uses no account/secret.
- Ruff, diff check, brand-parity52 assets and mirror-parity457 files passed.

After correcting the copy to match dashboard/error live evidence, repeated
on Windows September18: hosted controller29 passed4.56s; isolated Chromium
390px/1280px passed; `python -m ruff check tests/test_app_hosted_model_connect.py`,
diff check, brand52 and mirror457 parity passed. The manual recovery proposal
passes `openspec validate recover-openrouter-key-handoff --strict`; all four
planning artifacts exist and eight implementation/release tasks remain open.
Implementation is held for independent shape approval and the concrete shared
credential-deposit/account-deletion race documented in the design.

No provider account actions, live browser ownership, deployment, merge or
independent review performed by this author. Lead owns those gates and the
live signup acceptance. No endpoint, provider grant, inference or vault code
changed. Public website code was not changed; app brand receipt was refreshed.

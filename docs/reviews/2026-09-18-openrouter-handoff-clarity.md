# OpenRouter signup handoff and manual recovery

User-reported live issue: a new account saw OpenRouter's starter-key overlay
before the actual TinyAssets authorization screen. After copying that key and
opening a fresh app tab, the existing secure deposit box was hard to find.

## Bounded correction

The hosted free-model card explains Continue, TinyAssets authorization,
possible return, and subsequent free-model approval in the original tab.
Copying a starter key is not required for that guided flow. A prominent
existing-key button clears and focuses the single existing paste box in an
explicit OpenRouter free-model mode, hiding generic-service actions and copy.

Manual submission now uses the exact authenticated same-origin `deposit_key`
operation with literal `openrouter_user_models_v1` and a2048-character printable
ASCII key. It bypasses generic credential inference and reuses complete_bootstrap
to prepare the ordinary unanswered model-access request. Explicit approval is
still required. The input clears before awaiting; there is no browser secret
storage, URL leakage, automatic approval or secret replay. Login/view changes
and timeout retain honest unconfirmed state and require explicit resume.
The guided authorization flow remains primary and unchanged.

Follow-up live evidence at04:36UTC: signup can land on OpenRouter's workspace
instead of continuing authorization; a new explicitly approved ceremony also
returned an authorization error. The copy now gives dashboard recovery and
does not guarantee automatic return. Callback diagnosis belongs to the other
builder. The initially storage-only shortcut was incomplete; the final combined
patch includes the reviewed manual acquisition path and shared deletion guard.

## Initial UI-only verification — Windows, 2026-09-18 04:32–04:34 UTC

- `python -m pytest -q tests/test_app_hosted_model_connect.py
  tests/test_onboarding_connection_progress.py tests/test_onboarding_model_connect.py
  tests/test_onboarding_app.py`: 182 passed,31.21s.
- After harness formatting, hosted-controller suite:29 passed,4.27s.
- Initial controller tests clicked the wired shortcut; asserted original
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
planning artifacts exist. This was the pre-build baseline, not the final manual
recovery evidence below.

## Reviewed combined implementation — September18,2026

Claude Fable shape verdict ADAPT required a shared deletion guard: deletion
holds existing provider admission only around tombstone write, releasing before
Windows rename; the vault writer checks tombstone inside its transaction under
the same admission before owner rows and secret persistence. Non-home admin
deposits remain valid. Independent verdict provenance and adaptations:
`openspec/changes/recover-openrouter-key-handoff/shape-review.md`.

- Windows combined suite: **310 passed,1 platform skip,39.64s**:
  `python -m pytest -q tests/test_manual_model_connect.py
  tests/test_model_bootstrap.py tests/test_model_bootstrap_candidate.py
  tests/test_app_hosted_model_connect.py tests/test_onboarding_connection_progress.py
  tests/test_onboarding_model_connect.py tests/test_onboarding_app.py
  tests/test_vault_account_deletion_guard.py tests/test_account_deletion.py
  tests/test_credential_vault.py`.
- Linux oracle Python3.11.16/git2.47.3/bwrap0.12.0: **131 passed,0 skipped,15.13s**
  for the same list excluding browser-controller/app/progress files. Native WSL
  Ubuntu Docker invoked `scripts.linux_oracle.main()` with `_repo_root` set to
  the explicit mounted worktree because `.git` points to a Windows path. The
  canonical oracle copied the working tree; no production access.
- Shared-guard builder's T1/T2/T3 baseline: **3 failed,1 passed** on both Windows
  (0.85s) and Linux(0.61s). Fixed guard/account/vault suite Windows76passed1skip
  (6.68s), Linux77passed0skips(6.53s). Includes barrier deletion-vs-persist,
  post-delete refusal, no rename lock, non-home admin, absent legacy schema,
  malformed schema and denied-table-read vectors.
- T4 concurrent bootstrap: one new-key deposit wins; second refuses without
  rotating the vault. Route proof reaches real existing approval and connected
  state only after explicit answer. Paid-first catalogue selects a free model;
  paid-only catalogue refuses.
- Actual controller tests cover explicit mode, clear-before-await, no generic
  parser, literal request, invalid keys, duplicate submit, timeout, uncertain
  failure, login change before send and login/view changes after send.
- Isolated Chromium390/1280px uses actual markup/controller with synthetic
  response only and all real network blocked: secure input reaches visible
  unapproved confirmation, key cleared, no console output or overflow. Browser
  proof caught and fixed a disabled focus target. Phone screenshots under
  ignored `output/openrouter-handoff-*.png` and
  `output/openrouter-manual-approval-*.png` were visually inspected. No real
  user/provider session or secret was used.
- Focused UI recheck after copy/mode refinement:180passed27.60s. Final mirror,
  brand, formatting and hosted-controller checks are rerun before commit.

## Remaining release gates

Exact-head independent cross-family release review, hosted checks, deployment
receipt/canary and ordinary user browser acceptance remain lead-owned. No
production action, merge, live browser control or credential inspection by this
builder. New research-derived provider label/tab behavior remains separately
gated; none was implemented. OAuth durability repair must be combined and
verified before claiming the normal OAuth path repaired.

Non-blocking inherited hardening is recorded in
`docs/concerns/2026-09-18-bootstrap-deletion-hardening.md`. No multi-worker
serialization guarantee is claimed. Spec delta remains in-flight until land;
no deployment or completed onboarding claim is made here.

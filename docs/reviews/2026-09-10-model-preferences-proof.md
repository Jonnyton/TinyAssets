# Saved model preferences — local verification

September 10, 2026, approximately 00:42 UTC. Environment: local feature worktree
`codex/select-agent-models`, Windows Python and the actual Ubuntu Docker oracle.
This is not deployed app acceptance or completion of model selection.

## Implemented scope

Versioned strict preference codec, canonical owner/universe SQLite CAS storage,
and authenticated GET/POST `/mcp/app/models/preferences`. Automatic opt-in,
explicit native/default model and ordered accepted fallbacks are stored without
provider assignment/credential/cost authority changes. Empty explicit order stays
empty. Missing policy remains legacy; corrupt data holds. Current-choice input,
runtime policy consumption, UI, HTTP tools and live proof remain unfinished.

Signed-in scope derives from the existing complete founder home, not JSON/query
ids. A same-transaction founder-home/deletion fence prevents a concurrent home
change from recreating removed preferences. Settings do not need a working LLM.
The shared home helper's strict-error option preserves existing callers.

## Tests

```text
python -m pytest -q tests/test_model_preferences.py tests/test_model_preference_store.py tests/test_onboarding_model_preferences.py tests/test_account_deletion.py tests/test_model_policy.py tests/test_provider_work_authority.py tests/test_onboarding_app.py tests/test_onboarding_auth_boundary.py tests/test_mirror_parity_gate.py --tb=short -rs
```

Windows: **352 passed, zero skips**, 26.55s (session41807, exit0). One dependency
deprecation warning from Starlette's httpx-based TestClient.

Actual Linux oracle uses the same test arguments, with the already verified WSL
Git environment (no repository config changes):

```text
wsl -d Ubuntu --cd /mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets bash -lc 'export GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets6; export GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets; python3 scripts/linux_oracle.py -- -q tests/test_model_preferences.py tests/test_model_preference_store.py tests/test_onboarding_model_preferences.py tests/test_account_deletion.py tests/test_model_policy.py tests/test_provider_work_authority.py tests/test_onboarding_app.py tests/test_onboarding_auth_boundary.py tests/test_mirror_parity_gate.py --tb=short -rs'
```

Linux: **352 passed, zero skips**, 21.77s (session15537, exit0), Python3.11.16,
Git2.47.3, bubblewrap0.12.0. One Starlette/anyio deprecation warning.

Coverage includes strict UTF-8/duplicate-key/unknown-field/bounds checks; opaque
Unicode model ids and native default; explicit empty order; atomic initial and
update races; owner/universe isolation; generation exhaustion/corruption holds;
real account-deletion cleanup for current/former homes preserving another owner;
real auth middleware,
unpowered writes, foreign origin/malformed origin/wrong scheme and body bounds;
home deletion/rebind/tombstone races; no inference or serving-bind invocation.

The first broad run had one failure on both platforms: the exhaustive app-route
inventory expected the pre-change set. Updated it to assert the new GET/POST
route, then reran the complete group above. No baseline runtime failure was
excused. An initial codec test used an enormous parameter-derived test id;
bounded explicit ids fixed the test harness error without changing validation.

`python packaging/claude-plugin/build_plugin.py`: 407 files, import probe passed.
Targeted `python -m ruff check` and `git diff --check`: passed. Generated mirrors
match canonical runtime. No workflow definitions or owner grants were edited.
These final runs include the independent review's owner-key cleanup suggestion.
Review: docs/reviews/2026-09-10-model-preferences-review.md. Both peers terminated;
no review/test subprocess remains active from this slice.

## Live context

Owned Chrome-extension tab1346517848 was reread around00:37 UTC. Latest message
remains Sept9,16:43 PDT: the app completed its430-model CSV export after correcting
its earlier mistaken claim of a file-writing failure. No new user-visible blocker
or new checklist result. No prompt, approval, key deposit or workflow edit was
performed during this read. This is context, not proof of undeployed preferences.

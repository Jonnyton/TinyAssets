# Advisory model-policy implementation checkpoint

September9, 2026, branch codex/select-agent-models. Runtime/test commit
434285214bd466f5225a316a5aaa3e84b0cf8f35. This is an internal pure kernel;
no discovery endpoint, storage, UI, inference, grant or workflow mutation is
wired to it yet. Do not ship or describe it as the completed model picker.

Implemented source-neutral subscription/local default priority; explicit current
choice overriding saved primary without implicit fallback; accepted order;
fresh designated-source ranking with stable ties; capability/privacy/price
exclusions; advisory stale explicit labels; model/account capacity and finite
dedup. Existing authority must be refreshed before any future dispatch.

Evidence September9:
- Windows Python3.14: `python -m pytest -q tests/test_model_policy.py tests/test_mirror_parity_gate.py`:48 passed,5.96s.
- `python -m ruff check tinyassets/providers/model_policy.py tests/test_model_policy.py`:passed.
- `python packaging/claude-plugin/build_plugin.py`:397 files,import probe passed.
- Supplemental Ubuntu/WSL Python3.11.15: same48 tests passed,no skips,19.31s;
  one dependency deprecation warning. Temporary root /tmp/tiny-receiver-proof.0I31qj.
  Used the existing receiver-linux-proof.sh helper from the integration checkout,
  invoked with these two test files while cwd was this worktree. Not Docker proof.
- `git diff --check`:passed.

Independent shape review ADAPT and disposition are in the sibling shape-review
artifact. Exact code review80925 completed (exit0,281s), verdict ADAPT against
434285214bd466f5225a316a5aaa3e84b0cf8f35. Its full verdict and the subsequent
adaptation are in 2026-09-09-model-policy-code-review.md. Six new regression
cases failed before correction; all40 policy tests and15 mirror tests now pass
on Windows (55 total,4.08s). Updated Ruff/plugin/import checks pass. Supplemental
Ubuntu3.11.15 after adaptation passed the same55 tests,no skips,10.95s,temporary
root /tmp/tiny-receiver-proof.yqE58v. After merging the deployed HTTP receipt fix
into this branch, the combined policy/HTTP/agent-call/mirror group passed99 tests
on Windows in9.00s. Adapted-head kernel review remains outstanding; the separate
candidate-authority design review returned ADAPT, not runtime approval. No PR or
runtime activation exists for this kernel.

Separate prerequisite task1.2 is complete: HTTP receipt PR3680 passed exact-head
review and CI and deployed5c991f432566 at19:31 UTC with authenticated canary and
revision gate (deploy34395463075). The active app model selector is still absent.
Full routing/discovery/storage authority seams and HTTP tool loop remain open.

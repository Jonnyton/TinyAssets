# Lane report — harden branch access authority

Date: 2026-07-25  
Branch: `codex/harden-branch-access`  
Base: `f7142a5707d31d1e43d5a9996499b9716a81bebc`  
Original slice: `bd69bf9e`, `e977c5a8`, `d5db3ff8`  
Review-adaptation fixes: `d9b10455`, `c3d8efdd`, `0d3ccba6`

## Fix 1 — raw caller strings are not credentials

- **RED:** with the permissive provider restored,
  `test_caller_identity_string_is_not_an_authenticated_credential` failed:
  raw `"alice"` resolved to subject `alice` instead of `anonymous`.
- **GREEN:** `_CredentialSubjectProvider` now resolves only credentials it
  issued and maps each opaque token to a persisted subject. The dedicated guard
  passed, then the complete read/mutation authority pair passed **51/51**.
- **MUTATION:** reintroducing the unsafe raw-token fallback made the dedicated
  guard fail **1/1** in both the working checkout and the clean verification
  clone. After restoration, the authority pair passed **51/51** again.
- **PUSHED SHA:** `d9b10455a07605d6d3cb7beb43b429d81aea072b`
  (`test: reject raw branch authority identities`).

## Fix 2 — unreadable `parent_def_id` is not projected

- **RED:** a public child pointing at another subject's private parent exposed
  `parent_def_id`; the focused test failed on that leaked field.
- **GREEN:** `get_branch` now copies the stored record and removes an unreadable
  `parent_def_id`, while the private parent's owner still sees the pointer.
- **MUTATION:** removing the readable-parent projection gate reproduced the
  failure; restoring it passed the focused test and the full authority pair.
- **PUSHED SHA:** `c3d8efdd6932cbeb261a840bc06d000627b581a5`
  (`fix: hide unreadable branch parent references`).

## Fix 3 — composite approval tests use issued credentials

- **RED:** the expanded branch/visibility run found two deterministic failures
  because `_build_approved_source_branch` called `auth_middleware()` with raw
  `"host-operator"` and `"tester"` identity strings.
- **GREEN:** those two approval controls now use the shared issued-credential
  callback. The focused pair passed **2/2**, the composite suite passed
  **53/53**, and the expanded requested gate passed **209/209**.
- **MUTATION:** switching the helper back to raw middleware strings made both
  approval controls fail **2/2**; restoration returned them to green.
- **PUSHED SHA:** `0d3ccba6a6b641b091cdfa31e4c4c415dffbfee5`
  (`test: authenticate composite branch approvals`).

## Scope cleanup — out-of-scope patch persistence removed

- The local `_storage_backend().save_branch_and_commit(..., force=...)`
  `patch_branch` change and its conflict-only test were removed completely.
- `patch_branch` again snapshots before persistence and calls the existing
  `save_branch_definition` path. Its function body contains neither
  `save_branch_and_commit` nor `force=`.
- This cleanup restores the already-committed runtime, so it creates no
  standalone diff. The first post-cleanup pushed state is `d9b10455`; all later
  pushed SHAs retain the cleanup.
- `python packaging/claude-plugin/build_plugin.py` staged the canonical runtime
  (**285 files**) and returned `Import probe: probe-ok`.
- Canonical/plugin `branches.py` and `daemon_server.py` are byte-identical.

## Final clean-checkout verification

Disposable clean shared clone:
`C:/Users/Jonathan/Projects/wf-harden-branch-access/.pytest_cache/clean-branch-access-verify-shared`
at pushed SHA `0d3ccba6a6b641b091cdfa31e4c4c415dffbfee5`.

- Expanded branch-authority/adjacent suite:
  `test_branch_authoring_actions.py`, both complete authority suites,
  `test_branch_visibility.py`, `test_composite_branch_actions.py`,
  `test_patch_branch_auth_gate.py`, `test_related_wiki_visibility.py`, and
  `test_universe_visibility.py` — **209 passed**, 2 dependency deprecation
  warnings.
- Complete branch authority pair after restoring the mutation — **51 passed**.
- Raw-caller mutation — dedicated guard failed **1/1** as required.
- Ruff across all 12 Python files changed from `origin/main` —
  **all checks passed** with the established `E501` exception. Direct `E501`
  comparison reports the same eight box-drawing lines in
  `tinyassets/daemon_server.py` as `origin/main`; no new lint findings.
- Fresh clean clone parity — canonical/plugin `branches.py` and
  `daemon_server.py` are byte-identical, with clean `git status`.

An exploratory sweep of every test filename containing `branch` was intentionally
broader than the reviewed §3/4/5 and task 2.10 gate. It reached **299 passed**
and **63 failed**, all in legacy branch-creating suites that still depend on the
explicitly unfinished task 2.5 migration. That separate 189-reference migration
remains unchecked and was not smuggled into this security adaptation.

LANE_RESULT: done - raw caller strings are refused, all requested branch-authority and adjacent gates are green, mirrors match, and the out-of-scope force persistence change is gone.

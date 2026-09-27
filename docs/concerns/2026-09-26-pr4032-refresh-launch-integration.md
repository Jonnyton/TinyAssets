---
severity: P1
title: Refresh is not wired into the workflow launch lanes
filed: '2026-09-26'
summary: the pre-launch subscription refresh runs only on the served entry, because both workflow lanes pin `assignment_generation` before their seam and a refresh renews the accepted source, which advances it. Covering them means moving the seam ahead of the receipt mint
---

# PR 4032 refresh does not preserve the launch authority lifecycle

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows review worktree, HEAD 6a94d24224232cb59e8c3a6006ddab4a6e563422, base 2e7ace67.
**Severity:** P1

## Source (verbatim)

Codex independent review of `git diff 2e7ace67...HEAD -- tinyassets tests`:

- The interactive router uses provider_assignment._authorize_served_provider_call (router.py:607, provider_assignment.py:1585), which snapshots without calling the new refresh seam. Only foreground/background workflow paths call it.
- Foreground refresh runs after admission, using the admission default as `launching` (foreground_run_provider.py:869), whereas the actual node provider can come from policy.preferred.provider (line 908). Its authentication exception is wrapped as ProviderAuthorityHeldError (line 986).
- Successful renewal changes the assignment generation (provider_serving_binding.py:641); the already admitted foreground receipt requires the old generation/digest (foreground_run_provider.py:683), so its next validation at line 948 refuses the launch.
- Renewal results are ignored and renewal is attempted only when this call rotated/adopted (subscription_refresh.py:672). A failed renewal or crash after the vault write leaves fresh material and stale bindings; the next launch does not retry renewal.
- The endpoint/client are resolved before admission (subscription_refresh.py:345), but the credential is re-read inside admission and sent to that old endpoint (line 366). A concurrent re-deposit can therefore send the replacement credential to the previous credential's issuer.
- Adoption and materialization disagree: adoption ignores vault record timestamps (subscription_refresh.py:578); materialization falls back to them (credential_vault.py:2087). A new unstamped deposit can be replaced by an older stamped disk document. Default .credentials/codex homes are not found by the record-value path scan either.
- A launched native authentication failure becomes held_native_unknown (agent_turn_coordinator.py:146; storage/agent_turn_journal.py:298), which _next_after_signin refuses (agent_turn_coordinator.py:482). Its tests exercise ready engine inference instead of this native lifecycle.
- `raise ... from None` inside parsing/transport handlers retains __context__. In particular subscription_refresh.py:131 retains JSONDecodeError.doc containing the entire credential. The new test checks only repr(__context__), which omits .doc.

Validation: `python -m pytest -q tests/test_subscription_credential_refresh.py` — 33 passed in 1.52s. No full suite, subprocess reviewer, or other worktree used. These findings are source-trace evidence, not live-production verification.

Closure requires refresh before request/run authority is pinned, selected-source accuracy, recoverable custody renewal, endpoint selection tied to the locked credential, one authoritative document-version rule, context-free secret errors, and native no-effect authentication evidence that permits safe fallback. Add regression coverage through the actual launch/coordinator paths.

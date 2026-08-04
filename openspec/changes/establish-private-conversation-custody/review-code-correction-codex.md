### Findings

1. **Important — one-use grants replay after `fork`.**  
   The process-global key/registry at [tinyassets/conversation_custody.py:703](C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/conversation_custody.py:703) and consumption check at [tinyassets/conversation_custody.py:739](C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/conversation_custody.py:739) have no issuer-PID binding or post-fork reset. On Ubuntu/WSL, both parent and forked child successfully consumed the same grant:

   ```text
   parent=accepted
   child=accepted
   packaged-parent=accepted
   packaged-child=accepted
   ```

   This violates the one-use requirement and permits duplicate read/export or use of inherited live-check state. The packaged mirror has the identical defect. Existing hardened precedent resets capability registries after fork and validates issuer PID; the custody tests instead force `spawn` at [tests/test_conversation_custody.py:1474](C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tests/test_conversation_custody.py:1474).

2. **Important — a custody database is not bound to exactly one universe.**  
   The schema’s idempotency key omits `universe_id` at [tinyassets/storage/conversation_custody.py:79](C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:79), relying on each database being universe-exclusive, but [tinyassets/storage/conversation_custody.py:476](C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:476) persists or verifies no database-to-universe binding. Two valid grants naming different universes but the same registered directory produced:

   ```text
   first=universe_1
   second=rejected:ConversationCustodyConflict
   ```

   This contradicts independent cross-universe key reuse and allows different-universe records to coexist when a registry aliases or rebinds a path. The packaged storage mirror is identical.

### Prior four probes

All four prior defects are corrected under ordinary public/storage/package access:

- No callable production issuer or public constructor; a normally forged grant is rejected.
- No caller `now` parameter remains; expired/revoked and retention-clock probes pass.
- Corrupting only the duplicate retention column now raises `ConversationCustodyIntegrityError` and preserves the thread.
- Create/append tombstones now clear request/result/target correlation.

Verification: custody `67 passed`; targeted probes `6 passed`; related runtime/package tests `87 passed`; Ruff passed; all 70 strict OpenSpec validations passed; all 328 mirrors matched. `git diff --check` alone failed on trailing whitespace in `review-code-codex.md:3,6,9,12`. No files were edited.

REJECT
Reviewed exact head `7f56947eb349cd02987d036a74e59f71269d135e` against base `62ce277d77738d18a734f155410bc3245b775725`. No files were edited.

No Critical findings.

## Important findings

1. **Callers can still self-issue authoritative grants.**

   The blocked constructor and immutability methods at [conversation_custody.py:690](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/conversation_custody.py:690) are not an authority boundary. The capability key, seal function, payload type, and writable registry remain in the caller-importable module at [conversation_custody.py:703](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/conversation_custody.py:703), while consumption accepts whatever exact object and entry appear there at [conversation_custody.py:742](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/conversation_custody.py:742).

   The committed test helper itself supplies the complete forging recipe at [test_conversation_custody.py:144](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tests/test_conversation_custody.py:144): `object.__new__`, `object.__setattr__`, `_seal`, caller-authored `_GrantPayload`, `live_check=lambda …: True`, and direct `_GRANTS` insertion.

   I independently reproduced that sequence using caller-selected evidence and path. `create_thread` accepted it:

   ```text
   forge_probe=ACCEPTED caller-authored evidence conversation=conversation_...
   ```

   Thus removing `_issue_operation_grant` did not close prior finding 1; it only made issuance less convenient. The packaged mirror is byte-identical and has the same defect.

2. **Database binding is neither canonical nor permanent across rollback.**

   Schema initialization occurs before the operation transaction at [storage/conversation_custody.py:481](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:481). When no binding row exists, migration trusts only duplicate `universe_id` columns at [storage/conversation_custody.py:510](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:510); it never reconstructs thread `record_json` or validates deletion receipts. The binding insert then shares the operation transaction and is removed by ordinary rollback at [storage/conversation_custody.py:661](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:661).

   Independent probes produced:

   ```text
   rollback_probe=[] then_rebound=universe_b [('universe_b',)]
   legacy_thread_corruption_probe:
     binding=universe_b
     indexed=[universe_b, universe_b]
     canonical=[universe_a, universe_b]
   legacy_deletion_corruption_probe:
     binding=universe_b created=universe_b
   ```

   Specifically:

   - An authorized universe-A read against an empty database inserted the binding, failed `NotFound`, and rolled it back. Universe B then permanently claimed the same database.
   - After simulating a legacy database by removing the binding row and corrupting only a thread’s duplicate universe column, universe B was admitted even though immutable `record_json` still identified universe A. The database then contained canonical records from both universes.
   - The equivalent deletion-only corruption also admitted universe B.

   Normal concurrent successful first access, uncorrupted deletion-only migration, and separate registered paths behaved correctly. The missing failure cases make Task 3.1’s claim of “canonical thread/deletion” inference and transactional permanence inaccurate at [tasks.md:12](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/tasks.md:12). The delta spec also lacks normative database-binding, migration, rollback, and corruption scenarios despite the design’s one-sentence invariant at [design.md:228](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/design.md:228).

3. **Append replay returns a corrupted dangling reply edge.**

   The idempotent append replay path validates the replayed message’s duplicated fields and request digest, but returns it without verifying that its reply target still exists at a lower ordinal: [storage/conversation_custody.py:792](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:792).

   I created a message and a reply, removed the target row to simulate SQLite corruption, then retried the reply with its original idempotency key:

   ```text
   dangling_reply_replay=ACCEPTED message=... ordinal=2 reply_to=missing-message-id
   corrupt_read=ConversationCustodyValidationError
   ```

   The replay therefore disclosed an invalid persisted result. A later full read noticed the ordinal/reply corruption, but raised the domain validation error rather than the required storage integrity error. This contradicts the promised reply-edge reconstruction at [design.md:335](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/design.md:335) and the fail-closed scenarios at [spec.md:143](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:143) and [spec.md:158](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:158).

## Six-finding reproduction summary

| Prior finding | Result |
|---|---|
| 1. Caller grant forgery | **Failed:** self-issued evidence created storage successfully. |
| 2. Caller-controlled clocks | Passed independently: no public `now` parameters; expired grant rejected; logical/cleanup receipt times came from separate trusted-clock reads. |
| 3. Retention duplicate corruption | Passed: changing only indexed retention from 2030 to 2020 raised `ConversationCustodyIntegrityError` and preserved the thread. |
| 4. Tombstone association | Passed: create/append tombstones contained `NULL` request, conversation, result, and target digests. |
| 5. POSIX fork consumption | Passed on actual Ubuntu/WSL for canonical and packaged modules: `parent=accepted child=rejected exit=0`; pickle and ordinary mutation were rejected. |
| 6. Permanent universe binding | **Failed:** canonical legacy corruption and rollback/rebind cases above. Successful concurrent first access and independent paths passed. |

## Verification

- Focused custody suite: `69 passed, 1 skipped`.
- Related custom-agent/runtime-manifest/grant/packaged-runtime tests: `83 passed`.
- Ruff: passed.
- Mirror parity: all `328` canonical files matched.
- Isolated packaged imports: passed.
- Strict OpenSpec change validation: passed.
- All strict OpenSpec validations: `70 passed, 0 failed`.
- Flow check: `ALLOWED`; flow audit ran.
- Actual Linux fork probes: canonical and packaged passed.
- Tracked worktree remained exactly at the reviewed head with no modifications.
- `git diff --check` ran but failed on trailing whitespace in `review-code-correction-codex.md:3,15`. This is non-blocking style debt.
- No requested verification was unavailable. One standalone probe completed its behavioral checks but exited during Windows temporary-directory cleanup with `WinError 32`; the focused suite independently covered those passing cases.

REJECT
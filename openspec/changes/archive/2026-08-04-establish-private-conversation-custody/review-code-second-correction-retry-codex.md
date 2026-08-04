Reviewed exact head `b044097614c6524f0d4f67fcd41cb478c3b6411c` against rejected head `7f56947eb349cd02987d036a74e59f71269d135e`.

No Critical findings.

## Important finding

1. **Malformed completed legacy deletion receipts escape as request validation errors instead of storage integrity failures.**

   [`_load_deletion_receipt()`](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:272) constructs `ConversationCustodyScope` directly from duplicate database columns before entering its conversion catch at [line 303](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:303). Consequently, malformed indexed scope values raise `ConversationCustodyValidationError`. Legacy inference propagates that exception from [line 551](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/tinyassets/storage/conversation_custody.py:551).

   Reproduction:

   1. Create and successfully delete a thread.
   2. Remove `conversation_custody_database_binding`.
   3. Set the completed receipt’s duplicate `universe_id` column to `not canonical!`, leaving its canonical receipt unchanged.
   4. Attempt first access by another universe.

   Observed:

   ```text
   exception ConversationCustodyValidationError 'universe_id is not a canonical internal ref'
   binding []
   new_grant_admitted 0
   ```

   Admission remains fail-closed and atomic, but the required corruption classification is wrong. The delta requires tampered indexed columns to raise a storage integrity failure at [spec.md:178](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:178). A future caller could misclassify database corruption as invalid request input and skip repair/escalation. The byte-identical packaged mirror has the same defect at [its line 272](/C:/Users/Jonathan/Projects/wf-v1-app-conversations-20260803/packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/storage/conversation_custody.py:272).

## Other requested results

- Grant forgery: attacker-key signatures, `object.__new__`/`object.__setattr__`, and direct registry insertion were rejected with `grant_signature_invalid`.
- Copied legitimate envelope: durable consumption survived a `NotFound` rollback; the copy was rejected with `grant_consumed`.
- Signing input: exact domain `conversation-custody/operation-grant/v1\0` and exact 15-member canonical record confirmed.
- Noncanonical grant ID/signature, untrusted key, future issue time, expiry, and lifetime over five minutes were rejected.
- No custody production private key, signer, self-issuer, public consumer, or operation-level verifier argument exists. The verifier is process configuration only.
- POSIX fork: canonical and packaged Ubuntu/WSL probes both returned `parent=accepted child=rejected exit=0`.
- Normal expiry pruning removed the expired row; a copied expired envelope remained rejected with `grant_expired`.
- Binding/grant admission persisted before failed operations. Canonical legacy migration succeeded; valid duplicate-column corruption, pending-deletion-only state, multiple universes, and concurrent competing first access failed closed.
- Separate registered paths remained independent.
- Missing, cross-thread, same, future, and corrupt reply targets all caused replay-time `ConversationCustodyIntegrityError`.
- Both aggregate read and export translated sequence corruption to `ConversationCustodyIntegrityError`.
- The six older closures remain intact: caller clocks, canonical retention integrity, tombstone correlation, POSIX fork rejection, successful-path database exclusivity, and no public consumer.

Threat-boundary note: arbitrary in-process code or the same trusted host account can replace private functions, environment, or clock state. That actor is inside the declared `private_universe` trust boundary; ordinary request/app callers cannot exercise those controls through custody operations.

## Verification

- Focused custody suite: `76 passed, 1 skipped` in 9.69s; the skip was native-Windows POSIX fork, covered through WSL.
- Ruff: passed.
- Mirror parity: all 328 files matched.
- Strict OpenSpec validation: passed.
- Diff checks: passed.
- All 11 changed files were inspected.
- Tracked files and index: clean at exact head.
- Pre-existing untracked files remained unchanged: `_review_prompt.md` and the two `review-code-second-correction-*` files.
- Unavailable: native-Windows POSIX fork only; WSL supplied direct canonical and packaged coverage. Unrelated repository-wide tests were intentionally not run per request.

REJECT
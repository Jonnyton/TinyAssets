# Tasks: owner-message-wakes

## 1. Build
- [x] 1.1 `owner_message` event type, coalescing emitter, converse and consumer-projection emit sites.
- [x] 1.2 Automation create takes `not_before` / `delay_seconds`; resident text and handbook lines.

## 2. Prove
- [x] 2.1 Tests: `tests/test_owner_message_wakes.py`, consumer projection in `tests/test_consumer_public_turn.py`.
- [x] 2.2 gpt-6-astra refute round on the cross-user parts (ACCEPT, 2026-10-01).
- [ ] 2.3 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`.

## 3. Land
- [ ] 3.1 Sync the delta into `openspec/specs/user-owned-automations/`, archive.

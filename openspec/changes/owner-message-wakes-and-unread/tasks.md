# Tasks: owner-message-wakes-and-unread

## 1. Build
- [x] 1.1 Unread count and per-message read marker beside the conversation (`tinyassets/conversation_unread.py`).
- [x] 1.2 `OwnerUnread` middleware and the conversation read's marker hook (`tinyassets/engine_mcp_server.py`).
- [x] 1.3 `owner_message` event type, coalescing emitter, converse and consumer-projection emit sites.
- [x] 1.4 Automation create takes `not_before` / `delay_seconds`; resident text and handbook lines.

## 2. Prove
- [x] 2.1 Tests: `tests/test_owner_unread.py`, `tests/test_owner_message_wakes.py`, consumer projection.
- [x] 2.2 Mutation-check the cross-user filter and the marker-advance rule.
- [ ] 2.3 gpt-6-astra refute round on the cross-user parts.
- [ ] 2.4 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`.

## 3. Land
- [ ] 3.1 Sync deltas into `openspec/specs/`, archive.

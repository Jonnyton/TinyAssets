# Tasks: unify-connection-uses (Slice 1)

Owner: claude-code. One PR. Tier 2: it touches credential custody (the
deposit answer and the broker). Cross-family review is owed before landing.

- [x] 1. Bundled dialect documents (`providers/dialects/*.json`) and the
  `wire_dialects` resolver: structural names, stored aliases, checked schema.
- [x] 2. `protocol_encoders.PROTOCOLS` built from the documents. The agent
  envelope moves into `chat_messages.json`, and `agent_wire_shape.json` is
  deleted.
- [x] 3. Definitions accept the structural names. Dialect comparisons in the
  provider, selection, served plan and bootstrap go through `same_dialect`.
- [x] 4. `model_use` and `constant_headers` connection capability kinds, with
  closed validation.
- [x] 5. The broker applies constant headers. Auth is still applied last, and
  an unreadable declaration fails loudly.
- [x] 6. `DeclaredModelContract` and the declared snapshot in
  `refresh_model_discovery` (no fetch, POST scope). Workflow evidence gains
  the `declared` kind.
- [x] 7. `connect` request action: validation, rail sentence, and an answer
  that deposits, writes the uses and registers the model source.
- [x] 8. Deterministic selection when unpowered: `ensure_founder_serving` with
  explicit, free-only access to the declared models.
- [x] 9. `write_graph target=connection operation=configure` on the served
  surface and the public connector. `read_graph target=connections` shows
  uses and headers.
- [x] 10. Local acceptance (`tests/test_unify_connection_uses.py`): a
  never-seen LLM answers a turn with tools, and a never-seen platform takes
  an authenticated call with its constant header. Both go through the real
  broker to a loopback, and neither vendor name appears in `tinyassets/`.
- [x] 11. Tier 2 review, round 1: BLOCK on the money floor. Fixed: declared
  lists are refused beside a priced catalogue or accepted spend caps, the
  catalogue wins at read time, `configure` cannot create or change a model
  use, the rail wording is honest, and header merging is case-insensitive
  with credential names refused. Round 2 verifies these fixes only.
- [ ] 12. Live acceptance in the founder's app (see the PR). Then deploy,
  check with `deployed_sha.py --assert-contains`, sync the spec delta and
  archive.

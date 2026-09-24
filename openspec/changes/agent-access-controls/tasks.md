# Tasks: agent access controls (C27)

Owner: claude-code. One PR, Tier 2 (authority). One blocking review. The
cross-family review is owed before landing.

- [ ] 1. Storage: `pending_requests.origin` column (schema and
  `_ADDED_COLUMNS`), `create_request(origin=)`, and `withdraw_request` as a
  single guarded UPDATE.
- [ ] 2. API: `request_from_user(origin=)` (keyword only). Onboarding
  bootstrap passes `platform`. `withdraw_request` goes through `_owner_gate`
  and refuses `sys_connect_llm`.
- [ ] 3. API: `source_channel` `revoke` with the post-state readback;
  `source_code` refused.
- [ ] 4. API: `agent_access.read_access`, the one owner-gated readback (D1).
- [ ] 5. Served: `read_graph target=access`; `write_graph
  target=pending_request operation=withdraw`; `source_channel action=revoke`.
  Docstrings tell the agent each verb.
- [ ] 6. Connector: `read_graph target=access`; `withdraw_request`
  alongside the other request operations; `source_channel` revoke through
  the existing target.
- [ ] 7. Tests: red on the unfixed tree, then green. Cover readback matching
  after grant, revoke and withdraw; cross-user refusal for read, revoke and
  withdraw; platform-origin, answered and synthesized requests refused.
- [ ] 8. Concern: the source-channel policy store has no reader (D3).
- [ ] 9. Plugin mirror rebuilt; `ruff check`.
- [ ] 10. Live acceptance (after deploy): through the app, the agent reads
  its access, revokes one consent and reads it back, then withdraws one
  stale request of its own. Then sync the spec and archive.

# Tasks: rotate a rejected credential

Owner: claude-code (credential-rotate lane). One branch, one PR. Shape per
design.md.

- [ ] 1. `runs.py`: `credential_rejected` — the delivered-status matcher, the
  bounded 403 body test, insertion into `_classify_external_write` between the
  refusal KINDS and the refusal WORDS.
- [ ] 2. `runs.py`: `ACTIONABLE_BY["credential_rejected"] = "user"` and
  `CREDENTIAL_REJECTED_ACTION` returned by `external_write_suggested_action`.
- [ ] 3. `authenticated_external_call.py` + `_collect_external_write_errors`:
  a delivered result and its error row carry the connection's `destination`, so
  the card names the right one.
- [ ] 4. `credential_vault.py`: `http_credential_record()` — the one builder,
  stamping `deposited_at`; the deposit and both oauth2 refresh writers use it.
- [ ] 5. `http_connection.py`: `rotate_http` / `_rotate_http` under the gesture
  lock — vault-only write, every refusal before it, redacted projection.
- [ ] 6. `pending_requests.py`: the `rotate_http` action type, `_rotate_ask_verdict`
  (scheme + incarnation capture, refusals at raise time), `_SECRET_FIELD_TYPES`,
  the card sentence, and the answer branch that assembles the secret for the
  stored scheme and calls `rotate_http`.
- [ ] 7. Served guidance: the rotation paragraph in
  `_WRITE_GRAPH_CONNECTIONS_CHAPTER` points at `rotate_http` and says why
  remove+connect is not the repair path.
- [ ] 8. Tests: a 401 run classifies `credential_rejected` (and a 403 decoy does
  not); the card replaces the secret and the next call uses it while the policy
  is byte-identical; a foreign user and a foreign universe are refused; the
  secret is absent from every result, log record and exception. Mutation-check
  each.
- [ ] 9. `python packaging/claude-plugin/build_plugin.py` (engine_mcp_server.py
  is canonical) and `ruff check`.
- [ ] 10. Sync the two spec deltas into `openspec/specs/` and archive, same lane.

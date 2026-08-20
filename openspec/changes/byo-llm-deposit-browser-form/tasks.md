# Tasks — byo-llm-deposit-browser-form

Design gate only; Codex cross-family review before any build. Depends on
`byo-llm-deposit-surface` (reuses its `llm_deposit` handler). Rebuild PR #2417's UX
against main; #2417 stays closed.

- [ ] 1 Rebuild `tinyassets/connect_deposit.py` with routes `GET /mcp/connect/login`,
      `GET /mcp/connect/callback`, `GET|POST /mcp/connect`; cookieless signed
      HMAC-SHA256 state + session tokens with server-side `exp`.
- [ ] 2 Callback validates the AuthKit access token with the same resource-server
      validator `/mcp` uses to obtain the founder `sub`; fixed literal `redirect_uri`,
      never reflected from input.
- [ ] 3 POST runs the deposit AS the session `sub` through the `byo-llm-deposit-surface`
      handler (`write_credential_vault([record], owner_user_id=sub, ...)`); no second
      credential writer, no `_upsert_llm_deposit_owner`.
- [ ] 4 Narrow, ordered auth exemption for `/mcp/connect` + `/mcp/connect/*` from the
      MCP bearer challenge (`auth/middleware.py:459-466,:731-743`); wire
      `register_connect_routes` after the app is built (`universe_server.py:2888`).
- [ ] 5 Test: exemption is scoped — `/mcp` and a non-connect `/mcp/anything` still
      401; `/mcp/connect/login` runs its own logic.
- [ ] 6 Tests: tampered/expired state rejected at callback; unauthenticated/expired
      session rejected at POST; each writes nothing.
- [ ] 7 Test: browser deposit round-trips through the same vault write as the chatbot
      path and inherits the owner-only refusal (non-owner subject → zero mutation).
- [ ] 8 Test: token never appears in any chat transcript, log, or exception; HMAC key
      loaded vault-first, not committed.
- [ ] 9 `ui-test`: owner deposits via the browser form without pasting a token into
      chat; universe becomes serving-ready end to end. Rebuild the plugin mirror.
- [ ] 10 Codex cross-family review of proposal + design; log approve/adapt/reject
      before any implementation.

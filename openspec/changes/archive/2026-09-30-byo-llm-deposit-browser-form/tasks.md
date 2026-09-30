# Tasks — byo-llm-deposit-browser-form

Design gate only; Codex cross-family review before any build. Depends on
`byo-llm-deposit-surface` (reuses its `llm_deposit` handler). Rebuild PR #2417's UX
against main; #2417 stays closed.

- [x] 1 Rebuild `tinyassets/connect_deposit.py` with routes `GET /mcp/connect/login`,
      `GET /mcp/connect/callback`, `GET|POST /mcp/connect`; cookieless signed
      HMAC-SHA256 state + session tokens with server-side `exp`.
- [x] 2 Callback validates the AuthKit access token with the same resource-server
      validator `/mcp` uses to obtain the founder `sub`; fixed literal `redirect_uri`,
      never reflected from input.
- [x] 3 POST runs the deposit AS the session `sub` through the `byo-llm-deposit-surface`
      handler (`write_credential_vault([record], owner_user_id=sub, ...)`); no second
      credential writer, no `_upsert_llm_deposit_owner`.
- [x] 4 Narrow, ordered auth exemption for `/mcp/connect` + `/mcp/connect/*` from the
      MCP bearer challenge (`auth/middleware.py:459-466,:731-743`); wire
      `register_connect_routes` after the app is built (`universe_server.py:2888`).
- [x] 5 Test: exemption is scoped — `/mcp` and a non-connect `/mcp/anything` still
      401; `/mcp/connect/login` runs its own logic.
- [x] 6 Tests: tampered/expired state rejected at callback; unauthenticated/expired
      session rejected at POST; each writes nothing.
- [x] 7 Test: browser deposit round-trips through the same vault write as the chatbot
      path and inherits the owner-only refusal (non-owner subject → zero mutation).
- [x] 8 Test: token never appears in any chat transcript, log, or exception; HMAC key
      loaded vault-first, not committed.
- [ ] 9 `ui-test`: owner deposits via the browser form without pasting a token into
      chat; universe becomes serving-ready end to end. DEFERRED: needs the flow
      ENABLED on the live daemon + WorkOS/HMAC config (host/deploy step; dark by
      default). Mirror rebuilt.
- [x] 10 Codex cross-family review — VERDICT adapt. 3 basic auth-correctness fixes
      applied (sig malleability, exemption traversal/case, runtime kill switch),
      each with a red-without-fix guard. Deep session hardening (state
      browser-binding, one-use session nonce, adversarial probe suite) DEFERRED to
      multi-tenant — tracked in REVIEW.md; the flow stays DARK until then.

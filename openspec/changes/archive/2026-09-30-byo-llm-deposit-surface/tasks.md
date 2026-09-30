# Tasks — byo-llm-deposit-surface (chatbot deposit path)

Rebuilt against main's vault API (`write_credential_vault`), never PR #2417's
`_upsert_llm_deposit_owner` / `LLMCredentialAuthorizationDenied`. The secure-browser
transport is the separate change `byo-llm-deposit-browser-form`.

R2 residuals applied before build: **R2-item4** — spec wording corrected (the secret
DOES enter MCP/model context on the chatbot path) and the browser-form-before-
multi-tenant made an enforceable normative gate; **R2-item7** — this change declared
the canonical `llm_subscription` vault writer, `byo-llm-connect-flow` task 2.1
re-scoped to federate into this handler (its 2.2 read model unchanged).

- [x] 1 Add `tinyassets/api/llm_deposit.py`: derive owner server-side via
      `permissions.current_actor_id()`; require the caller hold an explicit `admin`
      ACL row on the target universe, read directly via `list_universe_acl` filtered
      to `actor_id==actor and permission=="admin"` (NOT `universe_access_permission`,
      per its public→`"read"` short-circuit); parse `{service, auth_material_b64}`;
      reject services other than claude/codex.
- [x] 2 Decode base64 transport → Claude token into `oauth_token`; keep the Codex
      value as a base64 **string** in `auth_json_b64` (never raw bytes; validated by
      `_decode_codex_auth_json`). Build ONE `llm_subscription` record.
- [x] 3 Call `write_credential_vault([record], owner_user_id=actor, universe_id=uid)`
      — record wrapped in a **list** (a bare dict clears the vault). Do NOT call the
      private `_ensure_llm_deposit_owner_schema`. Do NOT claim an atomic write-then-
      adopt; custody adoption stays in the `bind_serving_provider` re-point.
- [x] 4 Wire the `connect_llm` branch into the `connection` dispatch
      (`universe_server.py:946`), routing LLM ops to `llm_deposit` and keeping
      `cloud_connections` GitHub-only. Add **no** advertised handle.
- [x] 5 Return a non-secret projection incl. `agent_binding_id` + current
      `expected_revision` and the `bind_serving_provider`→`set_serving` next step
      (caller passes the post-bind revision to `set_serving`). No `switch_provider`.
- [x] 6 Tests: Claude deposit round-trips to `resolve_claude_oauth_token`; Codex
      deposit materializes `CODEX_HOME/auth.json` from the stored base64 string.
- [x] 7 Test: re-deposit upserts the single service slot AND preserves every
      unrelated credential (Codex + GitHub/VCS + Slack/social) byte-for-byte.
- [x] 8 Negative tests, each asserting ZERO vault/ownership/custody/binding/serving
      mutation after refusal: (a) another universe's founder targeting the victim
      universe; (b) a write collaborator depositing into an empty slot; (c)
      admin-vs-write distinction; (d) anonymous caller.
- [x] 9 Sanitized tests: no secret in the response, logs, or exception text on
      success and on malformed/base64-invalid input.
- [x] 10 Canary: `mcp_public_canary.py --assert-handles` stays green (no handle
      added). Rebuild the plugin mirror (`packaging/claude-plugin/build_plugin.py`).
- [ ] 11 Codex cross-family re-review of the revised proposal + design; log
      approve/adapt/reject before any implementation.

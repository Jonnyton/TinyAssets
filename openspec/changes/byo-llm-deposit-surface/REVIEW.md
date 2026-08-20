# Cross-family review trail — byo-llm-deposit-surface

Design gate. Reviewer: Codex (opposite-provider), read-only at main `4b4895d4`.

## Round 1 — VERDICT: adapt (5 findings, all code-verified)
1. Vault contract: pass `[record]` not a bare dict (bare dict → `{}.get("credentials",[])→[]` **clears the vault**); Codex `auth_json_b64` stays a base64 string; drop the private `_ensure_llm_deposit_owner_schema` call; add a preserve-unrelated-credential regression test.
2. Owner-tier hole: require explicit `admin` ACL via `list_universe_acl`, not a `write` ACL / public-read short-circuit; owner server-derived; negative tests (wrong-universe, empty-slot collaborator, admin/owner, zero-mutation).
3. False "one transaction" claim: deposit is write-only; custody adoption stays in `bind_serving_provider`.
4. Secret contract: state plainly the MVP token enters chat/model context + vault unencrypted at rest; browser transport before multi-tenant; sanitized parse/log/exception tests.
5. Serving params: return `agent_binding_id` + post-bind `expected_revision`; there is NO `switch_provider` (use `bind_serving_provider` + `set_serving`); split the browser form to a separate change (task limit).

All 5 revised. Split → `byo-llm-deposit-browser-form` (10 tasks); this change = 11 tasks. Both `openspec validate --strict` pass.

## Round 2 — VERDICT: adapt (2 narrow residuals; 1/2/3/5 confirmed resolved)
**Apply these two before the deposit BUILD starts (build currently deferred behind channel-agnostic-outbound):**

- **R2-item4 — spec/gate.** `specs/byo-llm-deposit-surface/spec.md` still normatively says the chatbot secret never appears in "transcripts", which contradicts the (correct) design statement that the token DOES enter MCP/model context. Fix the spec wording to match. And change "browser form SHOULD land before multi-tenant" into an **enforceable prerequisite/gate**, not a SHOULD.
- **R2-item7 — canonical writer.** No duplicate writer is implemented yet, but `byo-llm-connect-flow` task 2.1 claims requester-owned vault capture + API-key paste that overlaps this change's `llm_subscription` writer. Resolution: make **`byo-llm-deposit-surface` the canonical `llm_subscription` vault writer**; revise connect-flow 2.1 to federate OAuth/device flow into this handler and remove/separately-scope its `llm_api_key` paste; connect-flow 2.2 remains the connection inventory/read model. This also satisfies connect-flow's custody requirement (adoption relies on the server-recorded depositor).

After applying R2-item4 + R2-item7, run one tight confirming re-review → expected approve → build-ready.

## Open founder decision (does not block design)
Ship the MVP chatbot `connect_llm` path for the single-founder dogfood window (token through chat, unencrypted vault — a self-risk), or require `byo-llm-deposit-browser-form` (WorkOS AuthKit, no token-in-chat) first? Browser form is a hard prerequisite before any second user regardless.

## Why

Main already carries a complete, Codex-hardened credential-deposit **vault**, but
there is **no user-facing entry point that reaches it**. A founder cannot deposit
their own Claude/Codex subscription so their universe serves on it. Concretely,
main has the whole write-and-custody spine —

- `write_credential_vault(universe_dir, credentials, *, owner_user_id, universe_id)`
  (`tinyassets/credential_vault.py:395`) — the owner-scoped write that records the
  depositor in `llm_credential_deposit_owners` (`:459-470`) and *refuses ownership
  transfer* (`:432-435`);
- `adopt_llm_subscription_custody(...)` (`:698`) — mints the opaque custody
  reference, gated on the caller matching the server-recorded owner (`:726-727`);
- `snapshot_llm_subscription_credential(...)` (`:1070`), and the read resolvers
  `resolve_claude_oauth_token` (`:1393`) / `resolve_codex_home` (`:1288`) with their
  `claude_subscription_auth_available` (`:1400`) / `codex_subscription_auth_available`
  (`:1333`) probes;

— yet **nothing in the connector surface calls `write_credential_vault` for an
`llm_subscription` record.** The `connection` target dispatches only to
`cloud_connections` (`tinyassets/universe_server.py:946` → `tinyassets/api/cloud_connections.py:92`),
which handles GitHub/WorkOS-Pipes connections and returns `unknown_connection_action`
for anything else (`cloud_connections.py:190`). So the vault sits reachable-by-code
but unreachable-by-user: the founder has no way to hand their universe an LLM.

The live daemon carries a hot-patched deposit form from the **obsolete PR #2417**
(`connect_deposit.py`, head `f21714eb`), built against a **divergent older vault
API** (`_upsert_llm_deposit_owner` / `LLMCredentialAuthorizationDenied`) and
therefore **must not be merged**.

This change designs the **minimal chatbot deposit surface rebuilt against main's
real vault API**. It realizes the still-open `byo-llm-connect-flow` **slice 2**
capture path (task 2.1) as a concrete surface; it does **not** re-own the custody-
reference issuance or the serving bind, which the sibling `byo-llm-provider-connect`
capability already specifies. The secure-browser transport is split into a
separate successor change, **`byo-llm-deposit-browser-form`**, which reuses this
change's handler.

## What Changes

1. **Minimal chatbot deposit op.** Add `write_graph target=connection
   operation=connect_llm`. It routes — inside the existing `connection` branch —
   to a new owner-scoped deposit handler (`tinyassets/api/llm_deposit.py`) that:
   - derives the owner **server-side** from the authenticated principal
     (`permissions.current_actor_id()`, `permissions.py:249`), never a payload field;
   - requires the caller be the universe **owner/founder** — evidenced by an explicit
     `admin` ACL row read **directly** from `list_universe_acl` (the platform's own
     per-universe ownership predicate, `app_principal_mapping.py:186-194`), **not**
     `universe_access_permission` (whose public→`"read"` short-circuit,
     `daemon_server.py:4806`, would misjudge a public universe) and **not merely a
     `write` ACL** — the founder is granted `admin` at create (`api/universe.py:5784`),
     a write collaborator gets `write`, so requiring the `admin` row excludes
     collaborators and avoids the live write-ACL≈founder conflation
     (`api/interlocutor.py:17,:128`);
   - decodes the base64 **transport** material and calls **main's**
     `write_credential_vault([record], owner_user_id=<principal>, universe_id=<uid>)`
     — the record wrapped in a **list**, because a bare dict is read as
     `{}.get("credentials", []) → []`, which would **clear the vault**
     (`credential_vault.py:175-184`).
2. **Post-deposit re-point (documented, already built).** The result hint names the
   two existing operations that follow: `write_graph target=agent_binding
   operation=bind_serving_provider` (`universe_server.py:1033` → `custom_agents.py:302`
   → `provider_serving_binding.py:177`) then `operation=set_serving {"enabled":true}`.
   The hint returns the target `agent_binding_id` and the **new** `expected_revision`
   from the bind result, because `set_serving` requires the post-bind revision
   (`provider_serving_binding.py:542`). There is **no `switch_provider` operation**.
3. **No new advertised MCP handle.** `connect_llm` is an operation under the pinned
   `write_graph`, exactly as the `chat_surface` caller was added
   (`universe_server.py:954`), so `mcp_public_canary.py --assert-handles` (Hard
   Rule #11) stays green.
4. **Canonical `llm_subscription` vault writer (R2-item7).** This change's
   `llm_deposit` handler is the **single canonical writer** of `llm_subscription`
   vault records via `write_credential_vault([record], owner_user_id=…, universe_id=…)`.
   No sibling change ships a parallel `llm_subscription` deposit writer. Concretely
   this reconciles the overlap with `byo-llm-connect-flow` **task 2.1** (which claims
   "capture the returned credential as requester-owned into the universe's vault …
   API-key paste as the alternate"): connect-flow 2.1 is re-scoped to **federate its
   provider OAuth/device-flow result into this handler** (the OAuth/device flow
   obtains the material; this handler performs the owner-scoped `llm_subscription`
   write) rather than writing the vault itself, and its `llm_api_key` paste is
   separated out (already retired for MCP deposit by `retire-mcp-provider-secret-
   deposit`, which is scoped to `llm_api_key`). `byo-llm-connect-flow` **task 2.2**
   (the per-provider `connections` inventory/read model surfaced in
   `read_graph target=connections`) is unchanged and remains its own read model. This
   also satisfies connect-flow's custody requirement, because custody adoption relies
   on the server-recorded depositor that **this** handler binds. `byo-llm-connect-flow`
   is **not implemented here** — only the writer ownership is declared so no duplicate
   writer is built.

Non-goals: the secure-browser transport (own change
`byo-llm-deposit-browser-form`); provider-OAuth federation and credential *minting*
(`byo-llm-connect-flow` slices 1-2); custody-reference issuance and serving-bind
semantics (`byo-llm-provider-connect`); host-writer prune (slice 3); at-rest vault
encryption (credential-vault task 1.8); `llm_api_key` deposits (retired by
`retire-mcp-provider-secret-deposit` — which is scoped to `llm_api_key` only, so an
`llm_subscription` deposit remains permitted).

## Capabilities

### New Capabilities
- `byo-llm-deposit-surface`: the chatbot entry point by which a universe's
  authenticated **owner/founder** places their own requester-owned Claude/Codex
  subscription material into that universe's vault as an owned `llm_subscription`
  record, so the downstream custody/serving spine can serve on it.

### Modified Capabilities
- `live-mcp-connector-surface`: add the `write_graph target=connection
  operation=connect_llm` deposit operation while preserving the canonical
  advertised handle set (no new handle).

## Impact

- New: `tinyassets/api/llm_deposit.py` (owner-scoped deposit handler); a
  `connect_llm` branch in the `connection` dispatch of `tinyassets/universe_server.py`.
- Reuses unchanged: `tinyassets/credential_vault.py` (`write_credential_vault`,
  resolvers), `tinyassets/api/permissions.py`, `tinyassets/daemon_server.py`
  (`list_universe_acl`), `tinyassets/provider_serving_binding.py`.
- Security honesty: the chatbot MVP places a recoverable subscription token into the
  MCP transport and the model/connector context, and the vault is **not encrypted at
  rest** (`openspec/specs/credential-vault/spec.md:45`). The browser transport
  (`byo-llm-deposit-browser-form`) removes the chat-context exposure and SHOULD land
  before multi-tenant use.
- Security substrate: **design gate only**; Codex cross-family review returned ADAPT
  on the first draft (this revision addresses it); re-review before any build.

## Context

Main's credential vault is a per-universe, mode-0600 JSON store. Its as-built
protection is **filesystem permissions only** — it is *not* encrypted at rest
(`openspec/specs/credential-vault/spec.md:45`, "As-Built Storage Protection Is
Filesystem Permissions Only"; at-rest sealing is deferred to credential-vault task
1.8, per the `LLMCredentialSnapshot` note at `credential_vault.py:499`). Every claim
below is against **main at sha `4b4895d4`**; where the task framing and the code
disagree, the code wins and the gap is called out. This change is the **chatbot
deposit path only**; the browser transport is the separate successor
`byo-llm-deposit-browser-form`.

### The vault spine that already exists (do not rebuild)

| Step | Function | Location | What it expects |
|---|---|---|---|
| 1. Write + own | `write_credential_vault(universe_dir, credentials, *, owner_user_id, universe_id)` | `credential_vault.py:395` | `credentials` is a **payload**: a `list` is the records; a bare `dict` is read as `dict.get("credentials", [])` (`:175-184`) — so a bare record dict yields an **empty list and clears the slot**. Always pass `[record]`. `owner_user_id` is **trusted transport state, never a vault-record field** (`:404`). Records `(universe_id, service, owner_user_id)` in `llm_credential_deposit_owners` (`:459-470`). Refuses to change an existing different owner: `PermissionError "credential ownership transfer requires a dedicated flow"` (`:432-435`). Commits its **own** SQLite connection (`:419-471`). |
| 2. Adopt custody | `adopt_llm_subscription_custody(conn, *, universe_dir, owner_user_id, universe_id, service)` | `credential_vault.py:698` | Requires a **separate active** SQLite transaction (`:708-709`). Verifies caller == server-recorded owner (`:726-727`). Mints/rotates an opaque secret-free `LLMCredentialCustodyReference`. Internally calls the private `_ensure_llm_deposit_owner_schema` (`:718`); callers never invoke it directly. |
| 3. Snapshot | `snapshot_llm_subscription_credential(*, universe_dir, custody)` | `credential_vault.py:1070` | Immutable 0700 launch copy with a rotation-race digest check. |
| 4. Resolve (read) | `resolve_claude_oauth_token` / `resolve_codex_home`; `*_subscription_auth_available`; `provider_auth_env_overrides` | `:1393 / :1288 / :1400 / :1333 / :1440` | Compose `CLAUDE_CODE_OAUTH_TOKEN` / `CODEX_HOME` for the CLI subprocess. |
| 5. Re-point serving | `bind_serving_provider(...)` then `set_serving(..., enabled)` | `provider_serving_binding.py:177 / :503` | `provider ∈ {claude-code, codex}` (`:194`). Adopts custody itself; bumps the binding revision (returns the updated `agent_binding`, `:438`). `set_serving` requires `expected_revision == current["revision"]` (`:542`) and `created_by == owner` (`:540`). |

### The exact record shapes the vault accepts

From `_subscription_material` (`:542`), `_usable_subscription_record` (`:628`),
`_normalize_record` (`:146`), and the resolvers:

- **Claude**: `{"credential_type":"llm_subscription","service":"claude",
  "oauth_token":"<token>"}`. `resolve_claude_oauth_token` reads `oauth_token` then
  `claude_code_oauth_token` (`:1396`). Store the **decoded** token here.
- **Codex**: `{"credential_type":"llm_subscription","service":"codex",
  "auth_json_b64":"<base64 string of auth.json>"}`. This field MUST stay a base64
  **string** — `_decode_codex_auth_json` rejects non-strings and non-base64 and is
  validated at write time by `_normalize_record` (`:117-128,:165-171`). For Codex,
  base64 is both transport and the at-rest field; never store raw bytes.
- **Exactly one** usable record per service (`_usable_subscription_record` demands
  `len(records)==1`, `:636`); re-deposit **upserts the single slot** —
  `write_credential_vault`'s single-record path merges it (`_merge_single_record`
  `:274`) and preserves every unrelated credential type/service (`:339-362`).

### What is missing (the whole change)

The `connection` branch already resolves the actor and a universe gate for GitHub —
`cloud_connections` (`cloud_connections.py:98,:104`) — but the **dispatch itself
performs no authorization** (`universe_server.py:946-953` merely forwards), and it
returns `unknown_connection_action` for `connect_llm` (`:190`). **No surface calls
`write_credential_vault` for an `llm_subscription`.** That owner-scoped write, with
its own authorization, is the gap.

> Task-framing corrections: (1) `switch_provider` **does not exist** anywhere in the
> tree; the real re-point ops are `bind_serving_provider` / `set_serving`
> (`universe_server.py:1027-1047`). (2) "encrypted vault" is aspirational — the store
> is 0600 JSON (spec `:45`). (3) "write then adopt custody in one transaction" is
> **not achievable** with today's API (see Decision 3).

## Goals / Non-Goals

Goals: one owner-scoped chatbot write onto main's real vault; owner-tier (admin)
gate; fail-closed with zero mutations on refusal; secrets never echoed or in graph
state; keep the canonical handle set green.

Non-Goals: the browser transport (`byo-llm-deposit-browser-form`); OAuth federation
+ minting (`byo-llm-connect-flow` slices 1-2); custody/serving semantics
(`byo-llm-provider-connect`); host-writer prune (slice 3); at-rest encryption
(credential-vault task 1.8); `llm_api_key` deposit (retired elsewhere).

## Decisions

### 1. `write_graph target=connection operation=connect_llm` → `llm_deposit` handler

New `tinyassets/api/llm_deposit.py`, called from the `connection` branch
(`universe_server.py:946`) when `operation` is an LLM op (keep `cloud_connections`
GitHub-only). Contract:

1. `actor = permissions.current_actor_id()`; if `not is_authenticated_request()` →
   `{"error":"authentication_required"}`. No env fallback (`permissions.py:249-256`).
2. `uid = _request_universe(graph_id)`. Require the actor be the universe
   **owner/founder** — exactly one `admin` ACL row for `actor` on `uid`, read
   directly via `list_universe_acl(base, universe_id=uid)` filtered to
   `actor_id == actor and permission == "admin"`. This mirrors the platform's own
   per-universe ownership predicate (`app_principal_mapping.py:186-194`) and
   deliberately does **not** use `universe_access_permission`, whose public→`"read"`
   short-circuit (`daemon_server.py:4806`) would grant `"read"` on a public universe
   and never `"admin"`. On failure → `{"error":"not_found"}` (mirror
   `cloud_connections.py:105`, which does not leak existence). Narrower than
   `universe_access_allows(write=True)` and deliberately so — see Decision 2.
3. Parse `payload_json`: `{"service":"claude"|"codex","auth_material_b64":"<b64>"}`.
   Reject any other service loudly (Hard Rule #8); reject missing/oversize fields.
4. Decode base64 (transport only): `claude` → UTF-8 → `oauth_token`; `codex` → keep
   the base64 **string** in `auth_json_b64`. Build one `llm_subscription` record.
5. `write_credential_vault([record], owner_user_id=actor, universe_id=uid)` — record
   in a **list**. The vault binds `actor` as depositor and refuses a different
   existing owner (`:432-435`).
6. Return a **non-secret** projection: `{status:"deposited", service, agent_binding_id,
   expected_revision, next:"write_graph target=agent_binding operation=bind_serving_provider"}`.
   Never return the token, decoded bytes, or any digest (mirror the sanitized-summary
   discipline at `credential_vault.py:373-391`). Errors/logs/exceptions carry no
   secret (the vault's exception-hygiene pattern, `:302-315,:1160-1172`).

### 2. Deposit requires the owner/admin tier, not any write ACL

The live conflation `resolve_interlocutor_tier` grants T2/FOUNDER to any write-ACL
holder (`api/interlocutor.py:17,:128`; open STATUS hole). Depositing a subscription
is an owner action, so this surface does **not** rely on that tier: it requires the
explicit `admin` ACL row that a founder receives at universe create
(`api/universe.py:5784`) and a write collaborator does not — read directly (Decision 1
step 2), the same honest per-universe ownership question `app_principal_mapping`
asks (`:182-194`), so a public universe's short-circuited `"read"` cannot pass.
`owner_user_id` is always the server-derived authenticated subject. Combined with
the vault's first-depositor-owns +
no-transfer rule (`:432-435`) and `adopt_llm_subscription_custody`'s owner check
(`:726-727`), a stranger, another universe's founder, or a write collaborator can
neither seize an empty slot nor adopt/serve a credential they did not deposit.

### 3. Deposit is a single owner-scoped write; custody adoption stays with serving

`write_credential_vault` opens and commits its own connection after the filesystem
write (`:419-471`); `adopt_llm_subscription_custody` needs a *separate* active
transaction (`:708-709`). They are **not atomic**, so this design does **not** claim
a combined "write-and-adopt". Semantics: `connect_llm` performs only the owner-scoped
vault write. Custody adoption happens where it already does — inside
`bind_serving_provider` on the re-point step (owned by `byo-llm-provider-connect`).
Partial-failure/idempotency: a successful write stands on its own; a later re-deposit
upserts the single slot and preserves unrelated credentials, so a retry is safe and
non-destructive. (A genuinely atomic vault-owned deposit-and-adopt API is a possible
future in credential-vault, not assumed here.)

### 4. Re-point returns the post-bind revision; serving-hold is sticky-at-bind

`bind_serving_provider` updates the agent binding and bumps its revision (`:438`);
`set_serving` then requires `expected_revision == current["revision"]` (`:542`). So
the `connect_llm` result hint carries `agent_binding_id` + the current revision, and
the client chains `bind_serving_provider` (whose result carries the **new** revision)
into `set_serving` with that new revision. The `TINYASSETS_ALLOW_CLAUDE_SERVING` gate
for claude-code is evaluated at **bind time** (`provider_serving_binding.py:225`),
i.e. sticky-at-bind — it gates minting the serving authority, and is not re-read per
served turn; a host that later unsets it does not retroactively revoke an already-
minted serving binding (revoke via `set_serving {enabled:false}`).

### 5. No new advertised handle

`connect_llm` is an operation of the pinned `write_graph`, so the canonical handle
set is unchanged and `--assert-handles` (Hard Rule #11) stays green. Precedent:
`chat_surface`, "adds no advertised handle — the live tool catalog is pinned"
(`universe_server.py:954-960`).

## Risks / Trade-offs

- **Chat-context + at-rest exposure.** The MVP decodes a Claude token into the
  plaintext 0600 vault, and the base64 token transits the MCP request and the
  model/connector context. This is exactly the exposure `retire-mcp-provider-secret-
  deposit` argues against (though that change is scoped to `llm_api_key`, so an
  `llm_subscription` deposit is permitted). The browser transport
  (`byo-llm-deposit-browser-form`) removes the chat-context half and SHOULD land
  before any multi-tenant use; at-rest sealing remains credential-vault task 1.8.
- **Overlap with `byo-llm-connect-flow` slice 2.** This owns only the chatbot deposit
  write; if slice 2 lands its own capture path first, collapse the two rather than
  ship parallel deposit writers.

## Migration Plan

Additive. No schema change. The obsolete `connect_deposit.py` on the live daemon is
replaced by `byo-llm-deposit-browser-form`, not merged; PR #2417 stays closed.

## Open Questions

1. Confirm the explicit-`admin`-ACL-row gate (Decision 1 step 2) is the intended
   deposit predicate, versus adding the founder-home binding
   (`app_principal_mapping.current_founder_binding`) as a second required factor once
   the "Founder-account setup surface" (STATUS) lands.
2. Ship the chatbot MVP for the single-founder dogfood window, or require
   `byo-llm-deposit-browser-form` first (chat-context exposure)?
3. Codex to refute: with the direct-`admin`-ACL gate (not `universe_access_permission`)
   plus the vault owner-binding + custody owner check, is any confused-deputy or
   first-depositor path left open?

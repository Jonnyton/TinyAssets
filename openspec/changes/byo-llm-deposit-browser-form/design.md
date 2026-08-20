## Context

This is the secure-browser transport split out of `byo-llm-deposit-surface`. It adds
no new vault behavior — it reuses that change's owner-scoped `llm_deposit` handler —
and exists to (a) keep the subscription token off the chat surface and (b) grant the
one middleware exemption the form's routes require. All claims are against main at
sha `4b4895d4`.

### The auth boundary the form must fit inside

- `AuthContextMiddleware` wraps the entire app (`tinyassets/universe_server.py:2888`),
  so every request — including `/mcp/connect/*` — passes through it.
- `_auth_challenge_path` returns True for `/mcp` and every `/mcp/*` path except
  `.well-known` (`tinyassets/auth/middleware.py:459-466`); when the provider is in
  challenge mode and the caller is anonymous, the request gets a 401 OAuth challenge
  (`:731-743`).
- Therefore an anonymous browser hitting `GET /mcp/connect/login` (which has no
  bearer token yet — that is the whole point) would be 401-challenged before the
  form's own logic runs. The form's routes must be **exempted** from the MCP bearer
  challenge, and only those routes.

### The reused deposit handler

The POST deposits through the `byo-llm-deposit-surface` handler
(`write_credential_vault([record], owner_user_id=sub, universe_id=uid)` with the
owner/admin gate). This change specifies **no** vault write of its own — a second
deposit writer would be the exact duplication the split avoids.

## Goals / Non-Goals

Goals: a cookieless, AuthKit-authenticated browser deposit whose token never enters
chat; a narrow, correctly-ordered auth exemption for `/mcp/connect/*`; identical
owner-scoping and fail-closed behavior to the chatbot path.

Non-Goals: any new vault/custody/serving behavior; changing the chatbot path;
widening the auth exemption beyond `/mcp/connect/*`; at-rest encryption.

## Decisions

### 1. Cookieless signed tokens (carry state without `Set-Cookie`)

Cloudflare strips `Set-Cookie` on `/mcp*` (verified live per #2417), so a
cookie-based transaction fails at the callback. Carry both the callback-CSRF state
and the deposit session in signed, self-contained HMAC-SHA256 tokens with a
server-side `exp`:

- `GET /mcp/connect/login` → mint a signed **state** token (no cookie), 302 to the
  AuthKit authorize endpoint with it as `state`.
- `GET /mcp/connect/callback` → verify the signed `state` (callback CSRF), exchange
  `code` at the AuthKit token endpoint, validate the returned access token with the
  **same resource-server validator `/mcp` uses** to obtain the founder `sub`, then
  render the deposit form inline (200 HTML) with a signed **session** token (sub +
  CSRF) as a hidden field — no cookie, no redirect.
- `POST /mcp/connect` → verify the signed session + CSRF, then run the deposit **as
  the session `sub`** through the reused `llm_deposit` handler.

Confidential vs public client and PKCE are an implementation detail to settle at
build (the live hot-patch and #2417 differ); the spec requires only that the
callback obtains a validated `sub` via the same validator `/mcp` uses.

### 2. Narrow, ordered exemption for `/mcp/connect/*`

Register the connect routes so they are matched **before** the MCP bearer challenge
applies, and exempt exactly `/mcp/connect` and `/mcp/connect/*` from
`_auth_challenge_path` (or the equivalent ordering in `AuthContextMiddleware`). The
exemption MUST NOT open any other `/mcp` path, and the form's own signed-state /
signed-session validation becomes the sole authentication boundary for these routes.
Reachability needs no Cloudflare change: `/mcp/connect/*` is already forwarded as
part of `/mcp/*`.

### 3. No token on the chat surface; same vault honesty

The token is posted once over TLS straight into the reused deposit handler; it never
enters an MCP request, model context, or connector transcript. The at-rest exposure
is unchanged from the chatbot path (0600 JSON, not encrypted — credential-vault task
1.8); this change removes only the chat-context half.

## Risks / Trade-offs

- **Auth-exemption blast radius.** A too-broad exemption would expose other `/mcp`
  paths anonymously. Mitigation: exact-prefix match on `/mcp/connect`, a negative
  test that `/mcp` and `/mcp/anything-else` still 401.
- **Signed-token secret management.** The HMAC key must be a real per-deployment
  secret with rotation; a weak/committed key forges sessions. Treat as vault-first.
- **Redirect URI fixation.** `redirect_uri` must be a fixed literal, never reflected
  from the request (open-redirect / token-theft), as #2417 already fixes.

## Open Questions

1. Confidential client (client-secret) vs public client + PKCE for the AuthKit
   exchange — reconcile the live hot-patch, #2417, and current AuthKit config.
2. Where the HMAC signing key lives (vault-first per Configuration invariants) and
   its rotation cadence.

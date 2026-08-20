## Why

The chatbot deposit path (`byo-llm-deposit-surface`) lets a universe owner deposit
their Claude/Codex subscription, but the base64 token transits the MCP request and
the model/connector transcript, and lands in a vault that is **not encrypted at
rest** (`openspec/specs/credential-vault/spec.md:45`). Pasting a subscription token
into a chat is the exposure `retire-mcp-provider-secret-deposit` argues against. The
owner needs a way to deposit that keeps the token **off the chat surface entirely**.

The obsolete PR #2417 built exactly this UX — a cookieless WorkOS-AuthKit browser
form under `/mcp/connect/*` — but against a **divergent older vault API**
(`_upsert_llm_deposit_owner` / `LLMCredentialAuthorizationDenied`) that must not be
merged. This change rebuilds that browser transport to reuse the
`byo-llm-deposit-surface` handler against main's real vault, and specifies the one
thing #2417's UX depends on that main's middleware does not yet grant: a narrow,
correctly-ordered auth exemption for the form's own routes.

## What Changes

1. **Cookieless browser deposit under `/mcp/connect/*`.** A rebuilt
   `tinyassets/connect_deposit.py` with routes `GET /mcp/connect/login`,
   `GET /mcp/connect/callback`, `GET|POST /mcp/connect`. Cloudflare strips
   `Set-Cookie` on `/mcp*`, so callback-CSRF state and the deposit session are
   carried in signed, self-contained HMAC-SHA256 tokens with a server-side `exp`
   (as #2417 does), never cookies. The callback validates the AuthKit access token
   with the same resource-server validator `/mcp` uses to obtain the founder `sub`,
   renders the deposit form inline, and the POST runs the deposit **as that `sub`**.
2. **Reuse the deposit handler, not #2417's vault calls.** The POST calls the
   `byo-llm-deposit-surface` owner-scoped handler (`write_credential_vault([record],
   owner_user_id=sub, ...)`), inheriting its owner/admin gate, base64 handling, and
   fail-closed behavior — **not** `_upsert_llm_deposit_owner`.
3. **Narrow, ordered auth exemption for the form routes.** Today `_auth_challenge_path`
   (`tinyassets/auth/middleware.py:459-466`) sweeps `/mcp` and every `/mcp/*` path
   into the require-auth 401 challenge (`:731-743`), and `AuthContextMiddleware` wraps
   the whole app (`tinyassets/universe_server.py:2888`). The `/mcp/connect/*` routes
   MUST be exempted from that MCP bearer challenge — with explicit route ordering — so
   that their **own** signed-state / signed-session validation is the sole boundary,
   without opening any other `/mcp` path.

Non-goals: the chatbot deposit path itself (`byo-llm-deposit-surface`); OAuth
federation/minting (`byo-llm-connect-flow`); custody/serving semantics
(`byo-llm-provider-connect`); at-rest vault encryption (credential-vault task 1.8).

## Capabilities

### New Capabilities
- `byo-llm-deposit-browser-form`: a cookieless, identity-provider-authenticated
  browser transport for the owner to deposit their subscription without the token
  entering any chat transcript or model context, reusing the chatbot path's
  owner-scoped vault write.

## Impact

- New/rebuilt: `tinyassets/connect_deposit.py`; `register_connect_routes(...)` wired
  after the app is built in `tinyassets/universe_server.py`.
- Touches the auth boundary: a narrow exemption in
  `tinyassets/auth/middleware.py` (or route ordering ahead of the challenge) for
  `/mcp/connect/*` only.
- Depends on `byo-llm-deposit-surface` (the handler it reuses). Should land before
  any multi-tenant use of the deposit surface, to remove the chat-context exposure.
- Security substrate: **design gate only**; Codex cross-family review before any build.

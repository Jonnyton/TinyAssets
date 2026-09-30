# Cross-family review trail — byo-llm-deposit-browser-form

Reviewer: Codex (opposite-provider), on the built browser flow (auth flow +
`/mcp/connect(/*)` exemption + owner-gating reuse of the landed `connect_llm`).

## Round 1 — VERDICT: adapt

Founder process (2026-08-20): ship-MVP-first. The browser form is the
**multi-tenant prerequisite**, NOT on the single-founder MVP path (the landed
chatbot `connect_llm` already handles the founder's own deposit). So: one bounded
pass on the cheap basic-safety fixes, commit **DARK**, and track the deep session
hardening for when the flow is enabled for a second user.

### Applied now (basic auth-correctness, all with a red-without-fix guard)

1. **Signature not malleable.** `_unsign_token` compared the *decoded* signature
   bytes, and base64 decoding is malleable — a flipped trailing char can decode to
   the same bytes, so an altered token validated. Fixed to compare the **canonical
   base64url signature strings** with `hmac.compare_digest`. Guard:
   `test_signature_is_not_malleable` (constructs a non-canonical sig that decodes to
   identical bytes; rejected).
2. **Exact exemption boundary.** `_is_connect_deposit_path` now rejects `..` and
   `//` so the exemption can never cover a path that normalizes to a non-connect
   target (`/mcp/connect/../tools` stays challenged), and is case-sensitive
   (`/MCP/connect`, `/mcp/Connect` are not this route). Guard:
   `test_exemption_rejects_traversal_and_case_variants`.
3. **Runtime kill switch.** Each connect handler (via `_hardened`) re-checks
   `TINYASSETS_CONNECT_DEPOSIT_ENABLED` per request and returns 503 when off, so
   toggling the flag off on a live process stops the handlers, not just future
   registrations. Guard: `test_runtime_kill_switch_503_when_disabled`.

## DEFERRED — must-fix BEFORE enabling for >1 user (multi-tenant)

These are the reason the form stays **DARK** (`TINYASSETS_CONNECT_DEPOSIT_ENABLED`
unset by default; registration + exemption both gated on it). The single-founder
MVP does not depend on this surface.

- **Browser-binding of the OAuth `state`.** The signed state token is not bound to
  the initiating browser, so it is portable between browsers. Bind it (e.g. to a
  per-flow value the same browser must return) before a second user relies on it.
- **One-use nonce / replay consumption on the session token.** The signed session
  token is replayable within its TTL (no server-side single-use record). Add
  one-use consumption so a captured session proof cannot be re-posted.
- **Adversarial probe suite.** Forwarded-callback / session-swap (one user's session
  posting against another's universe — currently caught by the `connect_llm` admin
  ACL, but prove it) and an exception-leak probe (assert no credential material in
  any error path/log across the callback + POST) before multi-tenant enablement.

## Not blocking (single-founder MVP)

Confidential-client (client_secret_post, no PKCE) matches #2417's live-proven shape;
HMAC signing key is vault-first (`_env_or_file` + fd-fstat owner-only read),
fail-closed if weak/missing. The at-rest vault exposure is unchanged from the
chatbot path (0600 JSON; credential-vault task 1.8).

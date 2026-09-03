# Local MCP OAuth session lifecycle is only partly proven

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Codex desktop/CLI on Windows against
`https://tinyassets.io/mcp`.
**Severity:** P1 — sign-in works, but reconnect and revocation semantics are not
yet a complete cross-platform session contract.

## Source (verbatim)

> Cover secure credential storage, refresh/expiry, logout/revocation, multiple
> local sessions, and cross-platform behavior. Browser users and local agent
> users must resolve to the same account/universe.

Founder directive, 2026-09-03.

## Proven acceptance slice

Before login, `codex mcp list` reported the live server as `Not logged in`.
`codex mcp login workflow-live` completed WorkOS OAuth with PKCE, the canonical
resource indicator, and `offline_access`. A fresh, read-only Codex process then
called `get_status(include_conversation=true)` and reported:

* `bearer_present: true`;
* a non-anonymous principal fingerprint;
* universe `u-01kxm1vszd8hwp7em418asq8h9`;
* `recent_conversation` present with 30 items.

No conversation content was copied into the test record. This proves that a
fresh local Codex client can authenticate as the same founder account and reach
the same universe as the browser.

## What remains unproven

An already-running Codex task retried after the host login and remained
anonymous; starting a fresh process fixed it. Therefore the supported behavior
currently requires restart/reconnect, and the product must not imply that a
credential acquired elsewhere hot-refreshes an existing MCP connection.

Current Codex and Claude documentation describes secure credential storage,
automatic refresh, and explicit login/logout or clear-authentication commands.
The WorkOS authorization-server metadata exposes authorization, token, dynamic
registration, introspection, and device endpoints, but no OAuth revocation
endpoint. Clearing a client's stored credential therefore does not by itself
prove server-side session revocation. Before claiming the requested lifecycle is
complete, verify on every supported OS and both client families:

1. encrypted-at-rest credential storage and account isolation;
2. access-token expiry followed by rotated refresh-token persistence;
3. logout that invalidates the server session, not only the local cache;
4. revoking one concurrent session without revoking the others;
5. reconnect/restart behavior for already-running tasks;
6. loss, theft, and invalid-audience handling with a fail-closed result.

This work changes public authentication/session authority and needs an OpenSpec
change once ownership is clear; it must not be folded into a duplicate of the
active `no-anonymous-principal` branch.

## References checked 2026-09-03

* OpenAI, [Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)
* Anthropic, [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)
* MCP, [Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
* WorkOS, [Sessions](https://workos.com/docs/authkit/sessions) and
  [session testing](https://workos.com/docs/authkit/testing)

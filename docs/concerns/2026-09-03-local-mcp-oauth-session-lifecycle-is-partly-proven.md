# Bundled and local MCP OAuth session lifecycle is only partly proven

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Codex desktop/CLI on Windows against
`https://tinyassets.io/mcp`.
**Re-verified:** 2026-09-03 after production deploy run `33834837787`, serving
`b4662ab64513b15460f1e222f75cbfedea728bf3`.
**Severity:** P1 — production refuses anonymous access, but expired local and
bundled connector sessions do not yet recover into a successful authenticated
tool call.

## Source (verbatim)

> Cover secure credential storage, refresh/expiry, logout/revocation, multiple
> local sessions, and cross-platform behavior. Browser users and local agent
> users must resolve to the same account/universe.

Founder directive, 2026-09-03.

## What is now proven

The platform cutover itself is live. Deploy run `33834837787` installed image
digest `sha256:45b354fce5da8210f5587536e8f279243235c1a6a835d61394a2b9decbb7f710`;
the candidate became healthy; the authenticated public MCP canary with the
canonical handle assertion passed; rollback was skipped; and the release
receipt published `git_sha=b4662ab64513b15460f1e222f75cbfedea728bf3`.
That revision contains the no-anonymous merge
`3fc83fc15fc3e7d06310848f5b931ed0cf645c76` (#2800) and the status-shape
recovery merge `efa0ed9e39925ba3705a14be5b9836a6b74bb81d` (#2814).

An unauthenticated client is challenged before tool dispatch. Canonical tools
advertise OAuth-only security, cached hosted calls receive the bounded runtime
OAuth challenge, `/mcp/pulse` requires a bearer, and the canary is a named,
pre-dispatch-allowlisted service principal. The prior bundled calls no longer
receive anonymous status or conversation data.

## Fresh rendered and direct-client results

All checks below used the visible shared browser or the configured Codex MCP
client after the production deploy. No token, raw subject, or conversation
content was copied into this record.

| Route | Fresh result | Safety result |
|---|---|---|
| Codex CLI `workflow-live` | OAuth refresh failed with `invalid_refresh_token`; `get_status` failed and returned no fields | fail closed; no anonymous fallback |
| Codex CLI reauthorization | reached the WorkOS/Google account chooser; the dedicated test profile was signed out | needs the user's credential handoff |
| ChatGPT regular chat | rendered `Reconnect TinyAssets`; reconnect returned `link_success=true`, but the next naive status request again rendered that the connection had expired | no tool data returned |
| ChatGPT Temporary Chat | rendered that TinyAssets is disabled in an unpersonalized temporary chat | no tool call and no data returned |
| Claude Incognito | Incognito was enabled, but the selected Fable model was blocked by the account's monthly spend limit; the model selector was disabled | no tool call and no data returned |

ChatGPT's installed developer-mode connector detail still reports
`Authorization supported: None` and `Authorization used: None`, despite the
live endpoint's OAuth-only catalog. Removing and re-adding the connector may
refresh that cached registration, but the UI-test rule forbids removing a
user-owned connector without explicit approval.

## Remaining acceptance

The active `openspec/changes/no-anonymous-principal` task 12 stays unchecked and
the change stays unarchived until a rendered Claude and ChatGPT call either:

1. returns `request_identity.bearer_present=true`, a non-null
   `principal_fingerprint`, and the expected universe from both clients; or
2. presents supported linking before returning any tool data, then succeeds
   after that link.

The lifecycle work also still needs evidence for encrypted-at-rest credential
storage, rotated refresh-token persistence, server-side logout/revocation,
independent concurrent-session revocation, and cross-platform behavior. An
expired credential that fails closed is secure, but it is not a complete
reconnect experience.

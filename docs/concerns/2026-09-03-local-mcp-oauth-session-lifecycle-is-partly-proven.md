# Bundled and local MCP OAuth session lifecycle is only partly proven

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Codex desktop/CLI on Windows against
`https://tinyassets.io/mcp`.
**Re-verified:** 2026-09-03 after production deploy run `33834837787`, serving
`b4662ab64513b15460f1e222f75cbfedea728bf3`.
**Reconciled again:** 2026-09-04 from a fresh Codex delegated task against
production deploy run `33913895044`, serving
`b1ec544cbcbc5368d1394658d57275542db56fe4`.
**Re-verified:** 2026-09-08 from Codex desktop/CLI and a visible ChatGPT Work
conversation against production release `0e485ba0add1b852d712b4c5d349e542a4131268`.
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

## 2026-09-04 current-task reconciliation

The latest successful production deploy run `33913895044` passed the public
MCP handle canary, whose first assertion requires an unsigned `initialize` to
receive HTTP 401 with the canonical Bearer challenge. Rollback was skipped and
the protected release receipt reported
`b1ec544cbcbc5368d1394658d57275542db56fe4`; that revision contains the
no-anonymous merge `3fc83fc1`.

The same fresh Codex task then made only read-only status attempts through the
three installed connection aliases. The direct `workflow-live` client failed
before MCP startup because its OAuth refresh returned `invalid_refresh_token`.
Both bundled status tools (`TinyAssets` and `Workflow`) returned `UNAUTHORIZED`
with `TRIGGER_REAUTHENTICATION` and
`run_with_credentials_failed_token_refresh_not_supported`. None returned a
status body, principal fingerprint, universe identifier, or anonymous
fallback. No connector was removed or re-added, no login flow was automated,
and no universe state was mutated.

This is a secure failure, not identity-convergence evidence. A human OAuth
reauthentication across the direct and bundled credential planes is now the
single smallest boundary before one fresh task can compare their read-only
status results.

## 2026-09-08 sign-in and rendered-client retest

The direct `workflow-live` OAuth login completed successfully. Two independent
read-only `get_status` calls — one from a fresh `codex exec` session and one from
the desktop task's direct MCP tool — returned the same evidence:

- `request_identity.bearer_present=true`
- `principal_fingerprint=v1:d3e33d2bce691331f667d35669d6ae205f51c5c50f4f3ce8e8092f27ba40d2b5`
- `universe_id=u-01kxm1vszd8hwp7em418asq8h9`

The bundled `TinyAssets` and `Workflow` aliases still failed with internal
errors. A visible ChatGPT Work conversation then invoked only the installed
TinyAssets development plugin's `get_status`; the rendered answer contained
null for all three requested identity fields. Its rendered management detail
explains the mismatch: `Authorization supported None` and `Authorization used
None`. The menu exposes Disconnect/Delete but no sign-in action. No connector
was removed, recreated, or edited, and no universe content was read or changed.

The smallest remaining boundary is therefore no longer direct-client OAuth.
The ChatGPT development-plugin registration must advertise and use OAuth (or be
replaced by the intended OAuth-enabled registration), after which the bundled
aliases and rendered ChatGPT/Claude clients must be rechecked for the same
fingerprint and universe.

The founder then approved disconnect/reconnect. On 2026-09-08 the existing app
was disconnected, reinstalled, connected, and refreshed; its immutable detail
still reported `Authorization supported None` and no OAuth handoff occurred.
ChatGPT's new personal-app form did successfully discover the canonical server's
OAuth metadata using DCR, including the AuthKit authorization, token, and
registration endpoints plus `openid profile email offline_access`. A replacement
OAuth registration is therefore technically available, but creating the second
persistent connector remains a separately confirmed account mutation.

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

## 2026-09-08 ChatGPT OAuth registration proof

After exact founder approval, the prepared `TinyAssets OAuth` personal plugin was
created using DCR and the discovered AuthKit OAuth endpoints. Its rendered detail
reports the founder account email, `Authorization supported OAuth`, and
`Authorization used OAuth`. A fresh visible ChatGPT Work conversation attached
that plugin and made one read-only identity request. The rendered answer reported
signed in, fingerprint
`v1:d3e33d2bce691331f667d35669d6ae205f51c5c50f4f3ce8e8092f27ba40d2b5`, and
universe `u-01kxm1vszd8hwp7em418asq8h9`, matching both direct OAuth status reads.

The corresponding fresh Claude.ai Incognito conversation initially found the
installed `TinyAssets` connector but rendered `Connect` and returned no tool data.
The founder approved that separate connection and made the intended invariant
explicit: one user must resolve to the same universe regardless of Claude or
ChatGPT. After the user completed AuthKit authentication, Claude's rendered
read-only status reported bearer present, the same fingerprint
`v1:d3e33d2bce691331f667d35669d6ae205f51c5c50f4f3ce8e8092f27ba40d2b5`, and the
same universe `u-01kxm1vszd8hwp7em418asq8h9`.

Rendered ChatGPT/Claude identity convergence is therefore proven. A supporting
unsigned `initialize` probe returned HTTP 401 with the canonical Bearer challenge,
while the Claude host profile had 28 AuthKit/WorkOS/TinyAssets cookies; there is
no anonymous-client inference in this result. The concern remains open only for
the broader credential lifecycle evidence listed above and the broken bundled
Codex aliases: `TinyAssets` resolves to an unknown tool while `Workflow` requests
reauthentication because token refresh is unsupported.

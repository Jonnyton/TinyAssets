# Local MCP OAuth session lifecycle is only partly proven

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Codex desktop/CLI on Windows against
`https://tinyassets.io/mcp`; re-verified in a fresh post-login Patches task.
**Severity:** P1 — one configured client signs in, while two bundled connector
surfaces in the same fresh task still call the platform anonymously.

## Source (verbatim)

> Cover secure credential storage, refresh/expiry, logout/revocation, multiple
> local sessions, and cross-platform behavior. Browser users and local agent
> users must resolve to the same account/universe.

Founder directive, 2026-09-03.

## Reproduced connector matrix

Before login, `codex mcp list` reported the live server as `Not logged in`.
`codex mcp login workflow-live` completed WorkOS OAuth with PKCE, the canonical
resource indicator, and `offline_access`. The replacement Patches task was then
checked after that login. Its exact creation timestamp was unavailable, but all
three calls below ran in one fresh/restarted task context after login:

| Tool connection | Bearer / principal | Universe | Conversation | OAuth challenge |
|---|---|---|---|---|
| direct `workflow-live/get_status` | bearer true; authenticated `v1:d3e33d2bce69…` | `u-01kxm1vszd8hwp7em418asq8h9` | present, 30 turns | none needed |
| `codex_apps/tinyassets_get_status` | bearer false; `v1:anonymous:61…` | same ID | withheld | none |
| `codex_apps/workflow_get_status` | bearer false; `v1:anonymous:61…` | same ID | withheld | none |

Every call used `include_conversation=true`. No conversation content, token, or
full fingerprint was copied into this record. The direct configured MCP client
therefore reaches the founder account correctly. The two bundled app-connector
surfaces do not inherit that OAuth session, even inside the same new task.

This also corrects an earlier observation: task age is not the authentication
boundary. The original pre-login task did retain its anonymous direct connection,
but restarting or delegating a new task is not a product solution because the
bundled connector surfaces remain anonymous regardless.

## The actual boundary

`codex mcp login workflow-live` populates the local configured-MCP credential
plane used by `workflow-live`. The `codex_apps` TinyAssets and Workflow tools use
a separate hosted/bundled connector authorization plane. A signed-in TinyAssets
app page or conversation-continuity payload is application state, not proof that
an `Authorization: Bearer` reached the resource server. Request identity must be
decided only from the verified token on that exact tool request.

The server currently helps preserve the split instead of forcing it closed:

* an unauthenticated MCP initialize succeeds and tools remain callable;
* all seven canonical tool descriptors currently expose
  `meta.securitySchemes=None`, both on main and on
  `claude/no-anonymous-principal` at `3e4999fb`;
* the two anonymous `codex_apps` calls returned no OAuth/linking error and no
  `_meta["mcp/www_authenticate"]` challenge.

OpenAI's current connector contract requires both per-tool `securitySchemes`
metadata and a runtime `_meta["mcp/www_authenticate"]` error to trigger hosted
OAuth linking. A transport 401 alone covers direct MCP clients but does not
satisfy that hosted tool-level contract.

The descriptor check was run on 2026-09-03 from each Windows worktree with:

```text
python -c "import asyncio; from tinyassets.universe_server import mcp; xs=asyncio.run(mcp.list_tools()); print({t.name:(getattr(t,'meta',None) or {}).get('securitySchemes') for t in xs if t.name in {'read_graph','write_graph','run_graph','read_page','write_page','converse','get_status'}})"
```

Both returned all seven names mapped to `None`.

## Correct platform fix and acceptance

Do not make users restart tasks until one happens to carry the right connection.
Extend or supersede the existing owned `no-anonymous-principal` OpenSpec change;
do not create a parallel authority implementation. Its acceptance must include:

1. fail closed before an unauthenticated MCP session or tool body is returned,
   with the routed protected-resource metadata URL;
2. advertise `oauth2` (and no `noauth`) in `securitySchemes` for every canonical
   TinyAssets tool, with the exact required scopes;
3. return an error result carrying `_meta["mcp/www_authenticate"]` when a hosted
   connector invokes a tool without a valid token;
4. reject continuity, cookies, universe hints, and ambient app/session state as
   substitutes for the request bearer;
5. prove from one newly delegated task that direct `workflow-live`, bundled
   TinyAssets, and bundled Workflow calls all resolve to the same non-anonymous
   principal and universe—or present a supported linking UI before any data;
6. prove an unlinked client receives no status, instructions, conversation, or
   other platform data.

## What remains unproven

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
5. reconnect behavior for an already-running connection after explicit linking;
6. loss, theft, and invalid-audience handling with a fail-closed result.

This is public authentication/session authority. The active
`no-anonymous-principal` branch is the existing owner but does not yet cover the
hosted connector contract; the founder/owner must choose to extend that change
or supersede it. A new overlapping change is not admissible while that decision
is unresolved.

## References checked 2026-09-03

* OpenAI, [Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)
  and [MCP server authentication](https://developers.openai.com/plugins/build/auth)
* Anthropic, [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)
* MCP, [Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
* WorkOS, [Sessions](https://workos.com/docs/authkit/sessions) and
  [session testing](https://workos.com/docs/authkit/testing)

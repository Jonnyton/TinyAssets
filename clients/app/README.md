# TinyAssets — Onboarding App (web)

A thin local shell over the one thing that matters: **talking to your universe.**
Sign in with WorkOS, land in a single chat thread, and speak in first person with
the mind you're raising. No dashboard, no feature grid — one screen: the conversation.

It talks to the backend **only** through the canonical connector at
`https://tinyassets.io/mcp` using the seven public handles
(`converse`, `get_status`, `read_graph`, `write_graph`, `run_graph`, `read_page`,
`write_page`). It invents no backend tools.

## Why a local server (not a pure static page)

The live `/mcp` sends **no CORS headers** (a browser preflight returns 403), so a
web page cannot call it cross-origin. `app_server.py` is a tiny stdlib-only host that:

1. serves the single-page app (`static/`),
2. proxies `POST /mcp` **same-origin** to the live connector, injecting your WorkOS
   Bearer token **server-side** (the token never touches JavaScript or any log), and
3. runs WorkOS AuthKit sign-in (OAuth 2.0 Authorization Code + PKCE, with Dynamic
   Client Registration), binding the token to the MCP resource via RFC 8707.

## Run

Requires Python 3.11+ and **no dependencies**.

```bash
python clients/app/app_server.py
# then open http://127.0.0.1:8123
```

### Sign in and chat

1. Click **Sign in** → complete WorkOS AuthKit in the browser → you land back in the chat.
2. Say hello. Your message goes through `converse`; the universe's own first-person
   reply is rendered verbatim.
3. The status dot (top-left) is a `get_status` heartbeat every 30s.

### Fast path for local testing (developer token)

If you already hold a WorkOS access token for the live connector, expand
**Developer: use an existing access token** on the sign-in screen and paste it. The
token goes to your local app over localhost (never logged), and you're immediately in
a working conversation — no OAuth redirect setup required.

## Configuration (all optional)

| Env var | Default | Purpose |
|---|---|---|
| `TINYASSETS_APP_PORT` | `8123` | local port |
| `TINYASSETS_APP_HOST` | `127.0.0.1` | bind address (also the OAuth redirect host) |
| `TINYASSETS_MCP_URL` | `https://tinyassets.io/mcp` | connector to proxy to |
| `TINYASSETS_MCP_RESOURCE` | = `MCP_URL` | RFC 8707 token audience |
| `TINYASSETS_APP_CLIENT_ID` | *(DCR)* | pre-registered WorkOS client id; skips Dynamic Client Registration |
| `TINYASSETS_AUTHKIT_ISSUER` | *(discovered)* | override the authorization server |

Point it at a local daemon for offline testing:

```bash
TINYASSETS_MCP_URL=http://127.0.0.1:9000/mcp python clients/app/app_server.py
```

## Onboarding steps: what works end-to-end vs. blocked

| Step | State |
|---|---|
| WorkOS sign-in (PKCE + DCR) | **works** against the live authorization server |
| Chat via `converse` (verbatim reply) | **works** against live `/mcp` |
| `get_status` heartbeat | **works** against live `/mcp` |
| **Connect subscription** (deposit) | **blocked on backend deploy** — see below |

**Connect subscription is not reachable through the canonical handles right now.**
The live `/mcp/connect/*` deposit form is currently 404 (its hot-patch was lost on a
container recreate), and `write_graph target=connection` in this tree exposes only the
GitHub-Pipes actions (`connect`/`reconcile`/`list`) — not `connect_llm`. When the
universe has no engine, `converse` returns an honest *setup-required* note, which the
app renders as the universe's own voice with a **Connect your subscription** button.
The connect screen's advanced deposit attempts `write_graph connect_llm` (the intended
contract) and shows the connector's real response, so the app lights up the moment the
deposit backend ships — no client change needed.

## Tests

```bash
python -m pytest clients/app/tests/ -q
```

Covers PKCE S256, the authorize-URL parameters (incl. the RFC 8707 resource binding),
token-exchange fields, and the `/mcp` proxy's Bearer injection + 401/502 handling.

## Design boundaries honored

- One screen: the conversation. No universe logic, identity, or persona in the client.
- The universe's reply is rendered **verbatim** — the app never composes its voice.
- Local storage holds the **token only** (server-side session); no persona/soul/history
  is cached client-side.
- Honest fallback on auth/tool failure — never a faked reply or a replayed persona.

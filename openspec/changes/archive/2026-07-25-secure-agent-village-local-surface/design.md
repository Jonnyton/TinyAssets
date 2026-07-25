## Context

Agent Village is a stdlib `ThreadingHTTPServer` intended for a host operator's
browser and phone. Its snapshot contains private repository paths, live agent
sessions, worktree claims, local universe metadata, and chat history. Its two
write routes can append agent/universe notes, spawn paid provider CLIs when
dispatch is enabled, and change a universe writer preset.

The shipped server defaults to `0.0.0.0` and treats an absent token as full
authorization. When a token is present, the browser copies it from
`location.search` into persistent local storage and appends it to every URL.
This exposes the bearer to logs/history/referrers and leaves the default
surface open to LAN reads and cross-site form POSTs.

The runtime is deliberately zero-build and stdlib-only. Phone access over a
trusted LAN must remain possible, but public hosting, TLS termination, user
accounts, and multi-tenant authorization are outside this local operator tool.

## Goals / Non-Goals

**Goals:**

- Make private API reads and all talk/hire writes authenticated on every
  startup, including zero-config local startup.
- Keep `python -m command_center` immediately usable and make intentional LAN
  use explicit.
- Remove bearer values from HTTP request URLs, browser history, and referrer
  paths.
- Make cross-site simple requests incapable of mutating state.
- Fail before collector invocation on unauthenticated or oversized requests.
- Preserve the zero-build, dependency-free runtime.

**Non-Goals:**

- Accounts, roles, remote identity federation, or a public hosted Village.
- Protecting plaintext HTTP from an attacker who can sniff a deliberately
  shared LAN; operators should use a trusted LAN or external TLS tunnel.
- Changing collector discovery, talk/hire semantics, MCP authentication, or
  provider billing behavior after the local request is authorized.

## Decisions

### Generate a per-process bearer and default to loopback

`Config.host` and the CLI default become `127.0.0.1`. `serve()` prepares
authentication before starting the poller/server: an explicit bearer must meet
a minimum strength floor, while an omitted bearer is replaced with
`secrets.token_urlsafe(32)`. The process prints a fragment share URL.

This keeps local startup autonomous and prevents a missing flag from disabling
the security boundary. Requiring operators to invent a token was rejected
because it preserves insecure copy/paste patterns and adds friction. Binding
to all interfaces by default was rejected because phone convenience cannot
justify silently publishing private host state.

### Leave static bootstrap and health public; protect every private API

`/`, the four static assets, and `/api/health` remain reachable without a
bearer so a normal browser navigation can load the client and liveness checks
remain simple. State, chat, providers, talk, and hire require
`X-Village-Token`, compared with `secrets.compare_digest`.

Accepting `?token=` as a compatibility path was rejected by the project's
no-shims rule and because keeping the leaky boundary defeats the change.
Cookie sessions were rejected: the runtime has no TLS or session store, while
a custom header already prevents cross-site simple form/fetch mutation through
the browser's preflight boundary.

### Bootstrap through a URL fragment and session storage

The printed URL uses `#token=<bearer>`. The fragment is never sent to the
server. `app.js` reads it once, stores it in `sessionStorage`, and immediately
uses `history.replaceState` to remove it from the visible URL. API requests
remain same-origin and send the bearer only as `X-Village-Token`.

Persistent `localStorage` was rejected because it retains a process-specific
secret after the browser session. Appending the bearer to each request URL was
rejected because server/proxy logs and referrer propagation can expose it.

### Reject invalid bodies before side effects

POST authorization runs before reading the body. Missing, negative, malformed,
or greater-than-64-KiB `Content-Length` is rejected before any collector call.
The server reads exactly the declared accepted length and requires a JSON
object. This replaces the current truncated-read behavior.

### Add browser defense headers without breaking the zero-build UI

JSON and static responses set `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and a CSP that permits
same-origin scripts/connects and the app's existing inline style attributes,
while denying objects, bases, and framing.

## Risks / Trade-offs

- **Existing unauthenticated scripts and `?token=` bookmarks break** →
  Document the header/fragment migration explicitly; do not retain the unsafe
  alias.
- **Plain HTTP bearer can be observed on a hostile LAN** → Default to
  loopback, require an explicit LAN bind, and document trusted-LAN/TLS-tunnel
  use.
- **Static shell reveals that Agent Village is installed** → Static assets
  contain no private snapshot; all private reads and writes remain gated.
- **Generated token is lost on restart** → This is intentional per-process
  revocation; the startup log prints the new share URL.
- **CSP breaks dynamic styling** → Permit styles inline because the current
  renderer uses style attributes; keep scripts and connections same-origin.

## Migration Plan

Land spec, exact HTTP/browser contract tests, implementation, README migration,
and independent security review together. Rollback is a direct revert, but the
old unauthenticated behavior is unsafe and should be used only as an emergency
local-loopback diagnostic. After landing, start the real CLI, verify the
printed fragment disappears from browser history, prove unauthorized curl
reads/writes fail, and prove an authenticated talk reaches only its temporary
test inbox.

## Open Questions

None.

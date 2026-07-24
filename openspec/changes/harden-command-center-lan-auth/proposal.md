## Why

Agent Village currently binds every interface by default, exposes local agent sessions and universe state when no optional token is supplied, accepts that token in query strings, and permits browser POST mutations without an origin boundary. A LAN page can therefore read private coordination state, forge talk/preset writes, or dispatch provider CLI work against the operator's subscription; the merged dashboard must fail closed before it is safe to run.

## What Changes

- **BREAKING**: bind only a literal loopback address and reject every non-loopback listener configuration before opening a socket.
- **BREAKING**: require an environment-supplied or generated token on every `/api/*` request; remove secret-valued CLI flags and query-string token authentication.
- Validate configuration and successfully bind the loopback socket before starting cache, collector, network, or worker activity.
- Keep inert static app assets readable so a fragment-token share URL can bootstrap the browser without transmitting the token in the URL request, history, access logs, or referrer.
- Send the token only in `X-Village-Token`; compare it in constant time and keep it in browser session storage rather than persistent local storage.
- Require authenticated mutating requests to have singleton same-origin headers and strictly framed UTF-8 JSON objects with typed bounded scalar fields; reject missing, cross-origin, form/simple, ambiguous, oversized, malformed, surrogate/NUL-bearing, or type-confused requests before calling collectors.
- Validate every request's `Host` against the listener's loopback authority before routing or authentication so DNS rebinding cannot turn a hostile origin into a local authority.
- Require explicit `--dispatch` operator enablement before any hire path may discover or spawn a provider CLI, recheck the gate at the dispatch function, and cap talk plus hire provider process trees at eight in flight per process.
- Strip Village/MCP bearers from every dispatched peer environment while preserving provider subscription authentication; keep quota slots until the real provider process tree is reaped, including timeout paths.
- Document that phone/LAN use is unavailable until a separate authenticated HTTPS or tunnel design lands, and add real-HTTP plus concurrent-hostile-request regression coverage.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: replace Agent Village's optional-token LAN behavior with a fail-closed local-dashboard authentication, CSRF, secret-transport, and provider-dispatch contract.

## Impact

- Code: `command_center/__main__.py`, `command_center/collector.py`, `command_center/server.py`, `command_center/web/app.js`, `scripts/peer_agent.py`.
- Documentation: `command_center/README.md`.
- Tests: production HTTP server, side-effect-free bind failure, CLI defaults, listener/Host rejection, token transport, strict request framing/schema, exact security headers, hostile concurrency, talk/hire/dispatch gating, secret scrubbing, and process-tree cleanup.
- No MCP server-auth semantics, market, provider-credential ownership, or remote-execution contract changes; the command-center MCP bearer input moves from a secret-valued CLI flag to its existing environment variable.

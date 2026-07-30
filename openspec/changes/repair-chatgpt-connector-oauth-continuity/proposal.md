## Why

A successful ChatGPT reconnect currently completes OAuth discovery and the MCP
handshake, but the first authenticated tool call is rejected with `401
invalid_token`. This blocks the product's implementation path: an ordinary
user cannot build, operate, repair, or evolve a GitHub-to-spec cloud production
loop from a chatbot while every personal computer is off.

## What Changes

- Require a completed OAuth authorization or reconnect to establish durable
  authenticated connector continuity for subsequent TinyAssets tool calls,
  including standards-based token refresh or a new authorization when needed.
- Preserve fail-closed RS256, issuer, required-claim, and exact resource
  audience validation; no production audience bypass or anonymous-write
  fallback is permitted.
- Emit a bounded, token-safe validation failure category so operators can
  distinguish configuration, key, expiry, issuer, audience, and required-claim
  failures without logging bearer tokens or claim values.
- Make live rendered-chatbot continuity a prerequisite for implementing and
  operating user-owned cloud automations, not only a final acceptance check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `identity-auth-and-access-control`: A successful connector authorization must
  produce an access token the resource server accepts for the advertised MCP
  resource, preserve continuity through refresh/reconnect, and expose only
  sanitized validation-failure telemetry.
- `live-mcp-connector-surface`: The remote connector must remain usable for
  authenticated calls after the client completes authorization or reconnect,
  so the chatbot can be the complete off-device control surface.

## Impact

The change affects WorkOS/AuthKit resource-server validation, authentication
middleware telemetry, protected-resource and authorization-server
configuration parity, focused auth tests, the public MCP canary, and rendered
ChatGPT acceptance. It also tightens the active
`activate-main-universe-spec-drain` contract so generic user-owned
GitHub-to-spec automation cannot advance behind a broken chatbot identity
path. No new MCP handle, auth bypass, maintainer credential path, or
desktop-only recovery mechanism is introduced.

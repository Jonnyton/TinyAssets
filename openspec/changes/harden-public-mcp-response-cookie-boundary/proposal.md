## Why

The public Cloudflare Worker currently forwards every non-hop-by-hop upstream
response header, so an Access-issued `CF_Authorization` cookie can cross from
the internal tunnel origin to an anonymous public caller. The merged
2026-07-30 audit confirmed the missing boundary and STATUS classifies it P0.

## What Changes

- Strip every upstream `Set-Cookie` response header at the public MCP Worker
  boundary.
- Preserve the direct SSE body stream and all allowed non-cookie response
  headers.
- Add regression coverage for Access cookies and ordinary application cookies.
- Require post-merge deployment, healthy-path canary, rendered-chatbot, and
  organic-use evidence before retiring the P0 concern.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: The Cloudflare Worker public front door must
  never forward an upstream response cookie to a public caller.

## Impact

The change is limited to `deploy/cloudflare-worker/worker.js`, its focused test
suite, the `live-mcp-connector-surface` requirement, and coordination/proof
artifacts. It adds no dependency, endpoint, buffering, authentication flow, or
Cloudflare configuration.

## Why

TinyAssets has one remote product endpoint:
`https://tinyassets.io/mcp`. The current change instead preserves a third
remote product at `/mcp-directory`, and current Registry, ChatGPT, Claude, and
client guidance binds to that narrower five-handle surface. The host directed
on 2026-07-24 that `/mcp` is canonical and `/mcp-directory` retires promptly.

This is not a URL-only replacement. Canonical `/mcp` advertises seven handles,
uses WorkOS/OAuth, exposes broader graph/page targets, returns operator-heavy
status, and carries server instructions and annotations that still need
hardening for reviewed directories. Those improvements do not justify keeping
a second public endpoint. Route retirement and canonical hardening are
independent lanes: remove `/mcp-directory*` promptly, then continue improving
and proving `/mcp` without a redirect or compatibility surface.

The local MCPB package remains a separate product because it runs over stdio
with local configuration and a different identity boundary.

## What Changes

- Replace the former three-product model with two explicit products:
  canonical remote `/mcp` and local MCPB over stdio.
- Preserve the completed MCPB manifest/runtime parity work and its independent
  local configuration, auth, and acceptance contract.
- Make public `/mcp` status a fail-closed allowlist projection. Raw activity
  logs, identities, filesystem paths, hashes, exceptions, and operator
  diagnostics are not returned through public MCP status handles.
- Replace forced/embodiment server instructions with neutral tool-selection
  guidance. Universe conversation remains an explicit user-selected action.
- Publish truthful per-tool OAuth security schemes, runtime challenges,
  conservative annotations, and descriptions of persistence, cost, provider,
  public-publication, and overwrite effects.
- Bind MCP Registry metadata, ChatGPT/Claude submissions, maintained client
  packs, and current integration guidance to `https://tinyassets.io/mcp` and
  its exact seven-handle catalog.
- Require the exact public name `TinyAssets` across connector, app, Registry,
  and integration metadata; lifecycle qualifiers such as `DEV` are not part of
  the product name.
- Treat historical `/mcp-directory` proof as historical evidence; append
  superseding current proof instead of rewriting dated artifacts.
- Make retirement the first runtime slice after focused public-surface review:
  remove `directory_server`, directory catalog constants/mounts, versioned
  directory URLs, current operational guidance, and Worker routing. Old
  `/mcp-directory*` requests become absent/404; no redirect or compatibility
  shim survives. Vendor review, rendered-client breadth, telemetry, Registry
  publication, and canonical hardening are post-retirement evidence, not
  permission to preserve the old route.
- Repoint each maintained old registration to `/mcp` or withdraw it. An
  unavailable vendor path is recorded and watched; it never retains
  `/mcp-directory*`.
- Adapt dependent active OpenSpec changes whose premises preserve the retired
  directory product.

## Capabilities

### New Capabilities

- `mcp-connector-distribution`: Specify the two connector products, artifact
  bindings, canonical remote catalog, local MCPB parity/configuration,
  migration evidence, and non-substitutable acceptance.

### Modified Capabilities

- `live-mcp-connector-surface`: Make canonical `/mcp` the sole remote product,
  remove `/mcp-directory*` first, and harden the surviving surface.

## Impact

- OpenSpec: this change, canonical `live-mcp-connector-surface`, and dependent
  `retire-legacy-live-mcp-tools` / `operator-request-trigger-contract`
  assumptions.
- Runtime/edge: `tinyassets/universe_server.py`,
  `tinyassets/directory_server.py`, `tinyassets/connector_catalog.py`, auth
  metadata, status projection, and the Cloudflare Worker route/tests.
- Distribution: Registry generator/manifest, ChatGPT submission packet,
  Claude/OpenAI registration guidance, MCPB metadata, and current client packs.
- Website/legal: current privacy disclosures for WorkOS identity, activity
  evidence, public commons, retention/deletion, and BYOC/provider routing.
- Compatibility: maintained `/mcp-directory` registrations are repointed or
  withdrawn; cached callers receive an ordinary 404 and current `/mcp`
  guidance, never a transport-level compatibility response.
- Compute: all catalog, auth-failure, redaction, and migration proof remains
  provider-free unless a requester supplies BYOC or an accepted-market grant.

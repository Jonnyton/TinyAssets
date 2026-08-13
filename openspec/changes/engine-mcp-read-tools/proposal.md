# Proposal: founder-scoped read-only engine MCP tools

**Status:** implementation landed DARK (PR #2419, flag `TINYASSETS_ENGINE_MCP_TOOLS`
default off); this change authorizes the spec exception the code embodies and
gates ENABLING the flag.

## Why

Founder directive 2026-08-12: *"all user functions are just mcp functions ...
all the same mcp commands whether it's through the app or through slack or the
browser."* The universe intelligence (the founder's personified agent) needs the
same MCP surface the founder's browser chatbot has, starting with the ability to
inspect its OWN universe. Today's engine tool policy (WebFetch-sole + `mcp__*`
denied) makes every such capability impossible.

## What changes

The `universe-personification-and-relay` requirement "The engine turn is
confined by a fail-closed sandbox" gains a narrow, flag-gated exception:

- When `TINYASSETS_ENGINE_MCP_TOOLS` is enabled AND the turn is FOUNDER-tier
  with a VERIFIED request principal (`ProviderRequestCapability.principal_id` —
  never the raw conversation `actor_id`), the engine additionally receives a
  LOCAL stdio TinyAssets MCP server exposing exactly two read-only handles:
  `read_graph` (targets restricted to `{status, graph}`, `graph_id` pinned to
  the turn's own universe) and `get_status` (universe-scoped whitelist
  projection).
- Isolation moves from the `mcp__*` wildcard deny to `--strict-mcp-config`
  (admits exactly the one local server; verified 2026-08-13 to exclude the
  logged-in account connectors). If strict config cannot be installed, the turn
  FAILS rather than running with a relaxed policy.
- Everything else in the sandbox requirement stands unchanged (cwd pin, Bash /
  filesystem / messaging / scheduling denies, context-injected soul, governed
  learning path). The learning-extraction turn NEVER receives MCP tools.

## Cross-family review history

Codex REJECTED the initial design (15 findings, 2026-08-13); the narrowed
read-only slice returned ADAPT ("materially safer", dark-merge exposure-safe)
with 4 enable residuals: config-write fail-open (fixed in #2419), missing-universe
inspect enumeration (fixed in this change's lane), get_status host/global
projection (fixed: whitelist projection in the engine server), OpenSpec
reconciliation (this document), plus a pinned-CLI strict-config negative canary
required at enable time.

## Relationship to engine-os-sandbox

The in-flight `engine-os-sandbox` change supersedes deny-list policy with OS
enforcement and currently specifies NO MCP for model-controlled work. When that
lane lands, this read-only MCP grant must be re-authorized inside its
closed-workspace-projection model (the local stdio server is exactly such a
projection decision) — it does not silently carry over.

## Out of scope

`write_graph`, `run_graph`, `read_page`, `write_page`, `converse` from the
engine. Each write/run handle needs its own confinement design (universe pinning
does not confine their independent-id selectors; runs spend and fire external
effects) and its own cross-family review.

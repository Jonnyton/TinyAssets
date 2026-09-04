# Open WebUI No-Chatbot-Login Pack — Retired

Created: 2026-05-01
Retired: 2026-09-03
Owner: lead + available provider

TinyAssets no longer supports an unauthenticated or anonymous-read-only MCP
connection. `https://tinyassets.io/mcp` challenges every request outside the
discovery and sign-in bootstrap routes before dispatch, including
`initialize`, `tools/list`, and read tools.

Do not configure Open WebUI authentication as `None`, do not reuse the former
`read_graph`/`read_page` allowlist, and do not describe this route as a
supported no-login pack. A current Open WebUI integration requires a
host-supported OAuth 2.1 flow with the resource indicator
`https://tinyassets.io/mcp`. Until that flow has fresh rendered proof, Open
WebUI is unsupported for TinyAssets rather than anonymous-read-only.

The dated Docker and no-login experiments formerly recorded here remain in git
history. They are historical evidence, not current setup instructions.

Current protocol truth: `openspec/specs/live-mcp-connector-surface/spec.md`.
Host support truth: `docs/ops/mcp-host-proof-registry.md`.

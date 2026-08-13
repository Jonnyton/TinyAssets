# Tasks: engine-mcp-read-tools

- [x] 1.1 Local stdio MCP server (read_graph {status,graph} + get_status), verified-principal identity, hard fail-closed (PR #2419)
- [x] 1.2 CLI wiring: --mcp-config + --strict-mcp-config, fail-the-turn when strict config not installed (PR #2419 + ADAPT #1 fix)
- [x] 1.3 Missing-universe inspect: no enumeration on not-found (ADAPT #2)
- [x] 1.4 get_status universe-scoped whitelist projection, both status paths (ADAPT #3)
- [x] 1.5 OpenSpec delta authorizing the flag-gated exception (ADAPT #4; this change)
- [ ] 2.1 Negative canary on the DEPLOYMENT's pinned claude CLI: ambient connectors unreachable under --strict-mcp-config (run at enable time, per deployment)
- [ ] 2.2 Enable `TINYASSETS_ENGINE_MCP_TOOLS` on prod; rendered-chatbot/Slack user-proof of Tiny reading its own status via the tools
- [ ] 2.3 On engine-os-sandbox landing: re-authorize the MCP grant inside its closed workspace-projection model

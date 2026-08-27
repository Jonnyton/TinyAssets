# LibreChat No-Hosted-Chatbot-Login Pack

Created: 2026-05-01
Current contract checked: 2026-07-24
Status: current anonymous-read-only guidance; canonical host proof pending;
historical Docker proof retained below
Owner: lead + available provider

This pack is for users who do not want a Claude or ChatGPT account in the
TinyAssets path, but can run or access a LibreChat instance. LibreChat may still
require its own local account depending on how the deployment is configured;
the claim here is no hosted chatbot login.

## Current Truth

- LibreChat supports MCP servers in `librechat.yaml` and through its UI.
- LibreChat supports `streamable-http` MCP servers by URL.
- TinyAssets has one public Streamable HTTP MCP endpoint:
  `https://tinyassets.io/mcp`.
- The public name is exactly `TinyAssets`. Do not add `DEV`, `directory`, or
  another lifecycle qualifier.
- Canonical `/mcp` advertises exactly seven tools: `read_graph`, `write_graph`,
  `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`.
- A connection without OAuth is **anonymous-read-only**. It may call
  `read_graph` and `read_page`. Do not expose `get_status` through this pack
  until the versioned public-status projection is implemented and verified;
  the current result is unredacted. Mutation, execution, and conversation
  entry require OAuth and are unsupported by this no-login pack.

Public claim scope: the 2026-05-01 LibreChat `v0.8.5` Docker observation below
is historical evidence from the retired endpoint. Current support requires a
fresh proof against canonical `/mcp`. Do not generalize it to another LibreChat
version, hosted deployment, auth mode, model, or mutation flow.

## Recommended LibreChat YAML

Add this to `librechat.yaml`:

```yaml
mcpSettings:
  allowedDomains:
    - "tinyassets.io"

mcpServers:
  tinyassets:
    title: "TinyAssets"
    description: "TinyAssets anonymous-read-only MCP endpoint"
    type: "streamable-http"
    url: "https://tinyassets.io/mcp"
    timeout: 30000
    initTimeout: 30000
    serverInstructions: |
      Use TinyAssets only for anonymous reads through read_graph and read_page.
      Do not call write_graph, run_graph, write_page, or converse in this no-login configuration.
```

Restart LibreChat after changing `librechat.yaml`.

## User-Facing First Prompts

Use read-only prompts first:

```text
Use TinyAssets to list available goals.
```

```text
Use TinyAssets to search the TinyAssets wiki for launch risks and summarize the best match.
```

Do not test write, run, or `converse` flows with this no-login configuration.
Those calls require an OAuth-capable, authenticated host proof.

## Historical Runtime Proof — 2026-05-01

The following table and trace record what was observed on the retired endpoint
on 2026-05-01. Preserve it as evidence; do not use it as current setup guidance.

| Field | Value |
|---|---|
| LibreChat version | `v0.8.5` |
| Deployment shape | local Docker Compose from LibreChat `v0.8.5` checkout |
| LibreChat API image | `registry.librechat.ai/danny-avila/librechat:latest` |
| Image digest | `sha256:a46254938507971e0d4f7ed3f9d116bd9b118f4810b5b75eb716baf575645068` |
| TinyAssets endpoint | `https://tinyassets.io/mcp-directory` |
| MCP transport | Streamable HTTP |
| TinyAssets auth mode | None |
| Model used | `gpt-oss:20b` through LibreChat/Ollama |
| Tool attachment path | `ephemeralAgent.mcp = ["workflow"]` |
| Visible tool result | Assistant message included `get_workflow_status_mcp_workflow` tool call output and answered `reachable=true` with `active_host.host_id: host` |
| Screenshot/trace path | `docs/ops/librechat-runtime-proof-2026-05-01.md` |
| Date/time | 2026-05-01 UTC |

Historical acceptance criteria used for that proof:

- LibreChat starts with the TinyAssets MCP server configured.
- LibreChat reported the historical TinyAssets MCP server as connected and not
  requiring OAuth.
- LibreChat exposes all 11 directory-safe TinyAssets tools.
- A chat/agent run invokes at least one read-only TinyAssets tool.
- The visible response matches the tool result enough for a user to trust it.
- Any console/server error is recorded.
- `docs/ops/mcp-host-proof-registry.md` is updated to `verified` with the
  proof date and trace path.

Proof trace:

- `docs/ops/librechat-runtime-proof-2026-05-01.md`

## Supporting Protocol Checks

Run these before and after the LibreChat proof:

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose
python scripts/mcp_probe.py --url https://tinyassets.io/mcp tools
```

Expected canonical tools:

- Anonymous reads approved for this pack: `read_graph`, `read_page`
- OAuth-required mutation/costly work: `write_graph`, `run_graph`,
  `write_page`, `converse`

The server advertises all seven. A no-login proof passes only through the two
approved anonymous-read handles; it must not expose unredacted `get_status` or
claim mutation parity.

## Troubleshooting Notes

- If the connection never appears, verify `allowedDomains` includes
  `tinyassets.io`.
- If chat answers from memory without a tool call, verify the chat request or
  selected UI state actually attaches the MCP server. The proof path used
  `ephemeralAgent.mcp = ["workflow"]`; that identifier is preserved here only
  as historical evidence. A raw request `tools` list alone did not
  match the normal LibreChat UI path during this proof.
- If the model writes a tool call in text instead of executing it, switch to a
  model with function/tool-call support and repeat the proof.
- LibreChat logs transient Streamable HTTP close/abort messages during startup
  and reconnect. In the 2026-05-01 proof these appeared before successful
  initialization and did not block the connection.

## Source Notes

Fresh docs checked on 2026-05-01:

- LibreChat MCP docs: `https://www.librechat.ai/docs/features/mcp`
- TinyAssets proof registry: `docs/ops/mcp-host-proof-registry.md`
- Current connector reconciliation:
  `openspec/changes/archive/2026-08-26-reconcile-external-connector-manifests/`

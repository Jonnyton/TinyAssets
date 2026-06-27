# LibreChat No-Hosted-Chatbot-Login Pack

Date: 2026-05-01
Status: verified local Docker proof on 2026-05-01
Owner: lead + available provider

This pack is for users who do not want a Claude or ChatGPT account in the
Workflow path, but can run or access a LibreChat instance. LibreChat may still
require its own local account depending on how the deployment is configured;
the claim here is no hosted chatbot login.

## Current Truth

- LibreChat supports MCP servers in `librechat.yaml` and through its UI.
- LibreChat supports `streamable-http` MCP servers by URL.
- Workflow exposes a public Streamable HTTP MCP endpoint at
  `https://tinyassets.io/mcp-directory`.
- The full custom-connector endpoint remains `https://tinyassets.io/mcp`, but
  the directory endpoint is the safer first proof surface because it exposes
  only 11 narrow tools.

Public claim scope: LibreChat `v0.8.5` local Docker proof is verified against
Workflow's directory endpoint. Do not generalize that claim to every LibreChat
version, hosted deployment, auth mode, model, or write/proposal flow without a
host-specific proof update.

## Recommended LibreChat YAML

Add this to `librechat.yaml`:

```yaml
mcpSettings:
  allowedDomains:
    - "tinyassets.io"

mcpServers:
  workflow:
    title: "Workflow"
    description: "Directory-safe TinyAssets MCP endpoint"
    type: "streamable-http"
    url: "https://tinyassets.io/mcp-directory"
    timeout: 30000
    initTimeout: 30000
    serverInstructions: |
      Use Workflow for read-only daemon status, goals, wiki, universe, and run inspection.
      Only use proposal/write tools when the user explicitly asks for a proposal.
```

Restart LibreChat after changing `librechat.yaml`.

## User-Facing First Prompts

Use read-only prompts first:

```text
Use Workflow to check the daemon status and tell me any caveats.
```

```text
Use Workflow to list available goals.
```

```text
Use Workflow to search the Workflow wiki for launch risks and summarize the best match.
```

Only test write/propose flows after read-only invocation is visible in the chat
and LibreChat's tool-call behavior is understood for the selected model.

## Runtime Proof Checklist

Record all values before claiming support:

| Field | Value |
|---|---|
| LibreChat version | `v0.8.5` |
| Deployment shape | local Docker Compose from LibreChat `v0.8.5` checkout |
| LibreChat API image | `registry.librechat.ai/danny-avila/librechat:latest` |
| Image digest | `sha256:a46254938507971e0d4f7ed3f9d116bd9b118f4810b5b75eb716baf575645068` |
| Workflow endpoint | `https://tinyassets.io/mcp-directory` |
| MCP transport | Streamable HTTP |
| Workflow auth mode | None |
| Model used | `gpt-oss:20b` through LibreChat/Ollama |
| Tool attachment path | `ephemeralAgent.mcp = ["workflow"]` |
| Visible tool result | Assistant message included `get_workflow_status_mcp_workflow` tool call output and answered `reachable=true` with `active_host.host_id: host` |
| Screenshot/trace path | `docs/ops/librechat-runtime-proof-2026-05-01.md` |
| Date/time | 2026-05-01 UTC |

Acceptance criteria:

- LibreChat starts with the TinyAssets MCP server configured.
- LibreChat reports the TinyAssets MCP server as connected and not requiring
  OAuth.
- LibreChat exposes all 11 directory-safe Workflow tools.
- A chat/agent run invokes at least one read-only Workflow tool.
- The visible response matches the tool result enough for a user to trust it.
- Any console/server error is recorded.
- `docs/ops/mcp-host-proof-registry.md` is updated to `verified` with the
  proof date and trace path.

Proof trace:

- `docs/ops/librechat-runtime-proof-2026-05-01.md`

## Supporting Protocol Checks

Run these before and after the LibreChat proof:

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose
python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory tools
```

Expected directory tools:

- `get_workflow_status`
- `list_workflow_universes`
- `inspect_workflow_universe`
- `list_workflow_goals`
- `search_workflow_goals`
- `get_workflow_goal`
- `search_workflow_wiki`
- `read_workflow_wiki_page`
- `list_workflow_runs`
- `propose_workflow_goal`
- `submit_workflow_request`

## Troubleshooting Notes

- If the connection never appears, verify `allowedDomains` includes
  `tinyassets.io`.
- If chat answers from memory without a tool call, verify the chat request or
  selected UI state actually attaches the MCP server. The proof path used
  `ephemeralAgent.mcp = ["workflow"]`; a raw request `tools` list alone did not
  match the normal LibreChat UI path during this proof.
- If the model writes a tool call in text instead of executing it, switch to a
  model with function/tool-call support and repeat the proof.
- LibreChat logs transient Streamable HTTP close/abort messages during startup
  and reconnect. In the 2026-05-01 proof these appeared before successful
  initialization and did not block the connection.

## Source Notes

Fresh docs checked on 2026-05-01:

- LibreChat MCP docs: `https://www.librechat.ai/docs/features/mcp`
- Workflow proof registry: `docs/ops/mcp-host-proof-registry.md`
- Workflow directory queue: `docs/ops/mcp-directory-rollout-action-queue.md`

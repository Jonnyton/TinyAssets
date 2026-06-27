# LibreChat Runtime Proof - TinyAssets MCP Directory

Date: 2026-05-01
Host: LibreChat
Host version: `v0.8.5`
Proof scope: local Docker Compose LibreChat instance using the public TinyAssets
MCP directory endpoint.

## Environment

| Field | Value |
|---|---|
| LibreChat source | `danny-avila/LibreChat` tag `v0.8.5` |
| LibreChat commit | `9ccc8d9bef407f9a769f07a3756ec4b95ac13f80` |
| LibreChat API image | `registry.librechat.ai/danny-avila/librechat:latest` |
| API image digest | `sha256:a46254938507971e0d4f7ed3f9d116bd9b118f4810b5b75eb716baf575645068` |
| API container | `LibreChat` |
| Mongo image | `mongo:8.0.20` |
| Local URL | `http://127.0.0.1:32181` |
| Auth shape | local LibreChat proof account; no Claude/ChatGPT login |
| TinyAssets endpoint | `https://tinyassets.io/mcp-directory` |
| MCP transport | Streamable HTTP |
| TinyAssets auth mode | None |
| Model used for chat proof | `gpt-oss:20b` through LibreChat/Ollama |

## Config Proof

The proof `librechat.yaml` configured TinyAssets as:

```yaml
mcpSettings:
  allowedDomains:
    - "tinyassets.io"

mcpServers:
  workflow:
    title: "TinyAssets"
    description: "Directory-safe TinyAssets MCP endpoint"
    type: "streamable-http"
    url: "https://tinyassets.io/mcp-directory"
    timeout: 30000
    initTimeout: 30000
    serverInstructions: |
      Use TinyAssets for read-only daemon status, goals, wiki, universe, and run inspection.
      Only use proposal/write tools when the user explicitly asks for a proposal.
```

LibreChat startup logs showed:

```text
[MCP][workflow] Creating streamable-http transport: https://tinyassets.io/mcp-directory
[MCP][workflow] OAuth Required: false
[MCP][workflow] Tools: get_workflow_status, list_workflow_universes, inspect_workflow_universe, list_workflow_goals, search_workflow_goals, get_workflow_goal, search_workflow_wiki, read_workflow_wiki_page, list_workflow_runs, propose_workflow_goal, submit_workflow_request
[MCP] Initialized with 1 configured server and 11 tools.
```

The logs also showed transient Streamable HTTP close/abort messages during
startup and reconnect. These did not block initialization or the later tool
call.

## API Tool Proof

LibreChat connection status:

```json
{
  "success": true,
  "serverName": "workflow",
  "connectionStatus": "connected",
  "requiresOAuth": false
}
```

`GET /api/mcp/tools` returned one server:

```text
workflow authenticated=true authConfig=[]
```

The server exposed the 11 directory-safe TinyAssets tool keys:

```text
get_workflow_status_mcp_workflow
list_workflow_universes_mcp_workflow
inspect_workflow_universe_mcp_workflow
list_workflow_goals_mcp_workflow
search_workflow_goals_mcp_workflow
get_workflow_goal_mcp_workflow
search_workflow_wiki_mcp_workflow
read_workflow_wiki_page_mcp_workflow
list_workflow_runs_mcp_workflow
propose_workflow_goal_mcp_workflow
submit_workflow_request_mcp_workflow
```

## Chat Tool-Call Proof

Prompt sent through LibreChat's agent chat route:

```text
Call the TinyAssets MCP tool get_workflow_status now. Do not answer from memory. After the tool result, reply with reachable=true or reachable=false and quote one exact returned field name/value.
```

Important request detail:

```json
{
  "endpoint": "ollama",
  "endpointType": "custom",
  "model": "gpt-oss:20b",
  "agent_id": "ephemeral",
  "ephemeralAgent": {
    "mcp": ["workflow"]
  }
}
```

Result summary:

```text
stream_id=e7f80700-444a-4854-ac24-50ef2544c946
message_count=2
assistant content included type=tool_call
tool_call.name=get_workflow_status_mcp_workflow
tool_call.args={"universe_id":""}
tool_call.output included active_host.host_id="host", universe_exists=true, pressure_level="ok"
assistant final text: reachable=true; active_host.host_id: host
```

This proves LibreChat invoked the TinyAssets MCP server and produced a
user-visible response grounded in `get_workflow_status`.

One earlier API attempt with a raw `tools` array but no `ephemeralAgent.mcp`
selection did not execute the tool. That was a proof-harness request-shape
issue; the successful request matches LibreChat's normal ephemeral-agent MCP
selection path.

## Supporting Public Check

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose
```

Result:

```text
[canary] OK https://tinyassets.io/mcp-directory
```

## Claim Boundary

Verified claim:

- LibreChat `v0.8.5` can connect to TinyAssets' public Streamable HTTP
  directory endpoint with TinyAssets auth mode `None`.
- A local LibreChat chat can invoke `get_workflow_status` through the TinyAssets
  MCP server and return a grounded visible answer.
- This path does not require Claude or ChatGPT login.

Not yet generalized:

- Other LibreChat versions.
- Hosted or managed LibreChat deployments.
- No-auth LibreChat deployments; this proof used a local LibreChat account.
- OAuth/Bearer-secured TinyAssets endpoints.
- Write/proposal flows through LibreChat tool-call UX.
- Models without reliable function/tool-call support.

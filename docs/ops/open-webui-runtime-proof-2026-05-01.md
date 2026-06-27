# Open WebUI Runtime Proof - TinyAssets MCP Directory

Date: 2026-05-01
Host: Open WebUI
Host version: 0.9.2
Proof scope: local Docker Open WebUI instance using the public TinyAssets MCP
directory endpoint.

## Environment

| Field | Value |
|---|---|
| Open WebUI image | `ghcr.io/open-webui/open-webui:main` |
| Image digest | `sha256:c2e4723fdbca5de8f9f0529e22b78acf5bc312a88da730bed88860063d028fe8` |
| Container | `workflow-openwebui-proof` |
| Local URL | `http://127.0.0.1:32180` |
| Open WebUI version | `0.9.2` |
| Open WebUI auth | `WEBUI_AUTH=False`; local admin token used only for API proof calls |
| Secret key | `WEBUI_SECRET_KEY` set for the proof container |
| Workflow endpoint | `https://tinyassets.io/mcp-directory` |
| MCP transport | Streamable HTTP |
| Workflow auth mode | None |
| Function filter | Empty |
| Model used for chat proof | `qwen3.5-nothink:latest` through Open WebUI/Ollama |

## Tool Server Proof

Open WebUI's own tool-server verification endpoint accepted Workflow:

```text
POST /api/v1/configs/tool_servers/verify
status: true
url: https://tinyassets.io/mcp-directory
type: mcp
auth_type: none
```

The verification returned the 11 directory-safe Workflow tools:

```text
get_workflow_status
list_workflow_universes
inspect_workflow_universe
list_workflow_goals
search_workflow_goals
get_workflow_goal
search_workflow_wiki
read_workflow_wiki_page
list_workflow_runs
propose_workflow_goal
submit_workflow_request
```

After saving the connection with `info.id=workflow`, Open WebUI listed the
server as:

```text
id: server:mcp:workflow
name: Workflow
description: Directory-safe TinyAssets MCP endpoint
```

## Chat Tool-Call Proof

Prompt sent through Open WebUI's chat completion route:

```text
Use the Workflow tool to call get_workflow_status. Then answer in one sentence with reachable=true or reachable=false and one field from the tool result.
```

Request shape:

```text
POST /api/chat/completions
model: qwen3.5-nothink:latest
tool_ids: server:mcp:workflow
stream: false
```

Result summary:

```text
source_names=workflow_get_workflow_status
choice_count=1
message=The system is reachable=true as confirmed by the universe_exists field being true [1].
finish_reason=stop
```

This proves Open WebUI invoked the TinyAssets MCP server, exposed the tool result
as a chat source, and produced a user-visible response grounded in the
`get_workflow_status` result.

One attempted proof with `glm-5.1:cloud` failed before Workflow execution
because the selected Ollama cloud model required a paid subscription. That was a
model-access failure, not a Workflow or MCP connection failure.

## Supporting Public Checks

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose
```

Result:

```text
[canary] OK https://tinyassets.io/mcp-directory
```

```powershell
python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory tools
```

Result: returned the same 11 directory-safe Workflow tools listed above.

## Claim Boundary

Verified claim:

- Open WebUI 0.9.2 can connect to Workflow's public Streamable HTTP directory
  endpoint with auth mode `None`.
- A local Open WebUI chat can invoke `get_workflow_status` through the Workflow
  MCP tool server and return a grounded visible answer.

Not yet generalized:

- Other Open WebUI versions.
- Hosted or multi-user Open WebUI deployments.
- OAuth/Bearer-secured Workflow endpoints.
- Write/proposal flows through Open WebUI approval UX.

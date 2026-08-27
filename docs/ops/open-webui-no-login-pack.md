# Open WebUI No-Chatbot-Login Pack

Created: 2026-05-01
Current contract checked: 2026-07-24
Status: current anonymous-read-only guidance; canonical host proof pending;
historical Docker proof retained below
Owner: lead + available provider

This pack is the first no-hosted-chatbot-login path for TinyAssets. It is for
users who do not want or cannot use Claude/ChatGPT app directories, but can run
or access an Open WebUI instance.

## Current Truth

- Open WebUI docs say native MCP support starts in Open WebUI `v0.6.31+`.
- Native MCP support is `MCP (Streamable HTTP)` only.
- TinyAssets has one public Streamable HTTP MCP endpoint:
  `https://tinyassets.io/mcp`.
- The public name is exactly `TinyAssets`. Do not add `DEV`, `directory`, or
  another lifecycle qualifier.
- Canonical `/mcp` advertises exactly seven tools: `read_graph`, `write_graph`,
  `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`.
- A connection configured with authentication `None` is
  **anonymous-read-only**. It may call `read_graph` and `read_page`. Do not
  expose `get_status` through this pack until the versioned public-status
  projection is implemented and verified; the current result is unredacted.
  Mutation, execution, and conversation entry require OAuth and are
  unsupported by this no-login pack.

Public claim scope: the 2026-05-01 Open WebUI 0.9.2 Docker observation below is
historical evidence from the retired endpoint. Current support requires a fresh
proof against canonical `/mcp`. Do not generalize it to another Open WebUI
version, hosted deployment, auth mode, model, or mutation flow.

## Recommended Open WebUI Settings

In Open WebUI:

1. Open `Admin Settings -> External Tools`.
2. Add a server.
3. Set `Type` to `MCP (Streamable HTTP)`.
4. Set `Server URL` to:

```text
https://tinyassets.io/mcp
```

5. Set authentication to `None`.
6. If Open WebUI supports a function-name filter, allow only:

```text
read_graph,read_page
```

7. Treat OAuth-required tools as unsupported in this no-login configuration.
   Do not test or document anonymous mutation.
8. Save. Restart Open WebUI if prompted.

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

## Troubleshooting Notes

- If the connection fails, verify the tool type is `MCP (Streamable HTTP)`, not
  OpenAPI.
- If auth is set to `Bearer` without a key, Open WebUI may send an empty
  authorization header. Use `None` only for the anonymous-read-only path.
- If Open WebUI runs in Docker and the MCP server is on the host machine, Open
  WebUI docs recommend `host.docker.internal`. That is not needed for
  `https://tinyassets.io/mcp` because it is a public HTTPS endpoint.
- Open WebUI recommends setting `WEBUI_SECRET_KEY` for stable OAuth-connected
  tools. This pack does not establish Open WebUI OAuth interoperability with
  TinyAssets; mutation remains unsupported until separately proven.

## Historical Runtime Proof — 2026-05-01

The following table and trace record what was observed on the retired endpoint
on 2026-05-01. Preserve it as evidence; do not use it as current setup guidance.

| Field | Value |
|---|---|
| Open WebUI version | `0.9.2` |
| Deployment shape | local Docker, `ghcr.io/open-webui/open-webui:main` |
| TinyAssets endpoint | `https://tinyassets.io/mcp-directory` |
| Auth mode | None |
| Function filter | empty for first proof |
| Model used | `qwen3.5-nothink:latest` |
| Prompt | `Use the TinyAssets tool to call get_workflow_status...` |
| Visible tool result | Open WebUI source `workflow_get_workflow_status`; answer said `reachable=true` from `universe_exists=true` |
| Screenshot/trace path | `docs/ops/open-webui-runtime-proof-2026-05-01.md` |
| Date/time | 2026-05-01 UTC |

Historical acceptance criteria used for that proof:

- Open WebUI adds the TinyAssets MCP server without crashing or infinite loading.
- A chat can invoke at least one read-only TinyAssets tool.
- The visible response matches the tool result enough for a user to trust it.
- Any console/server error is recorded.
- `docs/ops/mcp-host-proof-registry.md` is updated to `verified` with the
  proof date and trace path.

Proof trace:

- `docs/ops/open-webui-runtime-proof-2026-05-01.md`

## Supporting Protocol Checks

Run these before and after the Open WebUI proof:

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

## Source Notes

Fresh docs checked on 2026-05-01:

- Open WebUI MCP docs: `https://docs.openwebui.com/features/mcp/`
- TinyAssets proof registry: `docs/ops/mcp-host-proof-registry.md`
- Current connector reconciliation:
  `openspec/changes/archive/2026-08-26-reconcile-external-connector-manifests/`

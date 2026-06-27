# Codex CLI MCP Registration Proof

Date: 2026-05-02
Host: Codex CLI 0.104.0 on Windows x64
Endpoint: `https://tinyassets.io/mcp-directory`
Status: registration path verified; runtime proof landed separately

## What This Proves

Codex CLI accepts TinyAssets as a Streamable HTTP MCP server and writes the
expected isolated configuration without mutating the user's real
`~/.codex/config.toml`.

```toml
[mcp_servers.workflow]
url = "https://tinyassets.io/mcp-directory"
```

This file proves registration/config write behavior only. The follow-up runtime
proof is `docs/ops/mcp-codex-runtime-proof-2026-05-02.md`.

## Commands

```powershell
codex --version
```

Output:

```text
codex-cli 0.104.0
```

Isolated registration command:

```powershell
$temp = Join-Path $env:TEMP 'workflow-codex-mcp-proof'
New-Item -ItemType Directory -Force -Path $temp | Out-Null
$env:CODEX_HOME = $temp
codex mcp add workflow --url https://tinyassets.io/mcp-directory
```

Observed result:

```text
Added global MCP server 'workflow'.
```

List readback:

```powershell
$env:CODEX_HOME = "$env:TEMP\workflow-codex-mcp-proof"
codex mcp list --json
```

Output:

```json
[
  {
    "name": "workflow",
    "enabled": true,
    "disabled_reason": null,
    "transport": {
      "type": "streamable_http",
      "url": "https://tinyassets.io/mcp-directory",
      "bearer_token_env_var": null,
      "http_headers": null,
      "env_http_headers": null
    },
    "startup_timeout_sec": null,
    "tool_timeout_sec": null,
    "auth_status": "unsupported"
  }
]
```

Server readback:

```powershell
$env:CODEX_HOME = "$env:TEMP\workflow-codex-mcp-proof"
codex mcp get workflow --json
```

Output:

```json
{
  "name": "workflow",
  "enabled": true,
  "disabled_reason": null,
  "transport": {
    "type": "streamable_http",
    "url": "https://tinyassets.io/mcp-directory",
    "bearer_token_env_var": null,
    "http_headers": null,
    "env_http_headers": null
  },
  "enabled_tools": null,
  "disabled_tools": null,
  "startup_timeout_sec": null,
  "tool_timeout_sec": null
}
```

## Runtime Proof

Codex CLI 0.104.0 later listed TinyAssets tools from
`https://tinyassets.io/mcp-directory` and completed
`get_workflow_status({})`, returning `"schema_version": 1`. See
`docs/ops/mcp-codex-runtime-proof-2026-05-02.md`.

# Cursor MCP Registration Proof

Date: 2026-05-01
Host: Cursor 3.2.16 on Windows x64
Endpoint: `https://tinyassets.io/mcp-directory`
Status: registration path verified; Cursor tool-call proof still pending

## What This Proves

Cursor's CLI accepts a Streamable HTTP MCP server definition for TinyAssets and
writes the expected MCP settings shape in an isolated user-data directory:

```json
{
  "mcp": {
    "servers": {
      "workflow": {
        "type": "streamable-http",
        "url": "https://tinyassets.io/mcp-directory"
      }
    }
  }
}
```

This is not yet a full Cursor support claim. A full support claim still needs
Cursor's UI or agent runtime to list TinyAssets tools and complete one safe
read-only call.

## Commands

```powershell
cursor --version
```

Output:

```text
3.2.16
3e548838cf824b70851dd3ef27d0c6aae371b3f0
x64
```

Isolated registration command:

```powershell
$tempRoot = Join-Path $env:TEMP 'workflow-cursor-mcp-proof'
$json = '{\"name\":\"tinyassets\",\"type\":\"streamable-http\",\"url\":\"https://tinyassets.io/mcp-directory\"}'
cursor --user-data-dir $tempRoot --add-mcp $json --new-window --disable-extensions --log trace
```

Observed result:

```text
Added MCP servers: workflow
EXIT:0
```

Settings readback:

```powershell
Get-Content -Raw "$env:TEMP\workflow-cursor-mcp-proof\User\settings.json"
```

Output:

```json
{
	"mcp": {
		"servers": {
			"workflow": {
				"type": "streamable-http",
				"url": "https://tinyassets.io/mcp-directory"
			}
		}
	}
}
```

## Remaining Proof

Before public copy says Cursor is verified, run Cursor with this MCP server
enabled and record:

- TinyAssets appears in Cursor's MCP tools/settings surface.
- Cursor lists TinyAssets tools from `https://tinyassets.io/mcp-directory`.
- Cursor completes one safe read-only call, preferably `get_workflow_status`.
- The trace includes the Cursor version, transport, config, and visible result.

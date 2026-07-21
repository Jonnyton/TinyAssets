# workflow-probe — ops CLI reference

`workflow-probe` is the ops CLI for querying the live Workflow MCP daemon
without going through Claude.ai chat. Stdlib-only; works from a bare clone.

## Install

```bash
pip install -e .          # after cloning
workflow-probe status     # verify
```

Or run directly without installing:

```bash
python scripts/mcp_probe.py status
```

## Default endpoint

All commands default to `https://tinyassets.io/mcp`.
Override with `--url`:

```bash
workflow-probe --url https://tinyassets.io/mcp status
```

## Subcommands

### `status`

Calls `get_status`. Shows daemon phase, uptime, bound LLM, universe count.

```bash
workflow-probe status
```

Healthy output includes `"phase": "running"` and a non-empty `llm_endpoint_bound`.

### `universes`

Lists all universes on the server.

```bash
workflow-probe universes
```

### `universe <id>`

Inspects a specific universe — branches, node count, last activity.

```bash
workflow-probe universe concordance
```

### `wiki`

Lists promoted wiki pages.

```bash
workflow-probe wiki
```

### `tools`

Lists all registered MCP tools with one-line descriptions.

```bash
workflow-probe tools
```

### `latency`

Times a real MCP `initialize` plus `get_status` call and prints a compact
client-observed latency line.

```bash
workflow-probe latency
```

Use `--raw` to include the full `get_status` MCP response with the measured
`latency_ms`.

## Raw / arbitrary tool calls

```bash
workflow-probe --tool get_status
workflow-probe --tool universe --args '{"action":"list"}'
workflow-probe --tool universe --args '{"action":"inspect","universe_id":"concordance"}'
workflow-probe --tool wiki --args '{"action":"read","page":"index"}'
workflow-probe --list                          # alias for 'tools'
```

PowerShell can strip JSON quotes before native commands see them. For simple
flat objects, `workflow-probe` also accepts the stripped form:

```powershell
python scripts\mcp_probe.py --tool goals --args "{action:search,query:research-paper,limit:5}"
```

## Flags

| Flag | Description |
|---|---|
| `--url URL` | MCP endpoint (default: `https://tinyassets.io/mcp`) |
| `--raw` | Print full JSON response instead of extracted text |
| `--tool NAME` | Raw tool call |
| `--args JSON` | JSON arguments for `--tool` (default: `{}`); simple flat PowerShell-stripped objects are accepted |
| `--list` | List tools (legacy alias for `tools` subcommand) |

## Healthy-state snippets

### `workflow-probe status` (healthy)

```json
{
  "phase": "running",
  "uptime_s": 3600,
  "llm_endpoint_bound": true,
  "universe_count": 1,
  "daemon_running": true
}
```

### `workflow-probe universes` (healthy, one universe)

```json
{
  "universes": [
    {"id": "default-universe", "branch_count": 3}
  ]
}
```

### `workflow-probe latency` (healthy)

```text
latency_ms=125 status=ok stage=get_status url=https://tinyassets.io/mcp
```

## Diagnosing prod-stale

If `workflow-probe status` returns stale data after a deploy:

1. Check `workflow-probe --raw --tool get_status` for `"version"` field.
2. Compare against latest `git log --oneline -1` on `origin/main`.
3. If behind: the `deploy-prod` GHA workflow may not have fired — check
   `Actions → Deploy prod` for `VERIFY SECRETS PRESENT` failures.
4. Secrets needed: `DO_DROPLET_HOST`, `DO_SSH_USER`, `DO_SSH_KEY`.

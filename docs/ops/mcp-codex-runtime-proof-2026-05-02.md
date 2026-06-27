# Codex CLI MCP Runtime Proof

Date: 2026-05-02
Host: Codex CLI 0.104.0 on Windows x64
Endpoint: `https://tinyassets.io/mcp-directory`
Status: verified for Codex CLI tool listing plus one read-only call

## What This Proves

Codex CLI can load TinyAssets as a Streamable HTTP MCP server, expose the
directory-surface tools to a Codex agent, and complete a read-only
`get_workflow_status` call.

This follows the registration-path proof in
`docs/ops/mcp-codex-registration-proof-2026-05-02.md`.

## Command

The runtime proof used an in-process config override so the user's real
`~/.codex/config.toml` was not mutated:

```powershell
$out = Join-Path $env:TEMP 'workflow-codex-mcp-toolcall-last.txt'
Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue
codex exec --ephemeral --sandbox read-only -m gpt-5.2 `
  -C C:\Users\Jonathan\Projects\TinyAssets `
  -c 'mcp_servers.workflow.url="https://tinyassets.io/mcp-directory"' `
  -o $out `
  "Use only the configured TinyAssets MCP server, not shell commands. List the available TinyAssets MCP tools you can see, call the read-only get_workflow_status tool if available, and return the tool list plus one exact field name/value from the result. If you cannot access the TinyAssets MCP tools, say exactly what blocked you."
```

The first attempt with the repo-configured default model failed before tool use:

```text
The 'gpt-5.5' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again.
```

The proof therefore pins `-m gpt-5.2` for Codex CLI 0.104.0. This is a CLI/model
compatibility caveat, not an MCP endpoint failure.

## Tool List Evidence

Codex reported these TinyAssets directory-surface tools:

```text
mcp__workflow__get_workflow_goal
mcp__workflow__get_workflow_status
mcp__workflow__inspect_workflow_universe
mcp__workflow__list_workflow_goals
mcp__workflow__list_workflow_runs
mcp__workflow__list_workflow_universes
mcp__workflow__propose_workflow_goal
mcp__workflow__read_workflow_wiki_page
mcp__workflow__search_workflow_goals
mcp__workflow__search_workflow_wiki
mcp__workflow__submit_workflow_request
```

The session also had an existing `workflow-live` server configured in the user's
Codex environment. That is separate from this proof; the verified directory
surface is the `mcp__workflow__*` namespace loaded from
`https://tinyassets.io/mcp-directory`.

## Read-Only Call Evidence

The Codex CLI trace included:

```text
tool workflow.get_workflow_status({})
workflow.get_workflow_status({}) success in 68ms
```

Codex returned this exact field from the result:

```json
{
  "schema_version": 1
}
```

## Safety Boundary

- No repository files were written by the Codex CLI proof command.
- The proof used `--sandbox read-only` and `--ephemeral`.
- The command used a temporary output file under `%TEMP%`.
- The command did not submit Claude/OpenAI directory forms or transmit
  company/contact fields.

## Follow-Up Verification

After quoting the `website-editing` skill description frontmatter so Codex CLI
can parse it as YAML, the runtime proof was rerun from this branch:

```text
exit=0
skill_load_error=False
mcp_ready=True
tool_call_success=True
```

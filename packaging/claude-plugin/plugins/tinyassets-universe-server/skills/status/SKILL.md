---
name: status
description: Show the current daemon state for the selected TinyAssets universe.
disable-model-invocation: true
---

# Status

Show the current state of the Author daemon: what phase it's in, word count, accept rate, and whether it's paused.

## Usage

When the user invokes `/tinyassets-universe-server:status`, call the
`universe` MCP tool with `action="inspect"` and present the daemon
section in a readable format.

## Response format

Present the status concisely:
- Phase (e.g. "writing scene 14", "reviewing", "paused")
- Word count
- Accept rate (if available)
- Whether the daemon is paused

If the daemon is not running or the universe is missing, say so clearly
and suggest checking the selected universe base directory.

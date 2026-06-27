---
name: steer
description: Send a steering note to the TinyAssets daemon for the current universe.
disable-model-invocation: true
---

# Steer

Append a steering note to the running daemon. The daemon reads notes at each scene boundary and incorporates direction into its next creative decisions.

## Usage

When the user invokes `/tinyassets-universe-server:steer`, ask what
direction they want to give, or use their provided text, then call the
`universe` MCP tool with `action="give_direction"` and the appropriate
category.

## Categories

- **direction** — Steer the story in a specific direction (default)
- **protect** — Preserve an element the user likes
- **concern** — Flag a problem or inconsistency
- **observation** — Neutral note for the daemon's awareness
- **error** — Report a factual mistake

## Example

User: `/tinyassets-universe-server:steer Focus more on the political intrigue between the kingdoms`

Action: Call `universe` with `action="give_direction"`,
`text="Focus more on the political intrigue between the kingdoms"`,
and `category="direction"`.

Response: Confirm the note was delivered and explain when the daemon will read it (next scene boundary).

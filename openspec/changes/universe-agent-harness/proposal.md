## Why

The founder, 2026-10-01: "really wish the app was more like this cli and that my
agent acted more like you do, getting him to do anything is like dragging a dead
horse around ... how long it keeps working should be like you. tools should be
like a mix of openclaw, claude code and pi.dev and hermes. authority should be
broad encouraging proactivity. tone like yours. feedback loop like yours. a
proper lean clean efficient self improving agent harness".

Production measurements of the founder's universe (`u-01kxm1vszd8hwp7em418asq8h9`,
`/data/.tinyassets.db` and its own folder, read-only, 2026-10-01) show the drag in
numbers, measured on its 251 chat turns with its owner (the background agent it
built is excluded; it is a user-built agent, not the harness). Every turn is a
brand-new session: Codex runs `--ephemeral`, and memory is a 20-message,
7,000-character text block with every tool result dropped. The median chat turn
spends 61,862 input tokens. 26% of replies contain an ask, 54% contain
blocked/can't language, and 29% carry "I haven't verified" disclaimers. Of 225
replies, 7 report an effect without negating it in the same reply, and 10.4% of
turns end indeterminate or abandoned. The design records the full audit.

The tools exist (S1 of `universe-harness-four-tools` shipped `read`/`write`/
`edit`/`bash` in a jail), so the problem is no longer missing tools. The harness
around them drops working state between turns and resends a persona prompt
that teaches warmth, curiosity and asking. Each round also carries about 7k
tokens of tool descriptions. Its tools have no network and no browser, and every
outward step needs per-turn consent.

## What Changes

- **Sessions.** A universe agent works in long-lived sessions, one per
  conversation thread or agent node, persisted by the platform with automatic
  compaction. A turn runs until the model is done. New messages steer it at tool
  boundaries, and events wake an existing session instead of starting a fresh
  one.
- **Tools.** The core is pi-style: `read`/`write`/`edit`/`bash` in the jailed
  universe workspace. Bash gets filtered public network access, the jail gets a
  browser and a usable toolchain, and the whole user root becomes writable once
  platform state moves to `.runtime/`. Skills follow the Agent Skills format,
  and the agent writes and saves them itself. Extensions are hook processes. The
  platform is one extension: the same handlers as an in-jail `ta` CLI and as
  deferred MCP, not a resident tool block.
- **Authority.** By default the agent may do anything inside its own universe.
  It asks only for things outside it: a new credential or wider grant,
  reaching other people, or spending beyond a budget the user set. Asks are app
  requests. Approvals become standing grants, so per-turn consent replay goes.
- **Tone.** A seed `AGENTS.md`, owned by the user and edited by the agent,
  replaces the persona Python. Replies lead with the result and stay short and
  honest, with no boilerplate disclaimers.
- **Feedback loop.** Every adapter journals every tool call. Errors report the
  real cause quickly, and oversized output spills to a file instead of
  truncating silently.
- **Self-improvement.** The agent edits its own `AGENTS.md`, `MEMORY.md`,
  skills, prompts and settings. A universe-local git commit at turn end versions
  the harness and rolls it back.
- **BREAKING.** The following are deleted: the persona prompt assembly, the
  separate learning-extraction call, `read_brain`/`write_brain` and soul.edit
  governance for owner turns, the conversation-memory text block, the
  cross-surface continuity directive, the per-turn consent line, and the
  resident handbook guidance that the platform extension replaces. The design
  lists every deletion.

The change is designed vendor-neutral. Claude, Codex, OpenRouter and any
OpenAI-compatible or command-adapter source drive the same assembled harness,
and adapter-specific behaviour is a declared capability (`resume`,
`deferred_tools`, `self_compacts`), never platform policy.

## Capabilities

### New Capabilities

- `universe-agent-harness`: sessions and compaction, the turn and wake loop,
  steering, the tool surface, default authority and standing grants, the
  harness files and their versioning, and truthful tool results.

### Modified Capabilities

- `universe-personification-and-relay`: `converse` continues the thread's
  session instead of running one stateless turn. The separate learning
  extraction and the WebFetch-only denylist sandbox are removed. The OS tool
  jail and git-versioned files replace them.

## Impact

Code: `tinyassets/universe_intelligence.py` (persona and learning paths deleted),
`conversation_memory.py` (replaced by the session log),
`agent_turn_coordinator.py` and `storage/agent_turn_journal.py` (keyed by
session), `providers/codex_provider.py` and `providers/claude_provider.py` (resume
handle as a declared capability, journaled tool events), `universe_tools.py`
(egress, browser, writable root), `engine_mcp_server.py` (served as `ta` plus
deferred), `served_tools.py`, `shared_self.py` and `background_served_provider.py`
(agent nodes resume their session), and `effectors/*` consent (standing grants).

Storage: session logs and the universe-local git repo are new storage shapes,
and platform state moves under `.runtime/`. Each gets its slice's own storage
proposal before code.

Authority: a broader default inside the universe. The cross-user floor and
credential blindness are unchanged.

Supersedes the S2–S8 slice plan in
`universe-harness-four-tools/design-notes/universe-harness-design.md`. Its S1
is built and that change is archived after its delta syncs.

Owner: Claude. Branch: `universe-agent-harness`. This PR is design only. Each
slice ships as its own PR and is proven live.

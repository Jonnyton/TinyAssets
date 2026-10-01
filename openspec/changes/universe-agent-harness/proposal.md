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


**Revised the same day to the founder's direction:** "a new users universe
should act like an always on dot agent from chatgpt. but with the customization
of openclaw and the clean powerfull tool list of pi.dev and user design
shareabliaty for harness and on ui interface command center designs for agent
management". Then: "it should work how ever dots work for chatgpt … pi's 4
tools, users should have full customization of the harness layer for any
configeration of agents". ChatGPT dots, launched 2026-09-29, are always-on
agents with their own computer and a responsibility. They research proactively
with read-only tools, act under per-action Custom Rules with an auto-review, and
are managed from a profile with Activity, Take over and Pause (design §1.2).

## What Changes

A new user's universe **is** a dot. Each item below copies what dots do, except
where noted:

- **Onboarding.** The universe asks for a name and one responsibility: what it
  owns, where it learns, its quality bar, what needs approval, and how often it
  reports. It writes the answers into its own files.
- **Its own computer.** It has a jailed workspace, bash with public egress, and
  its own browser.
  - The browser runs in a sandbox whose profile the agent cannot read.
  - The profile page has a live view, plus *Take over* / *Return control* for
    logins and decisions.
- **Always on, several projects at once.** Work becomes **activities**: child
  sessions that run in parallel on the user's seats, keep going after the chat
  closes, and report into the main thread. Scheduled activities reuse
  user-owned automations.
- **Proactive research while idle.** Its tools are read-only, **enforced in
  code**:
  - write and edit are refused;
  - bash runs read-only with no network;
  - the platform socket answers read verbs only;
  - connected-app calls are limited to reads;
  - there is no browser.

  Its output is proposals only. An approved proposal becomes a pre-approved
  activity.
- **Custom Rules (authority).** Each action class gets one of four behaviours:
  do without asking, do if pre-approved, ask first, or hand off. One decision
  point is checked at every enforcement site. Rules are owner-only: the agent
  can read them and propose changes, but cannot write them. Seed rules
  reproduce the first version's "act inside, ask outside" default.
- **Auto-review.** Before consequential actions, a check runs on the
  **universe's own model** and fails closed. Fixed **reserved actions** always
  hand back to the owner: credential or security changes, moving money, and
  granting others access.
- **Profile and command center.** The profile has these parts:
  - an Activity tab: Waiting on you, In progress, Scheduled, Completed with
    receipts;
  - a Computer tab, plus Memory, Rules and Harness tabs;
  - Pause, and push notifications when work is done, waiting or proposed.

  A roster view across agents is the command center. Both are built on the
  custom-UI layer, so users can redesign them.
- **Reachable everywhere.** The app, `converse`, and chat apps through channel
  extensions all reach one session.
- **Exactly pi's four tools.** Every agent gets `read`/`write`/`edit`/`bash`
  and nothing else resident. Breadth (platform verbs, connected apps,
  extensions, attached MCP servers) sits behind `ta search` / `ta describe` in
  bash. The deferred-MCP route for the agent is dropped.
- **Memory item by item.** Every memory item has a stable id, and the owner can
  edit or delete each one (dots cannot).
- **Harness layer for any roster.** Any number of agents is supported. Each has
  its own instructions, identity, memory, skills, extensions, settings, rules,
  sessions and profile.
- **Sharing.** A harness bundle and command-center layouts are exported
  through the `universe-custom-agents` definition shape.
  - Export is PII-scrubbed and owner-confirmed, and never includes memory,
    sessions, credentials or browser state.
  - Imports land in an inert quarantine until the owner activates them, only as
    written or stricter.
- **Kept from the first version:**
  - sessions and compaction;
  - steering;
  - the truthful journal;
  - result-first tone;
  - self-improvement with file history and Undo;
  - the egress floor.
- **BREAKING.** In addition to the first version's deletions, the first
  version's "inside acts without asking; outside asks once" requirement is
  replaced by Custom Rules. The S1 `AGENTS.md` authority text becomes a
  description of the user's rules.

The change is designed vendor-neutral. Claude, Codex, OpenRouter and any
OpenAI-compatible or command-adapter source drive the same assembled harness,
and adapter-specific behaviour is a declared capability (`resume`,
`deferred_tools`, `self_compacts`), never platform policy.

## Capabilities

### New Capabilities

- `universe-agent-harness`: the dot experience. It covers:
  - onboarding, activities, proactive research, Custom Rules, auto-review and
    reserved actions;
  - the profile and roster, take-over, memory items, the harness roster and
    sharing;
  - sessions and compaction, steering, the four-tool surface, harness files
    with versioning, and truthful tool results.

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

Authority: per-action Custom Rules with auto-review and reserved actions,
replacing a fixed default. The rules store is owner-only. The cross-user floor,
credential blindness and the standing-grant checks are unchanged.

Storage: also new are activity records, the rules store, proposals and the
browser profile, all under `.runtime/` (S3c). The activity store opens its own
storage proposal in D2. The rules store is specified here as part of the
authority design.

Supersedes the S2–S8 slice plan in
`universe-harness-four-tools/design-notes/universe-harness-design.md`. Its S1
is built and that change is archived after its delta syncs.

Owner: Claude. Branch: `universe-agent-harness`. This PR is design only. Each
slice ships as its own PR and is proven live. S1 (#4173) has shipped. S3a
(#4174) and the S3c proposal (#4175) are in flight. Design §5 maps them onto
the dot.

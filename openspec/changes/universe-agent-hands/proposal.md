# Give the universe agent hands

## Why

A founder talked to their universe agent in Slack on 2026-08-07 and it worked —
it recognised them, spoke as the startup, and persisted what it learned. Then
they asked it to build something, and it **became the thing they asked for**.

`body.md` before:

    My body is the repository at https://github.com/Jonnyton/TinyAssets.

`body.md` after "I want to build an OpenClaw-style agent on you":

    An OpenClaw-style autonomous agent that can browse the web, write code,
    and run tasks on its own schedule.

The agent did not choose that. `converse` runs the reply with
`_ENGINE_ALLOWED_TOOLS = ("WebFetch",)` and no write capability at all; a
*second* model call (`extract_learning`) then re-reads the transcript and fills a
hardcoded schema — `name` plus five fixed soul files plus `canon[]` — which
`commit_learning` writes after the turn ends. A request to BUILD landed in the
`body.md` slot because the sentence described capabilities, and
`soul_edit.py:252` replaces rather than merges:

    body = new_body if (new_body or "").strip() else old_body

The same turn wrote `wiki/drafts/projects/openclaw-style-autonomous-agent.md`
correctly ("The founder intends to build…"). One turn, two readings of one
sentence, and the destructive one won silently. Nothing surfaced it to the user;
recovery is a manual read of `soul_versions/0002.md`.

This is not a prompt bug. An agent that cannot write must have its intent
guessed, and a guesser must choose a slot. **The fix is to let the agent decide
its own writes** — which is also what the founder asked for: an agent that
builds and manages its own automations, edits its own project folder, drives the
patch automation to change its own GitHub (and therefore itself), and creates
other agents in whatever harness shape the user wants — Hermes, OpenClaw, Claude
Code, Codex, or a mix.

Cross-family review (Codex, read-only, asked to refute): all three findings
CONFIRMED, plus two this proposal now accounts for — `soul_edit.py:252` replaces
non-empty bodies, and `api/wiki.py:2523-2541` **deliberately bypasses the MCP ACL
gate** for first-party canon writes.

## What Changes

- **The universe turn gets real tools, in-turn.** `claude` supports
  `--strict-mcp-config` ("Only use MCP servers from `--mcp-config`, ignoring all
  other MCP configurations"). That makes "exactly our tools and nothing else"
  deterministically expressible for the first time — the reason the current
  policy is a rot-prone `mcp__*` wildcard deny.
- **A per-turn, universe-scoped MCP server** exposes the founder-owned actions
  that already exist on `write_graph`/`read_graph`: `agent`, `agent_binding`,
  `automation`, `connection`, `branch`, `goal`. No new primitives — the
  capability is already built and reachable by chatbot users today; the universe
  agent simply cannot call it.
- **Project-folder edits are daemon-implemented tools, not CLI filesystem
  tools.** `Read`/`Write`/`Edit` stay denied. Path confinement is enforced in
  Python, the way `_scoped_wiki_root` already does it, so an absolute path
  cannot escape the universe dir. This is why the OS sandbox is NOT a
  prerequisite for this change.
- **`commit_learning` and `extract_learning` are removed.** The agent writes its
  own soul files through the confined file tool, deliberately, and is told what
  it wrote.
- **The founder gate moves up: tier decides which TOOLS a turn is granted**, not
  what gets written after it. Today the sole gate is
  `if bound_tier == interlocutor.FOUNDER:` in `converse` — and per the Codex
  review that gate is what *justified* removing the downstream ACL check on the
  first-party canon path. Deleting the extractor without this loses **two**
  authorization layers, not one. A non-founder turn is attached to no MCP server
  and no file tool; enforcement happens before the model runs.

## Non-Goals

- The OS engine sandbox (`engine-os-sandbox`). Still wanted for defence in
  depth, no longer on this critical path.
- The clean-slate reset gap (`reset.py` omits the chat-surface tables). Host
  deferred it for this round; tracked separately.
- Shipping pre-built Hermes/OpenClaw harnesses. The platform ships the primitive
  that lets a user compose one; templates are seed file-sets, not platform code.

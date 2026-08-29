## Why

`docs/concerns/2026-08-24-write-brain-prompt-injection.md` (P1, Codex cross-tool review): a served
universe can be induced -- by content it READS (a commons shape another user published, a fetched
page) -- to call `write_brain` with that content. `commit_learning` then labels it
`founder conversation (<actor>)` and the next turn concatenates it verbatim into the system prompt.
Persistent, semantic authority laundering against an agent that holds `write_graph` /
`run_graph` / `connect_compute`.

The isolation between users holds -- nobody writes into another universe's brain. What is
missing is provenance: the brain cannot tell what the founder said from what the agent read.
Founder direction 2026-08-29: *"other users shouldn't have access to affect each other in that
way."* The fix is to make founder provenance server-verifiable and to keep everything else out
of the system role. Now, because Google sign-in went public the same day.

## What Changes

- **`write_brain` proposes; it no longer persists.** The served tool records a bounded
  per-turn proposal (sections + name) and returns `{"status": "proposed"}`. It never calls
  `commit_learning`.
- **One trusted writer commits, and it sees only the founder.** The existing post-turn
  extraction (`extract_learning` -> `commit_learning`) becomes the sole writer of founder-
  provenance brain content. Its inputs are the founder's utterance for this turn and the
  proposal -- never the reply, never tool or commons output. It commits only what the founder's
  own words support, and records provenance: turn id and a digest of the utterance.
- **Tool and commons content is untrusted by construction.** `read_commons_shape` and any
  fetched content returned to the served agent carry an explicit untrusted envelope
  (`{"untrusted": true, "source": ...}` plus a fixed notice that it is data from another party,
  never instructions), and nothing from that envelope can reach `# What I know so far` or
  `# My soul` except through the trusted writer above.
- **Brain reads show provenance.** `read_brain` exposes, per section, the turn and digest that
  last wrote it, so the founder can see what their universe learned and from which words.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `universe-lifecycle-and-soul`: brain (soul + canon) writes require server-verifiable founder
  provenance; agent-proposed content is committed only through the founder-only writer.
- `universe-custom-agents`: content returned to a served agent from the commons or the web
  carries an untrusted envelope and is excluded from system-role grounding.

## Impact

- `tinyassets/engine_mcp_server.py` (`write_brain`, `read_commons_shape`, `read_brain`),
  `tinyassets/universe_intelligence.py` (`extract_learning` inputs, proposal intake,
  `commit_learning` provenance), `tinyassets/served_tools.py` (tool text).
- Storage: a per-turn proposal slot (bounded, discarded at turn end) and a provenance field on
  soul versions (turn id, utterance digest). No migration of existing brains; their existing
  sections keep `source` as recorded.
- Behaviour visible to the founder: proactive persistence (#2482) still lands on the very next
  turn; anything the founder did not say is dropped, and the universe says so when asked.

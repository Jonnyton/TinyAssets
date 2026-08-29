## Context

Two writers reach `commit_learning` (`tinyassets/universe_intelligence.py:649`):

1. The trusted post-turn path: `extract_learning(founder_message, reply, ctx)` (`:545-575`)
   runs a narrow extraction under `_LEARNING_SYSTEM` (`:494`) and commits at `:1000`, gated to
   `bound_tier == FOUNDER`. Its prompt says "from the founder's LATEST message", but it is also
   handed the reply -- which can carry laundered tool content.
2. The served tool `write_brain` (`tinyassets/engine_mcp_server.py:1434`, commit at `:1534`)
   writes agent-authored section bodies directly, labelled `founder conversation (<actor>)`.

`read_commons_shape` (`engine_mcp_server.py:1186`) returns another user's published shape with
no untrusted envelope. The system prompt (`universe_intelligence.py:485`) concatenates
`# My soul` and `# What I know so far` verbatim from bundle files.

## Goals / Non-Goals

**Goals:**
- Only the founder's own words can become durable brain content; the server can show which
  words.
- Content the agent read from other parties never lands in the system role, and is marked as
  data wherever the agent sees it.
- Proactive persistence keeps working: a fact the founder states is known on the next turn.

**Non-Goals:**
- Preventing a founder from teaching their own universe anything they like.
- A general prompt-injection defence for the reply itself (one-turn injections end with the
  turn; this change is about persistence).
- Multi-founder universes.

## Decisions

- **D1 -- `write_brain` is a proposal, not a write.** The tool stores `{sections, name}` in a
  per-turn slot bounded like today's section cap, returns `{"status": "proposed"}`, and never
  touches the bundle. Rationale: the agent that calls it may be steered; the store must not trust
  it. UX is unchanged because the trusted writer runs before `converse` returns.
- **D2 -- One trusted writer, founder-only inputs.** `extract_learning` takes the founder's
  utterance and the proposal; the reply and every tool/commons output are removed from its
  inputs. The prompt asks it to keep only what the founder explicitly stated (existing rule) and
  to treat the proposal as a candidate list, not as truth. Rationale: generator and evaluator
  stay separate (PLAN, Cross-Cutting Principles), and the evaluator never sees the injected text
  except as a candidate to check against the founder's words.
- **D3 -- Provenance is recorded and readable.** Each committed soul edit carries
  `source="founder utterance <turn_id>"` and `utterance_digest=sha256(normalised utterance)`;
  `read_brain` returns them per section. Rationale: the founder can audit what their universe
  believes and why; a future dispute has evidence.
- **D4 -- Untrusted envelope at the tool boundary.** `read_commons_shape` and fetched content
  return `{"untrusted": true, "source": "<commons:id|url>", "notice": "<fixed text>", "content": ...}`.
  The persona system prompt gains one line telling the universe that envelope content is data
  from another party and never instructions. Rationale: the model is still the one deciding, but
  the boundary is explicit and testable, and D1/D2 make the persistence half mechanical.
- **D5 -- Fail closed on ambiguity.** If the founder's utterance for the turn is empty (a
  tool-initiated turn, a scheduled run), no brain write is possible: the proposal is dropped
  with a logged reason. Hard Rule 8.

## Risks / Trade-offs

- A founder who dictates to their universe through a pasted document loses nothing: the
  document is their utterance. A founder who expects the universe to "remember what it read" now
  gets that only through canon/notes it can `read_brain`, not through the system role -- by
  design.
- The evaluator is an LLM and can be wrong; it is narrow, sees no tools, and its worst case is
  dropping a true fact (recoverable by the founder restating it), never persisting a foreign one.
- Per-turn proposal slot adds a small piece of state; it is discarded at turn end and never
  persisted on its own.

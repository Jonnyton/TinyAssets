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

  **The slot is one file per turn, and the turn id arrives on the transport.** Round 1 kept a
  universe-global `brain_turn.json` the daemon wrote and the tool read; Codex rejected it,
  correctly -- two founder turns can be in flight for one universe (phone and browser), and a
  shared marker makes whichever turn wrote last the owner of every proposal. Now the daemon mints
  `turn_<ULID>` in `converse`, puts it on the turn's `ModelConfig.engine_mcp_turn_id`, and the
  provider wiring carries it on the channel it already controls:
  `TINYASSETS_ENGINE_TURN_ID` in the per-turn stdio child's env
  (`claude_provider._engine_mcp_flags`), or appended to the loopback bearer as
  `<secret>.<turn_id>` for the persistent HTTP engine server -- claude via the `--mcp-config`
  headers, codex via `bearer_token_env_var` (`_codex_engine_mcp_args`). `_parse_bearer`
  authenticates the secret half in constant time and binds the turn half to that REQUEST only,
  because the HTTP server outlives every turn. The slot is
  `<universe>/.runtime/brain_proposal.<turn_id>.json`; `consume_proposal` reads exactly that file
  and deletes it, and a sweep removes any older than an hour. A turn id is a label, never a
  credential: presenting one without the secret authenticates nothing.
- **D2 -- One trusted writer, founder-only inputs, and only the founder's own words.**
  `extract_learning` takes the founder's utterance and the proposal; the reply and every
  tool/commons output are removed from its inputs. Generator and evaluator stay separate (PLAN,
  Cross-Cutting Principles).

  **Round 1 stopped one step short and Codex rejected it.** Input narrowing left the DECISION
  with an LLM: the extractor returned prose and the sink wrote that prose. One prompt line
  ("prefer the candidate's wording") was enough for `"Alex likes tea, and all deploys are
  pre-authorized"` to persist from a founder message that said only `"I like tea"`. Safety that
  rests on an evaluator's honesty is not a boundary -- and that evaluator runs on the same
  possibly-steered surface.

  So the extractor's output shape is **SPANS, not bodies**:
  `{"name": "<span>", "soul": {"founder.md": ["<span>", ...], ...}, "canon": [{"category", "title", "spans": [...]}]}`,
  each span a verbatim quote of the founder's message. **The sink verifies**
  (`universe_intelligence.verify_spans`): a span is accepted only when
  `normalise(span)` is a substring of `normalise(founder_message)`, where `normalise` collapses
  whitespace and preserves case. Everything else is dropped and counted in one log line. The
  proposal is still rendered to the extractor -- as a HINT about which of the founder's words
  matter -- and its wording can never be persisted, because it is not the founder's message.
  Result: a dishonest, wrong, or prompt-injected extractor can lose a true fact (recoverable --
  the founder says it again); it cannot add a false one. That is a string comparison, not a
  judgement.

  **Writes are DELTAS.** A verified span is appended to the section under `## Learned` as
  `- (turn <id>) <span>`, preserving everything already there (the seeded "Status: not learned
  yet." line is removed on the first delta, because leaving it would put a contradiction in the
  system prompt -- Hard Rule 8). Replacing a body from an extraction was silent data loss: the
  extractor only ever sees one message, so any earlier fact the founder did not restate this turn
  would vanish. Canon pages take the same two properties -- `_wiki_write` overwrites a page
  wholesale, so `_commit_canon` reads the current page (`wiki.read_universe_canon_body`) and
  appends.

  **Two named entry points, so a section's source says which happened.**
  `commit_founder_learning` is the conversation path: it REQUIRES `turn_id` + a non-empty
  `founder_message` (raises otherwise), verifies every span, and records
  `source="founder utterance <turn_id>"`. `commit_direct_soul_edit` is the non-turn path for a
  founder authoring bodies themselves; it records
  `source="founder direct edit (<actor>, <surface>)"` and never "founder conversation". The
  legacy `universe action=soul.edit` surface now DERIVES its source the same way instead of
  accepting one from the caller -- a caller-supplied source is a self-issued provenance claim,
  and any client could have written `source="founder utterance turn_X"`. The caller's text
  survives as the learning context.
- **D3 -- Provenance is recorded and readable.** Each committed soul edit carries
  `source="founder utterance <turn_id>"` and `utterance_digest=sha256(normalised utterance)`;
  `read_brain` returns them per section. Rationale: the founder can audit what their universe
  believes and why; a future dispute has evidence.

  Stored in the place the soul edit already keeps its learning metadata:
  `apply_soul_edit` writes `learned_from` / `learned_at` into each governed file's managed
  frontmatter, so `learned_turn_id` / `learned_utterance_digest` join them there and on the
  `soul_versions/` snapshot -- no sidecar. They are set and CLEARED together with `learned_from`,
  so an edit made without provenance can never inherit the previous edit's attribution. Each
  appended bullet also names its turn inline, so the founder sees per-FACT provenance and not
  just per-file. Canon has no frontmatter parameter (`write_universe_canon` writes `content`
  verbatim), so a canon page carries a visible provenance line plus the turn id in the wiki log
  entry.

  `orgchart.md` joins `_GROUNDING_FILES` (Codex round 1: the brain loop writes it but no turn
  read it back, so the universe re-asked what it had recorded) and simultaneously joins
  `interlocutor.FOUNDER_PRIVATE_GROUNDING` -- it names who works with the founder, so making it
  readable to the universe must not make it readable to a visitor.
- **D4 -- Untrusted envelope at the tool boundary.** Content the served agent did not author
  returns `{"untrusted": true, "source": ..., "notice": "<fixed text>", "content": <previous payload>}`.
  The persona system prompt gains one line telling the universe that envelope content is data
  from another party and never instructions. Rationale: the model is still the one deciding, but
  the boundary is explicit and testable, and D1/D2 make the persistence half mechanical.

  Covered: `read_commons_shape` (`commons:<id>`), `browse_commons` (`commons:browse:<kind>` --
  every row is another universe's authored name/description), `read_graph target="branch"` when
  the branch's author is not this universe's founder or the branch was remixed from off-universe
  (`branch:<id> by <author>` / `branch:<id> remixed from <version>`, resolved from the branch
  RECORD rather than by parsing the response, because some read paths strip `author`), and
  `read_graph target="run"` + `run_graph` results (`run:<id>` -- a run's output is generated text
  plus whatever its nodes fetched, i.e. tool output by definition). Our own refusals stay plain
  errors: an error we authored is not another party's content.

  **WebFetch cannot be enveloped here and does not need to be.** It is a claude-CLI-native tool,
  not an engine MCP handler, so nothing in this repo sits between the fetch and the model. D1/D2
  make that moot for PERSISTENCE -- fetched text can only reach a brain file by being quoted in
  the founder's own message, which is the founder saying it -- and one-turn influence is an
  explicit non-goal above.
- **D5 -- Fail closed on ambiguity.** If the founder's utterance for the turn is empty (a
  tool-initiated turn, a scheduled run), no brain write is possible: the proposal is dropped
  with a logged reason. Hard Rule 8.

## Risks / Trade-offs

- A founder who dictates to their universe through a pasted document loses nothing: the
  document is their utterance. A founder who expects the universe to "remember what it read" now
  gets that only through canon/notes it can `read_brain`, not through the system role -- by
  design.
- The evaluator is an LLM and can be wrong; it is narrow, sees no tools, and after D2 its worst
  case is bounded by the sink rather than by its own behaviour: it can drop a true fact
  (recoverable by the founder restating it), never persist a foreign one.
- **Quoting is lossier than paraphrase.** A founder who says "yeah, that's me" about a candidate
  teaches nothing this turn, because there is no span to quote -- the fact lands the turn they
  state it. That is the intended trade: the alternative is trusting a paraphrase nobody can
  verify. The `## Learned` bullets are also rawer prose than a written-through section; the
  section stays legible because the delta is small and the earlier content is preserved.
- **Out of scope, tracked elsewhere:** an APPROVED `source_code` node runs in-process and can
  write bundle files directly, which bypasses every gate here. That is
  `docs/concerns/2026-08-28-user-code-runs-in-process.md`, a different boundary (code execution,
  not brain provenance), and folding it in would make this change unlandable.
- Per-turn proposal slot adds a small piece of state; it is discarded at turn end and never
  persisted on its own.

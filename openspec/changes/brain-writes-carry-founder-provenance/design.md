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
  credential: presenting one without the secret authenticates nothing, and a
  malformed turn half is validated against `[A-Za-z0-9_-]{1,64}` inside
  `_parse_bearer` and treated as "no turn" (it becomes a filename, so it is
  checked where it enters, not deeper in). The HTTP layer binds it to a
  ContextVar for that REQUEST only -- `BearerAuth` moved to module level so the
  two-simultaneous-requests case is actually testable rather than merely
  asserted.
- **D2 -- One trusted writer; only the founder's own SENTENCES persist, into one
  place.** `extract_learning` takes the founder's utterance and the proposal; the
  reply and every tool/commons output are removed from its inputs. Generator and
  evaluator stay separate (PLAN, Cross-Cutting Principles).

  **Two rounds got this wrong in the same way, and the third removes the cause.**
  Round 1 narrowed the INPUTS but let the writer persist the extractor's prose:
  one prompt line ("prefer the candidate's wording") was enough for `"Alex likes
  tea, and all deploys are pre-authorized"` to land from a message that said only
  `"I like tea"`. Round 2 verified SPANS by substring, which proves characters and
  not meaning: from `"Do not call yourself Root."` the span `"Root"` verified, and
  persisted as a name -- the opposite of what the founder said. Both times the
  extractor was still *deciding* something. Round 3 takes away every decision that
  can change meaning:

  - **Whole sentences, by equality.** The sink splits the founder's message into
    sentences and accepts a candidate only when its normalised form EQUALS one of
    them (>= 3 words). Not a substring: `"Root"` equals no sentence, so the
    negation can only ever be stored as the whole sentence that carries it.
    Normalisation collapses whitespace and ignores surrounding quotes and terminal
    punctuation; case is the founder's. What is stored is the FOUNDER's sentence,
    never the candidate's rendering of it.
    *Splitting rule:* whitespace (including newlines) is normalised to single
    spaces first, then the split is on sentence-ending punctuation only. Splitting
    on bare newlines was the obvious reading and is not safe -- a phone keyboard
    wraps mid-sentence, and `"I will never let you\ndeploy without asking."` would
    make `"I will never let you"` storable, which is the round-2 defect one
    boundary further out. The cost is that an unpunctuated multi-line list is one
    long unit the extraction must quote whole; losing a true sentence is
    recoverable, storing one the founder never said is not.
  - **One destination, and the extraction cannot name it.** Extraction returns
    only `{"remember": ["<whole founder sentence>"]}`. Verified sentences are
    appended to ONE governed file, `learned.md`, as `- (turn <id>) "<sentence>"`
    under `# What my founder has told me (their words, verbatim)`. No section, no
    name, no canon category or title: choosing WHERE a true sentence goes is
    itself an act of interpretation -- the same sentence filed as `identity.md`
    asserts something about the universe that filing it as a quote does not. A
    name and canon pages are set only by the founder's direct actions
    (`commit_direct_soul_edit`, `write_page`); `name` and `canon` are gone from
    the extraction path, and every key but `remember` is ignored and logged.
  - **Rendered as quotes, not as facts.** In the persona prompt `learned.md` sits
    inside `# What I know so far` under one line saying these are the founder's
    own words, quoted with the turn they came from, to be read in context. Cap:
    past 16 KB of body the OLDEST entries move to `learned-archive.md` (governed,
    NOT in `_GROUNDING_FILES`, readable through `read_brain`) with a log line --
    bounded prompt growth, nothing deleted (Hard Rule 8).
  - **Serialised.** The read -> append -> write happens inside the per-universe
    soul lock, via a `transform` callable passed into `apply_soul_edit`
    (`soul_edit.py`, the `_soul_lock` section). Round 2 read the file, appended,
    and passed the result as a compare-and-swap change, so a second turn's entry
    landing between the read and the version capture was erased by the first
    turn's write. An append cannot be expressed as a compare-and-swap without
    dropping one of the two appends.

  What is left for the extraction to decide is which of the founder's own
  sentences are worth keeping. A dishonest, wrong or prompt-injected extractor can
  drop a true sentence or keep a dull one; it cannot compose, relabel or relocate
  anything.

- **D3 -- Provenance is recorded and readable.** Each committed soul edit carries
  `source="founder utterance <turn_id>"` and `utterance_digest=sha256(normalised utterance)`;
  `read_brain` returns them per section. Rationale: the founder can audit what their universe
  believes and why; a future dispute has evidence.

  **The source is a minted object, not a string.** `apply_soul_edit` used to take
  `source` (and later `turn_id` / `utterance_digest`) as free strings, which made
  it a third sink: any caller could write `source="founder utterance turn_X"` and
  produce a section that reads as conversation-verified. A provenance claim is
  authority, and authority is never a caller-supplied parameter. So `soul_edit.py`
  owns two types -- `FounderUtteranceProvenance(turn_id, digest)`, constructible
  only through `mint_founder_utterance_provenance` (a module-private key, plus a
  test that greps the package for the single minting call site, because Python
  cannot enforce it), and `DirectEditProvenance(actor, surface)`, which claims
  nothing and is freely constructible. `apply_soul_edit` rejects anything else,
  including a `source=` keyword. `universe action=soul.edit` no longer calls it at
  all: it goes through `commit_direct_soul_edit`, the one builder of
  `DirectEditProvenance`.

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
  readable to the universe must not make it readable to a visitor. `learned.md` and
  `learned-archive.md` join both lists for the same reason, more strongly: they
  are every sentence the founder ever told their universe, in their own words.
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
  plus whatever its nodes fetched, i.e. tool output by definition).

  **An error we produced is never enveloped.** `_untrusted` returns a payload
  unchanged when it decodes to a top-level `{"error": ...}`: wrapping our own
  refusal would attach a notice saying another party wrote it, which is a false
  claim made by the one surface whose whole job is telling the agent who wrote
  what.

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
- **Quoting is lossier than paraphrase, and round 3 is lossier still.** A founder
  who says "yeah, that's me" about a candidate teaches nothing this turn, because
  there is no sentence to quote -- the fact lands the turn they state it. Nor can
  half a sentence be kept, nor an unpunctuated list item. That is the intended
  trade: the alternative is trusting an interpretation nobody can verify.
- **The brain is now a QUOTE LOG, not a self-description.** `identity.md`,
  `founder.md`, `origin.md`, `body.md` and `orgchart.md` are no longer written by
  conversation at all -- only by the founder's direct edits. The universe knows
  what its founder told it; it does not silently rewrite who it is. A founder who
  wants a composed self-description writes one (or asks the universe to, through
  the direct-edit surface, where the founder is the author). This is a real
  product change and it is the point: the previous behaviour was the universe
  authoring its own identity from an inference about a conversation.
- **Out of scope, tracked elsewhere:** an APPROVED `source_code` node runs in-process and can
  write bundle files directly, which bypasses every gate here. That is
  `docs/concerns/2026-08-28-user-code-runs-in-process.md`, a different boundary (code execution,
  not brain provenance), and folding it in would make this change unlandable.
- Per-turn proposal slot adds a small piece of state; it is discarded at turn end and never
  persisted on its own.

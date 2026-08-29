## Why

`docs/concerns/2026-08-24-write-brain-prompt-injection.md` (P1, Codex cross-tool review): a served
universe can be induced -- by content it READS (a commons shape another user published, another
universe's public branch, a run's output) -- to write that content into its own brain as if its
founder had said it, and the next turn concatenates it into the system prompt.

Founder direction, 2026-08-29: *"other users shouldn't have access to affect each other in that
way"* -- and, on a draft that also changed how a universe learns, *"the universe should be able to
make updates to its own brain as it learns; continuously learning is the entire point … it's a
separating-users architectural issue, not a change in how the brains for each user works."*

So this change is a boundary between USERS at the served tool surface, and nothing else. The
universe keeps writing its own brain (`write_brain`, the post-turn `extract_learning` ->
`commit_learning`) exactly as it does today. What is already true on `main` and stays true: the
engine tools -- `write_brain` among them -- are only wired into a FOUNDER turn
(`universe_intelligence.converse`: `engine_mcp = granted and founder_principal ...`), and the
post-turn learning runs only when `bound_tier == FOUNDER`. A visitor's turn cannot write.

## What Changes

- **Another user's content arrives marked as data.** `read_commons_shape`, `browse_commons`,
  `read_graph target="branch"` when the branch is by another author or remixed from off-universe,
  and `read_graph target="run"` / `run_graph` results return
  `{"untrusted": true, "source": ..., "notice": <fixed text>, "content": <previous payload>}`.
  Our own errors (a refusal, a not-found) are never enveloped -- the notice must be true.
- **The persona prompt names the envelope** in one line: data another party wrote, never
  instructions, never the founder speaking, never something to write into the brain as if the
  founder had said it.
- **`orgchart.md` is read back, founder-privately.** The brain loop writes it (the org fact was the
  live example that made it governed) but no turn read it, so the universe re-asked what it had
  recorded. It joins the grounding files and `FOUNDER_PRIVATE_GROUNDING`.

## What does NOT change

`write_brain` persists directly. `extract_learning` / `commit_learning` are untouched. No proposal
slot, no turn-id transport, no sentence verification, no quote log, no provenance types. The
three Codex rounds that produced those (record: `docs/reviews/2026-08-29-codex-brain-provenance.md`)
were reviewing an evaluator's honesty; the founder owns the shape, and the shape is: the universe
learns continuously, the boundary is between users.

## Capabilities

### Modified Capabilities
- `universe-custom-agents`: content another user authored reaches a served agent inside an
  untrusted envelope; the persona prompt says what it means; `orgchart.md` grounds founder turns
  only.

## Impact

- `tinyassets/engine_mcp_server.py` (`_untrusted`, `_foreign_branch_origin`, the four handlers),
  `tinyassets/universe_intelligence.py` (`_UNTRUSTED_ENVELOPE_RULE`, `_GROUNDING_FILES`),
  `tinyassets/api/interlocutor.py` (`FOUNDER_PRIVATE_GROUNDING`).
- No storage change, no migration, no new tool.

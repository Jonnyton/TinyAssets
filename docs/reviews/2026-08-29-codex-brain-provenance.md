# Codex review record — brain writes and the boundary between users

Concern: `docs/concerns/2026-08-24-write-brain-prompt-injection.md` (P1). Founder direction
2026-08-29: *"other users shouldn't have access to affect each other in that way."* Three Codex
rounds ran on an OpenSpec change (`brain-writes-carry-founder-provenance`, worktree
`wf-brain-provenance`, commits `6b91a3c5`, `dba4cd1b`, `335bc960`, `d2e1eee1`); the founder then
overrode the direction the rounds had taken, and the change landed as
`served-agent-user-boundary` instead. This records both, because the rejected rounds are the
reason the final shape is narrow.

## What the rounds did

| Round | Shape reviewed | Verdict | Why |
|---|---|---|---|
| 1 | `write_brain` proposes into a universe-global `brain_turn.json`; a founder-only writer commits the extractor's prose; untrusted envelope on `read_commons_shape`. | REJECT | Two founder turns can be in flight for one universe; a shared marker makes whichever wrote last own every proposal. The writer still wrote the extractor's PROSE, so one prompt line could launder a sentence. Also found: `orgchart.md` written by the brain loop but never read back; `read_graph target="branch"` a third foreign-content path. |
| 2 | Turn id on the transport (env for the stdio child, `<secret>.<turn>` bearer per request for the HTTP server); extractor returns verbatim SPANS verified by substring; envelope extended to `browse_commons`, foreign branches, run output. | REJECT | Substring proves characters, not meaning: from "Do not call yourself Root." the span "Root" verified and persisted as an identity. The extractor still chose the destination section. A read→CAS append could drop a concurrent turn's write. `universe action=soul.edit` accepted a caller-supplied `source`. |
| 3 | Whole-sentence equality only; one destination (`learned.md` quote log, 16 KB budget, archive overflow); append under the soul lock; minted provenance objects; identity/founder/origin/body/orgchart no longer written by conversation. | (stopped) | Founder, on seeing it: *"the universe should be able to make updates to its own brain as it learns — continuously learning is the entire point … largely you shouldn't be changing how that works, it was fine."* Then: *"it's a separating users architecturally issue, not a change in how the brains for each user works."* The round-3 dispatch was stopped before it returned. |

## What landed

`served-agent-user-boundary`: the untrusted envelope on the four foreign-content paths, one
persona-prompt line naming it, and `orgchart.md` read back founder-privately. `write_brain` and the
post-turn `extract_learning` → `commit_learning` are untouched. The per-turn separation between
users was already true on `main` (engine tools only on founder turns; learning only at founder
tier) and is now named in the design.

## Kept from the rounds without the rejected shape

- Codex round 1's finding on `orgchart.md` (written, never read) — fixed.
- Codex round 1's finding that `read_graph target="branch"` admits foreign public branches — enveloped.
- Codex round 2's finding that run output is tool output by definition — enveloped.
- Codex round 2's finding that our own errors must not be enveloped — honoured.

## Not landed, by the founder's decision

- Proposal slot / turn-id transport / sentence verification / quote log / provenance types
  (`wf-brain-provenance` up to `d2e1eee1`, kept in git). They made foreign-text persistence
  mechanically impossible by making the universe unable to author its own brain, which is the
  feature.
- Codex round 2's `universe action=soul.edit` caller-supplied `source` finding: the action is
  gated by `permissions.universe_access_allows(uid, write=True)`, so only a principal with write
  access to that universe can call it; the `source` string is a label on the founder's own edit.
  Recorded here rather than fixed.

## Lesson (memory: `universe-writes-its-own-brain-continuously`)

A review verdict about an evaluator's honesty is not a product decision. When a reviewer's fix
removes a capability the founder named as the point, stop and ask — do not run another round.

## Shape review of the narrow change (one round, 2026-08-29)

Codex on `served-agent-user-boundary` (`b0e9872e`): ADAPT on truthfulness only. (1) AGREE -- no
server-side consumer parses the four enveloped results. (2) `author == _ACTOR_ID` is the right
identity comparison, but an own-to-own remix was enveloped: fixed, the fork source's author is
resolved. (3) AGREE -- on `main` the engine tools and post-turn learning are founder-only; no
Slack, scheduled-run or custom-agent bypass. (4) The persona line is correctly qualified, but
`read_commons_shape` enveloped the founder's own shape and `browse_commons` their own rows:
fixed, own shapes come back bare and own rows sit beside the envelope under `own`. No further
round -- the founder's rule is "largely you shouldn't be changing how that works".

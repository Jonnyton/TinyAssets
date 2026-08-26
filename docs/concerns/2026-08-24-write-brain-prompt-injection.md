# P1 - `write_brain` persistent prompt-injection

**Filed:** 2026-08-24 | **Verified:** 2026-08-24 | **Re-verified:** 2026-08-25 | **Severity:** P1
**Found by:** Codex cross-tool review. **Pre-existing** - not introduced by #2509.

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

`write_brain` persistent prompt-injection (Codex cross-tool review; PRE-EXISTING, not from #2509).
A prompt-injectable served agent can `read_commons_shape`/WebFetch attacker-authored content -> be
induced to `write_brain` it -> `commit_learning` mislabels it "founder conversation" -> next turn
it's concatenated VERBATIM into the system prompt ("# What I know so far"), persistently steering an
agent holding `write_graph`/`run_graph`/`connect_compute` authority.

## Why it matters

Persistence is the whole problem. A one-turn injection ends with the turn; this one is written to
the brain and re-injected into the system role on every subsequent turn, against an agent that holds
build-and-run authority.

## The fix is a design call, not a removal

Do **not** simply remove `write_brain` - it is the founder's feature and the proactive-persistence
loop is proven live. Two properties are needed:

1. Brain writes need **server-verifiable founder provenance** - a one-use learning grant minted from
   the real founder utterance, not a label the agent supplies.
2. Tool/commons content is stored as **UNTRUSTED** and never lands verbatim in system-role grounding.

## Re-verification 2026-08-25

`write_brain` present in `tinyassets/engine_mcp_server.py`, `served_tools.py`, `universe_bundle.py`,
and `universe_intelligence.py`. Premise holds.

## Owner

Design: `openspec/changes/served-agent-build-run/design-hardening.md`

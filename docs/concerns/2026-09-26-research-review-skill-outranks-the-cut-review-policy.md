# The research-review skill still blocks implementation the cut says may proceed

**Filed:** 2026-09-26
**Severity:** P2
**Found by:** ChatGPT Astra review of PR #4025 (`output/astra-rulebook-cut-review.md`,
finding 5), dispatched via `peer-agents`.

## Source (verbatim)

> `.agents/skills/external-research-implications/SKILL.md:251` prohibits
> implementation beyond research/design stubs pending review; lines 261–264
> retain push, rollout, and acceptance-test blocks even after user approval.
> These contradict floor-only review dispatched after the PR opens.

## The conflict

PR #4025 narrowed cross-family review, on founder direction (2026-09-26), to
floor-class changes and receipt-gated paths: one round, dispatched in parallel
once the PR is open. The same PR deleted the `AGENTS.md` restatement of the
research-derived review gate, because `external-research-implications` owns it in
full — one authority per fact.

That skill still holds the stricter, pre-build, blocking shape: an unreviewed
research-derived concept may not be implemented past a stub, and push, rollout
and acceptance-test advancement stay blocked until the opposite-provider review
lands. So a research-derived change now reads one rule in `AGENTS.md` and a
stricter one in the skill.

`peer-agents/SKILL.md` was fixed in #4025 (it now points at the canonical scope
instead of restating it). This one was not, deliberately.

## Why it was not fixed in PR #4025

The skill's gate is an approved norm with its own rationale, not a restatement:
loosening it is a policy decision about research-derived work, not the
mechanical dedup that PR was doing. Rewriting it unilaterally inside a rulebook
cut would have changed behaviour nobody asked to change.

## Fix

Decide which shape survives for research-derived concepts, then make the skill
state only that:

- If review stays pre-build and blocking for research-derived work, say so in
  `AGENTS.md` § *Working Norms* as an explicit exception to floor-only.
- If it follows the new default, replace the skill's scope rules with a pointer to
  `docs/reference/quality-gates.md` and keep its dispatch mechanics.

Either way, run `powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1`.

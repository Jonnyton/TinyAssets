# Cross-family review — `claude/connect-any-llm` authority path

**Reviewer:** Codex (`gpt-5.6-sol`), dispatched via `scripts/peer_agent.py` on its
own subscription budget.
**Round:** 2 of 2. **Verdict: APPROVE.** **Reviewed head: `9503bf71`.**
**Date:** 2026-09-03.

Round 1 on the same lane returned **ADAPT** with five findings; this round was
scoped to the authority-path change made in response, which is what
`pr-scope-guard` requires an exact-head receipt for.

## Why an authority receipt was required

`pr-scope-guard` flagged two behavioural (AST-differing) changes on an authority
path:

- `tinyassets/provider_serving_binding.py`
- its mirror under `packaging/claude-plugin/.../runtime/tinyassets/`

The change adds `UnknownServingProvider(ValueError)` and
`ServingProviderNotOwned(PermissionError)`, retypes four `raise` sites inside
`_open_serving_context`, and classifies them in
`onboarding/serving.py::_ensure_founder_serving_locked` ahead of its broad
catches — where the documented `provider_not_yours` / `unknown_provider` reasons
had been unreachable dead code.

## What the reviewer verified

- **No refusal was weakened.** All four retyped raises retain their original
  `ValueError` / `PermissionError` behaviour for every existing caller — the
  reason the new types subclass the old ones.
- **No cross-universe existence oracle.** Distinguishing "not yours" from
  "unknown" is safe here: the differentiated path requires a current admin ACL on
  the universe, and `get_definition` is universe-scoped, so another universe's
  `definition_id` answers identically to a typo.
- **Ownership is genuinely enforced.** Removing the
  `grant.owner_user_id != owner_user_id or grant.universe_id != universe_id`
  comparison makes the rebuilt two-owner test fail, with the foreign provider
  reaching `status: serving`. Independently reproduces the author's own mutation
  measurement.
- **`_declared_path` introduces no cross-user bypass** — the outbound proxy still
  enforces the endpoint allowlist; the selector only chooses which allowlisted
  path is called.
- Targeted tests: 23 passed.

**Findings: none.**

## Recorded decisions, not omissions

Two items from round 1 were deliberately filed rather than built, and the
reviewer was told they do not block APPROVE:
`docs/concerns/2026-09-03-connect-any-llm-remaining-shapes.md` — the
`anthropic_messages` / `bearer` mismatch (needs a deposit-contract change), and
the two company names in the picker copy (needs the founder's wording).

## Head note

The review was performed against `9503bf71`. Committing this artifact advances
the branch head; that commit adds this file only and changes no code, so the
receipt head and the reviewed code are the same tree.

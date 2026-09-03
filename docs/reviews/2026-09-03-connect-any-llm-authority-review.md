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

## Head note — what the receipt's head means here

The authority review was performed against **`9503bf71`**. The receipt in the PR
body names a later head, because commits after the review advance it. Every such
commit is docs or tests only; the reviewed code is unchanged, which is checked
rather than asserted:

```
git diff 9503bf71 HEAD -- \
  tinyassets/provider_serving_binding.py \
  tinyassets/onboarding/serving.py \
  tinyassets/providers/api_key_http_provider.py \
  packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/provider_serving_binding.py
```

That diff is **empty** at the receipted head. Codex independently confirmed the
same thing in a third pass. Commits since the review:

- the review artifact itself (this file),
- `docs/concerns/README.md`: link the concern filed by this lane, which the
  index test requires at merge time,
- `tests/test_status_says_what_is_true.py`: lift `SERVICE_LABELS` alongside
  `serviceLabel` in its node extractor. This lane replaced a self-contained
  ternary with a module-level table, and a second extractor (in a file the local
  runs did not cover) threw `ReferenceError` before any assertion — caught by CI,
  not by me.

If a future commit touches an authority path, that diff stops being empty and
this receipt must not be reused: get a fresh review at the new head.

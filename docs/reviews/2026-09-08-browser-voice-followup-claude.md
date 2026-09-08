# Browser Voice follow-up — Claude review record

**Date:** 2026-09-08  
**Environment:** Windows worktree `codex/voice-barge-in-selector`, based on
production revision `4a1877f0044a974585ba0daaacf2d190256bf76e`  
**Candidate:** `46a95b75f2f6eb59345f25fedc60d3af321a7c89`

## Scope

The rendered production conversation preserved two founder complaints about the
browser/device speech path: it did not keep listening while it read the universe's
reply aloud, and it had no speaking-voice selector.

## Independent review rounds

Round 1 returned `VERDICT: ADAPT` but its saved output contained no finding,
citation, or review body. It is not treated as an approval or an actionable
review.

Round 2 returned `VERDICT: ADAPT` and surfaced two actionable defects plus three
material gaps:

- echo comparison was punctuation-sensitive;
- the non-wrapping composer could overflow below 520 px;
- echo arriving just after synthesis `onend` was not suppressed;
- the harness did not prove stale utterance callbacks and turn-serial isolation;
- an utterance recognized while the universe was thinking was silently dropped;
- rebuilding the selector on every state render was also noted as a minor issue.

The candidate was adapted to address every item: Unicode letter/number echo
normalization, a stacked narrow-screen grid row, a bounded trailing-echo window,
explicit stale `onend`/`onerror` race coverage, one held next utterance during
thinking, and voice-list fingerprinting.

Round 3 again returned `VERDICT: ADAPT`, but the saved output contained no finding,
citation, or review body. The project's three-round cap forbids a fourth review.
This record therefore does **not** claim independent approval.

## Verification after round 2 adaptations

- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py`
  — 125 passed on 2026-09-08.
- `python -m pytest -q tests/test_conversation_custody.py -k
  packaged_runtime_mirrors_exist_and_are_byte_identical` — passed.
- `python -m ruff check tests/test_onboarding_app.py` — passed.
- `git diff --check` — passed (line-ending notices only).
- `openspec validate realtime-voice-conversation --type spec --strict
  --no-interactive` — passed.

## Founder decision

On 2026-09-08 the founder asked what the blocker was and directed “proceed,”
explicitly accepting the recorded final-review gap. This resolves the concern;
merge and deployment may proceed subject to the executable quality gates.

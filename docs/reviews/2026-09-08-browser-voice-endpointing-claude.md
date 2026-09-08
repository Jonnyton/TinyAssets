# Browser voice endpointing follow-up — Claude review

**Date:** 2026-09-08  
**Scope:** the browser-speech follow-up that buffers finalized recognition fragments for a 900 ms grace period before one canonical `converse` turn.  
**Reviewer:** Claude (`scripts/peer_agent.py claude`, read-only, no sub-agents)  
**Author:** Codex

## Review history

1. **Round 1 — ADAPT.** Found a replacement character in the new status text, missing direct proof that stopping Voice clears a pending draft, and finalized fragments heard during thinking overwriting rather than joining.
2. **Adaptation.** Replaced the damaged punctuation with ASCII, joined distinct thinking-time fragments with consecutive-duplicate suppression, reset all draft/timer/segment state during teardown, and added tests for thinking-time aggregation plus a stale timer callback after stop.
3. **Round 2 — APPROVE.** Verified those adaptations. The reviewer also noted punctuation-varying duplicate fragments as a low-risk hardening opportunity.
4. **Hardening.** Added one Unicode alphanumeric recognition key for draft, pending, active-turn, and echo comparisons; tests repeat fragments with changed punctuation.
5. **Round 3 — APPROVE.** Final permitted review round returned no actionable finding.

## Verification

- `python -m pytest -q tests/test_onboarding_app.py` — 92 passed on Windows, 2026-09-08.
- `python -m ruff check tests/test_onboarding_app.py` — passed on Windows, 2026-09-08.
- `openspec validate realtime-voice-conversation --type spec --strict` — passed on Windows, 2026-09-08.
- `python scripts/invariants_run.py --pre-commit` — brand parity, cross-provider drift, runtime mirror parity, mojibake, skill validity, and context-budget gates passed on Windows, 2026-09-08.

## Limit

The automated browser-state harness proves aggregation, duplicate suppression, immediate barge-in, and teardown behavior. It does not substitute for an organic microphone retest of pause timing on the founder's browser/device.

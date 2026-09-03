# Conversation timestamps — cross-family review

**Reviewed:** 2026-09-03

**Environment:** Windows worktree `e878`, read-only Claude Code peer (Sonnet)

**Command:** `python scripts/peer_agent.py claude --model sonnet --out output/conversation-timestamps-peer-review.md --prompt-file output/conversation-timestamps-review-brief.md --timeout 900`

**Verdict:** `APPROVE`

The wrapper's final-output file was replaced by a later Claude session hook
message, so the review body was recovered from the same CLI session transcript
after the command exited successfully. The structured review itself is recorded
below; the unrelated hook message is omitted.

## Structured review

- **AGREE:** Timestamp units are consistent. Durable conversation history flows
  from stored epoch seconds to the renderer unchanged; client queue/inflight
  values are epoch milliseconds and are divided by 1,000 at the rendering
  boundary.
- **AGREE:** Missing or invalid timestamps are not fabricated. An unusable stored
  value reaches the renderer as `null` and displays `Date and time unavailable`
  without an HTML `time` element.
- **AGREE:** Visible and semantic representations are correctly separated. The
  viewer-local label uses `Intl.DateTimeFormat`, while `date.toISOString()`
  preserves the UTC instant. The executable Los Angeles/Tokyo test crosses a
  calendar boundary while retaining one ISO value.
- **AGREE:** Founder, universe, and system-notice messages now use one metadata
  renderer; no direct `msg--system` DOM construction bypass remains.
- **AGREE:** There is no public API or storage change. The existing `ts` field is
  consumed, and the canonical app plus its packaged runtime mirror remain the
  single renderer used by browser, desktop, and mobile shells.
- **AGREE:** A fresh universe reply has no server timestamp in its current
  payload, so client receipt time is the honest available event time.
- **DISAGREE_CONCERN:** Reload-generated saved-line notices initially displayed
  the queued item's old timestamp instead of the notice's appearance time.
- **DISAGREE_CONCERN:** An `Intl.DateTimeFormat` exception initially collapsed a
  known instant into the same unavailable state as missing legacy data.
- **DISAGREE_CONCERN:** The first test covered timezone/date conversion but not a
  daylight-saving transition.
- **DISAGREE_CONCERN (pre-existing):** Restored founder turns used role `you`,
  which had no founder bubble CSS, rather than the canonical `founder` role.

`VERDICT: APPROVE`

## Disposition

All four concerns were addressed in the same implementation lane without a
second review round: generated saved-line notices now use their appearance time;
a known instant falls back to viewer-local `Date.toString()` with GMT context if
`Intl` formatting fails; the deterministic test crosses the Los Angeles spring
daylight-saving boundary; and restored founder turns now use the canonical
`founder` role. Per the three-round review rule, an approved review with
non-blocking concerns does not trigger another review round.

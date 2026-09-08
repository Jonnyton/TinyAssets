# Request rail draft-preservation shape review

Independent Claude review, 2026-09-08, before implementation. Wrapper completed
exit 0 in 250 seconds, verdict ADAPT; no pre-build safety blocker. Full authored
verdict was read from reviewer session d11309a7-2499-4997-99cc-c5f36ca22140 because
the wrapper retained only the later stop-hook closing note. No subagents, edits
or test runs were made by the reviewer.

AGREE: the 15-second refresh rebuilds all controls and erases draft/checkbox/note
state. AGREE: keyed reconciliation should preserve unchanged cards and their
live controls, with no secret values copied to storage or a value cache.

Required adaptations:

1. Pending request rows have no revision; they are immutable until resolved.
   Do not add a storage field for this UI fix. Use content identity (reviewer
   suggests dedupe_key with a content fallback), including synthesized requests.
2. Resolve the current request from railCache at click time, not an old closure;
   a disappeared request must not dispatch a stale action.
3. Clear the host/cards on sign-out so preserved secret controls cannot survive
   into another session. Recheck session identity after an awaited refresh.
4. Reject out-of-order refresh responses so an older response cannot resurrect
   an answered request. Preserve in-flight disabled buttons on unchanged cards.

Minimum executable regressions: unchanged controls retain identity/values;
changed content discards them; removal and unrelated append/prepend preserve
other drafts; stale response rejected; sign-out clears controls; removed request
cannot dispatch; rendering never extracts values or persists them. Test the
failing baseline first. Avoid moving already-correct DOM nodes and losing focus.

This approves a direction with adaptations, not an implementation, deployed fix,
or live acceptance. Follow-up is retained in the request-rail concern.

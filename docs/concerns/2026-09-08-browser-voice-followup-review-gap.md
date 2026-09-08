# Browser Voice follow-up is fixed locally but lacks final review approval

**Filed:** 2026-09-08  
**Verified:** 2026-09-08, production `/mcp/app` rendered conversation plus local
candidate `46a95b75f2f6eb59345f25fedc60d3af321a7c89`  
**Severity:** P2

## Source (verbatim)

Rendered in the signed-in production conversation on 2026-09-05:

> you'd noticed some audio quirks, like me not listening while I'm replying and no voice selector yet.

The founder's 2026-09-08 direction was to inspect the webapp conversation because
the post-update Voice feedback was in those messages.

## Current state

Candidate `46a95b75` makes the browser/device speech path listen through thinking
and spoken playback, supports interruption without overlapping canonical turns,
guards immediate self-echo, and exposes a remembered device voice selector. The
focused suite is green (125 tests), mirror parity passes, and the as-built spec is
valid.

The opposite-family review reached the three-round cap. Round 2's concrete
findings were all fixed; rounds 1 and 3 returned `ADAPT` with no saved finding or
code citation. Under the review rule, that is not approval and no fourth round may
be opened. The candidate must remain unmerged unless the founder explicitly
accepts this recorded review gap. Full evidence is in
`docs/reviews/2026-09-08-browser-voice-followup-claude.md`.


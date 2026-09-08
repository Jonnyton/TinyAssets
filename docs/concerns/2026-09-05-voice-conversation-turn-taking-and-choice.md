# Voice conversation turn-taking and voice choice

**Filed:** 2026-09-05
**Verified:** Rendered production app conversation inspected 2026-09-05 03:40 UTC
and speaking-voice selector inspected read-only on 2026-09-08 after deploy
`3fa0b164a1d8`; no message, microphone, or account action was taken.
**Severity:** P2

## Source (verbatim)

Founder, 20:29 PDT: "I do see an issue though when I was rambling and mumbling it didn't it's kind of cut off my son"

App asked: "Were you saying it cut off your sentence while you were still talking?"

Founder: "yes exactly the one I was trying to point out what it was doing it did what I was talking about"

Founder, 20:30 PDT: "while you're thinking and while you're replying you can't pick up my discussion you don't listen all the time you only listen when it's my turn to talk"

Founder, 20:31 PDT: "I also have no way of changing which voice you're using"

## Evidence and limits

Founder explicitly confirmed hearing the app; multiple transcribed turns received
relevant replies. Ordinary post-fix conversation is now observed, resolving the
previous organic-use freshness watch. This does not prove clean voice usability.

The visible voice selector and listening-through-thinking/replies behavior shipped
in `3fa0b164a1d8`; the selector is confirmed in the rendered production app. The
endpointing follow-up now buffers finalized browser-recognition fragments for a
900 ms grace period, combines fragments heard while thinking, suppresses repeated
fragments even when only punctuation differs, and clears pending speech on stop.
The 92-test onboarding suite and three-round Claude review cover those state
transitions.

One evidence gap remains: no organic microphone retest has yet confirmed that the
900 ms pause grace feels correct on the founder's browser/device. Keep this concern
open only for that live usability proof; implementation inspection and automated
state tests are complete.

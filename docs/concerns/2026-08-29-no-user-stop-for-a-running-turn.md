# A served turn now runs until finished, and the user has no way to stop it

**Filed:** 2026-08-29
**Verified:** by construction -- #2674 raised the granted served turn's absolute cap to 3600s
(`_SERVED_ABSOLUTE_CAP_S`) so a progressing turn is never wall-clocked; no surface (app, phone,
connector) exposes a Stop for a running turn.
**Severity:** P2 -- the founder's rule (2026-08-29) is "a turn should continue till finished unless
interrupted by the user or should stop for some other reason". The first half is built; the
"interrupted by the user" half is not, and the 3600s backstop stands in for it.

## The claim

Before #2674 a served codex turn died at `communicate()`'s 300s; the founder saw it kill a healthy
five-step GitHub job and ruled that turns finish. Now the only things that end a turn are: the
provider finishing, the idle watchdog (no progress for 30s; 900s while a tool is in flight), the
provider failing, or the 3600s cap. A user watching a turn go somewhere they did not intend has no
control except waiting.

## What resolving it looks like

1. A Stop affordance on the app's composer while a turn is in flight, carried to the server as a
   cancel of that turn's subprocess (the reader already propagates `CancelledError` promptly --
   Codex round 3 on #2674 verified the cleanup path).
2. The cap becomes a user-set budget rather than a constant (`ideas/INBOX.md`, 2026-08-29); the
   per-universe `absolute_cap_s` knob already exists as the storage shape.

Delete this file when a live turn is stopped from the app and the subprocess is gone within a few
seconds, with the date, surface, and turn id.

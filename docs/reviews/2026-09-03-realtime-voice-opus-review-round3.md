# Realtime voice implementation review — Opus round 3

Date: 2026-09-03
Reviewer: Claude Opus via `scripts/peer_agent.py`
Reviewed head: `20cc50e0020154d981ef83ebd1cff21123f2de0c`
Verdict: **ADAPT**

This was the third and final review round permitted by `AGENTS.md`. The returned
receipt identified one remaining blocker: a superseded `_connect` attempt used
the global `_teardownTransport()` after its SDP exchange or from the reconnect
catch path. A newer attempt can install `this.pc`, `this.dc`, and `this.stream`
while the older outbound session exchange is still pending; when the older
attempt resumes, global teardown closes the newer transport. The reviewer
pointed to the earlier post-`getUserMedia` generation check as the correct
pattern: close only the attempt-local peer connection, data channel, audio
element, and stream.

The author accepted and repaired that blocker after this reviewed head. Each
connection attempt now disposes only its local resources on stale completion or
failure, while global teardown first detaches and then disposes only the current
transport. A deterministic two-attempt race test proves that the superseded
attempt closes its own resources without closing or replacing the newer live
attempt.

The raw reviewer message also stated that findings 7–12 were non-blocking and
should be taken to the founder, but it did not include the referenced numbered
findings 1–14 in the saved final response. Their content therefore cannot be
reconstructed or responsibly acted on. No fourth review will be opened.

## Raw final response

> Re-verified the blocker line by line. It is stronger than I stated, and one
> detail settles it: line 1312 handles the same stale case correctly — it stops
> only its local stream and returns without touching `this.*`. The author
> applied the right pattern there and not at 1342/1345, which is an oversight
> rather than a deliberate choice, and it tells you the fix shape. Also,
> `getUserMedia` at 1310 resolves in tens of milliseconds once permission is
> granted, so the replacement attempt installs `this.pc`/`this.dc`/`this.stream`
> well inside the stale attempt's `_session` window — a spawned-broker subprocess
> plus an outbound HTTPS round trip. The race window is wide, not narrow. And
> the guard at line 1303 does not save it: the new attempt's
> `setRemoteDescription` throws on a pc the stale attempt closed, and because
> the new generation is current, `fail()` fires correctly on a session that was
> destroyed underneath it.
>
> Corrected fix shape for finding 1: make 1342/1345 mirror 1312 — close the local
> `pc`/`dc`/`audio` and stop the local `stream`, never `this.*`; same for the
> `catch` at 1425.
>
> Verdict unchanged. Findings 1–14 as given above; finding 1 is the sole blocker,
> findings 7–12 are non-blocking and should go to the founder with this receipt
> rather than trigger a fourth round, per `AGENTS.md` "Three rounds, then
> escalate."

REVIEWED_HEAD: 20cc50e0020154d981ef83ebd1cff21123f2de0c
VERDICT: ADAPT

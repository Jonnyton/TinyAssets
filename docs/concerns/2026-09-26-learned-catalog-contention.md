---
severity: P2
title: A shared catalog read can degrade a model list under contention
filed: '2026-09-26'
summary: the 250 ms bound drops learned rows rather than stalling, measured 0.78 s read under an exclusive lock; best-effort write loss is fine, a silently shorter model list is not reported to the user
---

# Learned catalog contention remains synchronous and client-invisible

Nonblocking follow-up at `b655942b7579731962e75451a9618f99e04da000`.
2026-09-26 Windows/Python 3.14 exclusive-lock probes measured 0.779s reading and
0.807s writing through the public helper paths despite the 250ms SQLite setting.
Read returned empty contributions with an operator warning; write returned False
with a warning. Existing rows survived. A busy timeout is not a wall-clock budget.
Do not claim these Windows measurements establish Linux latency.

Optional learning can be retried; no required user data is lost. Consider moving
the best-effort write off the reply event loop and exposing read degradation in
the advisory result. These are not additional floor blockers.

Measured by Codex round 2 on PR #4028 with a direct `BEGIN EXCLUSIVE` probe on
Windows / Python 3.14: `_catalog_candidates` 0.779 s and `record_verified_model`
0.807 s. Both failures are logged; the read returned no contributions and the write
returned `False`. Existing rows survived. Best-effort WRITE loss is acceptable; a
silently shorter model LIST after a failed read is not currently reported to the
user, which is the open part.

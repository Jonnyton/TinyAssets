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

Full evidence: [round-2 review](../reviews/2026-09-26-learned-catalog-round-2.md).

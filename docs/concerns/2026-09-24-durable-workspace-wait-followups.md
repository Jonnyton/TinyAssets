# Durable workspace waiting: follow-ups from its Tier 1 review

**Filed:** 2026-09-24, from the PR #3950 review at head `d452d16d`. The verdict
was FLOOR_OK and the PR shipped.
**Severity:** P2. Each item is latent or needs two failures; none replays work
in today's single-daemon production.

1. **Exactly-once start is enforced in-process only.** The dispatch claim lives
   in process memory (`runs.py` ~475), and nomination never reads
   `dispatched_at`. The move from `queued` to `running` is unconditional for
   these runs, so two processes sharing one data directory could each start the
   same waiter and run its effects twice. Fix: make the transition conditional
   on `queued` (use `expected_statuses`), or check `dispatched_at` inside the
   claim.
2. **An unreadable waiter DB strands queued runs.** `_never_started_waiters`
   (~629) treats every queued row in the universe as waiting when the waiter DB
   is unreadable. A ticketless queued run whose worker was lost then stays
   `queued` forever instead of becoming `interrupted`. Nothing is replayed.
3. **A double failure wedges a universe's queue.** If a dispatch fails and the
   settle in its exception handler also fails, the head stays claimed and
   `queued`, and nomination stops at ~700 on every pass until restart.

Delete this file when all three are fixed or judged unnecessary after live use.

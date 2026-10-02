---
severity: P2
title: A timed-out agent call that borrowed a seat cannot lend it on after its parent lets go
filed: 2026-09-30
summary: Seat re-entry matches an exact depth; once a borrowing call's node times out and its parent releases, the borrower's remembered depth is stale, so a blocking call nested inside it waits for a new seat instead of re-entering.
---

# An orphaned seat borrower cannot lend on

**Found:** gpt-6-astra refute round 2 of the seats-per-account PR, 2026-09-30
(A, P2). **Area:** `tinyassets/universe_seats.py` `_reenter` / `release`,
`tinyassets/graph_compiler.py` `_run_agent_with_timeout`.

Re-entry is an exclusive depth transition: a nested call may borrow a seat only
when the seat's stored depth equals the depth its parent remembers. Release
decrements the stored depth whichever holder finishes first.

Interleaving: parent P holds depth 1; child C borrows (depth 2); C's node times
out while C's provider call keeps running; P unwinds and releases (depth 1). C
still remembers depth 2, so a blocking agent call D nested inside C cannot
borrow and waits for a fresh seat. If every other seat of the account is held by
work that is itself waiting on C, that wait does not end.

It needs a node timeout, an orphaned call that goes on to nest a blocking agent
call, and an account otherwise full of work blocked on it. Seats are still
released on every path and reclaimed on proven death; nothing is refused.

**Shape of the fix:** track the lender chain on the seat (who holds each depth)
rather than a bare counter, so a surviving borrower keeps a depth it can lend.

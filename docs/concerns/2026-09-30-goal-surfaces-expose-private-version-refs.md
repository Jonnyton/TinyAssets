---
severity: P2
title: Goal leaderboards and canonical history expose private branch version ids
filed: '2026-09-30'
summary: Goal reads, goal leaderboards and gate-event aggregations return branch version ids (and counts and dates) without checking that the caller can read each version's branch, so a private branch's version ids leak to anyone who can see the goal.
---

# Goal surfaces expose private branch version references

**Filed:** 2026-09-30
**Severity:** P2. Ids, counts and dates only. The content behind an id is gated since #4116 and
#4119 (version readers, `run_branch_version`, `set_canonical`).

## Source (verbatim, astra refute of #4119 at 281274ec, finding 4)

> **P2 — DISAGREE_EVIDENCE: goal surfaces expose private version identifiers and history.**
> Concrete sequence: Alice's private version is cited by a gate event under public goal `G`. Bob calls
> `goals(action="leaderboard", goal_id=G, metric="gate_events")`
> `market.py:1873` calls an aggregation without a viewer filter and returns version IDs, counts and
> dates. `gate_events/store.py:447` aggregates citations without checking branch visibility.
> Separately, public goal reads return the raw goal object (`market.py:1643`), including canonical
> bindings/history. Canonical assignment permits private versions, and replacement records previous
> version IDs (`daemon_server.py:3243`). Neither read projection filters those references.
> **Fix:** filter version references through branch readability before aggregation and serialization,
> including canonical history and fallback bindings.

## State

- The `goals` route in that sequence is no longer dispatchable; the fat tools were de-registered in
  #4119. Goal reads remain reachable through `read_graph target=goal` and through `browse_commons`.
- `set_canonical` now refuses an unreadable version (#4119). Canonical history recorded before that
  change can still hold one.
- Resolve by filtering every version reference in goal and leaderboard projections through
  `_resolve_readable_version`, with a cross-user test, then delete this file.

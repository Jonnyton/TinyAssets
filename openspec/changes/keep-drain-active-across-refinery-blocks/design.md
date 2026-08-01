## Context

`has_alternative_candidate()` filters the accepted blocker but then only treats
`OWNED`, `CLAIMABLE`, and `STALE` hints as alternatives. A refinery result can
therefore land a durable blocker while dozens of distinct `REFINERY` hints
remain, yet the controller waits the full idle interval. Runtime attempt 4 on
2026-07-31 reproduced this after PR #2053 with 47 refinable candidates.

## Goals / Non-Goals

**Goals:**

- Quarantine only the exact blocked target.
- Immediately loop to a distinct concrete refinery hint when present.
- Preserve sequential workers and all current-main/refinery safety checks.

**Non-Goals:**

- Parallel workers, a utilization floor, synthetic work, or product edits from
  a refinery assignment.
- Changing the normal idle behavior when every eligible candidate is filtered
  or absent.
- Changing watchdog/tray health categories.

## Decisions

The alternative predicate will accept all four dispatchable classifications:
`OWNED`, `CLAIMABLE`, `STALE`, and `REFINERY`. This reuses the already bounded,
fresh snapshot and the same recent-block and consumed-target filters used by the
next loop. It is preferable to special-casing the run loop because one predicate
then answers the exact question: whether the next loop can dispatch different
work without waiting.

The regression test will change the existing blocked-refinery expectation from
false to true when a distinct refinery hint remains and will retain a negative
case for the same target. This proves quarantine does not immediately retry the
blocked lane.

## Risks / Trade-offs

- A large blocked OpenSpec backlog can produce several coordination-only PRs in
  succession. The one-worker/one-PR contract, exact-current-main revalidation,
  recent-block suppression, and finite run budgets keep this bounded.
- A refinery hint can become stale after the post-block snapshot. The next loop
  fetches current main again and the worker must revalidate its exact assignment,
  so the hint does not become durable authority.

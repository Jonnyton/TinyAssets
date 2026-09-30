---
severity: P3
title: A failed publish can withdraw a concurrent publish of the same branch
filed: '2026-09-30'
summary: >-
  Two publish requests by one owner racing on the same branch: if the second succeeds while
  the first's bundle write is pending and the first then fails, the first's compensation
  un-marks the shared version and restores the branch's earlier private visibility.
---

# Concurrent publish rollback can withdraw a sibling publish

2026-09-30, gpt-6-astra refute round 3 on PR #4107 (publication-mark backfill),
DISAGREE_EVIDENCE, left open after the three-round cap.

`tinyassets/api/publish_requests.py:execute_action` records which minted versions
were unmarked (`newly_marked`) and each branch's prior raw visibility before its
commit point, and compensation reverses exactly those. Sequentially that is
correct (tested). Across two concurrent requests by the same owner it is not:

1. Request A sees version V unmarked and branch X private; A flips X public.
2. Request B publishes the identical snapshot and succeeds (V marked, X public).
3. A's bundle write fails: it un-marks V and restores X to private, withdrawing
   B's successful publication.

Same owner, own branch, fail-closed (less exposure, never more), and the window
is one bundle write. The fix is ownership of the change, not a snapshot of prior
state: e.g. a per-request publication token on the mark and the flip, reversed
only where the token still matches. The owner-withdrew-meanwhile case (X made
private while A is pending) is already handled: `_unflip` only restores while the
row still shows the flip.

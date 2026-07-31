# Design

Duplicate detection already occurs only after the worker emits a valid
`MERGED` result and the canonical PR identity is present in the run's
authoritative `merged_prs` receipts. The bug is the state transition after that
detection.

`apply_duplicate_merge_suppression` is a suppression transition:

1. keep `completed_slices` and `merged_prs` unchanged;
2. retain an audit `last_result` with `INVALID_DUPLICATE_MERGE`;
3. add the exact target to a bounded, run-lived
   `recent_consumed_targets` exclusion set;
4. clear `admission` and `resume_target`;
5. reset consecutive failure/transient counters; and
6. set a non-failure `duplicate-merge-suppressed` status.

The consumed-receipt exclusion is separate from `recent_blocked`: dependency
blockers are reconciled away when current main clears them and intentionally
allow an owned lane through, while a consumed target must remain excluded for
the entire bounded run across `OWNED`, `CLAIMABLE`, and `STALE`
classifications. The result remains visibly auditable while the supervisor
proceeds to fresh discovery. This transition applies only to a receipt already
proved and consumed by the same run. It cannot convert an unverified merge
into progress.

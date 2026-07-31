# Design

Duplicate detection already occurs only after the worker emits a valid
`MERGED` result and the canonical PR identity is present in the run's
authoritative `merged_prs` receipts. The bug is the state transition after that
detection.

`apply_invalid_duplicate_merge` will become a suppression transition:

1. keep `completed_slices` and `merged_prs` unchanged;
2. retain an audit `last_result` with `INVALID_DUPLICATE_MERGE`;
3. add the exact target to the bounded `recent_blocked` exclusion set;
4. clear `admission` and `resume_target`;
5. reset consecutive failure/transient counters; and
6. set a non-failure `duplicate-merge-suppressed` status.

Reusing the existing bounded exclusion set avoids a second candidate policy
owner. The result remains visibly auditable while the supervisor proceeds to
fresh discovery. This transition applies only to a receipt already proved and
consumed by the same run. It cannot convert an unverified merge into progress.

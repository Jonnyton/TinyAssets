# Workspace admission evidence — independent shape review

2026-09-08, local Windows working tree, before runtime implementation.
Command: `python scripts/peer_agent.py claude --out
output/workspace-admission-shape-review.md --prompt-file
output/workspace-admission-shape-brief.md --timeout 600`.
Completed successfully after 287 seconds. No tests, edits or delegation by peer.

The wrapper retained a closing-hook note; the actual review was read from the
completed session transcript `4dec7fab-3393-4ef8-8e54-6baf06d776f5` in this project's
Claude session directory. Verdict: **APPROVE**, no pre-live shape/basic-safety blockers.

The reviewer independently confirmed:

- Admission conflicts are discarded by the pool, absent from current receipts,
  and cannot be inferred reliably from user-visible run times or generations.
- Workspace evidence is preserved by effect dispatch, completion and failure
  persistence, and the ordinary get-run snapshot. Flattened error summaries do
  not carry it; `external_write_results` is the authoritative receipt home.
- Optional operation-local observations preserve policy and require no migration
  or new tool. No holder identifiers or lock-scope distinctions should be added.

Build precision notes accepted: retain observations on post-admission failure;
emit only when attempts >= 1; real lock tests must drive real admission, and
sleep timing assertions must distinguish injected clocks from actual elapsed time.
The design/spec wording was aligned accordingly before proceeding.

Reviewer also flagged the existing refusal detail's opaque holding-run ID.
The string is confirmed in `_acquire_lock`; cross-universe production reachability
is not established because workspace databases are universe-scoped. The conditional
finding and qualification are recorded in the existing workspace-admission concern.

This is design approval, not exact-head implementation approval, Linux evidence,
deployment proof, fairness proof or checklist acceptance.

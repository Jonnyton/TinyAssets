# Patch Request Incentives And Requester-Directed Daemons

Date: 2026-05-01
Status: accepted direction; v0 pickup-signal routing implemented 2026-05-02

## Summary

Patch requests may carry optional pickup incentives, and requesters may direct
their own daemons to work on a specific request. Both mechanisms accelerate who
looks at the work. Neither changes whether the patch is accepted, released, or
merged.

## Design Contract

- Incentives are daemon pickup signals only.
- Owner-directed daemon work is an iteration accelerator only.
- Acceptance remains controlled by tests, review, moderation, outcome gates,
  release gates, live observation, and rollback evidence.
- Paid or requester-directed work must keep a clear audit trail naming the
  requester, attached incentive terms, directed daemon, produced branch/run, and
  evidence handle.
- The system must not rank a patch as more correct, safer, or more mergeable
  because an incentive exists.
- If no daemon accepts the incentive, the request remains in the normal queue.
- If a requester daemon produces a proposal, it enters the same review and gate
  path as every other proposal.

## Interface Sketch

Future API surfaces should be additive fields/actions on existing request,
market, daemon, and work-target concepts rather than a new top-level tool.

```json
{
  "patch_request_id": "req_...",
  "pickup_incentive": {
    "enabled": true,
    "amount": "opaque",
    "terms": "paid on accepted claim / completed review packet / other gate",
    "visibility": "public"
  },
  "requester_directed_daemon": {
    "daemon_id": "daemon_...",
    "instruction": "work on this patch request",
    "scope": "proposal_only"
  },
  "authority_boundary": {
    "affects_pickup_priority": true,
    "affects_acceptance": false,
    "affects_release": false,
    "affects_merge": false
  }
}
```

Expected implementation homes:

- `tinyassets/api/market.py` for incentive/claim/bid semantics.
- `tinyassets/work_targets.py` for queue ordering and request assignment.
- `tinyassets/daemon_registry.py` for requester-directed daemon targeting.
- `tinyassets/api/runs.py` / `tinyassets/universe_server.py` only where run/attach
  evidence is needed after BUG-045/P1a.

## V0 Implementation Notes

Implemented v0 keeps incentives deliberately small:

- `universe action=submit_request` accepts `pickup_incentive`,
  `directed_daemon_id`, and `directed_daemon_instruction`.
- Non-host `priority_weight` is still clamped to `0.0`; incentives use a
  separate capped `pickup_signal_weight` so they can rank ahead of comparable
  user requests without crossing host/owner tiers.
- The branch-task queue exposes `pickup_signal_weight` and
  `directed_daemon_id`; dispatcher scoring caps pickup signal at `5.0`.
- Work-target materialization preserves incentive and directed-daemon metadata
  and ranks incentivized/directed request targets ahead of comparable plain
  request targets.
- Requester-directed daemon routing validates that the requester owns or is
  delegated to the daemon and records `scope=proposal_only`.
- Every stored/request response carries the authority boundary:
  pickup priority may change; acceptance, release, and merge may not.

## Evidence

- Public lab smoke `b2a2ca326a174898` completed on 2026-05-01 after storage
  recovery.
- Parent loop run `00e5e52661c240d2` completed on 2026-05-01 for this exact
  request. It selected child branch `e019229850f9`, returned
  `automation_claim_status=no_execution_claim`, `parent_loop_status=
  blocked_before_child_attach`, `release_gate_result=HOLD`, and preserved the
  BUG-045/P1a blocker behind #18.

## Implementation Tests

- `tests/test_patch_request_incentives.py` covers incentivized request pickup
  score, authority-boundary fields, target materialization/ranking, and
  requester-directed daemon ownership checks.
- Existing `tests/test_dispatcher_queue.py` still proves non-host
  `priority_weight` is clamped.
- Incentive/directed-daemon output still requires normal review/gate evidence;
  v0 only routes pickup and proposal work.

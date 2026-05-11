---
title: PR-103a Release Ship Validator Deterministic Canary Inputs
date: 2026-05-11
status: promoted
type: concept
sources:
  - docs/milestones/auto-ship-canary-v0.md
  - workflow/auto_ship.py
  - tests/test_auto_ship.py
---

# PR-103a Release Ship Validator Deterministic Canary Inputs

## Purpose

These packets are stable canary inputs for the release ship validator. They
give daemons, chatbot clients, and reviewers one packet that must pass and one
packet that must fail without relying on LLM judgment or live repo state.

In the current codebase, the deterministic validator is
`workflow.auto_ship.validate_ship_request`. The MCP-facing action is
`validate_ship_packet`, which accepts the same packet JSON as `body_json`.

## Should-Pass Packet

This packet stays inside the Auto-Ship Canary v0 safety envelope: docs-canary
ship class, allowlisted path, low risk, approved release gate, KEEP decision,
score at or above 9.0, stable evidence, and rollback instructions.

```json
{
  "request_id": "PR-103A-SHOULD-PASS",
  "parent_run_id": "run-pr-103a-parent-pass",
  "release_gate_result": "APPROVE_AUTO_SHIP",
  "ship_class": "docs_canary",
  "child_keep_reject_decision": "KEEP",
  "coding_packet": {
    "status": "KEEP_READY"
  },
  "child_score": 9.5,
  "risk_level": "low",
  "blocked_execution_record": {},
  "stable_evidence_handle": "outcome:pr-103a:pass",
  "automation_claim_status": "direct_packet_with_handle",
  "rollback_plan": "Close the PR before merge, or revert the committed docs canary change after merge.",
  "changed_paths": [
    "docs/autoship-canaries/pr-103a-deterministic-canary.md"
  ],
  "diff": "+# PR-103a Deterministic Canary\n+\n+Validator should accept this docs-canary packet.\n"
}
```

Expected validator result:

```json
{
  "ship_status": "skipped",
  "would_open_pr": true,
  "validation_result": "passed",
  "violations": [],
  "rollback_handle_prefix": "revert:",
  "dry_run": true
}
```

## Should-Fail Packet

This packet is intentionally unsafe: the release gate holds, the coding packet
is not keep-ready, the score is below threshold, the risk level is not low, an
execution block remains, and the changed path touches forbidden runtime API
surface outside the canary allowlist.

```json
{
  "request_id": "PR-103A-SHOULD-FAIL",
  "parent_run_id": "run-pr-103a-parent-fail",
  "release_gate_result": "HOLD",
  "ship_class": "docs_canary",
  "child_keep_reject_decision": "SEND_BACK",
  "coding_packet": {
    "status": "REVIEW_READY"
  },
  "child_score": 8.0,
  "risk_level": "medium",
  "blocked_execution_record": {
    "reason": "manual review still required"
  },
  "stable_evidence_handle": "outcome:pr-103a:fail",
  "automation_claim_status": "direct_packet_with_handle",
  "rollback_plan": "Do not ship; revise the packet and rerun validation.",
  "changed_paths": [
    "workflow/api/release_ship_validator.py"
  ],
  "diff": "+def unsafe_runtime_change():\n+    return True\n"
}
```

Expected validator result:

```json
{
  "ship_status": "skipped",
  "would_open_pr": false,
  "validation_result": "blocked",
  "rollback_handle": null,
  "dry_run": true
}
```

Expected blocking rule IDs include:

- `release_gate_not_approved`
- `coding_packet_status_not_allowed`
- `child_decision_not_keep`
- `child_score_below_threshold`
- `risk_level_not_low`
- `blocked_execution_record_nonempty`
- `changed_path_forbidden_prefix`
- `changed_path_not_allowed`

## Verification Command

For local deterministic verification, pass either JSON object to:

```bash
python - <<'PY'
from workflow.auto_ship import validate_ship_request

packet = {
    "release_gate_result": "APPROVE_AUTO_SHIP",
    "ship_class": "docs_canary",
    "child_keep_reject_decision": "KEEP",
    "coding_packet": {"status": "KEEP_READY"},
    "child_score": 9.5,
    "risk_level": "low",
    "blocked_execution_record": {},
    "stable_evidence_handle": "outcome:pr-103a:pass",
    "automation_claim_status": "direct_packet_with_handle",
    "rollback_plan": "Close the PR before merge, or revert after merge.",
    "changed_paths": ["docs/autoship-canaries/pr-103a-deterministic-canary.md"],
    "diff": "+# PR-103a Deterministic Canary\n",
}

print(validate_ship_request(packet))
PY
```

For chatbot/MCP verification, call `validate_ship_packet` with
`body_json` set to the serialized packet JSON. The action should return the
same validator decision shape.

## Related Workflow Concepts

- `docs/milestones/auto-ship-canary-v0.md` - Auto-ship safety envelope
- `workflow/auto_ship.py` - Deterministic validator implementation
- `tests/test_auto_ship.py` - Focused validator regression coverage

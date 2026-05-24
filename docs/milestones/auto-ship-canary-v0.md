# Milestone: Auto-Ship Canary v0

Status: proposal
Owner: Workflow community patch loop
Primary branch: `change_loop_v1` (`fd5c66b1d87d`)
Proposed variant: `change_loop_v1_auto_keep_canary`
Goal: land the first autonomously shipped patch through the community-driven patch loop, under a narrow, allowlisted, reversible canary envelope.

Roadmap extension: `docs/specs/2026-05-04-loop-autonomy-roadmap.md` records
the coherent autonomy ladder across PR creation, keyed auto-merge,
ship-class graduation, observation, rollback, and empty-queue self-seeking.

## 1. Purpose

The community patch loop can now ingest filed requests, run investigation/coding/release/observation stages, and persist receipts. What it cannot yet do is **ship a patch end-to-end without a human merging it**.

Empirical runs show the loop is intentionally conservative:

- many `change_loop_v1` runs complete successfully;
- completed runs commonly end with `release_gate_result=HOLD`;
- `coding_packet.status` often reaches `CHILD_REVIEW_READY`;
- release remains blocked because the packet is review-ready, not independently safe to ship;
- child invocation / attach semantics are still evolving under BUG-045 / BUG-049 / BUG-011.

The next milestone is not broad autonomous deployment. It is a deliberately constrained proof:

> A low-risk, allowlisted, reversible canary patch is generated, reviewed by gates, shipped by an automated lane, and observed for drift — without a human pushing the merge button.

The first successful outcome should be boring by design: a docs or canary metadata patch, not runtime code.

## 2. Milestone definition

The milestone is complete when the system can produce this evidence tuple without human pushing the merge:

```text
request_id
parent_loop_run_id
child_or_coding_run_id, if applicable
stable_evidence_handle
release_gate_result=APPROVE_AUTO_SHIP
shipper_run_id
pr_url or commit_sha
changed_paths
ci_status
ship_status=merged or landed
rollback_handle
observation_gate_result=OBSERVE
```

Minimum acceptable first patch:

```
docs/autoship-canaries/first-loop-autoship.md
```

or:

```
workflow/autoship_canaries/last_success.json
```

This is a real repo change but low-risk and mechanically reversible.

## 3. Non-goals

Auto-Ship Canary v0 does **not** authorize:

- runtime code changes;
- provider/router/auth changes;
- migrations;
- deploy workflow changes;
- secrets or configuration changes;
- arbitrary PR merges;
- auto-merging community code;
- bypassing CI;
- weakening `change_loop_v1`'s default HOLD posture;
- claiming parent-spawned child execution unless stable platform evidence proves it.

The canonical `change_loop_v1` should remain conservative. The auto-ship behavior belongs in a narrow variant or an additive opt-in gate.

## 4. Current blockers this milestone avoids

This milestone is designed to **avoid** depending on unresolved deeper primitives:

- BUG-011: durable lease / worker ownership / resume behavior;
- BUG-045: child branch invocation and typed output mapping;
- BUG-049: stalls at `invoke_autoresearch_lab` boundary;
- full deploy automation;
- broad auto-merge authority.

The first auto-ship canary may use a direct shipper packet produced from a completed parent loop run, even when child execution remains unreliable. This is intentional — the milestone proves the *shipper lane* works, not that every loop branch reaches it.

## 5. Architecture

Auto-Ship Canary v0 has three pieces:

```
1. Branch policy variant   → change_loop_v1_auto_keep_canary
2. Shipper adapter         → auto_ship_packet_v0
3. Evidence record         → auto_ship_evidence_v0
```

### 5.1 Branch policy variant

`change_loop_v1_auto_keep_canary` should fork or wrap `change_loop_v1`.

It preserves the existing stages:

```
intake_router
routing_policy_gate
attachment_receipt_gate
invoke_autoresearch_lab / await_autoresearch_lab / child_invocation_receipt_gate, when available
investigation_gate
coding_dispatch
review_release_gate
release_safety_gate
live_observation_gate
evolution_notes
```

But it adds a single new terminal release outcome:

```
APPROVE_AUTO_SHIP
```

This outcome is only allowed for canary-safe packets.

All other cases remain:

```
HOLD
SEND_BACK
OBSERVE
REJECT
ATTACH_REQUIRED
CHILD_REVIEW_READY
```

### 5.2 Shipper adapter

`auto_ship_packet_v0` is a small substrate adapter that takes an approved packet and performs a constrained repo operation.

Inputs:

```json
{
  "request_id": "FEAT-...",
  "parent_run_id": "...",
  "stable_evidence_handle": "outcome:...",
  "release_gate_result": "APPROVE_AUTO_SHIP",
  "ship_class": "docs_canary",
  "changed_paths": ["docs/autoship-canaries/first-loop-autoship.md"],
  "diff": "...",
  "rollback_plan": "...",
  "source_packet": {
    "coding_packet": "...",
    "release_plan": "...",
    "evidence_manifest": "..."
  }
}
```

Outputs:

```json
{
  "ship_status": "opened_pr | merged | failed | skipped",
  "pr_url": "...",
  "commit_sha": "...",
  "changed_paths": ["..."],
  "ci_status": "passed | failed | pending | skipped",
  "rollback_handle": "revert:<sha> or pr:<url>",
  "shipper_run_id": "...",
  "error": null
}
```

For v0, opening a PR is acceptable. Auto-merge may be enabled only for the narrowest canary path class after one successful PR-open round.

## 6. Auto-ship safety envelope

A packet may auto-ship only when **all** conditions pass.

### 6.1 Required packet fields

```
release_gate_result == APPROVE_AUTO_SHIP
coding_packet.status in [KEEP_READY, AUTO_SHIP_READY]
child_keep_reject_decision == KEEP
child_score >= 9.0
risk_level == low
blocked_execution_record == {}
stable_evidence_handle != ""
automation_claim_status in [child_attached_with_handle, parent_completed_with_handle, direct_packet_with_handle]
```

If child execution remains unavailable, the packet may use `direct_packet_with_handle`, but only for docs/canary-only patches and only with explicit `stable_evidence_handle` from the parent run.

### 6.2 Allowed ship classes

Initial allowlist:

```
docs_canary
metadata_canary
test_fixture_canary
```

Allowed paths:

```
docs/autoship-canaries/**
workflow/autoship_canaries/**
tests/fixtures/autoship_canaries/**
```

Forbidden paths:

```
workflow/runtime/**
workflow/providers/**
workflow/api/**
workflow/wiki/**
workflow/dispatcher/**
.github/**
scripts/deploy/**
migrations/**
*.env
*secret*
*auth*
```

The forbidden path check must run after resolving symlinks / normalized paths.

### 6.3 Required checks

Before shipping:

```
changed_paths subset allowed_paths
no forbidden paths touched
diff size below max threshold
no binary files
no secrets-looking content
release_gate_result == APPROVE_AUTO_SHIP
stable_evidence_handle present
rollback_plan present
```

For auto-merge:

```
CI passed
PR contains only allowlisted paths
PR title includes [autoship-canary]
shipper identity is expected bot/service identity
```

If any check fails:

```
ship_status=skipped
release_gate_result remains HOLD or SEND_BACK
manual_review_required=true
```

## 7. Release gate policy

The release gate should produce structured output, not just prose.

Suggested schema:

```json
{
  "decision": "APPROVE_AUTO_SHIP",
  "ship_class": "docs_canary",
  "risk_level": "low",
  "allowed_paths": ["docs/autoship-canaries/**"],
  "changed_paths": ["docs/autoship-canaries/first-loop-autoship.md"],
  "required_checks": [
    "path_allowlist",
    "diff_size_limit",
    "secret_scan",
    "rollback_plan_present",
    "ci_passed_before_merge"
  ],
  "rollback_plan": "Revert commit <sha> or close PR if not merged.",
  "manual_review_required": false,
  "reasons": [
    "Patch is canary-only.",
    "No runtime/provider/auth/deploy files touched.",
    "Stable evidence handle is present.",
    "Packet decision is KEEP with score >= 9.0."
  ]
}
```

If the packet is not safe:

```json
{
  "decision": "HOLD",
  "manual_review_required": true,
  "reasons": [
    "Patch touches non-allowlisted path.",
    "Child decision is REVIEW_READY, not KEEP.",
    "Stable evidence handle is missing."
  ]
}
```

## 8. Evidence record

Every ship attempt writes an evidence record.

Suggested table or JSON artifact:

```
auto_ship_attempts
```

Fields:

```
ship_attempt_id
request_id
parent_run_id
child_run_id
branch_def_id
release_gate_result
ship_class
ship_status
pr_url
commit_sha
changed_paths_json
ci_status
rollback_handle
stable_evidence_handle
created_at
updated_at
error_class
error_message
```

A wiki evidence page may also be written for human readability, but the source of truth should be structured.

Suggested committed artifact:

```
workflow/autoship_canaries/evidence/<YYYY-MM-DD>-<request_id>.json
```

Example:

```json
{
  "ship_attempt_id": "ship_20260502_001",
  "request_id": "FEAT-...",
  "parent_run_id": "...",
  "release_gate_result": "APPROVE_AUTO_SHIP",
  "ship_class": "docs_canary",
  "ship_status": "merged",
  "pr_url": "https://github.com/.../pull/...",
  "commit_sha": "...",
  "changed_paths": ["docs/autoship-canaries/first-loop-autoship.md"],
  "ci_status": "passed",
  "rollback_handle": "revert:<commit_sha>",
  "stable_evidence_handle": "outcome:...",
  "created_at": "2026-05-02T..."
}
```

## 9. First canary request

Use a request intentionally designed for low risk:

```
Feature request: First autonomous patch-loop canary ship

Create or update docs/autoship-canaries/first-loop-autoship.md with a short timestamped note proving the auto-ship lane is live.

Constraints:
- Only docs/autoship-canaries/** may be touched.
- No runtime/provider/auth/deploy code may be touched.
- The patch must include rollback instructions.
- The release gate must emit APPROVE_AUTO_SHIP only if all canary checks pass.
```

Expected patch content:

```markdown
# First Loop Auto-Ship Canary

This file is maintained by the Workflow community patch loop auto-ship canary lane.

Last successful canary:
- request_id: <id>
- parent_run_id: <run_id>
- ship_attempt_id: <ship_attempt_id>
- commit_sha: <commit_sha>
- timestamp: <timestamp>
```

## 10. Implementation phases

### Phase 0 — design only

Land this milestone doc.

### Phase 1 — shipper dry-run

Implement `auto_ship_packet_v0` in dry-run mode.

It validates packets and emits:

```
ship_status=skipped
dry_run=true
would_open_pr=true
```

No repo writes.

### Phase 2 — PR-open mode

Allow the shipper to open a PR for allowlisted canary paths.

No auto-merge yet.

Required evidence:

```
pr_url
changed_paths
validation_result
rollback_plan
```

### Phase 3 — auto-merge canary-only PRs

Auto-merge only if:

```
ship_class == docs_canary
changed_paths subset docs/autoship-canaries/**
CI passed
no human block label present
release_gate_result == APPROVE_AUTO_SHIP
```

### Phase 4 — observation gate

After merge, `live_observation_gate` records:

```
ship_status=merged
commit_sha exists
rollback_handle exists
changed_paths match allowlist
no forbidden files touched
```

Any mismatch triggers rollback recommendation or automatic revert PR.

## 11. Tests

### Release gate tests

```
test_release_gate_approves_docs_canary_keep_score_9
test_release_gate_holds_review_ready_packet
test_release_gate_holds_missing_stable_evidence_handle
test_release_gate_holds_non_allowlisted_path
test_release_gate_holds_runtime_path
test_release_gate_requires_rollback_plan
```

### Shipper tests

```
test_shipper_dry_run_validates_allowlisted_docs_patch
test_shipper_rejects_forbidden_path
test_shipper_rejects_secret_like_content
test_shipper_records_pr_url_on_opened_pr
test_shipper_records_commit_sha_on_merge
test_shipper_records_rollback_handle
```

### Evidence tests

```
test_auto_ship_attempt_persists_all_required_fields
test_get_run_or_status_surfaces_auto_ship_evidence
test_observation_gate_detects_changed_path_drift
```

## 12. Acceptance criteria

The milestone is accepted when a live run produces:

```
release_gate_result=APPROVE_AUTO_SHIP
ship_status=merged
changed_paths subset docs/autoship-canaries/**
commit_sha non-empty
rollback_handle non-empty
observation_gate_result=OBSERVE
```

And the merged commit touches only:

```
docs/autoship-canaries/**
```

Stretch acceptance:

```
The loop files a follow-up evidence note linking request_id, run_id, PR URL, commit SHA, and rollback handle in wiki + structured store.
```

## 13. Failure handling

If validation fails before PR creation:

```
ship_status=skipped
release_gate_result=HOLD
manual_review_required=true
```

If PR creation fails:

```
ship_status=failed
error_class/error_message recorded
release remains HOLD
```

If CI fails:

```
ship_status=failed_ci
auto_merge=false
manual_review_required=true
```

If merge succeeds but observation detects drift:

```
observation_gate_result=ROLLBACK_RECOMMENDED
rollback_handle used to open revert PR
```

## 14. Security and safety notes

The shipper must never trust prose alone.
It must parse structured fields from the release packet and enforce hard-coded allowlists.

Required hard checks:

```
path normalization
allowlist enforcement
forbidden path enforcement
secret-pattern scan
diff size cap
binary file rejection
rollback plan required
CI status required before merge
```

The release gate may recommend auto-ship, but the shipper is the final enforcement layer.

## 15. Open design questions

- Should `auto_ship_packet_v0` live under Workflow runtime, scripts, or GitHub Actions?
- Should the first version open PRs only, with auto-merge delayed?
- Should auto-ship evidence live in sqlite, committed JSON, wiki, or all three?
- Should `change_loop_v1_auto_keep_canary` be a forked branch or a release-gate mode on the existing branch?
- Should `APPROVE_AUTO_SHIP` require child decision `KEEP`, or may direct parent packets approve docs-only canaries?

Recommended answers for v0:

```
1. GitHub Actions or small repo-side shipper script.
2. Open PR first; auto-merge only after one successful dry-run/PR-open cycle.
3. Structured sqlite or JSON first; wiki summary optional.
4. Forked branch variant, not canonical loop mutation.
5. Prefer KEEP, but allow direct parent approval only for docs_canary and only with explicit stable evidence handle.
```

## 16. Recommended next implementation PRs

### PR A — Auto-ship milestone doc

Add this document.

### PR B — Release gate schema

Add `APPROVE_AUTO_SHIP` as a possible structured release-gate decision, but do not activate shipping.

### PR C — Dry-run shipper

Implement `auto_ship_packet_v0` dry-run validation and evidence output.

### PR D — PR-open shipper

Allow docs-only canary PR creation.

### PR E — Auto-merge docs canary

Enable auto-merge for `docs/autoship-canaries/**` only after CI passes.

## 17. Summary

The first autonomous patch should be intentionally small:

```
A docs-only canary patch, approved by a special auto-keep release gate, enforced by a path-allowlist shipper, observed by a drift gate, with a one-revert rollback handle.
```

This proves the loop can ship without weakening the safety posture of the canonical loop.

---

## Source

This milestone doc was authored by the dev-partner chat (ChatGPT gpt-5) with the
Workflow MCP connector installed, on 2026-05-02. The Cowork session captured
the chat and wrote the doc verbatim. Conversation: https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475

The dev-partner chatbot was invoked as a senior engineering peer to spec the
first auto-ship canary milestone, after the BUG-009 production sequence
(PR #196 dispatcher pickup, PR #201 `request_text` input normalization, and
PR #205 worker claim-grace) made wiki-filed `bug_investigation` requests
reliably become durable runs. That made the next blocker visible: completed
runs still stop short of autonomous release, commonly at
`release_gate_result=HOLD`. The auto-ship canary lane closes that loop.

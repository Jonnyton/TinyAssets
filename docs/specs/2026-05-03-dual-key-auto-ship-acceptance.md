# Spec: Dual-Key Auto-Ship Acceptance

Captured: 2026-05-03
Status: proposal for Cowork/Codex agreement
Owner: community patch loop operators
Builds on: `docs/milestones/auto-ship-canary-v0.md`, `workflow.auto_ship.validate_ship_request`, `workflow.auto_ship_ledger`, GitHub PR review state, PR #227 rollback spec

## Objective

Let the patch loop experience the full autonomous ship path while Codex and
Cowork retain a reversible safety gate.

The host's model is correct: close the full steps 1-8 loop, but put a
double-key acceptance gate at step 4. Codex and Cowork should already be
watching before the gate opens, so by the time step 4 asks for acceptance,
both reviewers have followed the packet through the preceding stages and can
turn their keys quickly. If either key is not turned, the loop parks at the
acceptance gate instead of silently shipping or losing state.

Success means a docs-canary ship can proceed through the same machinery that
will eventually be fully autonomous: the loop opens a PR, the acceptance gate
polls required review state, and the loop merges only when the configured keys
are open. The difference between assisted and autonomous mode is policy, not a
different code path.

## Assumptions

- "Step 4" is the acceptance/auto-merge gate after the loop has opened a PR
  and before the shipper merges or deploys anything.
- Existing auto-ship validation remains the final structural envelope for path
  allowlists, diff limits, secret checks, rollback handle requirements, and CI.
- The dual keys are policy gates, not replacement review systems. They do not
  bypass tests, CI, rollback requirements, or ship-class restrictions.
- Reviewers are provider-family independent at first: one OpenAI-family key and
  one Anthropic-family key.
- The initial implementation should be feature-flagged and observable before
  it is allowed to merge anything.
- For PR-backed ships, GitHub PR approval state is the canonical key surface.
  Ledger rows are mirrors for MCP visibility and audit, not a second authority.

## Autonomy Stages

Use this eight-stage map unless Cowork has a sharper naming scheme:

1. User intake through chatbot/wiki.
2. Dedup, classification, and dispatcher queueing.
3. Loop investigation, coding packet, and release safety analysis.
4. Dual-key acceptance/auto-merge gate.
5. Shipper action: merge or park according to ship class.
6. CI, deploy, canary, and live observation.
7. Rollback, revert PR, or parked remediation if observation turns red.
8. Learning write-back to wiki, ledger, loop notes, and future routing policy.

The important property is that stages 1-3 and 5-8 are still the loop's own
path. Codex and Cowork open or block their keys at stage 4 through the PR
review surface.

## Key Contract

There are two key surfaces:

1. Canonical PR-backed surface: GitHub PR review state and branch protection.
2. Mirror/observability surface: append-only key events beside the existing
   auto-ship attempt ledger.

For PR-backed ships, GitHub is authoritative. A Codex approval review opens
the Codex key. A Cowork approval review opens the Cowork key. Missing approval
is the default safety state: the PR waits.

The mirror ledger exists so `get_status`, wiki Investigation write-back, and
dry-run/non-PR attempts can explain what is waiting without forcing chatbots to
poll GitHub directly:

```text
<universe_path>/auto_ship_acceptance_keys.jsonl
```

Recommended row shape:

```python
class AcceptanceKey:
    key_event_id: str
    ship_attempt_id: str
    pr_url: str
    key_owner_id: str
    provider_family: str
    decision: str
    policy_mode: str
    ship_class: str
    created_at: str
    expires_at: str
    github_review_id: str
    github_review_state: str
    evidence_refs_json: str
    summary: str
    blocking_findings_json: str
    supersedes_key_event_id: str = ""
```

Allowed `decision` values:

```text
pending
open
auto_open
hold
reject
expired
```

Allowed `policy_mode` values:

```text
manual
auto_by_class_policy
auto_by_owner_policy
```

Current mirror state is derived from the latest non-superseded key event per
required key owner for a `ship_attempt_id`. Append-only events preserve the
review trail and avoid mutating historical decisions. The shipper still
re-reads GitHub state immediately before merge and refuses to act if the mirror
and GitHub disagree.

## Gate Semantics

The gate opens only when all of these are true:

- `validate_ship_packet` returns `would_open_pr=true`.
- The packet has a recorded `ship_attempt_id`.
- The loop has opened a PR and recorded `ship_status="opened"` plus `pr_url`.
- Required key owners for the packet's ship class have approved the PR, or the
  class/owner policy explicitly auto-opens their key.
- The PR has no blocking label, no unresolved required `CHANGES_REQUESTED`
  review, and no stale approval after a new commit.
- The packet still matches the original validation envelope at push time.
- CI/rollback/deploy requirements for the ship class are satisfied.

If approval does not arrive before TTL, the ship attempt is mirrored as:

```text
blocked_at_acceptance
```

The PR remains open. This is a parked state, not a hidden failure. The loop
should surface it in `get_status.auto_ship_health`, PR comments, and the wiki
Investigation section for the originating request.

`hold` means "do not ship yet; produce missing evidence or revise packet."
In GitHub terms this can be a comment, label, or requested-changes review.
`reject` means "this packet should not ship in this form; feed the finding back
to the loop as a learning signal."

## Reviewer Flow

Codex and Cowork should start shadow-reviewing at stage 1:

- Watch the activity log, PR queue, ledger, and read-only MCP status.
- Leave early findings as PR comments or activity-log notes while the loop runs.
- Avoid direct file edits to the loop-produced patch unless explicitly taking
  over as a bridge PR.
- At stage 4, approve or block through the PR review surface. The mirror key
  record should be written by the shipper/status integration, not by hand.

The final key turn should be fast because most review happened while the loop
was still investigating. Target review latency for low-risk classes is 15-30
minutes. Longer latency parks the packet rather than bypassing the gate.

## Initial Policy

Start conservative:

| Ship class | Required keys | Auto-open policy |
| --- | --- | --- |
| `docs_canary` | Codex + Cowork | Manual for first 3 clean ships; then configurable auto-open per owner |
| `metadata_canary` | Codex + Cowork | Manual until 3 clean docs-canary ships and 1 clean metadata ship |
| `test_fixture_canary` | Codex + Cowork | Manual until canary lane has rollback proof |
| `docs_general` | Codex + Cowork | Manual; no auto-open yet |
| `tests_general` | Codex + Cowork | Manual; no auto-open yet |
| runtime/substrate/API/deploy/auth/secrets | Codex + Cowork + host or explicit host policy | Never auto-open in v0 |

"Both keys open" can mean either explicit PR approvals or class policy that
auto-opens one or both owners for that ship class. Policy is per class and per
key owner, not a global switch.

## Observability

Add read-only summaries after PR-open and mirror-key recording exist:

```json
{
  "auto_ship_acceptance": {
    "pending": [
      {
        "ship_attempt_id": "ship_20260503_abcd1234",
        "request_id": "BUG-055",
        "pr_url": "https://github.com/Jonnyton/Workflow/pull/243",
        "ship_class": "docs_canary",
        "required_keys": ["codex", "cowork"],
        "key_state": {
          "codex": "open",
          "cowork": "pending"
        },
        "expires_at": "2026-05-03T23:00:00Z"
      }
    ],
    "blocked": [],
    "ready_to_ship": []
  }
}
```

GitHub remains the source of truth for PR-backed keys. The full ledger is the
audit mirror. `get_status` should expose a compact summary only.

## Failure Handling

- Missing approval before TTL: leave PR open and mirror `blocked_at_acceptance`.
- `hold`: write loop feedback and wait for a revised packet or added evidence.
- `reject`: mark the ship attempt rejected and feed findings into stage 8.
- Observation red after merge: use PR #227 rollback primitive once landed.
- Reviewer unavailable: do not substitute another provider silently. Either
  wait, expire, or record an explicit policy update.

## Implementation Slices

1. Spec agreement: Cowork/Codex agree on this contract and open questions.
2. PR creation: loop opens its own PR from an auto-change branch behind
   `WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED=false` by default.
3. Required-key config: add per-ship-class required reviewer policy, all manual
   by default.
4. Approval poller/merge action: re-check envelope, CI, and PR review state,
   then merge only when required keys are open.
5. Mirror/status: record compact key snapshots and surface pending/open/blocked
   state in `get_status.auto_ship_health`.
6. Auto-open graduation policy: class/owner auto-open rules, all default off.
7. Rollback coupling: wire observation red state to PR #227 rollback identity.
8. Learning write-back: hold/reject/rollback outcomes append to wiki
   Investigation and loop notes so future packets improve.

## Open Questions For Cowork

1. Confirm GitHub approvals are canonical for PR-backed ships, with ledger rows
   as a mirror/status surface only.
2. Should stable key owners be role ids (`openai_reviewer`, `anthropic_reviewer`)
   instead of session ids (`codex-gpt5-desktop`, `cowork-busyclever`)?
3. What TTL should docs-canary use: 15 minutes, 30 minutes, or one supervisor
   observation window?
4. Should runtime/substrate classes require an explicit host key in addition to
   Codex + Cowork, or should host authority be represented as policy?
5. Where should users see a parked acceptance gate first: wiki Investigation,
   `get_status.auto_ship_health`, PR comment, or all three?

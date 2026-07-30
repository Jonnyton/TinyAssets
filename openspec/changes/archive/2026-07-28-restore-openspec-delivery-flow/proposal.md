## Why

TinyAssets is creating and claiming OpenSpec work faster than it can verify,
archive, and deliver it: 34 active changes currently hold 834 unchecked tasks,
while broad multi-day goals keep provider sessions alive without a terminal
delivery boundary. The coordination runtime needs a measured pull system so
OpenSpec returns to its intended role as one focused behavioral delta per
branch and PR.

## What Changes

- Add a read-only OpenSpec flow inspector that joins change/task state with
  STATUS ownership and recent admission/archive history.
- Classify complete-but-unarchived, in-flight, queued, untracked, and oversized
  changes and recommend finish-first candidates.
- Add an enforcement mode for newly introduced changes: one intent, one owner,
  at most 12 task checkboxes, and no full-vision bulk-conversion umbrella.
- Add cross-provider rules that each exact session-specific provider identity
  owns at most one active delivery change, while global WIP is always visible
  and suffix-renaming to evade the limit is a review violation.
- Run inspection at dispatch/triage and admission checking after a change is
  scaffolded but before it is claimed or built; do not add another mandatory
  session-start gate.
- Treat the 12-task ceiling as a 2026-07-28 calibration to review on
  2026-08-11 against observed cycle time and model capability.
- Preserve existing oversized changes as diagnostic legacy state; do not
  mechanically split them or mutate/archive any change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: add measured OpenSpec flow inspection,
  bounded new-change admission, and finish-first delivery selection.

## Impact

- New diagnostic script and focused tests.
- `openspec/config.yaml`, `AGENTS.md`, and the cross-provider OpenSpec skill
  gain the same admission and delivery rules.
- No product runtime, MCP surface, stored user data, deployment, or existing
  active change is mutated by the inspector.

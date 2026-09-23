## Context

The served adapter rejects configuration already editable through canonical `patch_branch` staging. This is not a missing primitive. Existing ownership/record ACL checks precede the staged copy and persistence. Runtime admission, resource limits, consent and sandboxing remain independent.

## Goals / Non-Goals

**Goals:** Same-identity in-place editing of ordinary metadata and execution settings, one canonical validator, atomic refusal, actionable descriptions and tests of actual persisted readback.

**Non-Goals:** Editing private workflows as operators; changing tools/grants/ownership or publication; enabling invocation/handoffs; new MCP handles; new storage or runtime dispatch paths; changing existing admitted snapshots; any desktop dependency.

## Decisions

1. Retain the positive served allowlist. Add `description`, `phase`, `model_hint`, `reasoning_effort`, `input_keys`, `output_keys`, `timeout_seconds`, `retry_policy`, `enabled` alongside existing content/policy/effect/workspace fields. These configure an owned definition, not authority. Do not blindly derive this set from all storage fields. Keep `tools_allowed`, all invocation specs, approval/provenance, author, record ACL, visibility, credentials and host paths refused. Expose the accepted field list in refusal guidance rather than maintain a second prose list.
2. Reuse `_apply_node_updates` and final branch validation. Preserve served string validation for text that otherwise reaches storage; add description and phase there. Canonical finite/range checks must reject malformed timeout/retry values before persistence, if existing checks do not already do so. Avoid a second numeric grammar in the adapter. Reviewer must assess enabled/retry semantics before implementation: omit no field silently and do not expand resource authority.
3. Preserve staged-batch atomicity and existing source-review invalidation. A configuration change is not an execution and cannot mint consent. Omitted settings remain unchanged. Subsequent runs use the edited definition; existing admitted run snapshots remain unchanged.
4. Acceptance tests use the real served adapter, real canonical patch and temporary store, not only mocks that capture forwarded JSON. Cover every admitted field, unknown/authority fields, malformed multi-op batches, foreign ownership, output rename with matching schema, timeout reduction with workspace binding, and frozen-run identity where applicable. Prove new output/timeout tests red at the base before green.

## Risks / Trade-offs

- Runtime retry/timeout interpretation may be permissive -> inspect actual consumers and bound malformed settings canonically before exposing; retain independent run budgets.
- Declared IO names can change data flow -> ownership stays mandatory, compiler validates state/schema, no cross-universe reads or execution grants are added.
- A future canonical field could be unsafe -> explicit positive allowlist requires deliberate review; parity tests enumerate the accepted/refused contract.
- Existing tests call ordinary IO fields authority -> update that classification while retaining genuine authority-denial assertions.

## Migration Plan

No migration. One reviewed runtime patch, generated plugin mirror, normal required CI and cloud deploy. Verify authenticated public handles and deployed SHA, then send exactly `Retest your workflow checklist` in the existing app. Read the agent's own output/timeout edit readback and run evidence; do not operate its workflow directly. Sync and archive only on actual acceptance. Rollback the runtime release if the adapter regresses; stored valid definitions remain ordinary canonical definitions.

## Open Questions

Bounded pre-build Claude review: are all nine proposed ordinary fields safe under current validation/runtime, particularly retry/timeout/enabled? Identify concrete blockers, not speculative hardening. The final field matrix and tests must resolve that question before widening.

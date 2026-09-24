## Why

Immutable branch snapshots currently omit the user's branch-level model policy and concurrency budget. Reconstructing a pinned version loses those choices, and publishing an edit to only those choices can return the old version.

## What Changes

- Include existing non-null default_llm_policy and concurrency_budget in new immutable snapshots and content identity.
- Preserve all existing stored rows and unset-field hashes. No backfill of lost historical choices from mutable definitions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: immutable snapshots retain execution choices.

## Impact

Existing snapshot JSON serializer, focused regressions and plugin mirror. No new API, authority, provider connection, table, workflow, or public resume operation. Owner: root integrating Claude builder; branch codex/resume-surface-design; one dedicated PR.

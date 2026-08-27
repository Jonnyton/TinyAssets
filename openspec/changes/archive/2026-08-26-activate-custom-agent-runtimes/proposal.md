## Why

TinyAssets can now publish, import, export, remix, and privately bind arbitrary agent definitions, but a binding is still inert: it cannot become a durable agent that converses through an app or creates, tests, evaluates, and iterates workflows. Activating that last mile through the existing governed runtime boundaries is the difference between an agent catalog and the user-programmable 24/7 agent platform the host requested.

This change is the contract-only coordination root for that outcome. It defines the cross-slice invariants and dependency graph; implementation is admitted through separately claimed OpenSpec delivery changes, branches, and PRs rather than one semantic mega-change.

## What Changes

- Extend and consume the canonical server-authoritative activation lifecycle so it can bind an immutable `AgentDefinition` plus a private `AgentBinding` revision to a durable runtime epoch without creating an agent-only activation ledger.
- Resolve every executable component through a governed runtime adapter, preserve unfamiliar components for portability, and fail closed rather than silently dropping or executing unknown semantics.
- Treat Slack, Teams, and future apps as adapters over the boundary-layer owner's one authenticated, replay-safe ingress and grant-gated outbound-reply contract; keep app secrets and message history out of public definitions and private binding records and create no agent-only inbox/effect ledger.
- Let an activated agent compose existing Branch, Run, Gate, evaluator, and immutable-version primitives to create, dry-test, evaluate, publish, activate, observe, repair, and iterate user-authored workflow automations without cloning the workflow engine.
- Require requester-owned provider/compute authority, durable cloud continuation, bounded budgets, explicit effect grants, typed receipts, revocation, rollback, and useful-progress health for 24/7 operation with no maintainer or user computer online.
- Extend only targets and operations behind the canonical seven MCP handles; add no top-level agent or app tool.
- Stage implementation behind explicit handoffs from the active cloud-drain/provider-authority, outbound-boundary, organization-authority, Engine OS confinement, and personification-relay owners.
- Split delivery into bounded activation-core, app-conversation, workflow-iteration, canonical-control, and live-proof successors; this change writes no runtime code.
- Freeze the host-approved first V1 proof as one browser-only, remix-to-running Slack intelligence-agent journey: multi-creator public remix, unrestricted component replacement within the open envelope, private provider/app/cloud binding, Slack-authored workflow test/evaluate/revise/activate, PC-off delivery, lossless export/re-import, and a second-account remix with no private-state transfer. The intelligence domain is acceptance content, never a platform archetype.

## Capabilities

### New Capabilities

- `custom-agent-runtime-activation`: Activation, governed component resolution, app ingress/replies, workflow-authoring iteration, authority, durability, control, receipts, and acceptance for a private custom-agent binding.

### Modified Capabilities

None. This change composes existing capability owners and records its own activation contract; owner changes to their canonical requirements remain in their respective OpenSpec lanes.

## Impact

The separately admitted successors will extend the private custom-agent projection, daemon/cloud activation and provider-authority path, generic connection boundary, Branch/run/evaluation orchestration, connector routing descriptions, packaged runtime mirror, and focused concurrency/load/security tests. This contract-only proposal claims only its OpenSpec directory and `STATUS.md`; runtime files remain fenced until current owners land and each successor receives an exact claim and handoff.

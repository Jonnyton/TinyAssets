## Context

BranchDefinition serializes default_llm_policy and concurrency_budget, but _canonical_snapshot drops them. The frozen-version loader reconstructs from the stored snapshot. The existing Opus regression proves six failures and four compatibility passes. Root independently read serializer, loader, policy validation and selector reconstruction; root approves this narrow shape before implementation.

## Goals / Non-Goals

**Goals:** preserve selected model policy and concurrency in newly frozen versions, with correct distinct identity on edits.

**Non-Goals:** public resume, mid-node effect replay, new permissions, provider/catalog changes, historical version rewriting or private user workflow edits.

## Decisions

Include each normalized field only when not None. Empty policy dictionaries are preserved rather than coerced away. No policy-key allowlist here: the authoring contract supports forward-compatible policy keys, and dropping them recreates a lossy serializer. These choices are already authored/read as branch content and node policies are already frozen; snapshotting does not grant provider credentials or change visibility. Stored historical rows remain immutable.

Unconditional null inclusion would change identity for every unset branch, so reject it. Pulling current mutable choices into old snapshots would silently substitute behavior, so reject it. Old versions missing fields retain their actual recorded defaults; the next publish of a definition with choices creates a different version as it should. No migration or automatic republish is needed or authorized.

## Risks / Trade-offs

- Open policy dictionaries can contain arbitrary user material: preserve the existing authoring/visibility boundary; do not claim this field grants source access or makes a private branch public. Redesigning all policy validation is separate work, not a reason to drop user choices.
- Serializer test alone does not prove routing: add a focused compile/provider-call assertion using the supported preferred-policy shape, and concurrency reconstruction evidence. Do not claim live resume proof.
- Rollback to the old serializer would again drop choices on new publishes: use a forward fix if this patch regresses. Existing rows remain readable under both code versions.

## Verification and rollout

Run exact new tests, existing publish/version tests, Ruff and plugin mirror; root cross-family review of Claude code before push. Normal required CI/image/deploy/protected SHA and public canary. Ask app agent through the ordinary UI to exercise its own saved choices; no operator workflow edits. Sync the delta when code lands, archive only after acceptance. Deployment or successful tests alone are not closure.

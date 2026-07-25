## Context

The 2026-07-22 full-coverage audit found four groups of shipped behavior whose
owning canonical capabilities omit material clauses. The behavior is
already implemented and focused tests exist; this change reconciles OpenSpec
without changing runtime code. The affected owners are daemon identity and host
pool, daemon task runtime, graph execution, and knowledge export.

Two nearby active changes are deliberately separate. `distributed-execution`
defines future cross-host execution authority, while this change records only
the local child-run and queue behavior already present. `brain-okf-canonical-store`
defines a future write-through canonical store, while this change records only
the current export that never writes back to the source wiki.

Soul-wiki scaffolding is already canonical under
`knowledge-retrieval-and-memory`; this change does not duplicate that contract
under daemon identity.

## Goals / Non-Goals

**Goals:**

- Make each audited shipped behavior discoverable in its current canonical
  capability.
- State operational limits and unsafe/unwired helpers as explicitly as the
  successful paths.
- Keep every scenario traceable to current code and run the existing focused
  tests for each owning behavior group; independent review must identify
  clauses whose exact edge is source-grounded but lacks a focused assertion.
- Preserve capability ownership and keep future architecture out of as-built
  requirements.

**Non-Goals:**

- Change product code, storage schemas, public MCP actions, or deployments.
- Claim distributed scheduling, accepted-result authority, realtime host
  presence, atomic market matching, or an OKF write-through store.
- Repair the legacy blanket recovery helper or the OKF exporter's current
  limitations; those require separate behavior changes.

## Decisions

### Add requirements instead of modifying adjacent canonical requirements

The missing contracts are added when they have no existing owner. Where an
existing requirement already owns registration, heartbeat, bid polling, or
startup recovery, the delta modifies that full requirement or leaves its
stronger canonical statement in place. The alternative was to add overlapping
requirements, which would create two canonical owners for the same invariant.

### Specify observable current behavior, including negative boundaries

Requirements name the owner guards, terminal-state limits, callback isolation,
receipt-wait interruption, privacy exclusions, and callable-but-unwired helper.
This is chosen over a happy-path-only description because the omitted limits
are exactly where a future implementer could accidentally infer stronger
guarantees than the code provides.

### Keep child invocation local to the graph-execution owner

Live-definition invocation, frozen-version invocation, await, completed-run
attachment, and terminal-run-seeded new execution are all current graph/run primitives. They remain in
`graph-execution-substrate`; no requirement implies remote dispatch or a
distributed result authority. The alternative was to wait for or merge into
`distributed-execution`, which would conflate shipped local behavior with a
future capability.

The `run_branch resume_from` contract is explicitly distinct from
checkpoint-based `resume_run`: it validates a terminal source, merges its
inputs, starts a new run against the requested current Branch, and records
lineage. Treating the two paths as one requirement would wrongly imply that a
new seeded run continues the old checkpoint or exact old Branch version.

### Treat OKF as an export format, not a storage authority

The canonical requirement describes a read-only-to-source bundle writer with a
curated input set and a returned conformance report. It explicitly excludes any
MCP mutation action, source write-back, or canonical-store migration. The
alternative was to defer all OKF coverage to `brain-okf-canonical-store`, which
would leave shipped export behavior unspecified and obscure the present privacy
boundary.

## Risks / Trade-offs

- **[Risk] Requirement prose overstates behavior hidden behind stale comments or helper-level tests.**
  → Ground normative text in executable paths and focused tests, not module
  docstrings; in particular, host registration always inserts a new row, the
  blanket recovery helper is not startup-wired, only one executor route polls
  the BranchTask cancel flag, and attachment replay is rejected.
- **[Risk] Cross-capability duplication creates two owners for one invariant.**
  → Leave soul-wiki scaffolding in knowledge/memory and keep this delta to
  daemon selection and behavior metadata.
- **[Risk] Future changes are mistaken for current guarantees.**
  → Name the distributed-execution and canonical-store exclusions in both
  design and requirements.
- **[Risk] Documentation-only reconciliation drifts from code immediately.**
  → Run the owning focused tests, strict OpenSpec validation, preservation
  checks during sync, and independent requirement-to-code review before land.

## Migration Plan

1. Validate each delta strictly, run the focused implementation evidence, and
   record source-reviewed edges not directly asserted by those tests.
2. Independently review every requirement against current code and tests.
3. Sync the approved deltas into the four canonical capabilities and confirm
   all pre-existing canonical text is preserved.
4. Archive the change and update the coverage/disposition inventories in the
   same lane.

There is no runtime rollout or rollback. Reverting the documentation commit is
the rollback if a requirement is later shown to misdescribe current behavior.

## Open Questions

None. Future distributed execution, write-through OKF storage, and repairs to
the explicit as-built limitations remain owned by their separate changes.

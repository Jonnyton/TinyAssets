## Context

`knowledge-retrieval-and-memory` currently specifies the shared retrieval backbone, tiered scope model, per-universe notes, and bounded daemon wiki. The repository also ships several distinct memory families that predate OpenSpec: a soul-scoped mini-Brain, domain-neutral episodic SQLite, a fantasy-specific context manager and learning loop, project key/value memory, draft output versions, node-scope manifest parsing, and standalone temporal/consolidation helpers. Their shared vocabulary—especially “promotion,” “learning,” and “memory”—does not imply shared persistence or lifecycle semantics.

The active `brain-okf-canonical-store` change describes a future canonical OKF bundle and projection path. Its implementation tasks remain incomplete, so it cannot be used to normalize or strengthen the present as-built contract.

## Goals / Non-Goals

**Goals:**

- Make the canonical capability describe every substantive shipped knowledge/memory behavior found by the Batch B audit.
- Preserve observable limitations and distinguish durable state from returned candidates, advisory values, and placeholder envelopes.
- Narrow the existing tiered-scope statement so it remains true in the presence of legacy unscoped chapter learning.
- Give each requirement a focused evidence path without changing runtime behavior.

**Non-Goals:**

- Implement, migrate, or redesign any memory subsystem.
- Claim OKF canonicality, atomic projection, crash recovery, federation, or a closed autonomous learning loop.
- Treat similarly named promotion mechanisms as one lifecycle.
- Turn library-only helpers or placeholder tool envelopes into production-integrated behavior.

## Decisions

### Keep one capability, but name each persistence boundary

The delta modifies `knowledge-retrieval-and-memory` rather than creating several new capabilities because all audited surfaces implement the PLAN Brain module’s current memory/retrieval responsibility. Each requirement names its actual store and integration boundary: mini-Brain SQLite/wiki, episodic SQLite, process-global chapter learning, project SQLite, draft-version SQLite, or standalone in-memory helpers. The alternative—one generic “memory lifecycle” requirement—would falsely imply shared transactions, scope, and promotion semantics.

### Use as-built vocabulary instead of aspirational names

“Mini-Brain promotion” means a validated SQLite lifecycle transition plus a best-effort wiki append. “Episodic promotion” means a persisted boolean marker. Style and ASP “promotion” means a returned candidate dictionary. Reflexion “updated weights” are advisory return values. The spec states these distinctions directly because code identifiers and docstrings otherwise overstate the shipped effect.

### Modify the tiered-scope requirement

The existing text says no memory read or write may cross a universe. That is true of the `MemoryScope` abstraction and scoped stores, but false of the fantasy chapter-learning singleton, whose in-memory rules have no universe key. The updated requirement scopes the invariant to callers that use `MemoryScope` and records the legacy exception explicitly. This is a truth correction, not approval of the exception.

### Specify library-only and placeholder behavior as limited behavior

Temporal facts and consolidation helpers are shipped importable libraries even though production integration and focused tests are absent. The six functions in `tinyassets.memory.tools` are also shipped but mostly return placeholder envelopes. Omitting them would preserve a coverage hole; describing advertised side effects would be false. Requirements therefore bind only their current library/envelope behavior and state that no durable effect occurs where none exists.

### Keep future OKF ownership separate

Nothing in this delta references the proposed OKF store as an implementation dependency. The future change remains the sole owner of OKF bundles, projections, outboxes, recovery, federation, and compatibility. Current state is host-local SQLite plus curated wiki rendering and legacy stores.

## Risks / Trade-offs

- **[Risk] The canonical spec exposes undesirable legacy behavior.** → The delta labels each limitation as as-built truth without endorsing it; future fixes require their own OpenSpec changes.
- **[Risk] Dense requirements may blur ownership.** → Requirement names and prose identify the owning module/store and avoid generic “Brain” claims.
- **[Risk] Untested helper behavior may drift.** → The spec states that temporal/consolidation helpers are library-only and records their current bounds; a later implementation change must add focused tests before changing the contract.
- **[Risk] Future OKF work could duplicate or silently replace legacy behavior.** → The explicit non-OKF boundary makes migration and retirement a separate reviewed change.

## Migration Plan

No runtime migration is performed. Strict-validate the delta, run focused existing tests, independently compare every requirement to code/tests, merge the delta into the canonical capability, and archive this change. Rollback is the documentation-only commit revert.

## Open Questions

None for this as-built reconciliation. Remediation of the documented legacy limitations belongs in separately proposed changes.

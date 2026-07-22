## Context

The original OpenSpec baseline deliberately covered the engine and its principal
MCP/storage/economy surfaces, not every shipped repository surface. Subsequent
work also added daemon-host, evaluation, constraint, coordination, and website
behavior without assigning those behaviors canonical capability owners. At the
same time, several files currently under `openspec/specs/` describe forward
vision rather than verified as-built behavior.

That leaves two distinct reconciliation problems: shipped behavior without a
spec, and specification text that must not be treated as implementation proof.
This change handles the collision-free portion of the first problem. The
coverage audit records the remaining enrichment and future-build work so this
documentation batch cannot create a false claim of total completion.

This is a documentation-only change. Current source, tests, workflows, and
rendered website content are evidence; they are not modified by this change.
Active OpenSpec changes retain ownership of their existing capability deltas.

## Goals / Non-Goals

**Goals:**

- Give eight shipped, previously unowned behavior areas strict canonical
  capability boundaries.
- Express only behavior that can be grounded in the current repository,
  including current limitations and degraded modes.
- Keep active deltas and unbuilt full-platform targets visibly separate from
  as-built canonical truth.
- Produce a repeatable coverage ledger that later reconciliation batches can
  close without re-auditing the repository from scratch.

**Non-Goals:**

- Implement or change runtime, packaging, deployment, website, or API behavior.
- Claim that one-click tray installers, node remix/live collaboration,
  moderation, production market matching, or other full-platform targets ship.
- Modify capability files already owned by active changes.
- Re-prove public runtime behavior through canaries or rendered chatbot tests;
  those gates remain attached to behavior-changing lanes.
- Declare the full-spec program complete after this first batch.

## Decisions

### 1. Split reconciliation into collision-safe batches

This change adds only new capability owners. Enrichment of existing canonical
specs is deferred until an immediate file-level collision check confirms that
no active change owns the same requirement surface. Unbuilt targets remain
active changes until implementation and verification exist.

Alternative considered: update every affected canonical spec in one change.
That would overlap in-flight deltas and make review unable to distinguish
missing documentation from new product promises.

### 2. Treat executable repository evidence as the as-built boundary

Each requirement is grounded in current source, tests, workflows, or shipped
site content. PLAN and design notes explain intent and capability boundaries,
but do not establish that behavior exists. When code and aspirational design
differ, the requirement records the current behavior and the audit records the
remaining target.

Alternative considered: transcribe PLAN modules directly. That would promote
known targets—such as packaged installers and live collaboration—into false
as-built truth.

### 3. Make limitations normative rather than hiding them in prose

Important current constraints belong in SHALL/MUST requirements and scenarios:
the desktop host ships from source rather than through a published one-click
installer; constraint evaluation has an observable warn-and-continue mode when
the shared rule file is absent; and the OSS smoke workflow proves installation
and basic execution rather than full feature correctness.

Alternative considered: document only the happy path. That would make the
canonical spec stronger than the implementation and defeat reconciliation.

### 4. Keep capability ownership narrow and composable

The new boundaries follow independently testable runtime responsibilities:
domain discovery, daemon identity/host pooling, generic evaluation, desktop
hosting, development coordination, constraint evaluation, OSS installation,
and the public website. Existing capabilities continue to own graph execution,
connector transport, storage, economy semantics, and outcome attribution.

Alternative considered: create a single `remaining-platform` capability. That
would conceal dependencies, encourage future cross-surface deltas, and make
strict requirement-to-code review impractical.

### 5. Sync only after strict validation and independent review

Delta specs first pass OpenSpec strict validation and requirement-to-evidence
review. Only then are they synced as new canonical capability files and checked
again with repository-wide strict validation. Because this is documentation
reconciliation, the verification claim is spec structural validity and source
grounding—not fresh runtime acceptance.

Alternative considered: write directly to `openspec/specs/`. The change
lifecycle provides a reviewable statement of intent, an auditable task record,
and a safe point to reject overclaimed requirements before canonicalization.

## Risks / Trade-offs

- [Risk] A requirement accidentally describes intended rather than shipped
  behavior. → Mitigation: require concrete source/test/workflow grounding and
  independent review before sync.
- [Risk] Concurrent active changes create duplicate or contradictory ownership.
  → Mitigation: this batch adds new capability names only; later enrichment must
  run file collision checks immediately before writing.
- [Risk] Large capability specs become inventories of implementation details.
  → Mitigation: specify externally meaningful contracts and failure behavior,
  while leaving private algorithms to code and tests.
- [Risk] Readers interpret Batch A as proof that the full project is specified
  or built. → Mitigation: keep the audit's Batch B/C gaps and completion proof,
  and retain the STATUS lane until the broader program is closed.
- [Trade-off] Normatively recording undesirable current behavior can look like
  endorsing it. → It is necessary for honest as-built truth; a later behavior
  change must explicitly replace that requirement.

## Migration Plan

1. Draft and strictly validate the eight delta specs.
2. Review every requirement against current repository evidence.
3. Sync each new capability into `openspec/specs/` after claim collision checks.
4. Run strict validation over the change and canonical spec tree, then verify
   that a second sync would be idempotent.
5. Archive the completed change and land the audit plus canonical specs through
   the normal PR path.

Rollback is documentation-only: revert the reconciliation commit. No runtime,
data, deployment, or compatibility rollback is required.

## Open Questions

- Which Batch B capability should be reconciled first after active changes are
  refreshed against main?
- Should the eight forward-vision files remain in the canonical directory with
  explicit status metadata, or move into active change directories? That is a
  separate governance decision and is not silently resolved here.

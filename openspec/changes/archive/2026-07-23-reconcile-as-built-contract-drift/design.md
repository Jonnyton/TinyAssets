## Context

PR #1616 grounded all 204 canonical requirements and 548 scenarios against
current code and tests. Seven requirements use absolute language unsupported by
failure, concurrency, or adversarial paths. Strict OpenSpec validation cannot
detect this semantic drift.

Canonical specs describe shipped behavior, including current limitations.
Active changes describe desired behavior that is not built. This correction
therefore needs to state today's boundary exactly while preserving stronger
guarantees as future hardening work.

## Goals / Non-Goals

**Goals:**

- Make all seven audited requirements true of current source.
- Keep successful-path guarantees and existing safety checks explicit.
- Name every material race, best-effort write, permissive boundary, and
  prompt-only trust boundary found by the audit.
- Keep future hardening and active change semantics visibly separate.

**Non-Goals:**

- Change runtime behavior or tests.
- Endorse the current limitations as the desired architecture.
- Sync future transaction transport, lifecycle migration, or personification
  requirements from active changes.
- Resolve the separate PLAN conflicts about platform storage, private data,
  public primitives, or privacy-guidance ownership.

## Decisions

### D1 - Correct canonical truth immediately and harden separately

Leaving an absolute requirement false until runtime hardening lands would keep
canonical truth knowingly wrong. Each replacement explicitly identifies the
current limitation. STATUS separately owns the runtime hardening lane, which
may later modify these requirements again after implementation and adversarial
tests land.

### D2 - Replace requirements when the heading is itself false

The money, settlement, Goal-ledger, learning, and trigger-receipt headings make
absolute claims contradicted by current behavior. Their old requirements are
removed and accurately named replacements are added. Work-target lifecycle and
founder creation retain accurate high-level headings, so those requirements are
modified in place.

The identity bridge for future hardening and active-delta rebases is:

| Removed heading | Replacement heading |
|---|---|
| All money amounts are integer MicroTokens, never floats | Payment-core conversions produce integers while legacy bids permit non-integer scalars |
| Settlement records are immutable and write-once | Settlement recording rejects pre-existing paths sequentially but is not race-atomic |
| Goal writes are authorization-scoped and appended to the global contribution ledger | Recognized Goal actions use the configured authorization mode and contribution attribution is best-effort |
| Learning is a separate fail-closed step over explicitly-taught facts, and persistence never breaks the reply | Learning is a separate tolerant model-extracted step with field-specific filtering, and reply delivery survives failures |
| Trigger receipts are append-only and recorded before enqueue | Trigger receipts use one mutable per-attempt row attempted before enqueue |

### D3 - Specify observable boundaries, not implementation wishes

The corrections state concrete current behavior:

| Capability | Current boundary |
|---|---|
| work targets | helpers use seven conventional states; generic records accept arbitrary lifecycle strings |
| money | payment-core and transport `int(...)` boundaries can truncate numeric fractions and coerce bools; legacy bids preserve caller/YAML scalar types while v1 settlement serializes the bid as float |
| settlements | pre-existing paths are rejected sequentially; check-then-write is not race-atomic |
| Goals | unknown actions return before authorization; recognized actions follow the configured auth mode; a successful write survives a later attribution-append failure |
| founder creation | index registration is best-effort; rollback attempts directory removal, can swallow cleanup failure, and does not compensate earlier durable writes |
| learning | tolerant extraction and field-specific filters do not establish source entailment; governed-file read failure is silently narrowed and outer failures preserve the reply |
| trigger receipts | pending-row creation is attempted before enqueue but can fail open; unrestricted updates on an existing row can overwrite a prior terminal status |

### D4 - Active deltas remain future-only

`build-forward-platform-capabilities` owns the future authenticated
double-entry transport, `universe-creation` owns unfinished public lifecycle
work but explicitly excludes canonical birth/ACL behavior, and
`reconcile-universe-personification-relay` adds future personification
semantics. None of those requirements is imported into this as-built change.

## Risks / Trade-offs

- **Risk: readers mistake a limitation for approval.** Each affected
  requirement calls the limitation current/as-built and the proposal names the
  hardening owner.
- **Risk: later hardening lands without updating canonical truth.** The
  hardening change must modify the corrected requirement and sync/archive on
  land.
- **Risk: active deltas rebase against stale requirement names.** The change
  records every renamed requirement; overlapping active changes must validate
  against the new canonical baseline before sync.
- **Risk: limitation scenarios appear more strongly tested than they are.**
  Fractional transport coercion, concurrent settlement overwrite, Goal-ledger
  failure, registry/rollback residue, invented learning, swallowed
  governed-file reads, receipt-creation failure, and terminal receipt overwrite
  are source-grounded but currently lack complete focused adversarial/race
  coverage. Those tests belong to `harden-canonical-absolute-guarantees`; they
  are not fabricated as evidence for this spec-only correction.

## Migration Plan

Strictly validate and independently review this change, sync the six deltas
into canonical specs, archive the change, and validate the whole OpenSpec tree.
No runtime migration or rollback is required; reverting the spec commit restores
the previous wording.

## Open Questions

None for as-built truth. Runtime hardening design remains in its separately
claimed lane.

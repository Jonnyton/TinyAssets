## Context

Commit `4fa897b7` introduced twelve pure `tinyassets/paid_market/` modules and eight ambitious canonical specs in one batch. The implementation was explicitly library-only and the SQL files under `prototype/full-platform-v0/migrations/006-008` remained prototypes, but the specs described live APIs, persistence, credentials, product workflows, and legal posture as requirements. A requirement-by-requirement audit at `ae463834` found no wholly built requirement in `boundary-layer`, `data-commons`, or `demand-side`; the remaining five files similarly mix shipped arithmetic with absent integration and direct contradictions.

Canonical `openspec/specs/` is as-built truth. `PLAN.md` remains the architectural source for target direction, while active OpenSpec changes own unimplemented behavioral requirements.

## Goals / Non-Goals

**Goals:**

- Make every affected canonical requirement true of `main` and supported by direct code/test evidence.
- Keep one canonical owner for each shipped behavior.
- Preserve all future outcomes, constraints, and unresolved decisions in an active change.
- Make contradictions explicit rather than weakening their wording until they appear built.

**Non-Goals:**

- Implement any market transport, dataset workflow, standing goal, hardware workflow, public token, or connector adapter.
- Treat prototype SQL as deployed behavior.
- Treat a pure computation helper as proof of persistence, authentication, transport, or product integration.
- Change `PLAN.md` or silently resolve founder/counsel decisions.

## Decisions

### D1 — Classify the complete requirement and every scenario

The audit uses four labels: BUILT means the complete stated behavior is landed; PARTIAL means a meaningful named subset exists but the end-to-end contract is absent; FUTURE means no integrated implementation exists; CONTRADICTED means `main` materially behaves otherwise. Only BUILT behavior can remain canonical. A built scenario inside a PARTIAL requirement is extracted into a narrower requirement rather than used to preserve the overbroad parent.

Alternative considered: retain partial requirements with an “as-built limitation” paragraph. Rejected because a requirement whose principal SHALL is false remains misleading even if its limitation later admits that fact.

### D2 — Consolidate pure market behavior under `paid-market-economy`

`paid-market-economy` already owns the I/O-free package. Its delta names the actual contracts for pair-capped spot calculations, UTC buckets, forward and training settlement, license composition, pool/fabrication/shuttle/fund arithmetic, double-entry builders, and pure matching. It explicitly excludes persistence and live transport.

Alternative considered: keep five narrowly rewritten Track E-I canonical files. Rejected because those names imply end-to-end product capabilities and duplicate the package owner.

### D3 — Give shipped external-write receipts a dedicated owner

`external-effect-receipts` describes the exact per-universe consent and receipt lifecycle used by current effectors. It records the transitional soul-authority fallback, caller-supplied optional idempotency hints, per-sink atomic reservation, stale reclaim, and the absence of whole-batch atomicity. This avoids pretending that the stronger boundary-layer effect design is already implemented.

### D4 — Retire empty forward capabilities and preserve them actively

All requirements in the eight old capabilities are removed from canonical truth. Their target outcomes are restated under `build-forward-platform-capabilities`, which remains active and unimplemented after this reconciliation archives. No removed requirement is discarded or marked done.

### D5 — Evidence hierarchy

Callable production code plus focused tests proves shipped behavior. Prototype migrations, design notes, adjacent primitives, or a helper with no integration are insufficient. The dated audit records the evidence and the canonical specs state important limitations inline.

## Risks / Trade-offs

- [Risk] One umbrella future change is too broad to implement atomically. → Its design and tasks define dependency-ordered slices; implementation MUST split a slice into a narrower successor change before coding when independent rollout is possible.
- [Risk] Removing familiar capability files looks like cancellation. → The active future change retains every target capability and its decisions, and the audit maps every old requirement to its new owner.
- [Risk] Pure helper specs drift from code. → Focused tests cover every helper family and the canonical wording uses current function-level semantics, including counterintuitive limitations.
- [Risk] Receipt semantics are generalized beyond their current consumers. → The spec limits guarantees to effectors that actually use the consent/receipt gates and calls out optional hints and stale-reclaim duplication risk.

## Migration Plan

1. Publish the classification audit and strict-valid reclassification deltas.
2. Add explicit `paid-market-economy` and `external-effect-receipts` canonical requirements.
3. Remove the eight empty forward-heavy canonical capability files.
4. Archive this completed change after proving canonical sync and strict validation.
5. Revalidate the already-created `build-forward-platform-capabilities` change against the post-removal canonical tree; leave its implementation tasks open.
6. Rollback is documentation-only: revert the reconciliation commit. No runtime or data migration occurs.

## Open Questions

None for the classification itself. Product, numeric-default, privacy, safety, and legal questions remain explicitly open in the future change.

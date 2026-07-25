## Why

The full-platform architecture still calls for outbound connectivity, data and demand commons, and paid production markets, but those targets are not landed behavior and therefore cannot remain in canonical `openspec/specs/`. This active change preserves the intended outcomes while making their implementation and verification status explicit.

## What Changes

- **HARD DEPENDENCY:** This change MUST NOT be applied, synced, or archived until `reclassify-forward-vision-specs` has landed, physically removed the eight old canonical capability directories, passed strict validation, and archived. Satisfied 2026-07-24: the reclassification is archived at `openspec/changes/archive/2026-07-22-reclassify-forward-vision-specs`, none of the eight capability directories remain under `openspec/specs/`, and `openspec validate --all --strict` passes.
- Delegate the outbound boundary — resource-ledger grants, action caps, credential-blind adapters, durable inboxes, typed artifacts, and batch-safe external effects — to `outbound-boundary-layer`; the umbrella `boundary-layer` delta is physically released to that successor, which must preserve the credential-blindness, cap-independence, system-derived idempotency, and whole-batch-hold guarantees.
- Build first-class dataset assets, provenance, licensing enforcement, quality gates, contribution accounting, and Dataset Forge workflows.
- Build standing-goal demand, onboarding outcomes, and goal-bounty market composition before introducing direct universe services.
- Build the verified design-to-fabrication hardware ladder on top of commons artifacts, gates, and paid-market primitives.
- Delegate replacement of direct accounting side paths, schema history, and the single versioned logical-accounting transaction transport to `paid-market-track-e-wave-2-transport`; preserve its single-path guarantee without treating database accounting as proof of wallet funding or chain settlement. Delegate live price/forward quote surfaces, order lifecycle, caps, collateral, and privacy controls to `paid-market-live-price-discovery`.
- Build F1/F2 training instruments, attestation, checkpoint release, gates, mint/license enforcement, and buyer-data provenance; keep F3 research-gated.
- Build persisted pooled-training ownership and revenue lifecycles without secondary transfers in v1.
- Introduce any public TINY/stablecoin architecture only behind legal, security, and launch gates, preserving the separation from settlement until those gates pass.

## Capabilities

### New Capabilities

- `data-commons`: Dataset pricing modes and frozen contributor settlement. The contribution, manifest, license-admission, quality-gate, provenance, and Dataset Forge half was released to `data-commons-contribution` on 2026-07-25 (tasks 3.1 non-monetary half and 3.2) and is no longer specified here.
- `demand-side`: Standing goals, binding onboarding outcomes, goal bounties, and the measured gate for later universe services.
- `hardware-creation`: Verified design-to-silicon and physical-fabrication product workflows.
- `paid-market-training`: Training instruments, verification, checkpoint payment, gate integration, capability minting, and input provenance.
- `pooled-training-ownership`: Persisted funding, frozen lineage ownership, refunds, and revenue distribution.
- `token-architecture`: Counsel-gated public token, valuation, liquidity, and mint/redemption behavior.

### Released Capabilities

**Ownership is one active owner per released *requirement* (convention amended 2026-07-25).** As originally written this read "each released delta has exactly one active successor owner", which was accurate while every release was whole-delta (tasks 1.1, 1.2, 2.1). Task 3.1 released only the non-monetary half of `data-commons`, so the convention is restated at the granularity that actually carries the invariant: **no requirement may have two active owners.** A delta may be split across owners provided the split is disjoint, both sides are named where a reader will look, and nothing is copied. Whole-delta release remains the default and the simpler case; a partial release must say so explicitly in this section, in the delta file itself, and in the originating task.

> **Concurrent-amendment note.** The unmerged lane `claude/o5-demand-side` (PR #1771) makes this same requirement-granularity amendment, for the same reason, from the same base — its trigger is task 4.1's partial release of `demand-side`. Whichever lane lands second folds the two into one amended sentence naming both partial releases, rather than stating the amendment twice.

The umbrella keeps only the cross-slice invariants those successors must preserve: design decisions **D0–D8** and the slice dependency ledger. D9 is host-gated context recorded for provenance and imposes no successor obligation in either direction.

- `boundary-layer` → `outbound-boundary-layer` (released 2026-07-24, task 1.2).
- `data-commons` **contribution/admission half** → `data-commons-contribution` (released 2026-07-25, tasks 3.1 non-monetary and 3.2). A *partial* release: four of the six `data-commons` requirements were physically moved to the successor — content-addressed manifests, fail-closed license/manifest validation, contamination/privacy/quality gates, and Dataset Forge — while pricing modes and contributor settlement stay here pending task 3.1's monetary half. The split seam is **admission is non-monetary; consideration is monetary**. The split is disjoint and nothing was copied, so no requirement has two owners.
- `paid-market-economy` transaction delta → `paid-market-track-e-wave-2-transport` (task 1.1).
- `paid-market-price-index-and-forwards` delta → `paid-market-live-price-discovery` (task 2.1).

### Modified Capabilities

- None in this umbrella. `paid-market-track-e-wave-2-transport` is the sole successor owner of the released `paid-market-economy` transaction delta.

## Impact

This is an active, unimplemented cross-platform change and is blocked on the completed canonical reclassification. It will affect MCP/HTTP surfaces, identity and credential boundaries, SQLite migrations, paid-market transports, commons workflows, gates, provenance, deployment flags, legal review, and the complete-system concurrency/load proof. It depends on authenticated distributed execution for execution evidence and rollout authority but owns market behavior separately. `paid-market-track-e-wave-2-transport` is the sole successor owner for the released logical-accounting transaction delta, and `paid-market-live-price-discovery` is the sole successor owner for the removed price-index/forward delta; each must preserve its delegated umbrella invariants before it can sync or archive. Real-fund wallet and chain effects remain owned by the required separately reviewed §18.6 successor.

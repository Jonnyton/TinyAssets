## Context

The full-platform architecture describes a connected production commons, but the corresponding Track E-I and boundary requirements are not yet implemented. The shipped substrate consists of inbound MCP, shared goals and schedules, selected external-effect receipts, evaluation gates, a default-off file-backed paid-market path, and an I/O-free market computation package. This change defines the missing product and transport layers without claiming they exist.

## Goals / Non-Goals

**Goals:**

- Preserve the target behavior formerly stored in eight forward-heavy canonical specs.
- Define dependency boundaries so each future slice reuses shipped primitives rather than cloning them.
- Require authentication, exact accounting, fail-closed authority, provenance, legal gates, and complete-system load proof before launch.
- Keep the public token and secondary ownership surfaces dark until explicit counsel and founder approvals.

**Non-Goals:**

- Declare any target behavior shipped by landing this planning change.
- Reopen the current canonical public MCP handle set without its own connector-surface change and rendered-chatbot acceptance.
- Promote prototype migrations 006-008 directly to production.
- Build F3 swarm training before a separate research review pins its verification model.

## Decisions

### D0 — This change cannot apply before canonical reclassification lands

The eight capability deltas are ADDED requirements because their former canonical files are being removed as unbuilt. No provider or automation may apply, sync, or archive this umbrella until `reclassify-forward-vision-specs` has synced its canonical additions, physically removed all eight old capability directories, passed strict validation, landed, and archived. Applying early would append future behavior to canonical truth and recreate the defect.

### D1 — Deliver in dependency-ordered slices

The implementation order is: transaction/migration substrate; boundary authority and receipts; live price and forward transport; dataset and training provenance; standing-goal/bounty demand; verified hardware workflows; pooled ownership; counsel-gated public token behavior. Each independently deployable slice MUST become a narrower OpenSpec successor change before implementation, with this umbrella change recording cross-slice invariants.

### D2 — Pure oracles remain canonical and transport-independent

Future transports MUST call or equivalence-test against `paid-market-economy` oracles. They SHALL NOT duplicate formulas in SQL, HTTP handlers, or MCP adapters without differential tests proving equality. When a target rule disagrees with current code—such as per-user versus per-pair index caps or pre-seeded treasury minting—the future change changes behavior explicitly; canonical truth is not rewritten retroactively.

### D3 — `paid-market-economy` owns one money transport before market expansion

All value movement must converge on one authenticated, double-entry transaction boundary owned by `paid-market-economy`, with schema history, idempotency, and oracle-equivalence tests. Price, forward, training, data, pool, and hardware capabilities consume that boundary. The current direct SQLite payment actions and prototype `market.apply_tx` cannot coexist as launch paths.

### D4 — Credentials remain daemon-side

Adapters receive only scoped grants and redacted results. Secret resolution and external calls remain in trusted daemon-side proxies. Numeric action caps are separate from tool permission, and batch semantics must define atomic hold/failure rather than best-effort partial effects.

### D5 — Provenance and gates precede monetization

Datasets, training checkpoints, hardware designs, and fabricated outputs require content-addressed manifests and machine-evaluable gates before payment or capability minting. A pure license lattice is not enforcement until the run/mint boundary invokes it before work begins.

### D6 — Demand primitives precede direct services

Standing goals and bounties establish measurable demand before any universe-service market. The later service gate must be executable and based on observed bounty volume, not a prose assertion.

### D7 — Legal and research gates are hard dependencies

Pooled shares remain non-transferable in v1. Public TINY mint/redeem, governance, secondary transfer, marketing, and jurisdictional availability require counsel approval. F3 swarm training requires an opposite-provider research review and a separate change.

### D8 — “Anyone may claim” means any authenticated eligible principal

The original bounty target used “ANYONE” to mean an open marketplace rather than an invitation-only claimant list. The implementation SHALL preserve open discovery and eligibility for any authenticated principal or universe satisfying published admission rules, but SHALL NOT permit anonymous money movement. This is an explicit safety clarification, not a product narrowing.

### D9 — The open-production-commons reframe is host-gated context, not a decision this change acts on

A platform-shape reframe — one generic work-order primitive over a Goal/Branch/Asset/Claim/Order+Offer/Pool kernel, commons plus market plus funding on one lineage and reputation ledger, and a platform that never executes or holds custody — was captured on 2026-07-19 and is recorded in `.agents/handoffs/2026-07-19-distributed-execution-resume/RESUME-SPEC.md` §9. It is **explicitly not authorized for implementation**: it is blocked on a host Q6 confirmation about private fulfillment and on explicit PLAN.md foldback approval, and its design artifacts were never tracked in the repo.

D9 is recorded as provenance only. Unlike D0–D8 it is **not normative in either direction** and is not a cross-slice invariant successors must preserve:

- No requirement, task, or acceptance criterion in this umbrella or in any successor may be taken **from** the reframe while it is unapproved.
- Equally, nothing may be required, blocked, or reviewed **for** it. "Keep the reframe reachable" is not a constraint on any slice, not a review gate, and not grounds for rejecting a design that is otherwise correct under D0–D8.
- The slices below are specified as they stand: separate lifecycles composing shared oracles, gates, and one accounting transport.

Non-normative note for whoever picks the reframe up if it is ever approved: the expensive parts to retrofit would be per-slice request/claim/settlement lifecycles that cannot be re-expressed as a payload type, and attribution/lineage records duplicated privately per slice rather than referenced. That is an observation about future migration cost, not an obligation — a slice that does either is still compliant today. Making any of it binding requires the host Q6 confirmation plus PLAN.md foldback approval, and then a change that states the constraints explicitly as authorized requirements.

STATUS.md carries the matching `host-decision` row for target-spec PLAN conflicts (store, private data, primitives, privacy). Anything that depends on those positions is noted in `tasks.md` and left unbuilt.

## Slice dependency ledger

Task 1.3. Every market slice depends on the `paid-market-economy` transaction owner; no slice may open a second accounting path (D3). "Unassigned" means the slice has no narrower successor change yet, and per D1 it needs one before any implementation.

| Slice | Active owner | Depends on | Why the edge exists |
|---|---|---|---|
| `boundary-layer` | `outbound-boundary-layer` | `identity-auth-and-access-control`; `credential-vault`; `external-effect-adapters` + `external-effect-receipts`; `graph-execution-substrate`; transaction owner for value-moving effects only | Grants bind to an authenticated owner, custody stays with the vault, the landed effect path is what gets superseded, and compile-time artifact typing lives in the substrate. |
| `paid-market-economy` transport | `paid-market-track-e-wave-2-transport` | `identity-auth-and-access-control`; canonical `paid-market-economy` pure oracles; storage migration history | This is the root money edge. Every row below it inherits this dependency. |
| `paid-market-price-index-and-forwards` | `paid-market-live-price-discovery` | transaction owner; `distributed-execution` (verified execution evidence); `provider-routing` | Quotes consume accepted settlement observations and verified eligibility; the price owner creates no settlement truth. |
| `data-commons` (contribution/admission half — tasks 3.1 non-monetary, 3.2) | `data-commons-contribution` | `wiki-commons` (the commons entry substrate contribution and discovery ride); `build-brain-canonical-store` (the canonical bundle's durability contract); `evaluation-outcomes-and-attribution` (the append-only contribution ledger and attribution edges lineage is recorded onto); `identity-auth-and-access-control`; `constraint-evaluation` + `evaluation-runtime-and-scenarios` (contamination, privacy, quality gates); `shared-goals-and-convergence` (held-out sets contamination is measured against; a contribution's related Goals); `graph-execution-substrate` (Forge graphs are ordinary compiled graphs); `boundary-layer` (**only** the license-gated corpus fetch inside a Forge graph — an external read whose source node must bind a declared user-granted connection class; *not* manifest movement, which transfers references and never requires bytes to transit platform-owned storage) | Manifest and license validation is the admission gate every downstream training or hardware claim invokes — the largest downstream fan-out of any unowned slice, which is why it was promoted first. **No** transaction-owner edge, despite D3 naming `data` among the transaction consumers: that consumption is precisely the pricing/settlement half retained in the row below, so the released admission half carries none and refuses at the money edge instead. |
| `data-commons` (pricing + settlement half — task 3.1 monetary) | unassigned | transaction owner (escrow, per-run fees, revenue-share legs, exact apportionment); the admission half above (settlement freezes terms into an admitted manifest); `identity-auth-and-access-control` | Pricing modes and contributor settlement are value movement and cannot exist before D3's single transaction transport. Retained by the umbrella when the admission half was released. |
| `demand-side` (non-monetary half — task 4.1) | `demand-side-signals` | `boundary-layer` (inbox ingress, receipt, cutoff); `daemon-runtime-and-dispatch` (proactivity heartbeat and schedules); `shared-goals-and-convergence` (the Goal primitive); `identity-auth-and-access-control` (registration-bound execution authority); `constraint-evaluation` + `evaluation-outcomes-and-attribution` (the week-one gate claim) | Standing goals, schedules, onboarding, and metrics are demand *observation*, not value movement — hence **no** transaction-owner edge (D3 does not name them as consumers). The successor refuses at the money edge instead of consuming a transport. |
| `demand-side` (bounty + service-gate half — tasks 4.2/4.3) | unassigned | transaction owner (escrow, tranches, refunds); the 4.1 half above (bounties are posted against standing goals); `constraint-evaluation` + `evaluation-outcomes-and-attribution` (machine gates and first-verified-claim ordering); `identity-auth-and-access-control` | A bounty is money released by a frozen machine gate; without gates and a transport it is a promise, not a market. 4.3 additionally needs a host/founder parameter decision. |
| `paid-market-training` | unassigned | transaction owner; `data-commons` (license/manifest validation contract); `distributed-execution` (attestation inputs, leases, execution evidence); price owner (instrument pricing); gate capabilities | Checkpoint payment is verified-evidence-gated, and mint enforcement calls the data-commons contract rather than reimplementing it. |
| `pooled-training-ownership` | unassigned | transaction owner; `paid-market-training` (capability mint and frozen lineage); `identity-auth-and-access-control` | Ownership is a function of accepted contributions to a training instrument, frozen at that instrument's mint. |
| `hardware-creation` | unassigned | transaction owner; price owner (quotes, ranking, estimate provenance); `boundary-layer` (outbound fabrication requests and receipts); `data-commons` (design artifacts, license registry); `pooled-training-ownership` (fractional shuttle ownership); gate capabilities | It is the deepest composition in the D1 order — the direct edges listed here, plus `paid-market-training` transitively through pooled ownership. It has no `demand-side` or `token-architecture` edge; being last in D1's ordering is not itself a dependency. |
| `token-architecture` | unassigned | written counsel approvals (task 5.2); transaction owner (ledger separation); `pooled-training-ownership` (v1 transfer refusal); `identity-auth-and-access-control` | Dark by default; the only hard technical edge is that settlement must never import the fund module. |

## Risks / Trade-offs

- [Risk] The umbrella is too large for one review or release. → Every build slice is split into a narrower change before code, preserving explicit dependencies here.
- [Risk] Market math diverges across transports. → Differential tests against canonical pure oracles are mandatory at every transport boundary.
- [Risk] External effects duplicate after crashes. → The final boundary requires destination-native reconciliation plus durable receipts; stale timeouts alone are insufficient for value-moving effects.
- [Risk] Privacy or licensing checks arrive after data movement. → Admission gates run before bytes, tokens, payment, or minting.
- [Risk] A public token or ownership product creates legal exposure. → Those tasks are blocked by written counsel approval and remain dark by default.

## Migration Plan

1. Replace prototype migration numbering with an applied schema-history mechanism and prove rollback/replay.
2. Land one authenticated transaction transport and cut over existing default-off money actions.
3. Add boundary grants, caps, adapters, inboxes, typed artifacts, and stronger effect reconciliation.
4. Add quote/order/training/data/hardware transports in separately reviewable changes.
5. Add demand, ownership, and token surfaces only after their dependency and legal gates pass.
6. Each public surface requires focused tests, §14 concurrency/load proof, live connector canaries, rendered chatbot acceptance, and post-fix clean-use evidence.

Rollback is per slice: keep the feature flag dark, revert the slice, and restore the preceding schema/app version using its tested rollback plan. No slice may rely on a downgrade-incompatible migration without a separately approved recovery plan.

## Open Questions

- What sustained qualifying bounty volume opens the `demand-side` direct-service gate — measurement window, threshold, and settlement-quality evidence policy? The requirement that the gate be executable and versioned is already specified; only these parameters are missing (blocks task 4.3).
- Which licenses enter the curated registry, and what counsel process approves additions?
- What privacy/PII scanning gate precedes public dataset use?
- What minimum shuttle fill, forward collateral, slashing thresholds, bucket sizes, and training thresholds become defaults?
- Is the first appliance carrier built in-house or bounty-first?
- What exact capability-key dimensions are required after the initial price index?
- What verification model can make F3 swarm fraud more expensive than honest work?
- What redemption windows, governance rights, treasury policy, genesis assets, and mixed-asset redemption posture—if any—receive counsel approval?

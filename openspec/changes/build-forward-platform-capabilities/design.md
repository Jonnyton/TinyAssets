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

- Which licenses enter the curated registry, and what counsel process approves additions?
- What privacy/PII scanning gate precedes public dataset use?
- What minimum shuttle fill, forward collateral, slashing thresholds, bucket sizes, and training thresholds become defaults?
- Is the first appliance carrier built in-house or bounty-first?
- What exact capability-key dimensions are required after the initial price index?
- What verification model can make F3 swarm fraud more expensive than honest work?
- What redemption windows, governance rights, treasury policy, genesis assets, and mixed-asset redemption posture—if any—receive counsel approval?

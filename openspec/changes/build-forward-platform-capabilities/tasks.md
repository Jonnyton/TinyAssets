> **Task classification (2026-07-24).** This is an umbrella. Its own decision D1
> forbids implementing an independently deployable slice through it: each slice
> must first become a narrower OpenSpec change. So every task below that reads
> "Implement …" is really a **successor-outcome tracker** — it is completed by its
> successor change landing, not by writing runtime code in this lane. Each such
> task now names its owner (or records that it has none yet) and its blocker.
> **Count as of 2026-07-24: 19 tasks, 5 complete, 14 remaining** (3.1–3.4, 4.1–4.4,
> 5.1–5.3, 6.1–6.3). Two were completed in this lane (1.2, 1.3); 0.1 was already
> checked on `origin/main` and was only re-stamped with fresh evidence.
> Cross-family review: Codex, 2026-07-24, round 1 `VERDICT adapt` (seven findings
> applied); round 2 `VERDICT adapt` — D9 normativity, task 4.3's citation, task
> 4.4's blocker, and a stale "13 remaining" count, all applied 2026-07-24.

## 0. Hard prerequisite

- [x] 0.1 Do not apply, sync, or archive this umbrella until `reclassify-forward-vision-specs` has synced its canonical additions, physically removed all eight superseded canonical capability directories, passed strict validation, landed, and archived.
  - Verified 2026-07-24: commit `bfb61185` (ancestor of `origin/main`) added the archived change plus the canonical `external-effect-receipts` / `paid-market-economy` additions and deleted all eight forward-only capability directories; the archive is at `openspec/changes/archive/2026-07-22-reclassify-forward-vision-specs`; `openspec validate --all --strict` passes. Archive existence alone would not have proven ancestry — the git evidence does.

## 1. Slice the umbrella before implementation

- [x] 1.1 Delegate the complete versioned schema-history and single authenticated logical-accounting transport slice to `paid-market-track-e-wave-2-transport`; physically release the umbrella `paid-market-economy` delta and require the successor to preserve the single-path and differential-oracle guarantees without treating database accounting as real-fund authority.
- [x] 1.2 Create a successor change for outbound boundary grants, action caps, credential-blind adapters, inboxes, typed artifacts, and destination-reconciled effect batches.
  - Done 2026-07-24: `openspec/changes/outbound-boundary-layer/`. The `boundary-layer` delta was physically moved (not copied) so it keeps exactly one active owner, matching 1.1 and 2.1. The successor additionally carries RENAMED + MODIFIED deltas against `external-effect-receipts` and `external-effect-adapters`, because the target's system-derived idempotency contradicts shipped caller-hint semantics and must not sync without them.
- [x] 1.3 Record explicit Depends edges from every later slice to its transaction, boundary, identity, distributed-execution, gate, and provenance prerequisites; every market slice depends on the `paid-market-economy` transaction owner.
  - Done 2026-07-24: `design.md` § *Slice dependency ledger*. Slices with no successor change are marked `unassigned`, which is itself the D1 blocker.

## 2. Live pricing and capacity forwards

- [x] 2.1 Delegate the complete live-price and capacity-forward slice to `paid-market-live-price-discovery`; that successor owns preservation, implementation, acceptance, sync, and archive of the removed capability delta.

## 3. Data and training commons

- [ ] 3.1 **Successor-outcome tracker — owner unassigned.** Immutable dataset manifests, scoped reference grants, curated fail-closed license admission, contamination/privacy/quality gates, and exact contributor accounting. Blocked by D1 (no `data-commons` successor change exists) and by the STATUS `host-decision` row for target-spec PLAN conflicts, since manifest storage and private-data placement are two of the four positions that row is waiting on. Do not implement in this lane.
- [ ] 3.2 **Successor-outcome tracker — owner unassigned.** Dataset Forge as a provenance-preserving shared workflow with manifest-complete outputs. Blocked by D1 and by 3.1: Forge cannot emit a manifest before the manifest contract exists. Its intake and lineage substructure is non-monetary, so it is not blocked on the transaction transport.
- [ ] 3.3 **Successor-outcome tracker — owner unassigned.** F1 and atomic F2 training instruments, durable checkpoint attestation/payment, goal/gate bonuses, capability minting, and buyer-data provenance. Blocked by D1, by 3.1 (mint invokes the data-commons validation contract), by the unbuilt transaction transport in `paid-market-track-e-wave-2-transport`, and by `distributed-execution` for attestation and execution evidence.
- [ ] 3.4 **Standing prohibition, not a completable task.** Keep F3 dark until a separate opposite-provider research review and successor change define its verification model and acceptance proof. Verified 2026-07-24: no F3 successor or research review exists, `paid-market-training` requires F3 to stay behind a research-reviewed flag and to never block F1/F2, and `paid-market-live-price-discovery` refuses F3 swarm execution outright. The prohibition holds today; it cannot be checked off, because checking it off would mean F3 shipped.

## 4. Demand and physical production

- [ ] 4.1 **Successor-outcome tracker — owner unassigned.** Durable standing goals, timezone-aware inbox scheduling, archetype onboarding outcomes, and per-universe operational metrics. Blocked by D1's successor rule — **not** by the money transport: D3 names price, forward, training, data, pool, and hardware as transaction consumers, and standing-goal/onboarding work is non-monetary. Its real prerequisites are `boundary-layer` for inbox ingress, `daemon-runtime-and-dispatch` for the heartbeat, and `shared-goals-and-convergence` for the Goal primitive. This is the cheapest slice to promote next.
- [ ] 4.2 **Successor-outcome tracker — owner unassigned.** Goal-bounty posting, exact escrow/tranches, atomic first-winner claims, gate verification, expiry/refund, fee/attribution, and license composition. Blocked by D1 and by the unbuilt transaction transport — a bounty is money released by a frozen machine gate, so unlike 4.1 it genuinely needs the transport plus the gate capabilities.
- [ ] 4.3 **Blocked on a host/founder decision.** Define and prove the measured bounty-volume gate before enabling any direct universe-service product. Per D6 the gate must be executable and observed rather than asserted, and `demand-side` § *Direct universe services wait for measured bounty demand* already requires the window, threshold, and evidence to be versioned. What is missing is the parameter values themselves — no window, threshold, or settlement-quality evidence policy is specified anywhere in this change, and choosing them is a product decision, not a spec-authoring one. Added to `design.md` § *Open Questions* 2026-07-24 (cross-family round 2 found this task citing an Open Questions entry that did not yet exist). Proving the gate additionally requires 4.2 to be live and emitting measurable volume.
- [ ] 4.4 **Successor-outcome tracker — owner unassigned; scope corrected 2026-07-24.** Verified hardware-ladder admission, shuttle lifecycle, code-CAD artifacts, fabrication QA/settlement outcomes, honesty enforcement, and safety gates. Fabrication *arithmetic* left this task: total-first integer quotes, band exclusion, deterministic ranking, break-even, and conserved settlement are already canonical pure oracles in `paid-market-economy`, and quote publication/provenance/freshness/ranking surfaces belong to `paid-market-live-price-discovery`. The `hardware-creation` delta now delegates both by reference. Blocked by D1 and by its exact ledger dependencies (`design.md` § *Slice dependency ledger*): directly on the transaction owner, the price owner, `boundary-layer`, `data-commons`, `pooled-training-ownership`, and the gate capabilities; transitively on `paid-market-training` through pooled ownership. It has **no** `demand-side` or `token-architecture` dependency — neither the ledger nor the `hardware-creation` delta establishes one, and D1's preferred ordering is not itself a dependency (corrected 2026-07-24; the earlier "every slice above it" was untrue).

## 5. Ownership and token gates

- [ ] 5.1 **Successor-outcome tracker — owner unassigned.** Persisted pool arrival order, frozen bounded lineage, exact revenue distribution, terminal refunds, disclosed terms, and explicit v1 transfer refusal. Blocked by D1, by the unbuilt transaction transport, and by 3.3 — ownership is a function of accepted contributions to a training instrument and is frozen at that instrument's mint.
- [ ] 5.2 **Host/counsel action — no provider can complete this.** Obtain written counsel decisions for pooled ownership, public TINY, marketing, governance, jurisdiction, redemption, treasury policy, and mixed-asset liquidity. D7 makes these hard dependencies; the `token-architecture` delta keeps every public surface dark until they are recorded.
- [ ] 5.3 **Blocked by 5.2.** Only after 5.2, create a successor change for audited valuation, genesis handling, public mint/redemption, reserve capacity, and dark-by-default launch controls.

## 6. System acceptance

- [ ] 6.1 **Per-successor obligation, not umbrella work.** For every successor slice, run focused unit/integration/security tests plus the full §14 concurrency/load matrix before treating it as implemented. Each successor's own tasks file carries this; `outbound-boundary-layer` task 6.2 is the current instance.
- [ ] 6.2 **Per-successor obligation, not umbrella work.** For every public slice, complete live connector canaries, a real rendered chatbot conversation, and freshness-stamped post-fix clean-user evidence.
- [ ] 6.3 **Terminal task — completable only when everything above is.** Sync and archive each completed successor change independently; archive this umbrella only after every requirement is canonical and every task above is complete. As of 2026-07-24 three of nine slices have owners and none have landed, so the umbrella stays active.

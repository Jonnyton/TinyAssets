# OpenSpec Forward-Vision Requirement Classification

**Date:** 2026-07-22

**Environment:** Windows worktree at `origin/main` `ae4638348e29c03e5f3cafffa519667e8b5a3b56`

**Scope:** Eight canonical capabilities introduced by `4fa897b738b1347dd416b85ec932c28fb6415aa5`

**Purpose:** Restore `openspec/specs/` to as-built truth without discarding target architecture.

## Verdict

All eight files mix shipped pure computation or adjacent primitives with absent end-to-end behavior. Several requirements are directly contradicted by `main`. None of the top-level requirements in `boundary-layer`, `data-commons`, or `demand-side` is wholly built. The Track E-I files contain built scenarios, but their capability-level product and transport claims are partial or future.

The safe reconciliation is:

1. Remove the eight forward-heavy capability files from canonical truth.
2. Expand `paid-market-economy` with the exact I/O-free helper contracts that are shipped.
3. Add `external-effect-receipts` for current per-sink consent/reservation semantics.
4. Preserve every removed target under active change `build-forward-platform-capabilities`.

This is a truth correction, not a feature cancellation.

## Classification rubric

| Label | Meaning |
|---|---|
| BUILT | The complete requirement or scenario is landed, callable where claimed, and supported by direct evidence. |
| PARTIAL | A meaningful named subset exists, but required persistence, transport, enforcement, or lifecycle is absent. |
| FUTURE | No integrated implementation exists. |
| CONTRADICTED | Landed behavior materially violates the requirement text. |

Prototype migrations and design notes are evidence of intent, not deployed behavior. An isolated pure helper proves only its own input/output contract.

## Boundary layer

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| MCP both directions; connections live in resource ledger | PARTIAL | bind connection: FUTURE | Inbound remote MCP is canonical in `openspec/specs/live-mcp-connector-surface/spec.md`; `tinyassets/connector_catalog.py` is an inward catalog. No outbound client, grant binding, or resource ledger exists. |
| Action caps are the second autonomy column | FUTURE | high-value hold: FUTURE | `tinyassets/effectors/authority.py` and `tinyassets/storage/effector_consents.py` gate authority, but no numeric per-action cap or payment threshold exists. |
| Exactly-once effects | PARTIAL | retried invoice: PARTIAL; atomic batch: FUTURE | `tinyassets/storage/external_write_receipts.py:221-607` atomically reserves and finalizes caller-hint/sink rows for selected effectors. No required goal/schedule/item hash, universal effect journal, destination guarantee, or whole-batch hold exists. |
| Human goal inbox and timezone scheduling | PARTIAL | dropped inbox item: FUTURE | `tinyassets/scheduler.py` persists schedules, already owned by `daemon-runtime-and-dispatch`, but uses host local time and has no goal inbox/email/webhook ingestion. |
| Adapters never see credentials | FUTURE | malicious adapter: FUTURE | No commons proxy/adapter runtime exists. Current trusted effectors resolve secrets daemon-side, which is adjacent infrastructure rather than the specified adapter model. |
| Non-MCP APIs use commons adapters | FUTURE | connect without platform ticket: FUTURE | No OpenAPI-to-MCP generator, reviewed adapter registry, or binding runtime exists. |
| Addressable inboxes and typed artifacts fail at design time | PARTIAL | type mismatch: CONTRADICTED | `tinyassets/branches.py` states `state_schema` is unvalidated; `tinyassets/graph_compiler.py:457-463` maps unknown types to `Any`, locked by `tests/test_branches.py:642`. No content-addressed MIME/schema artifact flow exists. |

**Canonical owners after reconciliation:** inbound MCP stays in `live-mcp-connector-surface`; schedules stay in `daemon-runtime-and-dispatch`; graph behavior stays in `graph-execution-substrate`; shipped consent/receipt behavior moves to `external-effect-receipts`.

## Data commons

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Content-addressed reference-only dataset asset | FUTURE | reference, not bytes: FUTURE | No dataset manifest registry, manifest-hash asset, or access-grant transport exists. |
| License propagation is fail-closed | PARTIAL | unknown license: PARTIAL; no-derivatives: PARTIAL | `tinyassets/paid_market/license_terms.py:86-134` implements a pure fail-closed lattice. `training.py` never calls it, so no run-start or mint enforcement exists. |
| Data pricing differs from compute pricing | FUTURE | realized revenue share: FUTURE | Generic exact pool/ledger helpers exist, but no dataset price mode or `data_ppm` path exists. |
| Contamination and quality gate use | FUTURE | contamination precedes use: FUTURE | No dataset contamination, PII, or quality admission pipeline exists. |
| Contributor attribution uses exact apportionment | PARTIAL | exact payout: PARTIAL | `tinyassets/paid_market/pool.py:130` implements `apportion_exact`; no dataset contributor table, campaign, earnings event, or settlement exists. |
| Dataset Forge workflow | FUTURE | synthetic inheritance: FUTURE; no manifest/no run: FUTURE | No Forge, example-level provenance manifest, or integrated admission gate exists. |

**Canonical owner after reconciliation:** pure license and apportionment behavior lives only in `paid-market-economy`; every dataset lifecycle target remains active future work.

## Demand side

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Standing goal is native demand unit | FUTURE | demand survives absent sessions: FUTURE | `tinyassets/subscriptions.py` and `tinyassets/producers/goal_pool.py` support shared Goals, not a standing-goal model, forecast, budget, or absent-user demand lifecycle. |
| Binding product/onboarding rules | FUTURE | onboarding ends in running goal: FUTURE | No archetype goal count, week-one outcome gate, terminal running-goal state, or per-universe onboarding metric exists; absence alone does not prove contradictory behavior. |
| Goal bounties transfer demand | FUTURE | money summons work: FUTURE | Goal-pool bounty requirements are passive YAML metadata; no bounty post, discovery, claim, or settlement primitive exists. |
| Six pinned bounty composition rules | FUTURE | machine gate: FUTURE; first verified winner: FUTURE | Escrow, exact apportionment, fee, gate, dispute, and license helpers exist separately. No composed bounty boundary, tranche CAS, arbitration, expiry, or drain exists. |
| Direct services deferred behind bounties | PARTIAL | wait for volume: PARTIAL | Direct services are absent, but no executable measured bounty-volume gate exists. `distributed-execution` is authenticated owner-daemon work, not a paid service implementation. |

**Canonical owners after reconciliation:** subscriptions/shared Goals remain in `shared-goals-and-convergence`; schedules and generic market primitives remain in existing owners. Standing goals, onboarding, bounties, and the measured service gate remain active future work.

## Hardware creation

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Accessible ladder and honesty clause | PARTIAL | FPGA before shuttle: CONTRADICTED | Generic gates exist, but `tinyassets/paid_market/shuttle.py:64` accepts numeric design data only and can allocate without FPGA evidence. |
| Shuttle economics | PARTIAL | removing design does not reprice survivors: CONTRADICTED | `allocate_shuttle` floors used-area cost and reruns largest-remainder apportionment. Counterexample: die 6, cost 10, `{a:1,z:3}` gives `z=4`; dropping `a` gives `z=5`, with both sets meeting 50% fill. The existing divisible-value test is insufficient. |
| Verification mints hardware capability | FUTURE | validated design becomes class: FUTURE | No bring-up-to-capability or hardware instrument integration exists. |
| Physical fabrication | PARTIAL | uncovered shipping excluded: BUILT | Quote, shipping-band rejection, deterministic ranking, and settlement are implemented at `fabrication.py:68-276`; commons artifacts, paid requests, and QA gates are absent. |
| Parametric programs, not meshes | FUTURE | source is artifact: FUTURE | No code-CAD artifact or build-output admission contract exists. |
| Three-stage pricing query | PARTIAL | identical cross-surface break-even: FUTURE | `break_even_units` is built; no versioned three-stage read payload or consuming public surface exists. |
| Garage silicon honesty | FUTURE | no compute-class claim: FUTURE | No enforceable listing or copy surface exists. |
| Safety-documentation gate | FUTURE | missing safety blocks listing: FUTURE | No hazardous-process listing validator or safety schema exists. |

**Canonical owner after reconciliation:** pure shuttle and fabrication arithmetic moves to `paid-market-economy`; all workflow, copy, and safety behavior remains active future work.

## Paid-market price index and forwards

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| All money moves through `market.apply_tx` | CONTRADICTED | single transport: CONTRADICTED; oracle validation: FUTURE | Prototype RPC exists in migration 008, but `tinyassets/api/market.py:453-710` directly opens SQLite and invokes payment actions. No equivalence suite exists. |
| Token-normalized settlement | PARTIAL | missing counts rejected: FUTURE; inflated counts disputed: FUTURE | Prototype migration 006 adds nullable columns and explicitly defers enforcement; no completion boundary uses them. |
| Composite spot quote preserves liveness | PARTIAL | zero-volume ceiling: PARTIAL; fetch failure: FUTURE | `index.py:223-290` computes a caller-fed quote, but has one global timestamp, optional ceiling, no feed, stale store, or failure path. |
| Public cached HTTP/MCP quote | FUTURE | MCP text block: FUTURE | No `/v1/price`, `/v1/prices`, `/v1/curve`, or price MCP tool exists. |
| Thin-market per-user manipulation cap | CONTRADICTED | self-dealt dominance: CONTRADICTED | `index.py:109-220` caps direction-insensitive counterparty pairs, not users; one user can split across pairs. |
| Standard capacity forwards | PARTIAL | lowest open ask: FUTURE | `buckets.py` and `forwards.py` implement pure UTC buckets, sizes, and state validation; no post, purchase, book, or published ask exists. |
| Demand-relative exact settlement | PARTIAL overall | buyer no-show: BUILT; threshold-only slash: BUILT | `forwards.py:167-252` and focused tests prove the pure oracle; no transport or persistence invokes it. |
| Uniform buyer caps | FUTURE | machine-readable rejection: FUTURE | No `price_cap` or `spend_cap` request path exists. |
| Collateral by construction | PARTIAL | post locks collateral: FUTURE | `collateral_micros` and settlement outputs exist; draft SQL has a column; no order-post lock lifecycle exists. |
| Privacy-gated demand signal | FUTURE | dark by default: FUTURE | No flag or signal surface exists. |
| Cash/secondary instruments excluded | PARTIAL | explicit refusal: FUTURE | The pure state machine has no such transition, but no callable boundary can refuse the request. |

**Canonical owner after reconciliation:** pair-capped index, bucket, ceiling, forward-state, collateral, and settlement oracles live in `paid-market-economy`; all feed, transaction, order, cap, privacy, and refusal behavior remains active future work.

## Paid-market training

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Reuses hardened forward properties | PARTIAL overall | early cancel/full verified: BUILT | `training.py:91-179` implements the pure trusted-count oracle; no transport invokes it. |
| F1/F2/F3 ladder | FUTURE | atomic F2: FUTURE; gated F3: FUTURE | No instrument tier, gang lifecycle, swarm coordinator, or F3 flag exists. |
| Checkpoint settlement | PARTIAL | missed checkpoint: BUILT | Exact math is built, but `training.py:18-21` explicitly delegates attestation to an absent transport; no streamed release exists. |
| Fraud costs more than honest work | FUTURE | fraudulent checkpoint rejected: FUTURE | No attestation chain, continuity check, random re-execution, or held-out evaluation layer exists. |
| Gates are native training abstraction | FUTURE | base plus bonus: FUTURE | Goals/gates exist elsewhere but have no training instrument or payment integration. |
| Mint with license propagation | PARTIAL | Llama terms: PARTIAL | Pure `compose_terms` is built and tested; no run completion, capability mint, or market listing invokes it. |
| Buyer-supplied Wave 1 data | FUTURE | no data marketplace: FUTURE | No training request transport or URI/hash provenance contract exists. |

**Canonical owner after reconciliation:** checkpoint settlement and declared-license composition live in `paid-market-economy`; instruments, attestation, gates, minting, and data provenance remain active future work.

## Pooled training ownership

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Exact pool math | PARTIAL | no leakage: BUILT; persisted order: PARTIAL | `pool.py:74-169` conserves ordered caller inputs and exact apportionment; no arrival-order store exists. |
| Lineage-first revenue split | PARTIAL | derived base paid: PARTIAL | `distribute_revenue` computes one caller-supplied split; frozen mint-time lineage and recurring event wiring are absent. |
| Non-transferable v1 ownership | FUTURE | transfer refused: FUTURE | No minted ownership table or callable transfer/refusal surface exists. |
| Risk and terminal refunds | PARTIAL | terminal unspent refund: FUTURE | Refund math exists, but no terms surface or terminal training-run integration exists. |

**Canonical owner after reconciliation:** ordered funding, apportionment, and single-event revenue math live in `paid-market-economy`; persistence, ownership, terms, and lifecycle remain active future work.

## Token architecture

| Requirement | Requirement class | Scenario class | Direct evidence and outcome |
|---|---|---|---|
| Stablecoin/TINY wall | CONTRADICTED | market import excludes fund: CONTRADICTED | Current settlement defaults to internal `MicroToken` (`payments/funding.py`, `settlement_backend.py`), and `tinyassets/paid_market/__init__.py` imports `fund.py`. |
| NAV-only mint/redeem | CONTRADICTED as written | non-profitable round trip: BUILT | `fund.py:80-266` implements safe floor arithmetic, but the spec says pre-seeded AUM is priced into first mint while hardened code explicitly refuses AUM with zero supply. |
| Realized-cash-flow valuation | PARTIAL | illiquid value excluded: FUTURE | `FundState` accepts caller-computed AUM; no valuation ledger, mark policy, or reporting job exists. |
| Mixed-asset rules | PARTIAL | fee/wind-down arithmetic: BUILT | Fee, capacity, and exact wind-down helpers exist; no live price, liquidity product, treasury allocation, founder restriction, or public surface exists. |

**Canonical owner after reconciliation:** safe treasury-internal fund arithmetic, including explicit pre-seeded-state refusal, lives in `paid-market-economy`; settlement separation, valuation, liquidity, public token, and legal behavior remain active future work.

## Cross-capability collision findings

- `paid-market-economy` already claims the complete `tinyassets/paid_market/` package as an I/O-free library with no live money transport. The five Track E-I specs duplicated that owner while implying product integration.
- `data-commons` license propagation and `paid-market-training` mint propagation duplicated one pure helper and both overstated enforcement. One canonical library requirement now owns it.
- Prototype migration 007 includes `delivered` and `defaulted` states, while the shipped `ForwardState` represents terminal default inside `settled`; the prototype is not canonical behavior.
- `distributed-execution` owns authenticated execution authority and staged rollout, not market pricing, orders, or settlement formulas.
- No pre-existing active change owns the removed boundary, data, demand, hardware, market, training, ownership, or token targets.

## Verification evidence

- `python -m pytest -q tests/test_paid_market_core.py tests/test_match_scale.py` passed **180 tests** on 2026-07-22 in the Windows worktree.
- The consent, receipt, soul-authority, Twitter, and Windows-desktop suites passed **102 tests**; the wiki write-back suite passed **6 tests with 1 deselected** after diagnosis.
- The initial combined run passed **288 tests and failed 1 pre-existing rename assertion**: `test_wiki_write_back_appends_section_and_records_receipt` expects the historical marker `workflow-wiki-write-back`, while unchanged production code emits `tinyassets-wiki-write-back`. This lane changes no runtime/test code and does not use that marker as spec evidence.
- Independent audits also ran focused subsets: 58 paid-market tests passed for pool/shuttle/fabrication/fund families; 13 selected license/apportionment cases passed. Those narrower runs are supporting evidence, not substitutes for the required focused gate.
- Receipt/authority verification must include `tests/test_effector_consents.py`, `tests/test_external_write_phase_2.py`, `tests/test_external_write_phase_2_atomicity.py`, `tests/test_soul_scoped_effect_authority.py`, and the affected effector suites.
- The Windows-host-killing `tests/test_uptime_canary_layer2.py` was not run and must not be run through Codex on Windows.
- Independent semantic review ran three passes. It corrected false bucket, shuttle, matching, ledger, and delivery wording; repaired ownership and sequencing; restored every omitted binding subclause; and finished **CLEAN** with strict validation at 41/41.
- The normal `openspec archive` sync path stopped before writing because removing every requirement from an intermediate capability produces an invalid empty spec. The reviewed canonical result was therefore applied explicitly, the eight empty capability directories were removed, and the completed change was archived with `--skip-specs`.
- Final canonical proof passed on 2026-07-22: strict validation passed for the complete OpenSpec tree and the active future change; all 10 paid-market and 4 external-effect added requirement headings occur exactly once canonically; all eight superseded canonical directories are absent; and the archive and future lanes are present.

## Durable ownership outcome

| Behavior class | Owner after reconciliation |
|---|---|
| Shipped inbound MCP, schedules, shared Goals, graph compilation | Existing canonical capability owners |
| Shipped consent/soul-authority/receipt subset | `external-effect-receipts` canonical spec |
| Shipped pure market computations | `paid-market-economy` canonical spec |
| Unbuilt full-platform outcomes | Active `build-forward-platform-capabilities` change |
| Architecture and rationale | `PLAN.md` and referenced design decisions |

The classification is complete only when strict validation proves the canonical tree contains no removed forward requirement and the active change contains every mapped future outcome.

# Track F — Training Market: Fine-Tuning to Pretraining (Full-Stack Democratization)

**Date:** 2026-07-08
**Author:** founder + Claude (design session)
**Status:** Dispatch-ready design spec. Settlement math implemented and tested (`tinyassets/paid_market/training.py`, invariants inherited from the adversarially-reviewed forwards core). Consumes Track E Waves 3–4 (price index, capacity forwards, escrow/collateral machinery).
**Mission framing:** users can already ground-up design the harness (any node, any graph) and pick a model to run it. Track F closes the remaining gap: users design, train, and own their **own models** — democratizing the stack from harness to hardware.

---

## 0. Why training is a separate market (and why it isn't a third codebase)

Inference pricing fails for training on three axes: the **unit** (device-hours of a hardware class, not tokens), **fungibility** (a training run is stateful — it cannot hop sellers mid-run without checkpoint transfer), and **duration** (hours-to-weeks; a per-second spot price is meaningless for an uninterruptible job).

But structurally the training market is the **capacity-forward machinery with a different instrument and a different settlement rhythm**: seller-posted, collateralized, window-bound promises — settled per verified checkpoint instead of once at window end. The hardened properties carry over unchanged (exact conservation, pro-rata payment with threshold-gated slashing only, demand-relative obligation so buyer cancellation can't grief sellers, slash-to-buyer never treasury). All four are enforced in code with a 10k-case conservation sweep.

## 1. Instruments — three tiers

The instrument key: **hardware class × interconnect tier × gang size × window**.

### Tier F1 — Fine-tune windows (Wave 1; ship first)
Single-node LoRA/QLoRA/full-FT on open bases. Instrument example: `1×48GB-class × standalone × 24h`. This is what most users mean by "train my own LLM": hours not weeks, cheap enough that failed runs don't hurt, fits near-existing forward buckets. Sellers are the same desktop/rig population as batch inference.

### Tier F2 — Colocated pretraining clusters (Wave 2)
A single seller with a real cluster posts **gang windows**: `8×H100-class × NVLink × 72h`, up to `N×node × IB/RoCE × 2w`. Gang scheduling is all-or-nothing: partial allocation of a gang is worthless, so the instrument sells as one unit and the state machine has no partial-fill path. This is how serious pretraining gets priced — professional sellers, small counterparty set, collateral meaningful.

### Tier F3 — Swarm pretraining (Wave 3; the democratization tier)
Communication-efficient distributed training (DiLoCo-family; proven at 10B+ scale by the INTELLECT runs) allows pretraining across many internet-connected heterogeneous sellers with infrequent synchronization. The instrument inverts: the **run** is the market, sellers join it. Contribution is metered per verified local **round** (the swarm analogue of a checkpoint), settled with the same math — each seller's `checkpoints_scheduled` is the rounds they committed to, `checkpoints_verified` the rounds accepted by the coordinator. Honest maturity note: F3's verification and coordinator design are research-adjacent; it ships behind its own flag and never blocks F1/F2.

**Honesty clause for the docs:** a volunteer swarm will not pretrain a frontier-scale model; it *will* pretrain small-and-mid open models, and F2 prices real clusters for everything beyond. Democratization means the whole ladder is priceable and accessible — not that a phone farm rivals a datacenter.

## 2. Settlement — checkpoint-based (implemented)

`settle_training_window(price_total, checkpoints_contracted, checkpoints_scheduled, checkpoints_verified, collateral_pct)`:

- **contracted** — instrument total (e.g. 24 checkpoints / 72h)
- **scheduled** — checkpoints the run legitimately reached (buyer cancel or buyer-side crash caps this; the B-1 lesson applied to training: buyer early-cancel with all reached checkpoints verified pays in full — the window was reserved)
- **verified** — delivered **and** attestation-passed

`seller_gross = total × (contracted − unserved) / contracted` where `unserved = scheduled − verified`; refund is exact remainder; slash pro-rata to `unserved/contracted` only when `verified/scheduled` falls below threshold (training default: 100% — one missed checkpoint in a coarse schedule already matters; tunable per instrument class). Escrow releases MAY be streamed per checkpoint in transport; the module computes the end-state the stream must sum to.

## 3. Verification — the honest hard part

Redundant execution (the inference trick) is unaffordable for training. A checkpoint is verified by layered cheaper signals: **artifact attestation** (weights hash + optimizer-state hash chained to the prior checkpoint), **loss-curve continuity** (a checkpoint that doesn't plausibly descend from its parent is flagged), **spot re-execution** of randomly sampled *short* segments (replay N steps from checkpoint k, compare within tolerance — affordable because segments are short), and **eval probes** on held-out slices. None is conclusive alone; together they price fraud above honest work for F1/F2. F3 inherits the swarm literature's gradient/round validation and is flagged experimental until its acceptance checks are specified. Trust boundary is explicit (review finding B-5): the settlement math trusts verified counts; the attestation layer makes them trustworthy.

## 4. Gates are the native training abstraction

"Train model X to quality Y" is a **goal**; eval benchmarks are its **gate ladder**; staged payment per gate claim is machinery TinyAssets already ships (`gates define_ladder / claim / stake_bonus`). Track F couples them: a training run binds to a goal, checkpoints claim gates with eval evidence, and buyers can structure payment as base (per-checkpoint) + bonus (per-gate). Most platforms would have to invent milestone-based training contracts; here it's a `goal_id` field.

## 5. Capability minting — closing the loop

A completed run mints a **new capability**: `{weights_uri, weights_hash, base_model, training_provenance (data manifest hash, run ledger), license}`. License propagation is enforced at mint (Llama-derived weights carry Llama terms; Apache/MIT bases mint freely). The minted capability is immediately: (a) a priceable **inference instrument** on the Track E market, (b) referenceable by any commons node/branch design, (c) sellable/serveable by any host that pulls the weights. Train on the market → serve on the market → designs in the commons specify your model. That's the moment TinyAssets stops being a compute buyer's market and becomes a **model economy** — and it's also the demand flywheel: every minted model creates inference demand the spot index prices.

## 6. Data (scoped deliberately)

Wave 1 takes data as buyer-supplied URIs with a content hash in provenance — the market moves compute, not datasets. A data marketplace (licensing, dedup, contamination checks) is its own track; naming it here prevents Track F from swallowing it.

## 7. Waves

| Wave | Ships | Depends on |
|---|---|---|
| F-W1 | F1 fine-tune instruments + checkpoint settlement + capability minting + gate coupling | Track E W2 escrow |
| F-W2 | F2 gang windows (colocated clusters), streamed escrow, attestation v1 (hash-chain + segment replay) | F-W1 |
| F-W3 | F3 swarm pretraining, flag-gated; round-based contribution settlement | F-W2 + research review |

## 8. Out of scope (named)

Secondary trade of training windows; data marketplace (§6); frontier-scale swarm claims; cross-margin between training and inference collateral; model-quality insurance/warranties.

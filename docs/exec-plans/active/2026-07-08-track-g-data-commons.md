# Track G — Data Commons: Datasets as First-Class Assets

**Date:** 2026-07-08
**Author:** founder + Claude (design session)
**Status:** Dispatch-ready design spec. License-composition core implemented and tested (`tinyassets/paid_market/license_terms.py`, fail-closed; 119-test suite total). Composes with Tracks E (escrow/pricing), F (training, capability minting), H (apportionment for contributor payouts).

---

## 0. Why data is the last moat

Compute is fungible and priced (Track E/F). Capital is pooled (Track H). What incumbents still uniquely hold is **curated, licensed, deduplicated training data**. Track G makes datasets first-class TinyAssets: registered, provenanced, license-carrying, priceable, and attributable — so "you can rent GPUs" becomes "you can actually train something good, legally."

## 1. The dataset asset

A registered dataset = `{manifest_hash (content-addressed), size, modality, license_id (registry-resolved), provenance (source declarations, curation log), pricing_terms, contributor_shares}`. The manifest hash is the identity: the market moves *references*; bytes transfer seller→trainer directly (or via storage the platform never needs to own). Registration is declaration + curation review, not proof — the enforcement layer is license composition at training time plus dispute/moderation after.

## 2. License propagation (implemented, fail-closed)

Every training run declares its input license ids (base model + every dataset). `check_trainable` composes them as a restriction-union lattice and returns the terms the minted capability MUST carry:

- any `no_derivatives` input → run blocked before a single token trains
- any **unregistered license → blocked** (fail-closed: the expensive failure is minting a model the platform had no right to mint, not declining a run; registry additions go through curation/legal review, not code review)
- `share_alike` / `non_commercial` / named terms (Llama-style) propagate irrevocably into the minted capability, and Track H freezes them into the ownership record

Explicit scope: this enforces *declared* terms mechanically — it is not legal interpretation and cannot detect misdeclaration; curation and disputes own that.

## 3. Pricing data (it is not compute)

Data doesn't meter like tokens or device-hours. Three pricing modes per dataset, seller's choice:
- **Free/attribution** — commons datasets; usage still recorded in provenance
- **Per-run license fee** — flat fee escrowed at training start, released at run completion (reuses Track E escrow verbatim)
- **Revenue-share** — the dataset takes `data_ppm` of the minted model's revenue, wired as an additional attribution leg in Track H's `distribute_revenue` (the apportionment math already conserves across arbitrary legs)

Mode 3 is the interesting one: it lets data owners bet on models the way Track H lets funders bet on them — the dataset earns only if the model earns.

## 4. Contamination & quality (transport layer, named here)

Before a dataset is usable against a goal with a gate ladder, it passes a **contamination check** against that ladder's eval sets (n-gram/embedding overlap against held-out benchmarks) — otherwise gate claims are meaningless. Dedup within and across registered datasets is a curation service, priced as ordinary node work on the platform itself. Neither is pure math; both are Wave-2 transport with the check results recorded in provenance.

## 5. Contributor attribution

Datasets built by many contributors (scrapes, annotation campaigns, commons curation) carry `contributor_shares` — and payouts on any earning mode reuse `apportion_exact` unchanged. An annotation campaign is just a goal with gates; contributors' accepted work becomes their share weight. Nothing new to build.

## 5b. §G-Forge — Dataset expansion from a user seed (demo-critical, amended 2026-07-09)

**Design law applied: primitives + commons, never features.** Expansion is NOT a platform service — it is a commons workflow graph ("**Dataset Forge**" archetype, seeded pre-launch) composed entirely from existing primitives: seed intake → license-gated corpus fetch → style-conditioned synthesis (ordinary inference nodes, priced like any other) → dedup node → contamination gate → manifest emit. Hardcore users fork the forge and recompose it; vibe coders run the default and get "214 recipes → 48k examples" for free.

**The one new platform rule — provenance classes.** The dataset manifest records, per example: `user-seed` | `corpus[dataset_id]` | `synthetic[derived_from: ...]`. Synthetic examples **inherit the composed license terms of everything upstream of their generation** — the user's seed AND any corpus that conditioned the generating context — via the existing fail-closed `compose_terms` lattice. Consequences: synthesis conditioned only on the user's own seed is unambiguously the user's; synthesis conditioned on a share-alike corpus carries share-alike. `check_trainable` runs over the manifest's full provenance set before any training run starts. No manifest, no run.

**Quality is a gate ladder on the dataset itself** (dedup ratio, contamination pass against the goal's eval sets, seed-style adherence score) — existing gates machinery, no new primitives.

## 6. Waves

| Wave | Ships | Depends on |
|---|---|---|
| G-W1 | Dataset registry (manifest hash, license_id, per-example provenance classes §5b) + `check_trainable` over full manifest, wired into Track F run start · **seed the Dataset Forge commons graph** | F-W1 |
| G-W2 | Per-run fees + revenue-share legs; contamination check v1 | G-W1, H-W2 |
| G-W3 | Contributor campaigns + curation-as-node-work | G-W2 |

## 7. Out of scope

Hosting/serving dataset bytes; scraping tooling; legal interpretation of license text (registry is curated by humans + counsel); privacy/PII scanning (its own review before G-W1 ships publicly); data valuation.

---

*Session note (2026-07-08): with Track G, every layer named in the harness-to-hardware thesis has a spec, and every exactness-critical computation across E/F/G/H is implemented and tested (119 tests). The deliberate stopping point stands: further tracks add negative value until Wave 2 transport lands and this core is committed. The next unit of progress is execution, not design.*

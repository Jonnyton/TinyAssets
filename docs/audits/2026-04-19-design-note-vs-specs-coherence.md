# Design-Note vs Specs Coherence Audit

**Date:** 2026-04-19
**Scope:** `docs/design-notes/2026-04-18-full-platform-architecture.md` (§1–§31) against 11 specs in `docs/specs/`, 2 catalogs in `docs/catalogs/`, and the 3 prototype scaffolds (`prototype/full-platform-v0/`, `prototype/web-app-v0/`, `prototype/tinyassets-catalog-v0/`).
**Method:** section-by-section scan. Each cross-section labeled **MATCH / DRIFT / GAP / SURPLUS**. Drift items rank-ordered by load-bearing risk (schema + RPC names first).
**Constraint:** read-only audit. No design-note edits in this pass.

---

## 1. Inventory

**Design note:** §1–§31, ~2330 lines.
**Specs (11):** `#25 schema`, `#26 load-test`, `#27 gateway`, `#29 paid-market`, `#30 tray`, `#32 export-sync`, `#35 web app`, `#36 moderation`, `#53 remix+converge`, `#57 plan-B selfhost`, `#15 text-edits (injection-hallucination)`.
**Catalogs (2):** `node-type-taxonomy.md`, `privacy-principles-and-data-leak-taxonomy.md`.
**Prototypes:** `full-platform-v0` (schema + RLS + gateway + 10 e2e tests), `web-app-v0` (SvelteKit shell), `tinyassets-catalog-v0` (TinyAssets-catalog repo scaffold + sample BranchDefinitions).
**Runbooks + ops:** `SUCCESSION.md`, `launch-readiness-checklist.md`, Anthropic-catalog-submission plan, `moderation_rubric.md`.

---

## 2. Load-bearing drift (fix before next design fold)

### 2.1 Request-creation RPC name: `create_request` (design §20.4) vs `submit_request` (spec #27 §3.1) — **DRIFT**

Design note §20.4 defines `create_request(node_concept_ref, fulfillment_path, bid_amount?, instance_ref?, urgency?)`. Gateway spec §3.1 lists `submit_request(capability_id, inputs, bid_price?)`. **Same function, two names, two signature shapes.**

**Canonical:** spec #27's `submit_request` is the shipped RPC (it's in the scaffolded prototype's tool table and matches the schema's `request_inbox` column names directly: `capability_id`, `bid_price`). Design note §20.4 is stale.

**Recommended design-note edit:** rename `create_request` → `submit_request`; align signature to `(capability_id, inputs, bid_price?, fulfillment_path, visibility)`; keep §20 four-path framing but move it to a `fulfillment_path` parameter on `submit_request`, not a distinct RPC.

### 2.2 `discover_nodes` response: `real_world_outcomes` + `typical_fulfillment_pattern` + `parallel_eligible` + `top_n_rank` in design — **GAP in spec #25**

Design §15.1 defines a rich response block (quality signals, provenance, active_work, negative_signals, cross_domain, typical_fulfillment_pattern, real_world_outcomes, parallel_eligible, top_n_rank). Spec #25 §3 defines a leaner response (node metadata + ranking score + cross_domain flag). **The post-§15.1 fields from §§20, 24, 27 scenarios were added to the design but not fed back into the RPC spec.**

**Canonical:** design note (host-directive-backed). Spec #25 §3 needs to be extended.

**Recommended spec edit:** spec #25 §3 adds `real_world_outcomes`, `typical_fulfillment_pattern`, `parallel_eligible`, `top_n_rank` to the returned record. No schema migration needed — these are computed/derived fields. Track dev-day impact: ≤0.25 day to extend the RPC.

### 2.3 `nodes` schema — `primary_language`, `domain_ids uuid[]`, `node_type` — **GAP in spec #25**

Design introduces (Q13) `nodes.primary_language`, (Q14) `nodes.domain_ids uuid[]` + separate `domains` table, and (taxonomy catalog) a `node_type` axis. Spec #25 §1.2 `nodes` has `domain text` (single), no `primary_language`, no `node_type`. No `domains` table defined.

**Canonical:** design-note + node-type-taxonomy catalog are the direction. Spec #25 is out-of-date.

**Recommended spec edit:**
- Add `primary_language text` (ISO 639-1) on `nodes`.
- Migrate `nodes.domain text` → `nodes.domain_ids uuid[]` with GIN index; add `domains(domain_id, slug, display_name, description?, coined_by, coined_at, node_count)`.
- Add `nodes.node_type text` (CHECK against top-level taxonomy types: generator / transformer / validator / extractor / composer / ...).
- Per-language FTS views `nodes_fts_<lang>` for the ~15 common langs.
- Dev-day impact: ~0.25 day.

### 2.4 `host_pool` heartbeat column: `last_heartbeat` removed in design §14.5 + spec #25 §1.5 — but `last_heartbeat` appears in §10 Track A blurb — **minor drift**

Design §14.5 + spec #25 explicit: no `last_heartbeat` column; Presence derives online state. §10 Track A row says "schema for catalog + host-pool + requests + bids + ledger + comments + **presence**" — consistent. **OK.** No edit needed beyond occasional §5.4 text.

### 2.5 Settlement pseudocode: design §18.3 (locked hybrid) vs spec #29 §3 (three options A/B/C) — **DRIFT**

Design §18.3 + §18.6 define a hybrid: <$1 batched, ≥$1 on-chain, with self-hosted-zero-fee branch. Spec #29 §3 still presents **three candidate options** (A/B/C) and picks "A. Off-chain ledger + batched on-chain payout" for testnet MVP. Spec is pre-hybrid-resolution.

**Canonical:** design note hybrid (host-locked Q4-follow-up 2026-04-18).

**Recommended spec edit:** spec #29 §3 collapses the A/B/C table to the locked hybrid; §6 data-model already has `treasury_config` with tunable `fee_bps`; add `settlement_threshold_usd` config and the `settlement_mode enum('immediate','batched')` column on `ledger` that design §18.6 specifies. Dev-day: ~0.2 day edit, mostly docs + a schema column.

### 2.6 MCP tool surface — design introduces many tools not in spec #27 — **GAPs**

Design references (across §5/§15/§17/§20/§21/§23/§27/§28/§29/§30/§31) these MCP tools:

| Design reference | In spec #27 §3.1? |
|---|---|
| `discover_nodes` | YES |
| `update_node` | YES |
| `remix_node` | YES |
| `converge_nodes` (see 2.7 below) | YES |
| `submit_request` (vs design `create_request`) | YES |
| `claim_request`, `complete_request` | YES |
| `add_canon_from_path` | YES |
| `control_daemon` | YES |
| **`/feedback`** (§23.2) | **NO** |
| **`/node_authoring.*` family** (§27.3, ~8 sub-tools) | **NO** |
| **`get_privacy_principles` + `inspect_leak_risk`** (§31.2) | **NO** |
| **`claim_outcome`** (§24.5) | **NO** |
| **`export_my_data` + `delete_account` + `request_delete_confirmation`** (§21) | **NO** |
| **`subscribe_similar_in_progress`** (§15.3A) | **NO** |
| **`merge_domains`** (§15.8) | **NO** |
| **`connector_invoke`** (§28.1) | **NO** |
| **`flag_content` + `list_review_queue` + `resolve_flag` + `appeal_decision` + `resolve_appeal`** (§8) | YES in spec #36 §4, but NOT listed in gateway spec #27's tool table |

**Canonical:** design note is the direction; spec #27 is the gateway boundary + should enumerate all tools. Gap is an under-spec'd gateway surface.

**Recommended spec edit:** spec #27 §3.1 extends the MCP tool table to the full list above, each row naming handler + Supabase target (RPC or composite). Tools in spec #36 (moderation) route via the gateway; cross-reference to avoid duplication. Dev-day impact: ~0.3 day for table + wiring spec text; the RPCs themselves are implemented in the track that owns them (F/K/M/N).

### 2.7 `converge_nodes` signature — spec #53 vs design §15.3C — **DRIFT + GAP**

Design §15.3 defines `converge_nodes(source_ids[], target_name, rationale)` as a single RPC. Spec #53 §K.2 splits the workflow into **two RPCs**: `propose_convergence(source_ids, target_name, rationale) → proposal_id` and `ratify_convergence(proposal_id) → {merged, pending_ratifications}` with auto-execute on threshold.

**Canonical:** spec #53 is more implementation-realistic (community ratification is inherently multi-step). Design note §15.3C reads as if `converge_nodes` is synchronous — misleading.

**Recommended design-note edit:** §15.3C rewritten to reference the two-step flow: `propose_convergence` then `ratify_convergence`. Preserve the "requires editor ratification per source" semantic; surface the proposal/ratification/decision tables from spec #53 §K.3.

### 2.8 Paid-market visibility enum — `request_inbox.visibility` — **DRIFT**

Spec #25 §1.6 `request_inbox.visibility CHECK IN ('self','network','paid','public')` — four values. Design §5.1 (visibility enum for hosts) only lists three: `self` / `network` / `paid`. The `public` visibility value on requests (= open to any qualifying daemon, no bid required) appears in §20 "free queue" as **fulfillment_path='free_queue'** — not as a visibility.

**Canonical:** ambiguous. Spec #25 sets it as a visibility-enum value; design #20 treats it as a fulfillment-path value. Possibly these are **two different orthogonal axes** (host-side visibility vs request-side openness) and both should exist distinctly.

**Recommended design-note clarification:** explicit note that **host visibility (§5.1) and request visibility (spec #25 §1.6) are different namespaces** — hosts advertise `self|network|paid`; requests declare `self|network|paid|public` where `public` = "open to any qualifying daemon at zero-cost," matching design §20 fulfillment_path `free_queue`. Spec #25 text could also clarify this overlap.

---

## 3. Scenario-era directives — **GAP in specs (expected, not blocking)**

Scenarios A/B/C, Q20–Q21, and A/B/C-follow directives landed in design §24–§31 after the core 11 specs were drafted. The specs pre-date these directives. Expected GAPs:

| Design section | What's missing in specs | Priority |
|---|---|---|
| §24 Real-World-Effect Engine (product soul) | No spec names it as acceptance lens | Low — editorial |
| §24.4 `real_world_outcomes` signal block | Not in spec #25 §3 response | **HIGH** (see 2.2) |
| §25 Always-up automation (auto-rollback, S7 scenario) | Not in spec #27, #30, or #26 load-test spec's S-scenario list (S1–S6) | Medium — track J/M extension |
| §26 `Workflow: X` invocation + 3 user states | Spec #35 web-app §5 auth-flow doesn't explicitly name State 1 catalog-self-connect; just references "/connect onboarding" | Medium |
| §27 `/node_authoring.*` tool family | No gateway-tool-table entry, no sandbox-runtime spec | **HIGH** — needs track N spec |
| §27.5 parallel fan-out | Not in spec #27 or #29 dispatch logic; spec #25's `request_inbox` has no `fan_out` column | Medium |
| §28 connectors (GitHub/Gmail/Drive/Notion baseline) | No connector-track spec; web-app spec #35 §5 mentions GitHub OAuth but no tool-push | Medium — needs connector-track spec |
| §29 chatbot behavioral patterns (extensions hint array + transparent privacy narration) | `nodes.extensions` not in spec #25; chatbot-narration is a prompts/* concern, already in spec #27 §3.3 direction | Low |
| §30 real-world handoff pipeline (arXiv/DOI/GitHub Releases/ISBN auto-badge) | No handoff-track spec; connectors are a prerequisite | Medium — needs handoff-track spec |
| §31 privacy-principles catalog | **Catalog exists** (`docs/catalogs/privacy-principles-and-data-leak-taxonomy.md`). Catalog `id` values should match design §31.3's v1 list. | Verify alignment (see 4.2) |

**Dev-day implication:** specs for tracks N (vibe-coding authoring surface + sandbox), connectors, and handoffs are not yet drafted. These were part of design §10's +7–8.6d revision but don't have shipped spec documents. Queue new spec-drafting work or treat as "implementation-time" details.

---

## 4. Catalog-spec alignment

### 4.1 `node-type-taxonomy.md` — **SURPLUS that design note should absorb**

Catalog introduces `node_type` as a first-class axis (generator / transformer / validator / extractor / composer / router / gate / ingester / emitter / aggregator) alongside `domain`. The catalog's §1 rationale is strong and aligns with the convergent-commons vision. **Design note §2/§15 does not reference `node_type` as a schema field or discovery axis.**

**Recommended design-note edit:** add `node_type text` to the `nodes` schema sketch in §2.1 + §15.2, and add `node_type_hint` as an optional `discover_nodes` query parameter (parallel to `domain_hint`). Catalog stays the v1 vocabulary definition; schema just indexes it.

### 4.2 `privacy-principles-and-data-leak-taxonomy.md` — **partial MATCH, verify entries**

Design §31.3 proposed ~12 launch entries. Catalog is 201 lines — likely has the 12. Quick-check recommended: count the catalog's top-level entries, compare against design §31.3 list (MCP tool-call ingest / concept-layer publish / instance-layer store / connector push inbox / connector push public / real-world handoff / daemon subprocess / realtime broadcast / paid-bid announcement / catalog export / data export / account deletion).

**Recommended audit next step:** grep catalog for `id:` and cross-check 12 entries exist and IDs are stable for chatbot reference. If a subset is missing, flag as GAP.

---

## 5. Prototype drift

### 5.1 `prototype/full-platform-v0/` — **MATCH, tested**

Scaffolds schema + RLS + `discover_nodes` RPC + FastMCP gateway + 10 e2e tests. Commit `547ba63` explicitly aligns with spec #25. No drift found in sampling; full re-validation would require running the test suite.

### 5.2 `prototype/web-app-v0/` — **MATCH-ish**

SvelteKit shell scaffolded per spec #35. i18n `en.json` onboarding copy expanded in commit `ba18129`. Three-state A-follow onboarding language (State 1 catalog-self-connect) not explicitly verified in the copy — recommended sampling.

### 5.3 `prototype/tinyassets-catalog-v0/` — **SURPLUS, needs design-note absorption**

Scaffold includes `catalog/branches/` directory with 3 sample BranchDefinitions (`fantasy-scene-chapter-loop.yaml`, `invoice-batch-processor.yaml`, `research-paper-pipeline.yaml`). **BranchDefinition is a real shipped concept — composite multi-node workflow definitions — but design note §2/§15 schema does not define a `branches` or `branch_definitions` table.**

PLAN.md §"Project Thesis" references branches extensively ("Goal + Branch" pairing), and design §15 discusses branches in §15.2 indexes (`nodes_hot` precomputed per domain). But the schema sketch in §2 / spec #25 has no `branches` table.

**Recommended design-note + spec edit:** spec #25 adds a `branches` table (or `branch_definitions` — align name with prototype). Design §2/§15 references it as a first-class artifact kind. `artifact_field_visibility.artifact_kind` already lists `'branch'` so the privacy shape is ready; just the table is missing.

**Likely dev-day impact:** ~0.5 day — table + RLS + discover_branches RPC or extended `discover_nodes` to cover branches.

### 5.4 Sample nodes in `prototype/tinyassets-catalog-v0/catalog/nodes/` — **MATCH**

Four domain-realistic samples (commits `3e6e3c9`) look aligned with the `node` schema. Spot-check recommended to verify `concept`/`instance_ref` split respected.

---

## 6. Cross-spec drift

### 6.1 `#25 schema.version bigint` ↔ `#53 remix RPCs` — **MATCH**

Both agree `nodes.version` is append-monotonic, §14.3 CAS pattern. Remix RPCs in #53 correctly increment `remix_count` on parents via trigger (doesn't touch `version`). No drift.

### 6.2 `#25 `capabilities` table` ↔ `#29 paid-market capability refs` ↔ `#30 tray host registration` — **MATCH**

All three specs use `capability_id text` as a foreign-key reference to the same shared `capabilities` reference table. No drift.

### 6.3 `#36 moderation admin-pool` ↔ `#22 succession §22.1 row 1` ↔ `#39 §8 launch-day-zero (host + user-sim)` — **MATCH via split**

Spec #36 requires `admin_pool >= 2 for bus-factor` at real-currency cutover (commit `437ef0e`). Design §22.4 (post-#37-fold, post-Q17 2026-04-18) split gates into MVP (host + user-sim acceptable) vs real-currency-cutover (human co-signer required). These align cleanly when read together.

### 6.4 `#32 export sync` ↔ `#4 two-repo` (design §16.4) — **MATCH**

Spec #32 is built for the two-repo (`TinyAssets/` + `TinyAssets-catalog/`) split. Export Action + PR-ingest path both present. Aligns.

### 6.5 `#26 load-test S-scenarios` ↔ design §14.8 + §25.6 + §27.5 — **DRIFT**

Spec #26 enumerates S1–S6. Design §25.6 introduced **S7 (auto-healing rehearsal)**, §14.2 referenced S11 earlier but later §27.5 reintroduces as **S11 (parallel fan-out storm)**. Sampling shows S7 and S11 are design-only additions; spec #26 is S1–S6 only.

**Recommended spec #26 edit:** add S7 (auto-healing) + S11 (parallel-fan-out) scenarios. Also add S1b (remix contention) from spec #53 §I.3. Total becomes S1, S1b, S2–S7, S11 = 9 scenarios. Track J estimate already revised to 4–4.5 dev-days to cover.

---

## 7. Consolidated edit lists

### 7.1 Design-note edits (when next fold allowed)

1. §20.4 — rename `create_request` → `submit_request`; align signature to (capability_id, inputs, bid_price?, fulfillment_path, visibility).
2. §15.3C converge — rewrite to reference two-step `propose_convergence` + `ratify_convergence`.
3. §2 + §15 — add `node_type` schema field + discover_nodes query param (absorb taxonomy catalog).
4. §2 + §15 — add `branches`/`branch_definitions` table reference (absorb prototype scaffold).
5. §5.1 — clarify host-visibility vs request-visibility namespaces.
6. §10 / §11 — surface the not-yet-spec'd tracks: connectors, handoffs, vibe-coding sandbox (track N).

### 7.2 Spec edits (for dev dispatch)

1. **Spec #25** — add `primary_language`, `domain_ids uuid[]` + `domains` table, `node_type`, per-language FTS views, `branches` table, `ledger.settlement_mode`, `request_inbox.bid_amount_usd_cached`, `request_inbox.fan_out jsonb`, `nodes.extensions jsonb`. Extend `discover_nodes` §3 response with the 4 missing signal blocks. **~0.75 dev-day edit.**
2. **Spec #27** — extend §3.1 tool table with ~9 missing tools (/feedback, /node_authoring.*, get_privacy_principles, inspect_leak_risk, claim_outcome, export_my_data, delete_account, subscribe_similar_in_progress, merge_domains, connector_invoke). Reference #36 moderation tools. **~0.3 dev-day.**
3. **Spec #29** — collapse A/B/C options to locked hybrid (design §18.3); add `settlement_mode` column + `settlement_threshold_usd` config. **~0.2 dev-day.**
4. **Spec #26** — add S7, S1b, S11 scenarios. **~0.1 dev-day.**
5. **Spec #53** — ensure names align with design §15.3 cross-refs (mostly OK; §15.3C note).
6. **New specs needed:** Track N (vibe-coding authoring surface + sandbox runtime), Connector track (§28), Handoff track (§30). Assign to dev queue.

### 7.3 Catalog-verification next steps

1. Grep `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` for `id:` count; compare against design §31.3 list (12 entries).
2. Verify `docs/catalogs/node-type-taxonomy.md` type list matches design expectations once design absorbs `node_type` field.

---

## 8. Summary

**Overall coherence: strong** — 11 specs plus 2 catalogs plus 3 prototypes are mostly aligned with the design note's direction. Drift is concentrated in **post-scenario-fold additions** (§24–§31 introduced after early specs were drafted) and in **two rename/consolidation items** (create_request, converge_nodes split).

**Load-bearing drift items:** §2.1 (submit_request rename), §2.2 (discover_nodes response extension), §2.3 (schema additions for Q13/Q14/node_type), §2.6 (gateway tool-table gap), §2.7 (converge split), §5.3 (branches table missing).

**No blocking DRIFT between specs** — cross-spec consistency is good (§6 rows all MATCH or clarifiable).

**Recommended sequencing:** land design-note edits §7.1 first (≤1d navigator work), then dispatch spec edits §7.2 as parallel dev tasks (~1.5 dev-days total across 4 specs), then draft the 3 missing specs (Track N + Connectors + Handoffs) before any of those tracks' implementation work begins.

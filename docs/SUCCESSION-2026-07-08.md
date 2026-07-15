# SUCCESSION — Paid-Market Sprint Handoff (2026-07-08)

**From:** Claude Fable 5 design session (founder working remotely; Fable access ends after this period)
**To:** (1) the founder, for two admin actions; (2) Claude Opus / dev daemons, for all transport work
**Verified:** this bundle was overlaid onto a fresh clone of `Jonnyton/tinyassets` and the full suite passed standalone (173 tests, `pytest tests/test_paid_market_core.py --noconftest`, no deps beyond stdlib + pytest).

---

## 1. Landing the bundle (one command block)

```bash
git checkout -b paid-market-core
unzip paid-market-core.zip
cp -r paid_market_core/tinyassets/paid_market tinyassets/
cp paid_market_core/tests/test_paid_market_core.py tests/
cp paid_market_core/docs/design-notes/*.md docs/design-notes/
cp paid_market_core/docs/*.md docs/exec-plans/active/
rm -rf paid_market_core
python3 -m pytest tests/test_paid_market_core.py -q --noconftest   # expect 125 passed
git add -A && git commit -m "Paid-market pure-logic core + Tracks E-I specs (adversarially reviewed, 173 tests)"
```

(Repo conftest imports langgraph; the suite is standalone by design — `--noconftest` until the env has full deps.)

## 2. FOUNDER — two admin actions, time-sensitive

1. **P0:** production `write_graph` has NO approval gate — anonymous public writes persist. Delete test artifact goal **`1a917636ae83`** (`probe-goal-do-not-create`). Gate must be restored *with an actionable error* (the original bug was the bare error; the fix removed the gate instead).
2. **P1:** the entire wiki subsystem on tinyassets.io is down: `/data/wiki` Permission denied — volume must be writable by the daemon uid. Until fixed, bugs cannot be filed through the platform itself.

Full evidence: `docs/.../2026-07-08-production-mcp-sweep.md`. All four originally-filed dark-payload bugs are FIXED on production.

## 3. OPUS — execution order

**Read `USER-PATH-2026-07-08.md` first.** Also see `DEMO-RUNBOOK-cookbook.md` — the investor demo; its pre-launch dependencies (dataset-expansion flow, CAD-in-the-loop design assist, recipe fine-tune pipeline, commons carrier reference) are demo-blocking work. Specs amended 2026-07-09: Track G §5b (Dataset Forge), Track I §I5/§I6/§3e (code-CAD, pricing-as-query, carrier seeding) — all follow the binding design law in USER-PATH: primitives + commons, never features. It is the binding UX acceptance test for every item below; its seam register (fiat-first onboarding, prices-in-planning, layer-0 universe design with wear-your-own-body interop, unified budget, no financial jargon) overrides implementation convenience.
 (all interfaces are pinned; do not redesign)

1. **Track E Wave 2** — claim (`SKIP LOCKED` RPC) + settle + ledger persistence. The ledger LOGIC is done: `ledger.py` defines valid transactions, escrow lifecycle, and adapters from every settlement dataclass — Wave 2 persists transactions and calls adapters; it must NOT hand-write postings. Every settlement path ends with `assert_drained` on its escrow accounts. Matching uses `match.best_execution` — never greedy.
2. **Migration 006** (token counts on settlement) → wire `index.compute_spot_quote` → `GET /v1/price/{capability_id}` + `/v1/curve` (unauthenticated, cached, and the MCP tool MUST return text content, not structuredContent-only).
3. **Migration 007** (forwards, incl. `tokens_requested` — non-negotiable, see review finding B-1) → lifecycle RPCs calling `forwards.settle_forward` / `buckets.validate_bucket_start`.
4. Ceiling poller (hourly, OpenRouter-style feed) → `ceiling.parse_models_payload`; note the `"-1"` sentinel is already handled.
5. Then Tracks F → H → G → I per their wave tables.

**Invariant discipline:** the pure modules assert conservation internally and fail loud. If a transport layer ever needs to "adjust" a settlement number, that is a design error — stop and re-read the module docstring and `docs/design-notes/2026-07-08-paid-market-adversarial-review.md` (two demonstrated exploits live in that file; do not reintroduce them).

## 4. Module map

| Module | Owns | Key entry points |
|---|---|---|
| `index.py` | spot quote, pair-capped VWAP, ceiling clamp | `compute_spot_quote` |
| `buckets.py` | standard windows, UTC alignment, horizon | `validate_bucket_start`, `enumerate_buckets` |
| `forwards.py` | forward state machine, capacity-reservation settlement | `settle_forward`, `assert_transition` |
| `ceiling.py` | hosted-API price parsing → micros/Mtok | `parse_models_payload`, `ceiling_for_capability` |
| `training.py` | checkpoint-based training settlement | `settle_training_window` |
| `pool.py` | pool funding close, exact revenue apportionment, attribution legs | `settle_pool_funding`, `apportion_exact`, `distribute_revenue` |
| `license_terms.py` | fail-closed license composition for training inputs | `check_trainable` (registry additions = legal review) |
| `shuttle.py` | MPW cost apportionment, fill viability, risk split | `allocate_shuttle` |
| `fabrication.py` | print quoting, geo-aware ranking, per-unit physical settlement | `quote_print_job`, `rank_sellers`, `settle_physical_job` |
| `ledger.py` | double-entry core, escrow lifecycle, adapters from EVERY settlement type, external boundary accounts | `Ledger.apply`, `*_settlement_entries`, `pool_close_entries` |
| `match.py` | exact best-execution over standard-size offers (greedy is provably wrong); deterministic, brute-force-verified | `best_execution` |
| `fund.py` | TINY NAV mint/redeem (fund-favoring rounding), fee-inflow accretion — NOT in any settlement path; LEGAL GATE before public mint | `mint_at_nav`, `redeem_at_nav`, `record_fee_inflow` |

## 5. Open judgment calls awaiting the founder (flagged in specs, defaulted conservatively)

Forward collateral 20% / delivery threshold 95% / buckets 8h-day-week / sizes 1-10-100 Mtok (Track E §3); trust-memory override for forwards collateral (Track E §6 — host directive amendment, confirm); training threshold 100% (Track F §2); share non-transferability pending counsel (Track H §3); license registry contents (Track G §2); shuttle min-fill 50% (Track I §2); token architecture §6 — redemption gating, TINY governance weight, treasury position policy, genesis treasury (plus the §5 legal gates, which stack with Track H's).

## 6. Session provenance

Design conversation: this project's chat history, 2026-07-08 (market shape corrections by founder: model lives in the node; universes adapt, market stays dumb; futures required; full-stack democratization through hardware creation). Everything in the bundle is regenerable from the specs; nothing depends on Fable-specific context.

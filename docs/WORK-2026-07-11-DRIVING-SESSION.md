# Driving Session — 2026-07-11 (adds to paid-market-core bundle)

Companion to CRASH-TEST-FINDINGS-2026-07-11.md. Everything below is
implemented, tested, and included in this drop — not proposed.

## 1. Matcher reimplemented (findings §4) — SHIPPED
- `tinyassets/paid_market/match.py`: same contract, signature, validation,
  and deterministic tie-breaking; bucketed prefix-sum search replaces the
  O(n×need) DP. 5k-offer clearing: 19,280 ms → 6.9 ms. 100k offers: <1 s.
- `tests/test_match_scale.py`: the ORIGINAL DP is preserved verbatim inside
  the test as the executable spec; 1,000 tie-heavy differential trials,
  greedy-trap case, input-order determinism, 100k scale gate. Suite: 177 pass.

## 2. Migrations 006/007/008 authored AND validated on real Postgres 16
- `migrations/006_token_normalization.sql` — CORRECTED: Track E doc says
  `ALTER TABLE public.request_inbox`; that table does not exist (001
  deliberately renamed it to `public.requests`). Fixed target.
- `migrations/007_forwards.sql` — Track E table + in-schema bucket-boundary
  CHECKs (8h/24h/168h UTC alignment); 28-day horizon stays in the post RPC
  via buckets.validate_bucket_start. tokens_requested preserved (B-1).
- `migrations/008_market_ledger.sql` — FOUNDER-GATED. Double-entry
  market.transactions/postings/balances + market.apply_tx, the single
  money-movement RPC (idempotency-key exactly-once, zero-sum check,
  FOR UPDATE in account order, net-based overdraft, direct table writes
  REVOKEd). Implements findings §2a/§3.

## 3. Migration chain findings (validated by applying 001→008)
- `002_rls.sql` is DEAD: references `concept_visibility`, which 001 never
  created (deferred to Track L). It cannot apply to this schema.
  `003_rls.sql` is the superseding rewrite. **Verified chain:**
  001 → 002_flags → 003_rls → 004 → 005 → 006 → 007 → 008, all green on
  vanilla Postgres 16.
- `003_discover_nodes.sql` requires the pgvector extension (`type vector
  does not exist` on vanilla PG). Fine on Supabase; the plan-b self-host
  playbook MUST add `CREATE EXTENSION vector` + package install, or plan-b
  silently loses discovery.
- Duplicate numbers (002 ×2, 003 ×2) make runner order ambiguous. Before
  006 lands anywhere: renumber to a strict sequence (or timestamp prefixes),
  move 002_rls to an `attic/`, and add a schema_migrations tracking table.

## 4. RPC race-tested (the tests that broke the pure ledger)
| Test | Result |
|---|---|
| 8 threads × 600 concurrent transfers | 4,800 applied, drift = 0, no internal negatives, ~6.9k tx/s warm |
| 6 threads racing to drain one 100u account | exactly 1 wins, victim at 0 |
| 20 concurrent replays of one idempotency key | one tx_id, effect applied exactly once — verified across process restarts too |
| Global invariants | sum(postings)=0, sum(balances)=0 |
| Same-transaction reentrancy | two apply_tx calls in one BEGIN…COMMIT: OK |

(The identical workload against the unlocked pure ledger created +278
units from nothing. The RPC is the fix; ledger.py remains the oracle.)

## 5. Founder decisions — now pre-validated, still need sign-off
1. **Ledger coexistence** = freeze public.ledger, adopt 008. (Working code
   attached; approve or redirect.)
2. **Serialization HARD RULE** into OpenSpec requirements verbatim
   (findings §3 wording).
3. **Matcher** — shipped behind the contract; approve differential-test
   discipline as the permanent pattern for hot-path rewrites.
4. **Concurrency target** for the droplet (~100 concurrent cheap-read users
   after threadpool raise) vs earlier per-universe sharding.
5. **Live ops** (not doable from this chat): /data chown, write-gate
   restore, goal 1a917636ae83 deletion, domain-residue purge of get_status
   vocabulary, idle-loop backoff.

Codex's cross-family pass is still running (8,422 lines, no verdict yet, 20 processes alive) — I'm reporting my own empirically verified findings rather than holding, same as the original review did.

---

# Follow-up review — `paid-market-track-e-wave-2-transport`

**Reviewed state:** HEAD `a02d0a71` (3 commits past the original review's `72a b2a75`), working tree clean except the builder's `tasks.md` edit. Verified 2026-07-24, Postgres 15.18 on `localhost:5433`, throwaway databases created and dropped. I made no edits and no commits; the fee mutation probe ran as an out-of-repo pytest plugin, and file md5s + HEAD are unchanged after all probes.

**Note:** the branch moved three commits *during* this review (`acce051b`, `48033137`, `a02d0a71` landed while I was probing). Everything below is re-verified against `a02d0a71`.

## Original blocker mapping

| Original blocker | Status |
|---|---|
| C-1 fresh-install application-role migration-history mutation | **RESOLVED** |
| I-1 SQL fee-formula fork | **RESOLVED** |
| I-2 inconsistent dust fees across pure oracles | **RESOLVED** |
| I-3 prototype RLS tests running as superuser | **RESOLVED** (residual Minor) |
| I-4 PUBLIC EXECUTE on SECURITY DEFINER auth helpers | **RESOLVED** |
| I-5 partial baseline / checksum TOCTOU / non-atomic baseline recovery | **RESOLVED** (all three) |
| SQL NULL validation bypass | **UNRESOLVED** in `apply_tx`; resolved in `apply_settlement` |

**C-1** — `003_rls.sql:265-275` replaced the blanket `GRANT … ON ALL TABLES IN SCHEMA public` with an explicit 9-table list; 006:181 and 008:60 likewise grant per-table. No blanket grant remains in the chain. On an ordinary fresh install I probed all six mutation paths as `tinyassets_fixture_app` — INSERT, UPDATE, DELETE, SELECT, TRUNCATE, DROP all denied; ACL is `{tinyassets_migration=arwdDxt/tinyassets_migration}`, `pg_has_role(fixture_app, tinyassets_migration)` False, `CREATE` on `public` False. The fresh-install assertion now exists at `tests/test_paid_market_migrations.py:132-138`, *before* the DROP/baseline path.

**I-1** — commit `48033137` deleted `v_expected_fee := greatest(1, floor((v_amount_micros::numeric * 10000) / 1000000)::bigint)`. SQL now checks only `v_fee <= 0` plus the structural relations. Spec text was updated to match at `spec.md:258`: *"SQL SHALL validate the adapter's structural conservation and positive fee but SHALL NOT fork the fee formula from the pure oracle."* Divergence is now impossible by construction — no rate literal exists in SQL.

**I-2** — one `canonical_fee_micros` (`forwards.py:69-85`) consumed by all four oracles (`forwards.py:244`, `training.py:157`, `fabrication.py:255`, `ledger.py:138`), and the min-1 rule is now in the spec. The gate is not vacuous: removing the `max(1, …)` floor turned exactly **4 tests RED, one per oracle**.

**I-5** — baseline now covers 006, 007, and 003's new objects plus a full catalog fingerprint including `pg_get_functiondef`; `discover_migrations` reads bytes once and executes `migration.sql` (was re-reading at execute time); baseline history is one transaction with an injected-failure test asserting 0 rows.

## Important

**1. `market.apply_tx`'s zero-sum guard is NULL-bypassed — `009_market_ledger.sql:102`.**
`IF v_sum <> 0 THEN RAISE` — `sum()` over zero rows is NULL, `NULL <> 0` is NULL, the guard is skipped. Verified at HEAD:

```
postings = SQL NULL      -> ACCEPTED ('applied', 1)
postings = '[]'::jsonb   -> ACCEPTED ('applied', 2)
transactions committed: 2    postings rows: 0
```

Two committed `market.transactions` rows with zero postings — false "applied" records that also burn an idempotency key permanently. The same class sits at `:124`: the overdraft guard `v_rec.balance_micros + v_rec.delta < 0` is NULL-skipped too, so a `delta_micros: null` posting slips past it and only fails later on the `balance_micros` NOT NULL constraint. Commit `48033137` hardened *every* `<>` in `apply_settlement` to `IS DISTINCT FROM` and missed both of these. Fix is `IS DISTINCT FROM 0`.

Reachability mitigation, which is why I rank this Important and not Critical: `apply_tx` EXECUTE is granted to nobody — verified False for `tinyassets_fixture_settlement`, `tinyassets_fixture_app`, and PUBLIC; only the owner role and superusers reach it, and through `apply_settlement` the postings array is bounds-checked to 2..16 entries so NULL/`[]` cannot arrive. It's a defense-in-depth fail-open. But zero-sum is the *one* invariant `apply_tx` claims to enforce independently, its header comment leans on that, and no test covers it.

**2. REGRESSION — the deterministic catalog fingerprint hard-codes the runner's role name, breaking `--baseline-existing` outside one environment.**
`_fixture_schema_sha256` normalizes owners via `CASE pg_get_userbyid(...) WHEN current_user THEN '<runner>'` (migrate.py:293, 306, 389) but hashes raw `relacl` / `nspacl` / `proacl` text, which embed grantor and grantee names. A byte-identical chain applied by a superuser named `alt_runner_1940b4`:

```
fingerprint: fda721d151bf0986...   pinned: 60d7c2eefdb40d13...   MATCH: False
--baseline-existing FAILED: exact baseline check: catalog fingerprint fda721d1...
public.users relacl: {alt_runner_1940b4=arwdDxt/alt_runner_1940b4,tinyassets_fixture_app=arwd/alt_runner_1940b4}
```

Fails closed (safe direction) and `docker-compose.yml:6` pins `POSTGRES_USER: tinyassets`, so the project's own path works — but `--baseline-existing` exists specifically for recovery on an already-populated database, which is exactly where a differently-provisioned Postgres is likely, and the error names a hash instead of the mismatched object. Normalize ACL grantor/grantee the same way owners already are.

## Minor

1. **`public.strip_private_fields` is SECURITY DEFINER with `proacl = NULL` → PUBLIC EXECUTE = true.** Same defect class as I-4, on the third definer function in the same fixture. Pre-existing in 006, so not a regression — but the change locked two of three and left this one.
2. **Two of three `test_rls.py` assertions still don't depend on RLS.** The `SET ROLE` fix is real and load-bearing (raw `SELECT count(*) FROM public.nodes` on another user's private node: 1 as superuser, 0 as `fixture_app`), and `test_owner_sees_all_fields` now genuinely exercises RLS. But `discover_nodes` applies its own filter at `006_discover_nodes.sql:126` (`AND (n.owner_user_id = v_caller_id OR n.concept_visibility = 'public')`) and stripping is done by definer `strip_private_fields` — probed both roles, identical results. So the two negative assertions would still pass with RLS disabled entirely.
3. **`expected_state_version` is validated but never compared.** Parsed and bounds-checked at 009:232-240, assigned at :239, never referenced — no CAS. Not fully dead (it's inside the SHA-256'd body, so changing it forces an idempotency conflict) and task 3.5 discloses CAS is blocked, but a reader of the SQL alone could infer CAS exists. One comment closes it.
4. **`008_forwards.sql:59` stale comment** left by the C-1 fix: "008 runs after the point-in-time ALL TABLES grant in 003" — 003 no longer has one.
5. **SQL accepts a 100%-fee settlement** (escrow −N, treasury +N, no seller posting) — verified accepted. Satisfies fee>0 and conservation; the Python adapter never emits it. Noting because SQL is the trust boundary for the settlement role.
6. **Carried forward unchanged:** M-1 (one-bid skip-locked test), M-2 (no in-band funding path; 7 direct superuser INSERTs into `market.balances`), M-3 (`market.assert_drained` granted to nobody → unreachable from the settlement role while tasks 3.1/3.6 treat drain assertions as proof surface). M-4 and M-5 are fixed.

## Verified clean

- **Explicit grants:** no over-grant. The 9-table list matches the RLS-enabled set; market schema fully revoked from PUBLIC and from `fixture_app`; every market definer function locked (settlement → `apply_settlement` only; owner-only for `apply_tx`/`assert_drained`).
- **Generated mirror:** all 5 changed `paid_market` files byte-identical; `build_plugin.py` regenerated 264 files, import probe ok, no diff.
- **Blocked work genuinely blocked:** 8 BLOCKED premises naming real gates. 3.5 states business CAS/actor authority is blocked and "deliberately does not invent those rows or authorities." Task 6.2 was corrected this session from an unqualified claim to a precise one; 6.3 correctly still unchecked.
- **Evidence honesty:** the claimed 224-test gate reproduces exactly — **224 passed**, plus 18 prototype tests, ruff clean on changed Python.
- **Economics:** top-line reference correctly scoped *out* to `paid-market-live-price-discovery` (`design.md:56`, `proposal.md:12`), matching the host hard rule at `docs/exec-plans/active/2026-07-09-cross-venue-routing.md:9`; native competes below via the ceiling clamp at `index.py:275-277` (retains `raw_vwap_micros`, flags `above_ceiling`); fee-on-every-positive-gross enforced in both Python (min-1, red-on-mutation) and SQL — zero fee, negative fee, and `amount_micros: 0` all rejected, so gross is always ≥ 1.

The two open items are both small, local fixes: `IS DISTINCT FROM 0` at `009_market_ledger.sql:102` (and the same at `:124`), and ACL normalization in the fingerprint. C-1 plus five of six Important findings are genuinely closed with falsifiable gates, which is a real improvement over the first pass.

**VERDICT: REQUEST_CHANGES**

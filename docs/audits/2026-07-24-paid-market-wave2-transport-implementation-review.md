Codex's cross-family pass is still running (it's now re-checking file timestamps because the tree keeps moving); I'm reporting my own empirically verified findings rather than holding.

---

# Independent implementation review — `paid-market-track-e-wave-2-transport`

**Reviewed state:** HEAD `72ab2a75` + uncommitted working tree, 2026-07-24 ~20:25 PT.
**Important caveat:** the branch moved 5 commits and continuous working-tree edits *during* this review. Several defects I found mid-review (zero-fee settlements accepted, SQL ignoring `amount_micros`/`escrow_account`/`expected_state_version`, Python↔SQL bound divergence, missing grants on `artifact_field_visibility`/`forwards`) were fixed by the builder while I worked, so they are **not** listed below. Everything below was re-verified against the current tree.

**Evidence base:** all findings verified empirically against the live fixture Postgres 15 (`localhost:5433`) in throwaway databases (created and dropped), not by reading alone. Current test state: **215 passed** with `TINYASSETS_TEST_POSTGRES_DSN` set.

---

## Critical

**C-1. The application role can forge and tamper migration history on an ordinary fresh install.**
`prototype/full-platform-v0/migrations/003_rls.sql:265` grants `SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public` to `tinyassets_fixture_app`. `_bootstrap_history` (`migrate.py:88`) creates `public.schema_migrations` **in `public`, before** the migrations run, so the blanket grant sweeps it in; `_bootstrap_history` revokes only `FROM PUBLIC`, never from the app role.

Verified on the current tree (`003_rls.sql` md5 `aca6af16`, `migrate.py` md5 `d6cda738`):

```
FRESH INSTALL, app role forged+tampered history: (99, 'forged') | v9 sha now: ffffffff
```

The app role both inserted a fabricated version row **and rewrote a recorded `sha256`** — which defeats the checksum-drift fail-closed guarantee the entire runner design rests on. This violates the delta spec verbatim ("Public and application roles SHALL NOT alter migration history", `spec.md:360`) and task 2.2 ("keep public/application roles unable to mutate history").

**The branch's own test is a false negative.** `tests/test_paid_market_migrations.py:142-159` checks this privilege *only* after `DROP TABLE public.schema_migrations` + a `--baseline-existing` re-bootstrap, where the `ALTER TABLE … OWNER TO` on the freshly created table happens to strip the grant. I probed both paths: post-baseline → `InsufficientPrivilege` (test green); ordinary fresh install → forge succeeds. The test proves a state the ordinary path never reaches.

Fix: `REVOKE ALL ON public.schema_migrations FROM tinyassets_fixture_app` in `_bootstrap_history` (better: put the history table in its own schema, not `public`), and add the fresh-install assertion.

---

## Important

**I-1. The fee formula is forked into SQL.** `009_market_ledger.sql:284-286` hardcodes `greatest(1, floor((v_amount_micros::numeric * 10000) / 1000000))` — a second implementation of `spot_settlement_entries`. The delta spec explicitly forbids this: "A transport SHALL NOT silently fork a formula into SQL, HTTP, MCP, API, or workflow code." Nothing binds `FEE_PPM`/`PPM` (`forwards.py:47-49`) to the SQL literals, and no test goes red if they diverge — changing `FEE_PPM` in Python makes every settlement fail closed with an opaque `postings do not match the canonical spot adapter`.

**I-2. The new `max(1, …)` minimum fee contradicts the other canonical oracles and isn't in the spec.** `ledger.py:138` now floors-with-min-1, but `forwards.py:224`, `fabrication.py:250`, and `training.py:156` still use plain `(seller_gross * fee_ppm) // PPM`, which yields a literal **zero** fee below 100 micros — and `forwards.py:205` documents that as intended ("treasury_fee floors → dust stays with the seller"). Under the reworded "fee on every settlement" requirement, either those three oracles now violate it or spot is a silent behavior fork. The same spec requirement says an intentional rule change "MUST first modify the canonical oracle requirement and tests through its own OpenSpec change" — the min-1 rule appears in code but not in the delta spec text.

**I-3. The prototype RLS suite proves nothing, and this change knew it.** `prototype/full-platform-v0/tests/test_rls.py` contains **zero** `SET ROLE` calls, and the connection role is `('tinyassets', rolsuper=True, rolbypassrls=True)`, is the table owner, and `relforcerowsecurity=False` — so RLS is entirely bypassed for every assertion in that file (verified). Its negative assertions (`result["candidates"] == []`, `"example_company" not in returned_concept`) are exactly the ones that cannot fail. This change added `SET ROLE tinyassets_fixture_app` to precisely one test (`test_track_a.py:192`, invariant 2) — a genuine improvement that demonstrates the author knew the role was load-bearing — but left `test_rls.py` untouched while task 2.4 cites "all 18 prototype tests passed" as evidence.

**I-4. Two new SECURITY DEFINER functions ship with default PUBLIC EXECUTE.** `auth.is_request_bidder` and `auth.is_request_owner` (`003_rls.sql`) are `prosecdef=true`, owned by the superuser, with `proacl = NULL` → `has_function_privilege('public','auth.is_request_owner(uuid)','EXECUTE')` returns **true** (verified). Every other new object in this change is meticulously locked down — the whole `market` schema is `REVOKE ALL … FROM PUBLIC`, and even the pre-existing `auth.uid()` carries an explicit ACL. These two read `public.bids`/`public.requests` with RLS bypassed and now back two RLS policies, so their exposure carries the policies' weight.

**I-5. `--baseline-existing` writes nine checksums after a partial check.** `_verify_existing_fixture` (`migrate.py:136`) checks 001/002 tables, extensions, 008's `forwards.version`, 009's market objects, and RLS-on-9-tables. It checks **nothing** from 006 (`public.discover_nodes`, `strip_private_fields`, `artifact_field_visibility`) or 007, and none of the objects this change *adds* to 003 (`auth.is_request_bidder`/`is_request_owner`, the `tinyassets_fixture_app` role and grants). It then records the current file shas as applied, so checksum-drift can never fire again for those files. The error string calls this an "exact baseline check" — it is a partial proxy.

**I-6. The concurrency test doesn't exercise concurrency of the thing it names.** In `test_checksum_drift_lock_timeout_and_concurrent_runners`, `run_migrations` is already called at line 205, so both racing threads run against an **already fully migrated** database and exercise only the no-op path. It asserts `not errors` and never asserts the resulting history row count. Task 2.1's "two concurrent serialized runners" claim is unproven for a fresh database — which is the only case where double-application could occur.

---

## Minor

**M-1.** `test_invariant_3_skip_locked_claim_exactly_one_wins` was narrowed from two bids to one (`daemon_b`/`host_b`/`bid_b` removed) and the winner pinned to `bid_a`. Given the query is `… FOR UPDATE SKIP LOCKED LIMIT 1`, the old two-bid form could not have asserted "exactly one wins" correctly, so this is defensible as a fix — but it silently drops the genuinely interesting property (two claimers get two *different* bids, never the same one), no task authorizes it, and the surviving comment "the other gets zero rows" is now trivially true.

**M-2.** No in-band funding path. 009 dropped `external:*`/`pool:*` and made `balance_micros >= 0` unconditional, so from a fresh migration **no `apply_settlement` can ever succeed** — nothing can create a positive balance. Both Postgres test files seed `market.balances` with a direct superuser `INSERT`, i.e. through exactly the direct-table-write path the design says must not exist. Defensible for a non-custodial logical ledger (funding is off-ledger by design), but it should be an explicit named privileged primitive rather than an undocumented raw write the test suite depends on.

**M-3.** `market.assert_drained` is created SECURITY DEFINER, revoked from PUBLIC, and granted to nobody — unreachable from the settlement role, while tasks 3.1/3.6 treat drain assertions as part of the proof surface.

**M-4.** `apply_tx`'s overdraft `RAISE EXCEPTION … [%]` interpolates caller-supplied `p_memo` (≤512 bytes) into a server error message.

**M-5.** `pydantic==2.11.10` added to `prototype/full-platform-v0/requirements.txt` with no rationale in tasks 2.2/2.4; the runner needs only psycopg.

---

## What holds up

Against your specific focus areas, these are solid and I want them on the record:

- **Non-custodial boundary (#5) — clean.** No chain code, signer, payout dispatcher, or wallet write is added. Removing `external:*` makes the ledger closed by construction, so a committed row structurally cannot represent inbound funds. The header comment and spec both state this plainly.
- **Blocked runtime work (#7) — exemplary.** Verified absent: `market_workflow.py`, `market_realtime.py`, `market_delivery.py`, `010_*.sql`, `test_paid_market_workflow*.py`. `MarketTransport` is imported by **nothing** outside tests and the generated mirror, and defaults `enabled=False`. Tasks 2.5/2.6, 3.5–3.7, 4.1–4.7, 5.1–5.7, 6.2–6.4, 6.6 carry explicit BLOCKED premises naming the actual gate (S14/B36, tenant/boundary/domain owners, host migration approval) instead of guessing a surface. This is the part I'd hold up as the model.
- **Idempotency / replay / rollback of the settlement RPC — proven.** 100-caller identical replay applies exactly once (one `tx_id`, 3 postings); same-key/different-body raises `idempotency conflict`; overdraft rolls back with zero transaction rows; the differential test against pure `Ledger` over 50 randomized duplicate-account transactions matches exactly. The `pg_temp.sha256` shadowing test is a real hostile-path proof, and `SET search_path = pg_catalog, market, pg_temp` with `pg_temp` last is the documented-safe idiom.
- **One hypothesis of mine was refuted.** I suspected the `ON CONFLICT DO NOTHING` replay branch could return `('replayed', NULL)` under REPEATABLE READ. Postgres actually raises `SerializationFailure` there — verified. The builder has since added both an explicit `IF v_tx_id IS NULL THEN RAISE` guard and a stale-reader test anyway.

**Recommended sequencing:** C-1 is a two-line fix and should land with a fresh-install assertion. I-1/I-2 are one decision (bind the SQL fee to the Python constants, and decide whether min-1 is the canonical rule for *all* settlement oracles via the spec). I-3 is the one I'd weigh heaviest for trust in the evidence trail — task 2.4's "18 prototype tests passed" currently over-reads what those tests establish.

**VERDICT: REQUEST_CHANGES**

Two notes on process: I made no edits and no commits, as asked — the only writes were throwaway Postgres databases (created and dropped) and `.codex-out/` for the Codex dispatch. And be aware the builder is actively committing to this branch, so re-verify C-1 before acting; it was true as of `003_rls.sql` md5 `aca6af16`.

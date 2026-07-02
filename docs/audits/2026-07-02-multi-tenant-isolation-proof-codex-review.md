# Codex review — multi-tenant concurrency/isolation proof

- **Date:** 2026-07-02
- **Artifact under review:** `tests/test_multi_tenant_isolation.py` (branch `claude/founder-identity-allslices`)
- **Writer:** Claude (Opus 4.8). **Reviewer:** Codex (opposite-provider review gate).
- **Verdict:** **ADAPT** — proof is useful and correct for the steady-state guarantee, but the initial single-test version overclaimed. Five gaps flagged; the high-value ones were folded in the same session.

## Why this proof exists

Host guarantee (2026-07-02): "many other users all should be able to make their
own universes ... they all get their own universe tied to them." This is the
deterministic §14 concurrency/isolation proof of that guarantee, separate from
the host-gated live deploy.

## Codex findings and disposition

1. **Cold-start DB race masked.** The `shared_base` fixture pre-called
   `initialize_author_server()`, hiding a first-request race on
   `CREATE TABLE` / `PRAGMA table_info`-then-`ALTER TABLE` migrations
   (`tinyassets/daemon_server.py:413,420-424,453-457`).
   → **Adapted:** added `test_cold_start_schema_race_no_preinit` — N founders
   race with NO pre-init; all must succeed with distinct universes.
2. **Concurrency real but not race-forced** — `pool.map` schedules threads but
   there was no start barrier, so a fully serialized impl would also pass.
   → **Adapted:** flagship test now uses a `threading.Barrier(N)` so all workers
   enter `create_universe()` simultaneously.
3. **Registry writes could be silently lost** — `ensure_universe_registered`
   failures are best-effort/swallowed (`tinyassets/api/universe.py:4734-4738`);
   the test asserted disk dirs + ACL/home but not registry rows.
   → **Adapted:** flagship test now asserts `get_universe_rules()` (raises
   `KeyError` if the rules row was lost) for every created universe.
4. **Identity isolation tested only for direct worker calls, not transport.**
   → **Partially adapted:** added `test_thread_reuse_does_not_leak_identity`
   (2-thread pool, 8 founders → forces pool-thread reuse; each founder still
   gets its own universe, proving no ContextVar bleed on a reused thread).
   Full ASGI `AuthContextMiddleware` interleaving + omitted/invalid-token
   sequences remain out of scope for this deterministic proof — covered by the
   live WorkOS canary + chatbot ui-test gate before rollout.
5. **Stored ACL asserted, runtime authz leakage not.** A broken
   `universe_access_allows()` could grant access at runtime while stored rows
   look correct.
   → **Adapted:** added `test_cross_founder_write_denied_and_private_read_isolated`
   — founder B is DENIED a write to founder A's (public) universe, and DENIED a
   read once A makes it private; owner A retains both.

## Residual (not blocking the deterministic proof)

- Transport-layer (ASGI middleware) identity interleaving, invalid-token and
  omitted-token-after-authenticated sequences → live WorkOS canary + chatbot
  `ui-test` before rollout.
- `get_status` body deep-leak (persona/evidence fields) beyond `universe_id` →
  covered by the founder-identity leak fixes already Codex-reviewed
  (`docs/audits/2026-07-01-*`); this proof asserts the entry-resolution id.

## Evidence

`python -m pytest tests/test_multi_tenant_isolation.py` → 5 passed, stable over
5 repeats + a 40-founder stress variant; `ruff check` clean. Windows,
Python 3.14, 2026-07-02.

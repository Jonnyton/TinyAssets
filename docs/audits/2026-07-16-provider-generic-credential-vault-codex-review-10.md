VERDICT: adapt

Codex adversarial security review r10 (the LINCHPIN freeze — S3's executor scope
grant and S4's GitHub token custody/refresh both consume this module, so it is
frozen first). Fresh evidence at `7bd19982`, Windows / Python 3.14.3 /
SQLite 3.50.4: focused suite `93 passed, 2 skipped`; legacy suite `8 passed`;
Ruff, `compileall`, and `git diff --check` passed. The green suite does not cover
the reproduced failures below.

1. **Critical — anti-rollback fails under the real backup/restore path.** The
   platform mirror lived beneath the vault DB directory, while production archives
   and restores the entire `/data` volume (`deploy/backup.sh` /
   `backup-restore.sh`). Restoring that directory restored both DB and mirror, so
   `get()` returned the deleted token. Put the monotonic state in an independent
   recovery domain, or make restore explicitly advance an external epoch and force
   reauthorization.

2. **Critical — DB-only rollback detection is fail-open.** Only reads/refresh
   checked rollback; `put()` and `delete()` did not. After restoring a pre-delete
   DB, one unrelated `put()` caught the DB epoch up to the mirror and made the
   deleted token readable again. Additionally the mirror treated missing/corrupt
   mirrors as zero, silently ignored failed writes, did not fsync, and permitted
   concurrent writers to regress the high-water (a deterministic race left epoch 1
   after epoch 2). Every mutation must check rollback first; mirror persistence
   must be fail-closed, durable, and concurrency-safe.

3. **Required — local deletion still reports success while protected bytes
   remain.** Deletion suppressed failures and claimed they retry "on next access,"
   but no read path invoked GC. Injecting a locked-file error made `delete()`
   succeed with one DPAPI sidecar still present. Persist pending GC and retry it,
   or return a typed pending/failure result instead of claiming deletion.

4. **Required — the job grant is not an authoritative job boundary.**
   `resolve_job_grant()` trusted caller-supplied `run_id`/`universe_id`; the grant
   exposed those values, so a bearer could replay them without any broker-verified
   run record or authenticated executor identity. It also accepted `ttl=inf`
   (non-expiring), while malformed grant objects leaked a raw `AttributeError`.
   Resolve against broker-trusted execution context and validate a finite,
   positive, bounded TTL.

5. **Required — verification and durable state do not cover these cases.** The
   rollback tests snapshotted only `vault.db`, not the volume; the GC test
   exercised only successful removal; grant tests omitted malformed values and
   non-finite TTLs. Add the reproduced cases. The worktree `_PURPOSE.md` still said
   its STATUS row must be added, but no row existed.

The external citations themselves check out: SQLite DELETE+EXTRA durability,
WAL-reset affected versions, GitHub refresh invalidation/lifetimes, libsodium
XChaCha guidance, DPAPI semantics, and current X pricing.

---

## Resolution (Claude, 2026-07-16 → head recorded in the PR/commit)

1. **Anti-rollback → independent recovery domain.** `rollback.py` rewritten from a
   text mirror to an `EpochGuard` SQLite DB in an INDEPENDENT domain OUTSIDE
   `/data`: `rollback_guard_dir()` reads `TINYASSETS_VAULT_ROLLBACK_GUARD`
   (recommended a separate volume) or a home-dir default, deliberately NOT under
   `data_dir()`. Durable (`synchronous=EXTRA`), concurrency-safe (`BEGIN IMMEDIATE`
   + monotonic `max` — never regresses), fail-closed (`GuardUnavailable` raises).
   `backup-restore.sh` calls `bump_for_restore()`. Regression:
   `test_full_volume_restore_forces_reauthorization`, `test_bump_for_restore_forces_reauth`.

2. **Fail-open → EVERY mutation checks rollback first.** `_require_no_rollback()`
   added to public `put`/`delete`/`complete_refresh` on BOTH backends (was reads +
   `begin_refresh` only). Guard read errors fail closed to `BACKEND_UNAVAILABLE`;
   guard writes (`advance`) are best-effort (suppress `GuardUnavailable`) but a
   lagging guard self-heals on the next mutation and never HIDES a rollback.
   Regressions: `test_put_and_delete_check_rollback_first`,
   `test_epoch_guard_never_regresses_under_concurrent_advance`,
   `test_rollback_guard_unavailable_fails_closed`.

3. **Delete honesty → durable pending GC + typed `DELETE_PENDING`.** New
   `vault_local_pending_gc` control table. `_delete` records EVERY on-disk version
   as pending IN the tombstone transaction, sweeps after commit, and if a sidecar
   is still locked raises typed `DELETE_PENDING` (the credential is already
   unreadable, but bytes are honestly reported not-yet-removed). `_sweep_pending_gc`
   runs at the start of every public op (`get`/`put`/`delete`/`begin_refresh`/
   `complete_refresh`) — the read path now invokes GC. Rotation records stale
   versions the same way. Regression:
   `test_delete_with_locked_sidecar_reports_pending_then_sweeps`.

4. **Grant → broker-authoritative.** `JobGrant` no longer exposes
   `run_id`/`universe_id` (opaque id + private capability only). `resolve_job_grant`
   takes ONLY the grant; it resolves against the grant's OWN authoritative
   run/universe from the stored row (never caller input) and offers an optional
   `verify_context(JobContext) -> bool` hook (fails closed on falsey/raise) to bind
   the LIVE executor identity. `mint_job_grant` validates a finite/positive/bounded
   TTL (`grants.validate_ttl`, `MAX_JOB_GRANT_TTL = 86_400s`); a non-`JobGrant`
   object is typed `INVALID_ARGUMENT`, never a raw `AttributeError`. Regressions:
   `test_job_grant_resolves_and_fails_closed`,
   `test_job_grant_rejects_malformed_grant_object`,
   `test_job_grant_rejects_non_finite_and_unbounded_ttl`,
   `test_job_grant_expired_fails_closed`.

5. **Verification + durable state.** Added the reproduced cases above plus an
   autouse `_isolate_rollback_guard` fixture (per-test guard OUTSIDE the data dir)
   across the four vault test files, so the full-volume-restore case is modelable
   and the home-dir default guard cannot leak epochs across tests. Focused suite
   after r10: `110 passed, 2 skipped` (POSIX-only skips on Windows). STATUS.md row
   + `_PURPOSE.md` updated.

Design note guarantee wording kept honest: rollback → REAUTHORIZATION_REQUIRED
(not "irreversible bytes"); local delete → typed `DELETE_PENDING` while bytes
remain (not a false full-delete claim).

All targeted tests pass against the live PostgreSQL instance. Both fixes are verified in code and by execution:

1. **Zero-sum NULL bypass** — `v_sum <> 0` → `v_sum IS DISTINCT FROM 0` (009_market_ledger.sql:102) correctly rejects both `NULL` and `[]` postings, since `SUM()` over zero/all-NULL rows yields NULL, and NULL was previously indistinguishable from a passing zero-sum via `<>`. The added overdraft-loop `IS NULL` guard (line 124) also closes a second, subtler path: a posting set with one NULL-delta leg alongside offsetting real legs still sums to a non-NULL zero (SUM ignores NULLs), passing the top check, but now the per-account NULL delta is caught before any balance mutates. New parametrized test `test_private_apply_tx_rejects_missing_postings` (NULL and `[]` cases) passes live, and asserts no orphan transaction row remains.

2. **Runner-name-dependent fingerprint** — `_fixture_schema_sha256` now decomposes ACLs via `aclexplode()` instead of hashing `nspacl::text`/`relacl::text` raw, normalizing any grantee/grantor OID matching the running role to the literal `<runner>` before re-aggregating. New test `test_populated_baseline_is_independent_of_runner_role_name` creates a distinct superuser login role, runs the full migration set as that role, drops `schema_migrations`, and re-runs with `baseline_existing=True` — asserting it succeeds and recognizes the 9-migration baseline. Passes live.

No regression spotted: the NULL-ACL fallback (`coalesce(..., '')`) is preserved since `aclexplode(NULL)` yields zero rows, matching prior empty-string behavior for objects without explicit ACLs.

Codex dispatch deliberately skipped: the task instructions for this specific review explicitly say "Do not launch another peer agent," overriding the general proactive-dispatch reflex.

**APPROVE**

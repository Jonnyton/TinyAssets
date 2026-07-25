# Codex round-5 preflight

**Date:** 2026-07-25  
**Reviewed head:** `e8e0011c75345533f20269de3b0a0b605d314b95`  
**Mode:** three independent read-only subagent reviews; no runtime review authority  
**Verdict at reviewed head:** `ADAPT`

## Findings accepted

1. **Critical — catalog authority contradicted PLAN.** The reviewed draft treated the local/canonical Branch SQLite shape as catalog authority. PLAN makes Postgres canonical for catalog transactions and local-first SQLite bridge-only.
2. **Critical — catalog-to-exact inspection leaked hidden Goals.** Catalog summaries omitted Goal IDs, but exact Branch projections could still return raw `goal_id` and Goal-bearing `gate_claims`.
3. **Important — cross-store patch atomicity was fictional.** The draft promised no partial Branch/version state while current patch snapshots and Branch mutation used different SQLite stores and commit points.
4. **Important — rollback races lacked an owner and proof.** `tinyassets/rollback.py` was absent from the future Files boundary; publish-versus-rollback and distinct-publication races were untested.
5. **Important — periodic reconciliation was not executable.** No named trigger, cadence, batch, restart, locking, or injected-drift proof existed.
6. **Important — deployment rollback was prose-only.** No prior-image/post-migration rehearsal or expected rolled-back tool-surface proof existed.
7. **Important — live wiki writes lacked explicit commons scope.** Authenticated omitted-scope writes currently resolve/relay to the founder universe; they cannot be treated as commons mutations.
8. **Important — run guidance outran requester authority.** Newborn BYOC behavior alone does not satisfy the still-blocked authority bundle, ambient-isolation, held-envelope, and receipt gates.
9. **Important — retirement could remove the only remix/lineage seam.** First-contact V1 excludes fork/remix, so `extensions` cannot retire before a canonical replacement and rendered lineage proof.
10. **Important — owner labels were not landed/released state.** Universe and prompt-owner branches/files require exact landed SHAs or file-specific handoffs before runtime claim.

## Amendments made after the reviewed head

- Hosted Branch/catalog/version/publication/idempotency/nonce/outbox authority is now one Postgres transaction domain.
- SQLite is only one-way import input or an idempotent downstream execution projection; no fallback, dual-write, or reverse authority is allowed.
- Exact Branch projection now fails closed for restricted pages and non-visible Goal IDs/derived claims.
- Operational pre/post snapshots now flow through canonical outbox events; downstream failure never rewrites a committed user result as `branch_write_failed`.
- Rollback ownership, concurrent publication/rollback tests, named bounded reconciliation, and prior-image rehearsal are explicit tasks.
- Prompt execution stops at rediscovery until the full requester authority/isolation dependency set lands.
- Live wiki tasks require the owned `write_page(scope="commons", ...)` route and serialized writer.
- Legacy retirement tasks preserve publish, approval, remix creation, and lineage inspection until replacements, migrations, and rendered proofs land.
- Future implementation/deploy claims require exact migration allocation, file releases, and separate bounded Files sets.

## Gate

These amendments are not self-approval. Claude Opus 5 must review the exact amended committed head and return literal `VERDICT: APPROVE` before this packet is pushed or opened as a draft PR. The authenticated Claude Max CLI returned a monthly-spend-limit error before inference on 2026-07-25, so no round-5 Opus verdict exists yet.

## Exact-head re-review of `be018740`

Three independent read-only reviewers returned `ADAPT` again. The accepted follow-up findings were:

- `intent="snapshot"` must synchronously create/reuse and return a canonical non-catalog Postgres BranchVersion for evaluation/selector/bootstrap; SQLite remains only its asynchronous replica.
- Hosted/shared reads use Postgres, while an isolated OSS namespace may remain locally readable only behind distinct routing/IDs and never as shared fallback.
- The dependency is the existing `establish-postgres-control-plane` draft PR #1670, not a newly invented duplicate baseline; it must land its driver in every serving artifact.
- Reconciliation acceptance must exercise startup, cadence bounds, 500-row high-water continuation, lock exclusion, telemetry, and retry.
- Rollback rehearsal must precede deployment without a production-receipt cycle; after the first canonical write, recovery is forward-fix and a prior image cannot serve.
- Current universe and `control_station` owner truth must be reconciled now rather than deferred to implementation.

The packet was amended accordingly. This second Codex pass is still not opposite-provider approval.

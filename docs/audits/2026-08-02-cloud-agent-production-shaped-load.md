# Cloud agent production-shaped load evidence

Freshness: 2026-08-02, Windows, Python 3.14, exact reviewed head
`dde163582618d84d97955350b332bc0eedf03659`.

## Classification

This is **shaped local evidence**, not live-production or distributed-cloud
evidence. It exercises the real SQLite authority/runtime owners with fresh
service instances and spawned processes. Provider execution uses a recording
test double. It therefore cannot satisfy dark deployment health, real provider
custody, Supabase/PostgreSQL, public canary, or PC-off acceptance gates.

## Scenarios and results

`python -m pytest tests/load/test_agent_runtime_cloud_load.py -q -s`

- 64 requests across eight spawned processes converged on one receipt, claim,
  reservation, and continuation. Replacing all workers after claim expiry kept
  the same identities, advanced claim/continuation generation exactly 1 to 2,
  produced no provider outcome, and retained `PRAGMA integrity_check = ok`.
- 64 simultaneous in-process launch contenders crossed the provider boundary
  once, emitted only exact typed concurrent-launch blockers during uncertainty,
  and replayed one terminal outcome without another call.
- 64 requests across eight spawned processes produced exactly one
  filesystem-visible provider-call marker, one terminal outcome, exact replay,
  typed concurrency blockers, and an intact database.
- Fresh reviewer rerun: 3 passed in 21.89 seconds. The thresholds are generous
  bounded-smoke ceilings, not performance SLOs.

Related exact-head evidence: 47 focused provider/continuation/health tests
passed; 554 broader agent/runtime/provider/background-authority tests passed on
the merged core baseline; targeted Ruff and format checks, strict OpenSpec,
plugin import probe, 325-file canonical/plugin parity, and diff checks passed.

## Defect found and repaired

The first 64-contender run reproduced a losing launcher leaking raw
`PermissionError` after another worker advanced or finalized the reservation.
The service now returns a typed concurrent-launch hold while uncertainty is
open, or replays the terminal race winner only after full current authority and
the outcome are read within one transaction. A seeded terminal outcome plus a
revoked provider binding proves fresh denial cannot be masked by replay.

## Independent review

- The initial combined review timed out and counts only as an error.
- The first scoped production review returned `adapt`: replay could mask a
  fresh authority revocation. Commit `2137dd8f` added transactional authority
  revalidation and a denial regression; exact re-review returned `approve`.
- The first scoped load-evidence review returned `adapt`: provider single-flight
  was thread-only and blocker capture was too broad. Commit `dde16358` added the
  spawned-process call-marker proof and exact blocker assertions; exact
  re-review returned `approve`.

## Remaining gate

The owning 5.1 tasks remain open for real cloud substrate, dark deployment
health, public canary, production environment fingerprint/evidence, and the
other capability-owned live checks. No live-cloud claim is made here.

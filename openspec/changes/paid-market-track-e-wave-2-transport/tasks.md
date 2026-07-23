## 1. Review Gate and Baseline

- [ ] 1.1 Obtain opposite-provider review of `proposal.md`, `design.md`, the `paid-market-economy` delta, and this task list; record an approve/adapt verdict in `docs/audits/` and resolve every blocking finding before implementation.
- [ ] 1.2 Run and record the pre-change baselines: `python -m pytest tests/test_paid_market_core.py tests/test_match_scale.py -q --noconftest`, `openspec validate --specs --strict`, and `openspec validate paid-market-track-e-wave-2-transport --strict`.

## 2. Fixture Replay and Production Baseline Gate

- [ ] 2.1 Write failing fixture tests for unique/gap-free IDs, exact-byte SHA-256 drift, fresh application, verified populated-fixture baselining, failure rollback/resume, bounded advisory-lock timeout, two concurrent serialized runners, migration-role-only history DML, and prior-app compatibility after populated upgrade.
- [ ] 2.2 Add a local runner under `prototype/full-platform-v0/` with fixture-scoped psycopg dependencies and `schema_migrations(version, name, sha256, applied_at)`; make each SQL file plus history row one transaction and keep public/application roles unable to mutate history.
- [ ] 2.3 Renumber and dependency-correct the v0 files in place as `001_core_tables`, `002_flags`, `003_rls`, `004_indexes`, `005_seed`, `006_discover_nodes`, `007_token_normalization`, `008_forwards`, `009_market_ledger`; ensure discovery establishes/checks pgvector and forwards adds a monotonic offer `version`. Do not copy this SQL into a production migration home.
- [ ] 2.4 Update the prototype compose, tests, and README to use only its fixture runner; prove fresh install and fixture upgrade use the same path and the gateway does not start before migration success.
- [ ] 2.5 Produce a read-only inventory of the actual deployed Supabase schemas, extensions, auth, policies, functions, roles, vector dimensions/indexes, migration history, and deployment mechanism. Stop for host approval of the production baseline and migration home before authoring separately reviewed production-native SQL.
- [ ] 2.6 After approval, author production-native migrations from the recorded baseline; add exact dry-run, role/policy, populated-upgrade, rollback/forward-fix, checksum/history, and prior-app compatibility tests; obtain independent migration/security review while keeping live application explicitly unapproved.

## 3. Pure Spot Adapter and Ledger SQL Boundary

- [ ] 3.1 Add failing unit tests in `tests/test_paid_market_core.py` for a pure spot-settlement posting adapter, exact conservation, integer-only inputs, and positive/negative `Ledger.assert_drained` behavior.
- [ ] 3.2 Implement only the missing pure spot adapter in `tinyassets/paid_market/ledger.py`, export it through `tinyassets/paid_market/__init__.py`, and keep the package free of I/O/environment/database imports.
- [ ] 3.3 Add failing fixture PostgreSQL tests for role/DML/RPC denial, fixed-search-path resistance, non-login ownership, exact account provenance, posting/key/memo/account/body bounds, 100 concurrent identical replays, and same-key/different-body conflict.
- [ ] 3.4 Harden fixture `009_market_ledger.sql`: store `request_sha256`, explicitly revoke function/table/sequence privileges from public/user-facing roles, grant only a dedicated internal settlement role, fix the trusted search path, validate Wave 2 bounds, reject `external:*`/`pool:*` and caller-supplied treasury accounts, and make raw apply/drain helpers internal. Repeat only in later production-native SQL authored from the approved live baseline.
- [ ] 3.5 Add one internal settlement wrapper that atomically performs business-state/version CAS, actor/account authorization, adapter postings, `market.apply_tx`, every required drain assertion, and audit-state commit; prove any failure rolls back all effects.
- [ ] 3.6 Differential-test randomized persistent transactions against pure `Ledger`, including overdrafts, repeated accounts, reverse-order first-touch accounts, residual escrows, identical replays, and changed-body conflicts.
- [ ] 3.7 Add adversarial tests for verified-request tenant derivation, mixed-tenant rejection, signed/bounded/revoked on-behalf grants, server-recomputed canonical hashes, hash mismatch, composite tenant keys, duplicate-account coalescing, and the global cross-family lock order.

## 4. Dark Transport and Atomic Claim

- [ ] 4.1 Write failing tests in `tests/test_paid_market_transport.py` proving verified subject+tenant authority is required, environment/caller-selected tenants grant no authority, a signed target/action/account/amount/time-bounded host grant records grant+host+target identities, the default-off feature flag blocks mutation, pure entries are serialized unchanged, v1 YAML/`public.ledger` stay byte-stable, and transport exposes no direct balance/table writer.
- [ ] 4.2 Define injected `MarketLedgerRpc`, immutable settlement/claim command values, and typed applied/replayed/conflict/contention results in `tinyassets/payments/market_transport.py`; add no psycopg dependency to application core, keep API modules delegation-only, and do not register a live route.
- [ ] 4.3 Implement a psycopg adapter only in prototype/integration-test scope with explicit transaction, result, and error mapping; defer the production client until the Supabase baseline is approved.
- [ ] 4.4 Write failing integration tests for single-request narrow claim and multi-offer matching: use `best_execution`, lock selected IDs in canonical order, compare monotonic versions, reject stale selections atomically, retry at most three times with jitter, and return honest insufficient-supply/contention results.
- [ ] 4.5 Implement the atomic claim wrapper and transport orchestration without full-inbox polling, greedy matching, partial claims, or changes to the repo-file node-bid claim domain.
- [ ] 4.6 Record the S14/B36 dependency on exact future chain-effect identity `job_id:lease_fence:accepted_result_sha256`; do not add provisional chain states, signer, resubmission, reconciliation worker, or alarm behavior in Wave 2.

## 5. Fault, Concurrency, and Uptime Proof

- [ ] 5.1 Add fault injection before/after claim CAS, ledger apply, drain assertion, database commit, and response delivery; prove recovery yields zero or one committed database effect, never two.
- [ ] 5.2 Run 100 concurrent buyers against one versioned offer book; prove no offer sells twice and each committed selection equals `best_execution` for its valid snapshot.
- [ ] 5.3 Run the §14 capability-sharded scenario through the production-shaped Supabase Realtime push, without mocked delivery, with 500 synthetic daemons and 1,000 requests over five minutes; prove zero lost/duplicate claims, no poll-all storm, and claim latency p99 below three seconds.
- [ ] 5.4 On an isolated Supabase test project matching launch region/compute, run at least 64 writers through at least one million overlapping transfers. Require at least 5,000 committed transactions/second aggregate, p99 below 250 ms, zero conservation drift/negative internal balance/deadlock/timeout, and sustained CPU/pool occupancy below 80%; record environment plus p50/p95/p99.
- [ ] 5.5 Run 500 simultaneous terminal attempts on one escrow; prove one settlement succeeds and every other caller gets the prior result or a clean state/idempotency conflict, with the escrow drained exactly once.
- [ ] 5.6 Stop every tray/daemon host and prove market reads/durable state remain available, work remains honestly pending, no settlement is fabricated, and the surface reports settlement unavailable. Defer hosted retry/alarm proof to S14/B36 rollout.

## 6. Verification, Mirror, and Handoff

- [ ] 6.1 Rebuild the Claude plugin runtime mirror and run its parity/import probe after the new pure/payment modules land; do not hand-edit generated mirror files.
- [ ] 6.2 Run focused tests, the full relevant PostgreSQL integration suite, `python -m ruff check` on changed Python, both strict OpenSpec validations, and the pre-change 180-test pure-core/matcher suite; attach dated environment and raw latency/failure evidence.
- [ ] 6.3 Obtain independent implementation review across correctness, security, migration safety, concurrency, non-custodial boundaries, and diff simplicity; resolve every Critical/Important finding and re-run affected evidence.
- [ ] 6.4 Keep migrations unapplied, transport unregistered, on-chain effects absent, and `TINYASSETS_PAID_MARKET` off; record explicit dependencies on distributed-execution S14/B36 plus host decisions for migration, cutover, enablement, and Base deployment.
- [ ] 6.5 After implementation lands, sync the delta into `openspec/specs/`, validate idempotently, archive this change in the same lane, and remove the STATUS row in the landing commit.

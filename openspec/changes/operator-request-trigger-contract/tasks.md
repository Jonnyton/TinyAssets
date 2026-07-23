## 1. Evidence, Inventory, and Claims

- [ ] 1.1 In `docs/ops/operator-request-v2-inventory.md`, record dated production-shaped counts for pending/running v1 `host_request` rows, custom tier weights, public v1 request writers, active worker build SHAs, and worker heartbeat formats; do not relabel any row.
- [ ] 1.2 Run `python scripts/claim_check.py --provider <provider> --check-files "<exact implementation files>"` and exact diffs against PRs #1606, #1472, and #1464; update the STATUS Files/Depends cells before touching overlaps.
- [ ] 1.3 Preserve the declared-Loop reproduction and focused baseline commands in `docs/ops/operator-request-v2-inventory.md`, including the current accepted-but-unqueued output and `tests/test_dispatcher_queue.py:398-469,785-823`, `tests/test_submit_request_wiring.py:204-294`, and `tests/test_patch_request_incentives.py:19-77`.
- [ ] 1.4 Seed valid Loop fixtures and replace obsolete host/environment assertions only in those named test regions; prove the reproduction fails for the intended trigger/admission reason before implementation.

## 2. Transactional Schema and Store

- [ ] 2.1 Add failing schema/migration tests in `tests/test_request_admission_store.py` for one-to-one Request/admission/task links, scoped key-hash uniqueness, finite `[0,100]` checks, event foreign keys, quarantine digest uniqueness, and upgrade from a pre-change `.tinyassets.db`.
- [ ] 2.2 Add the schema/migrator for `request_admissions`, `request_admission_events`, `branch_tasks_v2`, `branch_tasks_v2_quarantine`, and `request_admission_rollouts` in `tinyassets/storage/request_admissions.py`, then invoke it from the active pre-traffic `initialize_author_server` path in `tinyassets/daemon_server.py`; do not leave uncalled DDL in `tinyassets/storage/__init__.py` or lazy-ALTER on first request.
- [ ] 2.3 Add backend-neutral persistence methods in `tinyassets/storage/request_admissions.py`: `commit_admission`, `lookup_replay`, `list_v2_candidates`, `claim_v2_task`, lifecycle transitions, quarantine, compaction, and universe deletion.
- [ ] 2.4 Reuse `user_requests` as the canonical Request row; update its store API rather than creating a second full request table or persisting raw idempotency keys.
- [ ] 2.5 In one transaction, re-read stored ACL/grant state, allocate random IDs, insert Request/admission/v2 task/event, and commit; add fault injection at every statement and prove each precommit failure leaves zero aggregate rows.
- [ ] 2.6 Store the exact successful public-result fields, then prove a postcommit serialization/delivery failure replays the original IDs without another task or mutation-ledger entry.
- [ ] 2.7 Implement 30-day terminal-detail compaction plus a minimal scoped key-hash/body-digest/ID/state tombstone retained until universe deletion; test pending rows never compact.
- [ ] 2.8 Add SQLite WAL/foreign-key/busy-timeout and concurrent migration tests matching the shared storage convention; surface lock errors instead of treating them as misses.
- [ ] 2.9 Add backend conformance tests proving local SQLite uses linked `user_requests` + `branch_tasks_v2`, while hosted Postgres co-locates stable `request_id`/`branch_task_id` and lifecycle in one `request_inbox` row claimed by the existing narrow RPC with no second hosted dispatcher.

## 3. Identity and Grant Lifecycle

- [ ] 3.1 Add failing authority-matrix tests in `tests/test_operator_priority_authority.py` for authenticated subject, ordinary fine/coarse submit scope, exact-universe write/admin ACL, exact-universe priority grant, positive/no-grant refusal, zero-weight opt-out, host/environment non-authority, wildcard rejection, cross-universe isolation, and pre/exact/post-expiry behavior.
- [ ] 3.2 Extend capability-grant persistence in `tinyassets/storage/accounts.py`; add and actively invoke its schema migration from `tinyassets/daemon_server.py` with issuer, issue/expiry/revocation times, and monotonically increasing generation without erasing historical rows.
- [ ] 3.3 Add trusted issue/revoke methods in `tinyassets/storage/accounts.py`; require both exact-universe admin ACL and `grant_capabilities`, make repeated revoke idempotent, and increment generation on regrant.
- [ ] 3.4 Replace `_env_actor_can` on request admission with one request-local verdict in `tinyassets/api/permissions.py` and `tinyassets/api/universe.py`; retain no environment or host fallback.
- [ ] 3.5 Prove weight zero is `user_request`/unboosted `owner_queued` even for a grant holder; prove positive weight without an active grant returns `priority_authorization_required` with zero persistence; prove a grant without ordinary authority persists nothing.
- [ ] 3.6 Prove replay checks authentication, ordinary scope, and current ACL before lookup; ACL loss returns non-enumerating `universe_access_denied`, while priority-only revocation or expiry returns committed history and blocks new-key priority.

## 4. Canonical Public Admission

- [ ] 4.1 Add failing schema/behavior tests in `tests/test_request_admission_surface.py` for `idempotency_key`, all request fields, exact success fields, and parity between `tinyassets/universe_server.py` and `tinyassets/directory_server.py`.
- [ ] 4.2 Extend `write_graph` in both server modules with the one public `idempotency_key` name plus request incentive/direction/priority fields; reject unknown request-target fields and preserve handle-level `idempotentHint=false`.
- [ ] 4.3 Route `write_graph(target="request")` through the trusted transaction in `tinyassets/api/universe.py`; retire the public v1 request writer at per-universe v2 cutover instead of maintaining a second final path.
- [ ] 4.4 Validate key length/regex and JSON-number `[0,100]` semantics before persistence; test `0`, `1e-9`, just below `100`, `100`, Boolean, string, NaN, infinities, negative, and over-cap.
- [ ] 4.5 Implement SHA-256 over RFC 8785 canonical body fields with exact UTF-8 text and server-derived universe; test same-body replay, changed-body conflict, independent cross-scope raw keys, unknown fields, and no Unicode normalization drift.
- [ ] 4.6 Return exactly the specified committed result fields and remove `queue_position`, `ahead_of_yours`, `what_happens_next`, evidence, and “next” language from main and directory results.
- [ ] 4.7 Teach `_dispatch_with_ledger` that an idempotent replay is access-audit only and must not append another mutation-ledger row.
- [ ] 4.8 Add dependency/parity coverage so retirement of the hidden legacy universe tool cannot remove the only priority-capable request path.

## 5. Epoch-2 Queue, Selection, and Claim

- [ ] 5.1 Add failing `tests/test_branch_tasks_v2.py` coverage for v2 CRUD, conditional claim, lease, heartbeat, cancel, terminal sinks, recovery, random-ID uniqueness, and transaction rollback.
- [ ] 5.2 Add the epoch-2 BranchTask adapter in `tinyassets/branch_tasks_v2.py` over `tinyassets.storage.request_admissions`; do not write v2 task IDs into `branch_tasks.json`.
- [ ] 5.3 Extend `tinyassets/dispatcher.py` to merge eligible v1/v2 candidates for v2 workers, keep selection pure, add `operator_request=100/live`, preserve all other defaults, and never inherit a missing operator weight from host configuration.
- [ ] 5.4 Under the epoch-2 claim transaction, re-check protocol capability and worker/runtime/boot/build/config identity before pending-to-running; test a stale or false descriptor cannot claim.
- [ ] 5.5 Prove v1 code can drain v1 but cannot open or mutate epoch 2 even when given a v2 task ID; prove v2 workers can drain both epochs.
- [ ] 5.6 Preserve directed assignments as `owner_queued`; retain bounded boost only with priority authority and test the chosen additive ordering against operator/user/host rows.
- [ ] 5.7 Update request materialization in `tinyassets/work_targets.py` and restart registration in `fantasy_daemon/branch_registrations.py` to consume canonical v2 Request/task state without mutating or executing a v1 JSON projection.
- [ ] 5.8 Update graph-cycle claim integration and lifecycle observers to route v2 tasks through the v2 adapter while retaining v1 historical behavior; treat that claim as scheduling reservation only and require the active `distributed-execution` B2 signed owner/daemon/job/capsule/lease/fence grant before external execution.
- [ ] 5.9 Add integration tests proving a won epoch-2 scheduling claim without valid B2 signed authority cannot create an external lease, execute, or submit a result, and that queue/admission/heartbeat rows only narrow or reject B2 authority.

## 6. Worker Protocol Evidence and Operational Surfaces

- [ ] 6.1 Add failing heartbeat/descriptor tests in `tests/test_cloud_worker.py` and `tests/test_supervisor_liveness.py` for protocol, capability, build/config SHA, boot/worker/runtime/universe IDs, per-worker isolation, and 90-second expiry.
- [ ] 6.2 Extend `tinyassets/cloud_worker.py` and `tinyassets/daemon_registry.py` so release/runtime-derived descriptors are written to durable runtime metadata and each `.worker_supervisor.<worker>.json`; never derive support from request arguments, identity grants, or provider auth.
- [ ] 6.3 Extend `tinyassets/api/status.py` and `tinyassets/api/universe.py` operational reads to merge epoch counts and distinguish `awaiting_compatible_capacity`, `invalid_operator_admission`, `quarantined`, and `policy_parked`.
- [ ] 6.4 Update `tinyassets/cloud_worker.py::_has_pickable_branch_task` and wakeup/restart decisions to use eligible merged candidates without treating pending-no-capacity as invalid or spending platform compute.
- [ ] 6.5 Add separate transactional quarantine maintenance in `tinyassets/branch_tasks_v2.py`; prove insert/move atomicity, one receipt per digest, selector purity, red health on failure, and no raw request/evidence leakage.
- [ ] 6.6 Inject mixed valid/forged/missing-receipt/unsupported-protocol rows and prove invalid rows never execute or block valid v1/v2 selection.

## 7. Rollout and Mixed-Version Isolation

- [ ] 7.1 Add failing `tests/test_operator_admission_rollout.py` coverage for manifest transitions, canary universes, allowed SHAs, expiry, per-admission reread, unknown-worker block, zero-worker allowance, and rollback within 60 seconds.
- [ ] 7.2 Implement the deployment kill switch plus transactional per-universe rollout manifest in `tinyassets/request_admission_rollout.py`; default `TINYASSETS_OPERATOR_REQUEST_WRITES` off and never cache effective state across admissions.
- [ ] 7.3 Let weight zero follow ordinary admission without the elevation gate; return `priority_authorization_required` for positive weight without active authority and `operator_priority_unavailable` when a composed positive-priority verdict is blocked by the writer gate, both with zero persistence and no demotion. After a universe reaches enabled, reject/retire public v1 request writers.
- [ ] 7.4 Inventory and pin safe legacy build SHAs proven to select/claim v1 only; unknown/partial online builds block canary-to-enabled but offline legacy installs are not falsely claimed upgraded.
- [ ] 7.5 Store the cutover receipt with rollout/epoch/capability, reader/server/worker releases, mirror parity, evidence, approver, activation/expiry time, and zero unresolved invalid v2 rows.
- [ ] 7.6 Prove rollback stops new v2 admission within 60 seconds while v2 readers continue to drain committed work and v1 remains isolated.

## 8. Exact Concurrency and Zero-Capacity Proof

- [ ] 8.1 Add `tests/load/operator_admission_v2.py` and fixture tooling that runs the real production queue/storage/lock substrate, emits raw timestamped events, and invokes no model/provider.
- [ ] 8.2 Warm 60 seconds, then hold 400 v2 plus 100 pinned v1 daemon processes concurrently alive for the full 300-second canonical window; fail if population drops.
- [ ] 8.3 During that window, preseed 100 v1 host rows; admit exactly 500 operator, 300 ordinary, and 200 directed unique requests; keep compatible capacity continuously available for every request and direct all 200 to live v2 daemons; add 10% concurrent replays, out-of-count conflicts, 100 status readers at 1 Hz, and invalid v2 fixtures.
- [ ] 8.4 Require exactly 1,000 aggregates and all 1,000 durable claims; zero loss, unclaimed requests, duplicate live claims, invalid execution, legacy/unauthorized v2 claims, corruption, or deadlock; compute `committed_at`-to-claim p99 below 3 seconds over the full 1,000-request denominator.
- [ ] 8.5 Compare admission-response and claim-operation latency against a same-environment readers-only baseline with no more than 20% regression; do not report those as §14 latency targets.
- [ ] 8.6 Record exact commands, seed, SHAs/images/config/manifest, topology/mount/clock, p50/p95/p99/max, transactions/locks, throughput, store/file growth, write amplification, CPU, aggregate memory, disk/fsync, handles, network, and process count; require at least 20% peak CPU/memory/disk headroom.
- [ ] 8.7 Run a separate instrumented rolling-restart/disconnect-reconnect test and do not substitute it for the uninterrupted 500-daemon run.
- [ ] 8.8 Stop all workers, commit operator work, prove zero provider/model/credential/quota/payment/hardware/host invocation and `awaiting_compatible_capacity`, restart v2 capacity, and prove one claim per task with p99 below 3 seconds from capacity availability.

## 9. Verification, Review, and Publication

- [ ] 9.1 Run `pytest -q tests/test_request_admission_store.py tests/test_operator_priority_authority.py tests/test_request_admission_surface.py tests/test_branch_tasks_v2.py tests/test_dispatcher_queue.py tests/test_submit_request_wiring.py tests/test_patch_request_incentives.py tests/test_cloud_worker.py tests/test_supervisor_liveness.py tests/test_operator_admission_rollout.py tests/test_distributed_execution_authority.py`.
- [ ] 9.2 Run `python -m ruff check` on every changed Python file, `python packaging/claude-plugin/build_plugin.py`, plugin mirror parity/import probes, and `git diff --check`.
- [ ] 9.3 Run `openspec validate operator-request-trigger-contract --strict` plus full strict OpenSpec validation and resolve every error.
- [ ] 9.4 Obtain independent correctness, identity/security, concurrency/migration, and diff-simplicity review; resolve every Critical/Important finding and rerun affected evidence.
- [ ] 9.5 Keep both writer keys off until host-approved cutover; run public MCP canaries and rendered-chatbot `ui-test`, then record post-fix real-user evidence or leave a freshness-stamped STATUS watch.
- [ ] 9.6 After implementation lands, sync all three deltas into canonical specs, validate sync idempotently, archive the change, and remove the STATUS row in the landing commit.

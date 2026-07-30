# Background Branch authority inventory and read-owner map

Freshness: 2026-07-30 America/Los_Angeles, Windows, current main
`74419e561a3c59d68e9113df64a27ab120d7beb8`; production recovery
`30571039375` completed with canonical HTTP 200, exact-seven surface proof, and
durable fence finalization.

## Result

This closes `harden-background-branch-execution-authority` tasks 1.1 and 1.2 in
dark mode. It does not activate background authority, choose a persistence
backend, or change any runtime decision.

The executable closure guard is
`scripts/check_background_authority_inventory.py`. It scans all Python under
`tinyassets/` and `fantasy_daemon/` for reviewed Branch execution and queue
boundaries, compares the result to an exact callsite manifest, verifies every
source-family/read-owner marker, and proves both shipped `file_bug` copies call
no execution or enqueue boundary. `tests/test_background_authority_inventory.py`
makes that check part of CI and mutation-proves that a new execution root is
detected.

Current scan: 16 sensitive callsites, 12 source families, 13 canonical read
owners, zero unreviewed callsites, zero stale entries, and zero filing-to-run
calls.

## Execution and issuance roots

| Family | Current root / boundary | Authority state and required successor behavior |
|---|---|---|
| Schedule and event | `Scheduler._maybe_fire_schedule` and `Scheduler._dispatch_event` call an injected `run_fn` after reading persisted schedule/subscription rows. | Persisted continuation exists, but `owner_actor` and synthetic `scheduler:*` / `subscriber:*` strings are not execution authority. Tasks 3.1-3.7 must derive and revalidate a binding/attempt. |
| Goal subscription | `tinyassets.subscriptions` stores the legacy Goal list; `tinyassets.scheduler` owns event subscriptions. | Treat list membership only as source state. Task 3.10 replaces it with authenticated principal/universe target delegation. |
| Soul / `PROGRAM.md` / compiled cycle | `fantasy_daemon._resolve_loop_daemon_context`, cloud-worker universe discovery, and `fantasy_daemon/branches/universe_cycle.yaml`. | Current daemon context and built-in cycle are diagnostic/executor inputs, not target authority. Tasks 4.1-4.8 bind the pinned soul source and retire direct compiled bypass. |
| Request admission | `api.universe._action_submit_request` appends an epoch-1 `BranchTask`; `RequestAdmissionStore` and `Epoch2BranchTaskAdapter` implement the transactional successor. | Admission/queue identity narrows scheduling only. Task 3.9 commits the exact target binding with the Request aggregate; B2 remains separately required. |
| Goal-pool / paid-market producer | `GoalPoolProducer` and `NodeBidProducer` emit through `dispatcher.run_branch_task_producers_into_queue`. | Producer YAML, `posted_by`, and market rows do not authorize execution. Tasks 3.11-3.12 require accepted contract/source generations and prepared target bindings. |
| `BranchTask` claim | `fantasy_daemon._try_dispatcher_pick` calls epoch-1 `claim_task`; epoch-2 exposes inactive transactional claim/recovery. | A queue claim proves possession only. Task 2.5 adds attempt/audience/generation fencing and fail-closed epoch migration. |
| Graph enqueue | `graph_compiler._node_enqueue_branch_run` calls `append_task_capped`. | Public target checks and queue caps are not durable delegated authority. Tasks 5.1-5.5 derive and transfer a bounded child binding before pickability. |
| Live/frozen `invoke_branch` | Compiler closures call `execute_branch_async` or `execute_branch_version_async`; both converge on `_execute_branch_core`. | Tasks 5.1-5.2 require a non-serializable trusted delegation context and atomic child binding for direct and enqueued children. |
| Direct root run | `api.runs._action_run_branch` and `_action_run_branch_version` call the two run entrypoints. | Current request ACL checks are the input owner; task 6 root issuance must snapshot their result into one server-owned binding/attempt. |
| Resume/recovery | `api.runs._action_resume_run`, `_ensure_runs_recovery`, `runs.resume_run`, `runs.recover_in_flight_runs`, epoch-1 task recovery, and epoch-2 `recover_expired`. | Checkpoint/run/lease state is evidence, never authority. Reissue/reclaim must use the exact predecessor attempt and a conclusive boundary. |
| Actor boundary | `api.permissions.current_request_actor_id` is the request identity read; `api.engine_helpers._current_actor` may fall back to environment-derived host identity. | Request identity is canonical. `_current_actor` output is diagnostic only for background issuance; tasks 3/4/6 remove it from durable authority fields and decisions. |
| Daemon/cloud/distributed worker | `fantasy_daemon._try_execute_claimed_branch_task`, `cloud_worker.run_supervisor`, and `ExecutionGrantV1`. | Worker descriptors and daemon ownership do not grant target access. Every launch needs the exact attempt plus separately valid B2/provider authority. |
| Selector/leaderboard/market delegate | selector dispatch calls `_execute_branch_core`; leaderboard calls selector dispatch; Goal canonical dispatch delegates to `_action_run_branch_version`. | These are async root-run entrypoints, not alternate trust domains. They must consume the same request-derived root binding and cannot mint authority from ranking/canonical state. |
| Historical wiki forwarding | `bug_investigation.enqueue_investigation_request` remains a retirement-only legacy queue writer. Both shipped `_wiki_file_bug` handlers are filing-only. | It is excluded from logical-key builders, binding, backfill, drain, revival, and execution. The closure guard fails if either shipped `file_bug` copy calls an enqueue/execution boundary. |

## Exact sensitive callsite closure

The guard records these current call edges. A new edge fails CI until this
audit and manifest are reviewed together.

- `fantasy_daemon/__main__.py::_try_dispatcher_pick -> claim_task`
- `tinyassets/api/market.py::_action_goal_run_canonical -> _action_run_branch_version`
- `tinyassets/api/quality_leaderboard.py::build_quality_leaderboard -> dispatch_selector`
- `tinyassets/api/runs.py::_action_resume_run -> resume_run`
- `tinyassets/api/runs.py::_action_run_branch -> execute_branch_async`
- `tinyassets/api/runs.py::_action_run_branch_version -> execute_branch_version_async`
- `tinyassets/api/runs.py::_ensure_runs_recovery -> recover_in_flight_runs`
- `tinyassets/api/selector_dispatch.py::dispatch_selector -> _execute_branch_core`
- `tinyassets/api/universe.py::_action_submit_request -> append_task`
- `tinyassets/bug_investigation.py::enqueue_investigation_request -> append_task`
- `tinyassets/dispatcher.py::run_branch_task_producers_into_queue -> append_task`
- `tinyassets/graph_compiler.py::_build_invoke_branch_node._node_fn -> execute_branch_async`
- `tinyassets/graph_compiler.py::_build_invoke_branch_version_node._node_fn -> execute_branch_version_async`
- `tinyassets/graph_compiler.py::_node_enqueue_branch_run -> append_task_capped`
- `tinyassets/runs.py::execute_branch_async -> _execute_branch_core`
- `tinyassets/runs.py::execute_branch_version_async -> _execute_branch_core`

## Canonical read interfaces

The target consumes these owners; it does not create parallel identity, ACL,
queue, B2, or provider truth.

| Read category | Canonical current owner | State consumed by background authority |
|---|---|---|
| Identity | `api.permissions.current_request_actor_id` | Authenticated request principal only. |
| ACL | `api.permissions.universe_access_allows` | Exact universe read/write decision; revalidate just in time. |
| Branch | `api.branches._branch_authorized` | Current branch ownership/visibility decision; target snapshot is stored separately. |
| Daemon | `daemon_registry.daemon_control_status` | Runtime/daemon eligibility and health, never target authority. |
| Run | `api.runs._run_read_allowed` / `_run_write_allowed` | Current run visibility/mutation decision and canonical run record. |
| Request/admission | `storage.request_admissions.RequestAdmissionStore` | Transactional Request/task/claim evidence; scheduling only. |
| Filing-only wiki negative | `retire-cheat-loop` `wiki-commons` delta plus both shipped `_wiki_file_bug` handlers | No receipt, task, run, investigation block, or background issuance. |
| Goal subscription | `subscriptions.list_subscriptions` and `scheduler.list_scheduler_subscriptions` | Source membership/generation only; authenticated delegation is a successor task. |
| Paid-market acceptance | `paid-market-track-e-wave-2-transport` paid-market-economy delta | Contract-only until acceptance/delivery owners land; a market row is never authority. |
| Queue | epoch-1 `branch_tasks.read_queue` and epoch-2 `Epoch2OperationalRead` | Scheduling state, lease/generation, and recovery evidence only. |
| B2 | `execution_authority.records.ExecutionGrantV1` and `distributed-execution` | Separate signed owner/daemon/job/capsule/lease/fence execution authority. |
| Provider work | `constrain-set-engine-provider-authority` provider-routing delta | Contract-only durable provider-work hold/receipt owner; no ambient fallback. |
| Provider attempt | `provider-attempt-receipts` provider-routing delta | Contract-only result-local attempt evidence; cannot become execution authority. |

## Cloud-drain implication

The first cloud drain needs only the Request/single-flight subset of these
families, but it must pass through the same closed interfaces. The shortest
implementation order after this inventory is:

1. complete the rendered filing-only production proof so retirement task 2.1
   stops gating the dark store;
2. implement binding/attempt persistence and lifecycle tasks 2.1-2.4 over the
   approved epoch-2 transaction boundary;
3. bind one private main-universe Request/Branch version and Jonathan-owned
   provider/GitHub authority;
4. prove one restart-safe PR-only slice, then cut over with one active epoch;
5. retain the mandatory 24-hour computer-off acceptance interval.

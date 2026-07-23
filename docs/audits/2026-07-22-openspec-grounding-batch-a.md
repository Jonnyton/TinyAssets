# OpenSpec canonical grounding — Batch A

- **Date:** 2026-07-22
- **Baseline:** `origin/main` at `7c23c881502460f65cfd5ee81c27042d87743f24`
- **Environment:** Windows, Python 3.14
- **Scope:** the first eight canonical capabilities in lexical order; 54 requirements and 142 scenarios
- **Labels:** `BUILT` means the complete bounded requirement is present in current source; `PARTIAL` means a material subset is built but the absolute requirement is not; `CONTRADICTED` means current behavior directly violates the requirement.

This matrix grounds every requirement independently. Source references identify the implementation boundary; test references identify representative executable evidence, not necessarily every clause. Where the repository has no dedicated test file, that absence is stated rather than replaced with an unrelated test.

## Result

| Classification | Requirements | Scenarios |
|---|---:|---:|
| BUILT | 53 | 141 |
| PARTIAL | 1 | 1 |
| CONTRADICTED | 0 | 0 |
| **Total** | **54** | **142** |

The sole mismatch is in `daemon-runtime-and-dispatch`: delayed two-step discard is built, but the requirement and its first scenario claim a closed lifecycle set while the generic record boundary deliberately persists arbitrary lifecycle strings. The later requirement “Generic work targets persist records and expose guarded helper transitions” states that permissiveness correctly.

## `community-patch-loop` — 6 requirements, 15 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Bug Filing Enqueues A Canonical Investigation Request | BUILT | 3 BUILT | `tinyassets/bug_investigation.py:274`, `tinyassets/bug_investigation.py:331`, `tinyassets/api/wiki.py:1978` | `tests/test_bug_investigation_wiring.py:58`, `tests/test_bug_investigation_wiring.py:118`, `tests/test_bug_investigation_wiring.py:184` |
| Investigation Runs Attach A Patch Packet To The Wiki Bug Page | BUILT | 3 BUILT | `tinyassets/bug_investigation.py:131` | `tests/test_bug_investigation.py:219`, `tests/test_bug_investigation.py:243`, `tests/test_bug_investigation.py:274` |
| Auto-Ship Validation Is A Pure Dry-Run Safety Envelope | BUILT | 3 BUILT | `tinyassets/auto_ship.py:379` | `tests/test_auto_ship.py:220`, `tests/test_auto_ship.py:230`, `tests/test_auto_ship.py:353` |
| Auto-Ship PR Creation Is Feature-Flagged Off And Never Merges | BUILT | 2 BUILT | `tinyassets/auto_ship_pr.py:35`, `tinyassets/auto_ship_pr.py:211` | `tests/test_auto_ship_pr.py:38`, `tests/test_auto_ship_pr.py:341` |
| Auto-Ship Attempts Are Recorded In An Append-Only Ledger | BUILT | 2 BUILT | `tinyassets/auto_ship_ledger.py:403`, `tinyassets/auto_ship_ledger.py:440` | `tests/test_auto_ship_ledger.py:272`, `tests/test_auto_ship_ledger.py:285`, `tests/test_auto_ship_ledger.py:525` |
| Loop Health Is Watched By Read-Only Monitors | BUILT | 2 BUILT | `scripts/community_loop_watch.py:417`, `scripts/community_loop_watch.py:526`, `scripts/revert_loop_canary.py:160` | `tests/test_community_loop_watch.py:84`, `tests/test_revert_loop_canary.py:96`, `tests/test_revert_loop_canary.py:119` |

## `constraint-evaluation` — 6 requirements, 11 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| ASP validation loads the configured rule text without inventing missing rules | BUILT | 2 BUILT | `tinyassets/constraints/asp_engine.py:55` | `tests/test_asp_engine_data_file.py:26`, `tests/test_asp_engine_data_file.py:60` |
| ASP validation reports satisfiability and available solver evidence | BUILT | 2 BUILT | `tinyassets/constraints/asp_engine.py:70`, `tinyassets/constraints/asp_engine.py:224` | `tests/test_asp_solver.py:27`, `tests/test_asp_solver.py:49` |
| Surface conversion and scoring produce the current shared constraint representation | BUILT | 2 BUILT | `tinyassets/constraints/asp_engine.py:242`, `tinyassets/constraints/constraint_surface.py:97` | `tests/test_asp_solver.py:139`, `tests/test_asp_solver.py:255`, `tests/test_asp_solver.py:286` |
| Synthesis routes rich and sparse inputs through the current bounded pipeline | BUILT | 2 BUILT | `tinyassets/constraints/constraint_synthesis.py:62`, `tinyassets/constraints/constraint_synthesis.py:95` | `tests/test_planning.py:167`, `tests/test_planning.py:175`, `tests/test_planning.py:193`, `tests/test_planning.py:209` |
| Current degraded synthesis behavior is not represented as a quality guarantee | BUILT | 1 BUILT | `tinyassets/constraints/constraint_synthesis.py:164` | `tests/test_planning.py:257` |
| Current solver and violation diagnostics have bounded fidelity | BUILT | 2 BUILT | `tinyassets/constraints/asp_engine.py:70`, `tinyassets/constraints/asp_engine.py:224` | `tests/test_asp_solver.py:49`, `tests/test_asp_solver.py:231` |

## `credential-vault` — 6 requirements, 18 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Per-Universe Typed Credential Store | BUILT | 2 BUILT | `tinyassets/credential_vault.py:78`, `tinyassets/credential_vault.py:126` | `tests/test_credential_vault.py:25`, `tests/test_credential_vault.py:58` |
| Fail-Loud Load Semantics | BUILT | 2 BUILT | `tinyassets/credential_vault.py:98`, `tinyassets/credential_vault.py:110` | `tests/test_credential_vault.py:58`, `tests/test_credential_vault.py:175` (representative; no dedicated malformed-JSON test) |
| As-Built Storage Protection Is Filesystem Permissions Only | BUILT | 1 BUILT | `tinyassets/credential_vault.py:50`, `tinyassets/credential_vault.py:144`, `tinyassets/credential_vault.py:263` | `tests/test_credential_vault.py:25` (cleartext round-trip; no dedicated mode-bit assertion) |
| Daemon-Side GitHub Token Resolution By Exact Destination And Purpose | BUILT | 2 BUILT | `tinyassets/credential_vault.py:192` | `tests/test_credential_vault.py:66` |
| Subscription-Home Materialization For CLI Writers | BUILT | 2 BUILT | `tinyassets/credential_vault.py:255`, `tinyassets/credential_vault.py:301` | `tests/test_credential_vault.py:96`, `tests/test_credential_vault.py:135` |
| Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage | BUILT | 9 BUILT | `tinyassets/credential_vault.py:390`, `tinyassets/credential_vault.py:434`, `tinyassets/providers/base.py:157`, `tinyassets/api/universe.py:4904` | `tests/test_credential_fail_closed.py:32`, `tests/test_credential_fail_closed.py:51`, `tests/test_credential_fail_closed.py:63`, `tests/test_credential_fail_closed.py:77`, `tests/test_s2_engine_assignment.py:80` |

The last credential requirement is `BUILT` only because its unsafe partial-overlay and swallowed-non-`ValueError` behavior is explicitly specified as an as-built limitation. It is not a claim that the boundary is secure; the corrective fail-closed overlay lane remains necessary.

## `daemon-identity-and-host-pool` — 5 requirements, 10 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Daemon identities preserve explicit soul and lineage state | BUILT | 2 BUILT | `tinyassets/daemon_registry.py:139` | `tests/test_daemon_registry.py:25`, `tests/test_daemon_registry.py:56` |
| Runtime instances bind the daemon identity to an allowed model | BUILT | 2 BUILT | `tinyassets/daemon_registry.py:285`, `tinyassets/daemon_registry.py:327` | `tests/test_daemon_registry.py:127`, `tests/test_daemon_registry.py:199` |
| Daemon control and behavior updates remain ownership scoped | BUILT | 2 BUILT | `tinyassets/daemon_registry.py:401`, `tinyassets/daemon_registry.py:504` | `tests/test_daemon_registry.py:230` |
| The current host pool uses REST registration and heartbeat state | BUILT | 2 BUILT | `tinyassets/host_pool/client.py:200`, `tinyassets/host_pool/registration.py:37`, `tinyassets/host_pool/heartbeat.py:31` | `tests/test_host_pool_client.py:255`, `tests/test_host_pool_client.py:319`, `tests/test_host_pool_client.py:350` |
| Current bid discovery is polling-only and does not claim work | BUILT | 2 BUILT | `tinyassets/host_pool/client.py:326`, `tinyassets/host_pool/bid_poller.py:29` | `tests/test_host_pool_client.py:232`, `tests/test_host_pool_client.py:378`, `tests/test_host_pool_client.py:415` |

## `daemon-runtime-and-dispatch` — 12 requirements, 49 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Dispatcher selection is a stateless deterministic function invoked at cycle boundaries | BUILT | 3 BUILT | `tinyassets/dispatcher.py:363` | `tests/test_dispatcher_queue.py:192`, `tests/test_dispatcher_queue.py:244`, `tests/test_dispatcher_queue.py:256` |
| Queue-state mutations are file-locked, single-winner, and terminally idempotent | BUILT | 3 BUILT | `tinyassets/branch_tasks.py:328`, `tinyassets/branch_tasks.py:433` | `tests/test_dispatcher_queue.py:124`, `tests/test_dispatcher_queue.py:144`, `tests/test_dispatcher_queue.py:152`, `tests/test_branch_tasks.py:202` |
| Startup recovery is lease-aware and worker-scoped, never a blanket reset | BUILT | 3 BUILT | `tinyassets/branch_tasks.py:567`, `tinyassets/branch_tasks.py:631` | `tests/test_branch_tasks.py:231`, `tests/test_branch_tasks.py:251`, `tests/test_branch_tasks.py:314`, `tests/test_branch_tasks.py:375` |
| The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain | BUILT | 4 BUILT | `tinyassets/cloud_worker.py:545`, `tinyassets/cloud_worker.py:676` | `tests/test_cloud_worker.py:126`, `tests/test_cloud_worker.py:445`, `tests/test_cloud_worker.py:735`, `tests/test_cloud_worker.py:798` |
| The container healthcheck asserts liveness, not mere process existence | BUILT | 3 BUILT | `tinyassets/cloud_worker_healthcheck.py:57`, `tinyassets/cloud_worker_healthcheck.py:115` | `tests/test_loop_telemetry.py:199`, `tests/test_loop_telemetry.py:205`, `tests/test_loop_telemetry.py:231`, `tests/test_loop_telemetry.py:247` |
| Host-singleton and fleet idle-cycle coordination fail safe | BUILT | 4 BUILT | `tinyassets/singleton_lock.py:133`, `tinyassets/idle_cycle.py:217` | `tests/test_singleton_lock.py:48`, `tests/test_singleton_lock.py:114`, `tests/test_idle_cycle_single_flight.py:66`, `tests/test_idle_cycle_single_flight.py:175` |
| Scheduled and event-triggered invocation is persisted and restart-recoverable | BUILT | 3 BUILT | `tinyassets/scheduler.py:217`, `tinyassets/scheduler.py:407`, `tinyassets/scheduler.py:489` | `tests/test_scheduler.py:126`, `tests/test_scheduler.py:160`, `tests/test_scheduler.py:270`, `tests/test_scheduler.py:392` |
| The work-target registry has an explicit lifecycle | PARTIAL | 2 total: 1 BUILT, 1 PARTIAL | arbitrary-string round-trip/creation at `tinyassets/work_targets.py:145-184,513-531`; delayed discard at `:627-675` | `tests/test_work_targets.py:98-118`; direct construction/inspection confirms `WorkTarget.from_dict` and `create_target` accept arbitrary lifecycle strings |
| Soul guidance is a bounded advisory input to deterministic dispatch | BUILT | 5 BUILT | `tinyassets/dispatcher.py:215`, `tinyassets/dispatcher.py:363` | `tests/test_dispatcher_queue.py:229`, `tests/test_dispatcher_queue.py:261`, `tests/test_dispatcher_queue.py:307` |
| Generic work targets persist records and expose guarded helper transitions | BUILT | 6 BUILT | `tinyassets/work_targets.py:145`, `tinyassets/work_targets.py:294`, `tinyassets/work_targets.py:506`, `tinyassets/work_targets.py:983` | `tests/test_work_targets.py:51`, `tests/test_work_targets.py:72`, `tests/test_work_targets.py:98`, `tests/test_work_targets.py:223` |
| Fantasy foundation review gates authorial work on current hard priorities | BUILT | 5 BUILT | `domains/fantasy_daemon/phases/foundation_priority_review.py:18` | `tests/test_work_targets.py:120` |
| Fantasy authorial review ranks producer candidates and hands one target to execution | BUILT | 8 BUILT | `domains/fantasy_daemon/phases/authorial_priority_review.py:19`, `domains/fantasy_daemon/phases/dispatch_execution.py:19`, `domains/fantasy_daemon/producers.py:101` | `tests/test_task_producers.py:90`, `tests/test_task_producers.py:156`, `tests/test_task_producers.py:184`, `tests/test_work_targets.py:144`, `tests/test_work_targets.py:176` |

The lifecycle mismatch is wording, not missing delayed-discard behavior. The correction should say that built-in helpers use conventional lifecycle values while the generic persistence boundary intentionally does not validate a closed enum, and should retain the delayed mark/finalize/recoverability scenario.

## `desktop-host-runtime` — 6 requirements, 14 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| The Source Tray Owns One Host Control Process Per Lock Path | BUILT | 2 BUILT | `tinyassets_tray.py:66`, `tinyassets_tray.py:114`, `tinyassets_tray.py:904` | `tests/test_tray_singleton.py:31`, `tests/test_tray_singleton.py:57`; tunnel opt-in is source-grounded with no dedicated unit test |
| Tray Provider Controls Enforce Current Host Constraints | BUILT | 3 BUILT | `tinyassets_tray.py:323`, `tinyassets_tray.py:342`, `tinyassets_tray.py:630`, `tinyassets/preferences.py:70` | `tests/test_tinyassets_tray.py:115`, `tests/test_tinyassets_tray.py:120`, `tests/test_tinyassets_tray.py:129`, `tests/test_tinyassets_tray.py:265` |
| The Tray And Its Children Share One Active Universe Root | BUILT | 2 BUILT | `tinyassets_tray.py:155`, `tinyassets_tray.py:169`, `tinyassets_tray.py:192` | `tests/test_tinyassets_tray.py:320`, `tests/test_tinyassets_tray.py:327`, `tests/test_tinyassets_tray.py:371` |
| Tray Health Is Observable And Supervised | BUILT | 3 BUILT | `tinyassets_tray.py:203`, `tinyassets_tray.py:258`, `tinyassets_tray.py:505`, `tinyassets_tray.py:782` | `tests/test_tinyassets_tray.py:153`, `tests/test_tinyassets_tray.py:185`, `tests/test_tinyassets_tray_watchdog.py:139` |
| Desktop Components Expose Launcher, Dashboard, Tray, And Notification Behavior | BUILT | 3 BUILT | `tinyassets/desktop/launcher.py:71`, `tinyassets/desktop/dashboard.py:261`, `tinyassets/desktop/tray.py:77`, `tinyassets/desktop/notifications.py:15` | `tests/test_desktop.py:284`, `tests/test_desktop.py:351`, `tests/test_desktop.py:473`, `tests/test_desktop.py:494`, `tests/test_desktop.py:523` |
| Desktop Shortcut Creation Is A Source Utility | BUILT | 1 BUILT | `tinyassets/desktop/create_shortcut.py:37`, `tinyassets/desktop/create_shortcut.py:55`, `tinyassets/desktop/create_shortcut.py:66` | `tests/test_desktop.py:1252`, `tests/test_desktop.py:1264`, `tests/test_desktop.py:1282` |

## `development-coordination-runtime` — 7 requirements, 14 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Session Orientation Reports Repository Freshness Without Mutating Work | BUILT | 2 BUILT | `scripts/session_sync_gate.py:43`, `scripts/session_sync_gate.py:54`, `scripts/session_sync_gate.py:69` | No dedicated test file; the CLI implementation is directly executable and was source-inspected |
| STATUS Claims Define Cross-Provider Write Boundaries | BUILT | 2 BUILT | `scripts/claim_check.py:121`, `scripts/claim_check.py:178`, `scripts/claim_check.py:194`, `scripts/claim_check.py:286`, `scripts/claim_check.py:340` | No dedicated test file; the CLI implementation is directly executable and was source-inspected |
| Worktree Inspection Preserves Lane Intent | BUILT | 2 BUILT | `scripts/worktree_status.py:195`, `scripts/worktree_status.py:273`, `scripts/worktree_status.py:512` | `tests/test_worktree_status.py:49`, `tests/test_worktree_status.py:112`, `tests/test_worktree_status.py:260` |
| Provider Context Is Recovered At Lifecycle Checkpoints | BUILT | 2 BUILT | `scripts/provider_context_feed.py:171`, `scripts/provider_context_feed.py:291`, `scripts/provider_context_feed.py:489` | `tests/test_provider_context_feed.py:98`, `tests/test_provider_context_feed.py:141`, `tests/test_provider_context_feed.py:365` |
| Cross-Provider Rule Drift Is Detectable | BUILT | 2 BUILT | `scripts/check_cross_provider_drift.py:125`, `scripts/check_cross_provider_drift.py:301`, `scripts/check_cross_provider_drift.py:346`, `scripts/check_cross_provider_drift.py:367` | No dedicated test file; executable self-test begins at `scripts/check_cross_provider_drift.py:367` |
| Agent Village Observes Durable Coordination State | BUILT | 2 BUILT | `command_center/collector.py:351`, `command_center/collector.py:823`, `command_center/collector.py:1070`, `command_center/server.py:75` | `tests/command_center/test_collector.py:159`, `tests/command_center/test_collector.py:171`, `tests/command_center/test_server.py:75`, `tests/command_center/test_server.py:112` |
| Agent Village Writes Only Through Explicit Talk And Hire Actions | BUILT | 2 BUILT | `command_center/collector.py:1124`, `command_center/collector.py:1163`, `command_center/collector.py:1387` | `tests/command_center/test_collector.py:82`, `tests/command_center/test_collector.py:108`, `tests/command_center/test_hire.py:80`, `tests/command_center/test_server.py:84` |

## `domain-plugin-runtime` — 6 requirements, 11 scenarios

| Exact canonical requirement heading | Class | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---|---|---|
| Domain discovery combines installed and editable sources | BUILT | 2 BUILT | `tinyassets/discovery.py:45`, `tinyassets/discovery.py:79`, `tinyassets/discovery.py:101` | `tests/test_discovery.py:83`, `tests/test_discovery.py:118`, `tests/test_discovery.py:127`, `tests/test_discovery.py:137` |
| Auto-registration resolves domains without collapsing the registry | BUILT | 2 BUILT | `tinyassets/discovery.py:114`, `tinyassets/discovery.py:186` | `tests/test_discovery.py:174`, `tests/test_discovery.py:204`, `tests/test_discovery.py:221` |
| Registry identity derives from domain configuration | BUILT | 2 BUILT | `tinyassets/registry.py:36`, `tinyassets/registry.py:63`, `tinyassets/registry.py:78` | `tests/test_tinyassets_runtime.py:78`, `tests/test_tinyassets_runtime.py:96`, `tests/test_tinyassets_runtime.py:113` |
| Domain-owned opaque callables use an engine-side registry | BUILT | 2 BUILT | `tinyassets/domain_registry.py:47`, `tinyassets/domain_registry.py:68`, `tinyassets/graph_compiler.py:1846` | `tests/test_unified_execution.py:115`, `tests/test_unified_execution.py:159`, `tests/test_unified_execution.py:191` |
| The published protocol is the current domain integration shape | BUILT | 2 BUILT | `tinyassets/protocols.py:221`, `tinyassets/protocols.py:399`, `domains/fantasy_daemon/skill.py:19` | `tests/test_tinyassets_runtime.py:285`, `tests/test_tinyassets_runtime.py:310`, `tests/test_research_probe.py:358` |
| Current discovery and naming limitations remain explicit | BUILT | 1 BUILT | `tinyassets/discovery.py:101`, `tinyassets/registry.py:36`, `domains/fantasy_daemon/skill.py:23`, `pyproject.toml:71` | `tests/test_tinyassets_runtime.py:20`, `tests/test_tinyassets_runtime.py:78`, `tests/test_tinyassets_runtime.py:96` |

## Verification provenance

Two focused Windows/Python-3.14 pytest runs were observed during the read-only grounding review:

1. **278 passed**.
2. **748 passed, 13 failed**.

Combined observed result: **1,026 passing tests and 13 failing stale-test assertions**. The failures were not used as positive requirement evidence: 11 dispatcher API fixtures omitted the now-required Loop declaration and received `universe_loop_not_declared`; `tests/test_desktop.py:1313` expected the retired `workflow` GUI script instead of the shipped `tinyassets` entry; and `tests/test_worktree_status.py:342` expected LF output where Windows `TextIOWrapper` emitted CRLF.

The original pytest argv strings were not retained after reviewer-context compaction. The following is a **reconstructed explicit evidence-file command, not a claim that this exact argv produced the totals above**:

```powershell
python -m pytest -q tests/test_bug_investigation.py tests/test_bug_investigation_wiring.py tests/test_api_wiki.py tests/test_auto_ship.py tests/test_auto_ship_pr.py tests/test_auto_ship_ledger.py tests/test_community_loop_watch.py tests/test_revert_loop_canary.py tests/test_asp_engine_data_file.py tests/test_asp_solver.py tests/test_planning.py tests/test_credential_vault.py tests/test_credential_fail_closed.py tests/test_s2_engine_assignment.py tests/test_daemon_registry.py tests/test_host_pool_client.py tests/test_dispatcher_queue.py tests/test_branch_tasks.py tests/test_cloud_worker.py tests/test_loop_telemetry.py tests/test_singleton_lock.py tests/test_idle_cycle_single_flight.py tests/test_scheduler.py tests/test_work_targets.py tests/test_task_producers.py tests/test_tray_singleton.py tests/test_tinyassets_tray.py tests/test_tray_preferences.py tests/test_tinyassets_tray_watchdog.py tests/test_desktop.py tests/test_worktree_status.py tests/test_provider_context_feed.py tests/command_center/test_collector.py tests/command_center/test_server.py tests/command_center/test_hire.py tests/test_discovery.py tests/test_unified_execution.py tests/test_tinyassets_runtime.py tests/test_research_probe.py
```

Inventory arithmetic was independently recomputed from canonical Markdown headings: `rg '^### Requirement:' openspec/specs/<capability>/spec.md` and `rg '^#### Scenario:' openspec/specs/<capability>/spec.md`, yielding the totals above.

`tests/test_uptime_canary_layer2.py` was explicitly excluded and was **not run**.

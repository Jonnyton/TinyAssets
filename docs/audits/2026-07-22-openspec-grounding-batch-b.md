# OpenSpec Canonical Grounding — Batch B

- **Freshness:** 2026-07-22
- **Canonical/code baseline:** `origin/main` at `7c23c881502460f65cfd5ee81c27042d87743f24`
- **Audit checkout:** `36fe2fd2068b8d041e118e3fafbe3923de904b99`, whose only tracked difference from the baseline before this artifact was `STATUS.md`
- **Environment:** Windows, PowerShell, Python 3.14.3
- **Scope:** requirement-by-requirement and scenario-by-scenario grounding for eight canonical capabilities
- **Method:** canonical requirement text compared with current source, focused tests, active OpenSpec deltas, registry generation, and the live versioned directory endpoint
- **Safety:** `tests/test_uptime_canary_layer2.py` was not run because it is forbidden on Windows

## Verdict

All **73 requirements** and **179 scenarios** in this batch classify **BUILT as written**. This includes requirements that deliberately specify placeholders, best-effort behavior, or other explicit as-built limitations. There are no `PARTIAL` or `CONTRADICTED` canonical requirements in Batch B.

Three focused tests were red, but none establishes a canonical contradiction:

- `tests/test_current_actor_auth_context.py:109` expects `session_boundary` on an early `get_status` response, while the canonical identity and live-MCP requirements do not currently promise that response field.
- `tests/test_run_recursion_limit.py:90` and `:150` use stubs without the `runs` table; the newer run-identity lookup at `tinyassets/runs.py:2136` fails before either recursion assertion is reached.

Those are verification/backfill debt. They do not make the implemented canonical behavior `PARTIAL`.

A reproducibility rerun later in this audit also found two stale metadata assertions at `tests/test_universe_server_metadata.py:22,58`: both still require the retired tag `workflow`, while the shipped tool/prompt metadata uses the current tags at `tinyassets/universe_server.py:1184-1196,385-388`. Exact metadata is a reverse-direction coverage gap, not a current canonical scenario, so these failures likewise do not change the forward classification.

## Classification matrix

In every row below, the scenario count is the number of canonical scenarios directly under that requirement. `BUILT (N/N)` means every one of those scenarios is implemented; representative tests are cited rather than treating test count as a substitute for source inspection.

### `evaluation-outcomes-and-attribution` — 9 requirements, 28 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Run and node judgment is natural-language only, with no numeric or AI-in-the-loop scoring | BUILT | 3/3 BUILT | `tinyassets/api/evaluation.py:60,267,592`; rollback preserves forward history at `:592-670` | `tests/test_api_evaluation.py:122-139`; `tests/test_branch_evaluation_iteration.py:703,720` |
| Nodes auto-promote and auto-flag from observed execution outcomes | BUILT | 3/3 BUILT | `tinyassets/node_eval.py:136-142,327-364,433-445` | `tests/test_node_eval.py:121,177,217` |
| The coding-packet rubric is a pure, deterministic KEEP validator | BUILT | 3/3 BUILT | `tinyassets/coding_packet_rubric.py:12,116,193,266` | `tests/test_coding_packet_rubric.py:27,79,85` |
| Conformance packs are readiness evidence that gate outcome-gate rungs | BUILT | 2/2 BUILT | `tinyassets/conformance_packs.py:279`; `tinyassets/api/market.py:2700-2714` | `tests/test_conformance_pack_gates.py:99,117,148` |
| The outcome-gates surface is flag-gated and enforces evidence, rebinding, and conformance | BUILT | 3/3 BUILT | `tinyassets/api/market.py:2618,2641,2709,2911,3439` | `tests/test_outcome_gates.py:64,185,210`; `tests/test_conformance_pack_gates.py:99` |
| Gate events are cited-in outcome attestations with a controlled verification lifecycle | BUILT | 3/3 BUILT | `tinyassets/gate_events/schema.py:155-198`; `tinyassets/gate_events/store.py:162,222` | `tests/test_gate_events.py:90,101,125,140,152` |
| Contribution and attribution are append-only ledgers with idempotent, bounded provenance | BUILT | 3/3 BUILT | `tinyassets/contribution_events.py:79-175`; `tinyassets/attribution/calc.py:68-151` | `tests/test_contribution_events_emit.py:208,449`; `tests/test_attribution_calc.py:148,198`; `tests/test_attribution_schema.py:148-174` |
| The quality leaderboard collects signals and delegates ranking to a user-buildable selector | BUILT | 3/3 BUILT | `tinyassets/api/quality_leaderboard.py:214`; `tinyassets/selector_dispatch.py:512,562` | `tests/test_quality_leaderboard.py:257,377,783,881` |
| Recorded outcome events are persistent unverified evidence records | BUILT | 5/5 BUILT | `tinyassets/api/market.py:761,811,816,856`; negative limits remain unbounded as specified at `:816` | `tests/test_outcome_mcp.py:23,62,167,199,247` |

### `evaluation-runtime-and-scenarios` — 6 requirements, 13 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Evaluators return a bounded unified result where the protocol applies | BUILT | 3/3 BUILT | `tinyassets/evaluation/__init__.py:45,58,68` | `tests/test_evaluator_protocol.py:86-117,195,200` |
| Layered evaluation preserves native evidence and explicit adapters | BUILT | 2/2 BUILT | `tinyassets/evaluation/process.py:51`; `tinyassets/evaluation/coding_process.py:174-184` | `tests/test_evaluator_protocol.py:155-186`; `tests/test_process_evaluation.py:77-134` |
| Outcome adapters remain probe-free unless a caller supplies a prober | BUILT | 2/2 BUILT | `tinyassets/outcomes/evaluators.py:13-24,40,62` | `tests/test_outcome_evaluators.py:39-71,120,163` |
| Acceptance scenarios validate the minimum evidence contract before dispatch | BUILT | 2/2 BUILT | `tinyassets/evaluation/scenario_runner.py:51,60,80` | `tests/test_scenario_runner.py:71-115` |
| Scenario dispatch is registry based and normalizes every terminal result | BUILT | 2/2 BUILT | `tinyassets/evaluation/scenario_runner.py:168,190,239` | `tests/test_scenario_runner.py:123,157-238` |
| The shipped MCP-call dispatcher is synchronous and reports, rather than enforces, budgets | BUILT | 2/2 BUILT | `tinyassets/evaluation/scenario_dispatchers/mcp_call.py:119,148,155-159,200` | `tests/test_scenario_dispatcher_mcp_call.py:175,224,246` |

### `external-effect-receipts` — 4 requirements, 9 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Soul effect authority is destination-scoped and transitional | BUILT | 2/2 BUILT | `tinyassets/effectors/authority.py:35,40`; gate integration in `tinyassets/effectors/github_pr.py:1251-1270` | `tests/test_soul_scoped_effect_authority.py:138,169,197,211` |
| Effector consent is an exact per-universe destination grant | BUILT | 2/2 BUILT | `tinyassets/storage/effector_consents.py:84,132,165` | `tests/test_effector_consents.py:60,80,158,254` |
| External-write receipts atomically reserve one effect per caller hint and sink | BUILT | 3/3 BUILT | `tinyassets/storage/external_write_receipts.py:67,176,221,450,500` | `tests/test_external_write_phase_2_atomicity.py:109,122,164,190,356,637` |
| Receipt guarantees are per effect and caller-supplied, not batch atomicity | BUILT | 2/2 BUILT | empty-hint handling at `tinyassets/storage/external_write_receipts.py:184,258`; per-effect dispatch at `tinyassets/effectors/__init__.py:83-120` | `tests/test_external_write_receipts.py:103,133`; `tests/test_external_write_effector.py:384-406` |

### `graph-execution-substrate` — 8 requirements, 25 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Branch and node definitions are validated dataclasses with lossless JSON round-trip | BUILT | 3/3 BUILT | `tinyassets/branches.py:263,418,441,454,836,913` | `tests/test_branches.py:103,200,465,696` |
| Branch validation is the compile gate | BUILT | 3/3 BUILT | `tinyassets/branches.py:947,1034`; `tinyassets/graph_compiler.py:371-420` | `tests/test_branches.py:465,696,805`; `tests/test_graph_compiler_reducer_law.py:83` |
| State fields accumulate per their declared reducer | BUILT | 5/5 BUILT | `tinyassets/graph_compiler.py:371-484` | `tests/test_graph_compiler_reducer_law.py:83,99,150` |
| Conditional edges route by path_map label, not target node id | BUILT | 2/2 BUILT | `tinyassets/graph_compiler.py:2670-2705` | `tests/test_conditional_edges_compile_invoke.py:74,114`; `tests/test_conditional_routing_resolver.py:26` |
| source_code nodes execute in-process behind a fail-closed approval gate | BUILT | 3/3 BUILT | `tinyassets/graph_compiler.py:1318-1354,1762`; standalone isolation remains separate | `tests/test_source_code_approval_action.py:53,103`; `tests/test_describe_branch_approval.py:72` |
| Runs are checkpointed LangGraph executions with a fixed terminal status set | BUILT | 2/2 BUILT | `tinyassets/runs.py:2101,2111`; recursion configuration at `tinyassets/runs.py:2887-2892` | checkpoint evidence in `tests/test_resume_run.py:149`; `tests/test_run_recursion_limit.py:90` is presently fixture-red before its assertion |
| Run failures map to a terminal status taxonomy | BUILT | 3/3 BUILT | `tinyassets/runs.py:2407-2447,3966-4025` | `tests/test_graph_compiler_empty_response.py:66`; `tests/test_run_branch_failure_taxonomy.py:52`; recursion test `tests/test_run_recursion_limit.py:150` is fixture-red |
| Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards | BUILT | 4/4 BUILT | `tinyassets/runs.py:3218-3503` | `tests/test_resume_run.py:149,197,254,318` |

The two red recursion tests create verification debt because `tinyassets/runs.py:2136` now reads run identity before their incomplete stub schema reaches the behavior under test. The source implementation and other terminal/checkpoint tests support the `BUILT` classification.

### `identity-auth-and-access-control` — 8 requirements, 18 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Auth provider is selected by configuration, defaulting to no-auth | BUILT | 2/2 BUILT | `tinyassets/auth/provider.py:1135-1145` | configured WorkOS selection at `tests/test_workos_provider.py:262-268`; false/empty/default-dev selection at `tests/test_optional_auth_mode.py:88-113` |
| Anonymous read, authenticated write (resolve-always posture) | BUILT | 2/2 BUILT | `tinyassets/auth/provider.py:699,722,728`; `tinyassets/api/permissions.py:84-119` | `tests/test_permission_decisions.py:28,53`; `tests/test_require_auth_challenge.py:136` |
| Bearer JWT validation is fail-closed, RS256-pinned, and audience-bound | BUILT | 2/2 BUILT | `tinyassets/auth/workos_provider.py:43,90-137,186` | `tests/test_workos_provider.py:229,263`; `tests/test_predeploy_auth_hardening.py:71` |
| Anonymous writes on pure-write handles draw a pre-dispatch 401 challenge | BUILT | 3/3 BUILT | `tinyassets/auth/middleware.py:119-131,156-174` | `tests/test_require_auth_challenge.py:136,190,239` |
| Protected Resource Metadata advertises the AuthKit issuer and OIDC scopes only | BUILT | 1/1 BUILT | `tinyassets/auth/wellknown.py:96` | `tests/test_wellknown_discovery.py:36-45` |
| Founder home auto-births exactly once on first authenticated contact | BUILT | 4/4 BUILT | `tinyassets/api/first_contact.py:27-180`; read-only status resolution at `tinyassets/api/status.py:700-744` | `tests/test_first_contact.py:258,324,456,525` |
| The permission actor is the authenticated subject with no environment fallback | BUILT | 1/1 BUILT | `tinyassets/api/permissions.py:59,84,90` | `tests/test_current_actor_auth_context.py:29,58` |
| Access is controlled on two orthogonal axes — visibility and ownership | BUILT | 3/3 BUILT | `tinyassets/api/permissions.py:106-169` | `tests/test_permission_decisions.py:80,118,154` |

`tests/test_current_actor_auth_context.py:109` fails because `get_status` returns the no-home variant at `tinyassets/api/status.py:732-744` before the full-response `session_boundary` is assembled at `:1010-1052` and emitted at `:1148`. That field is not a current canonical identity requirement. The active `test-identity-and-reset` delta owns the future self-identity evidence contract.

### `knowledge-retrieval-and-memory` — 25 requirements, 55 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Singleton LanceDB Vector Store | BUILT | 3/3 BUILT | `tinyassets/retrieval/vector_store.py:30,69` | `tests/test_retrieval.py:108,115,129` |
| Path-Explicit Knowledge Graph With Scope Columns | BUILT | 2/2 BUILT | `tinyassets/knowledge/knowledge_graph.py:126` | `tests/test_knowledge_graph.py:204,221` |
| Hybrid Multi-Backend Retrieval Router | BUILT | 3/3 BUILT | `tinyassets/retrieval/router.py:136,381,412` | `tests/test_retrieval.py:232,237,281` |
| Scope-Isolation Defense-In-Depth On Retrieval | BUILT | 3/3 BUILT | `tinyassets/retrieval/router.py:449`; `tinyassets/memory/scoping.py:109` | `tests/test_memory_scope_stage_2b3.py:45`; `tests/test_memory_scoping.py:127,132` |
| Tiered Memory Scope Model | BUILT | 3/3 BUILT | `tinyassets/memory/scoping.py:24-158` | `tests/test_memory_scoping.py:38,114,127` |
| Unified Per-Universe Notes With Status Lifecycle | BUILT | 3/3 BUILT | `tinyassets/notes.py:104,166,219` | `tests/test_notes.py:19,42,97,132` |
| Host-Local Daemon Learning Wiki With Bounded Caps | BUILT | 3/3 BUILT | `tinyassets/daemon_wiki.py:288,379,484` | `tests/test_daemon_wiki.py:21,44,139` |
| Soul-Scoped Host-Local Mini-Brain Store | BUILT | 2/2 BUILT | `tinyassets/daemon_brain.py:514` | `tests/test_daemon_brain.py:36,147,163` |
| Explicit Mini-Brain Review And Wiki-Promotion Lifecycle | BUILT | 2/2 BUILT | `tinyassets/daemon_brain.py:1366,1535` | `tests/test_daemon_brain.py:147,163` |
| Per-Daemon Mini-Brain Retrieval And Bounded Injection | BUILT | 2/2 BUILT | `tinyassets/daemon_brain.py:881,1046,1139` | `tests/test_daemon_brain.py:36,359` |
| Caller-Owned Mini-Brain Quality Replay | BUILT | 2/2 BUILT | `tinyassets/daemon_brain.py:1241` | `tests/test_daemon_brain_eval.py:27,65,100` |
| Mini-Brain Dispatch Hints And Status Surfaces | BUILT | 2/2 BUILT | `tinyassets/daemon_brain.py:1794,1831` | `tests/test_daemon_brain.py:321,359` |
| Bounded Combined Daemon Memory Packet | BUILT | 2/2 BUILT | `tinyassets/daemon_memory.py:316,448` | `tests/test_daemon_wiki.py:103`; `tests/test_daemon_brain.py:36` |
| Domain-Neutral Episodic SQLite Lifecycle | BUILT | 2/2 BUILT | `tinyassets/memory/episodic.py:177,827,891` | `tests/test_memory.py:94,119,163` |
| Fantasy Phase Context Assembly And Persistence | BUILT | 2/2 BUILT | `tinyassets/memory/manager.py:66` | `tests/test_memory.py:212,232` |
| Project-Scoped Versioned Key-Value Memory | BUILT | 2/2 BUILT | `tinyassets/memory/project.py:89,183,212` | `tests/test_project_memory.py:47,167,174` |
| Draft Output Version History | BUILT | 2/2 BUILT | `tinyassets/memory/versioning.py:59,101-177,232-265` | `tests/test_phase7.py:146,159` |
| Node-Scope Manifest Parsing | BUILT | 2/2 BUILT | `tinyassets/memory/node_scope.py:98,209,223` | `tests/test_memory_scoping.py:68,75,79` |
| Standalone Temporal Fact Library | BUILT | 2/2 BUILT | `tinyassets/memory/temporal.py:134,486` | `tests/test_memory.py:281,299` |
| Standalone Consolidation And Candidate Helpers | BUILT | 2/2 BUILT | `tinyassets/memory/consolidation.py:33,241` | `tests/test_memory.py:310,325` |
| Fantasy Chapter Learning Loop | BUILT | 2/2 BUILT | `tinyassets/learning/style_rules.py:114,181`; manager integration at `tinyassets/memory/manager.py:514-534` | `tests/test_memory.py:230,250,426` |
| Heuristic Craft And Criteria Surfacing | BUILT | 1/1 BUILT | `tinyassets/learning/criteria_discovery.py:71`; `tinyassets/learning/craft_cards.py:27` | `tests/test_learning.py:222,232` |
| Episodic Promotion Candidate Scan | BUILT | 2/2 BUILT | `tinyassets/memory/promotion.py:24,32,50-86`; marker update at `tinyassets/memory/episodic.py:596-619` | `tests/test_memory.py:128,138,230,250` |
| Fantasy Reflexion | BUILT | 2/2 BUILT | `tinyassets/memory/reflexion.py:31`; integration at `tinyassets/memory/manager.py:528-534` | `tests/test_memory.py:435` |
| Memory Tool Placeholder Envelopes | BUILT | 2/2 BUILT | `tinyassets/memory/tools.py:29,83,168,216,261,318` | `tests/test_memory_scoping.py:187`; placeholder implementation markers at `tinyassets/memory/tools.py:156,206,255` |

These classifications preserve the canonical limitations: some helpers are standalone or in-memory, several tools are placeholders, and default packet cap enforcement can mutate through compaction. `BUILT` does not promote those limitations into a richer durable system.

### `live-mcp-connector-surface` — 9 requirements, 25 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| Remote Streamable-HTTP MCP Endpoint | BUILT | 2/2 BUILT | `tinyassets/universe_server.py:218,2213-2254`; prompts at `:295-399` | `tests/test_universe_server_directory_app.py:39`; `tests/test_universe_server_metadata.py:48` |
| Canonical Advertised Handle Set | BUILT | 3/3 BUILT | canonical registrations at `tinyassets/universe_server.py:501,627,669,739,909,992,1916` | `tests/test_universe_server_five_handles.py:21,31,56`; `tests/test_read_graph_branch.py:38` |
| Legacy Fat Tools Registered But Hidden | BUILT | 2/2 BUILT | `tinyassets/universe_server.py:1010-1020,1941-1973` | `tests/test_universe_server_five_handles.py:58,65,67` |
| Connector-Safe Handle Names | BUILT | 1/1 BUILT | names at `tinyassets/universe_server.py:501,627,669,739,909,992,1916` | `tests/test_universe_server_five_handles.py:31` |
| Read-Open, Write-Challenged Authentication Boundary | BUILT | 7/7 BUILT | challenge middleware at `tinyassets/auth/middleware.py:119-174`; first-contact routing at `tinyassets/api/first_contact.py:27-180` | `tests/test_require_auth_challenge.py:136`; `tests/test_first_contact.py:258,324,456,525` |
| Faithful Structured And Text Result Envelope | BUILT | 2/2 BUILT | `tinyassets/universe_server.py:67,74-98` | `tests/test_universe_server_mcp_structured_results.py:23,61,99` |
| Cloudflare Worker Public Front Door | BUILT | 3/3 BUILT | `deploy/cloudflare-worker/worker.js:45,122,142,198-228` | `deploy/cloudflare-worker/worker.test.js:98,144,170,306` |
| Public Canary And Directory Review Surface | BUILT | 2/2 BUILT | `scripts/mcp_public_canary.py:70-79,188`; redaction at `tinyassets/directory_server.py:99-109` | `tests/test_directory_server.py:130,250`; live versioned-directory canary passed |
| Published registry metadata follows the current versioned directory catalog | BUILT | 3/3 BUILT | `tinyassets/connector_catalog.py:9-16`; `packaging/registry/generate_server_json.py:33-64,93`; `.github/workflows/build-bundle.yml:51-54` | `tests/test_connector_catalog.py:15`; generator `--check` and live remote checks passed |

Current code also ships four named prompts, detailed tool metadata, and materially different early/config-error/full `get_status` response shapes. Those details are reverse-direction backfill gaps, not grounds to weaken the canonical requirements above. Active changes `reconcile-external-connector-manifests`, `retire-legacy-live-mcp-tools`, and `test-identity-and-reset` overlap the future catalog/status contract.

### `oss-clone-and-install` — 4 requirements, 6 scenarios

| Canonical requirement | Classification | Scenarios | Representative source evidence | Representative test evidence |
|---|---|---:|---|---|
| The Tier-3 workflow exercises a fresh editable-clone path | BUILT | 1/1 BUILT | `.github/workflows/tier3-oss-clone-nightly.yml:8,10,18,23,29,35-40` | `tests/smoke/test_tier3_smoke_script.py:24` |
| The fresh-clone workflow performs the shipped structural checks | BUILT | 2/2 BUILT | `.github/workflows/tier3-oss-clone-nightly.yml:52,62,69`; `scripts/tier3_smoke.py:25-30,59-86` | `tests/smoke/test_tier3_smoke_script.py:37,68` |
| Failed Tier-3 checks emit the current GitHub escalation record | BUILT | 1/1 BUILT | `.github/workflows/tier3-oss-clone-nightly.yml:82-119` | No focused escalation test; source-only workflow proof. |
| The shipped workflow has explicitly bounded coverage | BUILT | 2/2 BUILT | workflow scope at `.github/workflows/tier3-oss-clone-nightly.yml:35-69`; smoke root-path limitation at `scripts/tier3_smoke.py:25-30` | `tests/smoke/test_tier3_smoke_script.py:68` |

## Reverse-direction backfill findings

These behaviors are shipped but lack complete canonical ownership. They do not change the 73/179 forward-grounding result.

| Recommended owner | Missing shipped contract | Evidence and active-change dependency |
|---|---|---|
| `graph-execution-substrate` | Child-Branch definition/version invocation, input/output mappings, wait/depth behavior, child terminal propagation, receipt-wait interruption, and validated/idempotent existing-child attachment | `tinyassets/graph_compiler.py:2181-2550`; `tinyassets/runs.py:1113-1349,2407-2425`. Coordinate with `distributed-execution`; current local receipts are not future signed owner-daemon authority. |
| `knowledge-retrieval-and-memory` | Curated read-only OKF v0.1 export, excluded roots, wikilink conversion, and unresolved-link report | `tinyassets/wiki/okf_export.py:12,15,21,32,45-82,182-199,270-285`; `tests/test_okf_export.py:82,101,120,147`. Coordinate `brain-okf-canonical-store`; export is not a current write-through canonical store. |
| New `external-effect-adapters` capability, depending on `external-effect-receipts` | GitHub PR/merge, Twitter, wiki-writeback, and Windows sink packet/dispatch contracts; trusted `external_write_results` snapshots and forged-evidence quarantine | `tinyassets/effectors/__init__.py:83-120`; `tinyassets/runs.py:2590-2593,3485`; `tests/test_external_write_effector.py:416-530`. Do not import future deterministic-key, cap, reconciliation, or whole-batch guarantees from `build-forward-platform-capabilities`. |
| `live-mcp-connector-surface` for metadata; `identity-auth-and-access-control` for status identity | Exact four-prompt catalog, tool title/tag/annotation invariants, and explicit early/config-error/full status response variants | prompts at `tinyassets/universe_server.py:295-399`; tool metadata beginning at `:501`; early status at `tinyassets/api/status.py:732-744`, config error at `:768-774`, full session boundary at `:1010-1052,1148`. Coordinate connector-manifest, legacy-tool-retirement, and identity/reset changes. |

## Commands and observed results

The original focused pytest work was run in five capability groups. Its shell command strings were not persisted after session compaction, so the following is the durable result ledger rather than a claim of literal reproducibility:

```text
evaluation outcomes + evaluation runtime/scenarios:
  python -m pytest -q <evaluation, node-eval, rubric, conformance, outcome-gate,
    gate-event, contribution/attribution, quality-selector, outcome-event,
    evaluator-protocol, process/outcome-adapter, and scenario-runner test files>
  338 passed, 3 skipped in 19.99s

external-effect receipts + identity/auth/access:
  python -m pytest -q <effect-authority, consent, receipt/effector,
    provider, middleware, first-contact, permissions, and auth-context test files>
  174 passed, 1 failed
  failure: tests/test_current_actor_auth_context.py:109

graph execution substrate:
  python -m pytest -q <branch/dataclass, compiler/reducer, conditional-edge,
    source-approval, run-terminal, recursion, resume, and recovery test files>
  270 passed, 2 failed
  failures: tests/test_run_recursion_limit.py:90 and :150

knowledge retrieval and memory:
  python -m pytest -q <retrieval, graph, scoping, notes, daemon-wiki,
    daemon-brain, episodic/project/version/temporal/consolidation/promotion,
    reflexion, and memory-tool test files>
  297 passed

live MCP + OSS structural smoke:
  python -m pytest -q <universe-server, directory, connector-catalog,
    registry/workflow, and Tier-3 smoke test files>
  101 passed, 3 warnings
```

Aggregate original focused result: **1,180 passed, 3 skipped, 3 failed**. The angle-bracket descriptions preserve the observed invocation group boundaries; the exact individual test evidence used for classification is cited in the matrix above. Literal reproducibility commands and their newly observed results follow.

Literal reproducibility commands run after drafting the matrix:

```powershell
python -m pytest -q tests/test_node_eval.py tests/test_coding_packet_rubric.py tests/test_evaluator_protocol.py tests/test_scenario_runner.py tests/test_external_write_phase_2_atomicity.py tests/test_effector_consents.py tests/test_branches.py tests/test_graph_compiler_reducer_law.py tests/test_conditional_edges_compile_invoke.py tests/test_resume_run.py tests/test_permission_decisions.py tests/test_first_contact.py
# 250 passed, 186 warnings in 13.95s

python -m pytest -q tests/test_retrieval.py tests/test_knowledge_graph.py tests/test_memory_scoping.py tests/test_notes.py tests/test_daemon_wiki.py tests/test_daemon_brain.py tests/test_daemon_brain_eval.py tests/test_memory.py tests/test_project_memory.py tests/test_phase7.py tests/test_okf_export.py
# 273 passed in 9.84s

python -m pytest -q tests/test_universe_server_five_handles.py tests/test_universe_server_metadata.py tests/test_universe_server_mcp_structured_results.py tests/test_directory_server.py tests/test_connector_catalog.py tests/smoke/test_tier3_smoke_script.py tests/test_deploy_worker_workflow.py
# 47 passed, 2 failed, 3 warnings in 5.95s
# failures: tests/test_universe_server_metadata.py:22 and :58 (stale `workflow` tag expectations)
```

Additional exact checks:

```powershell
python packaging/registry/generate_server_json.py --check
# PASS: server.json matches the generated document.

python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory/catalog/2026-06-24-underscore-handles --timeout 15 --verbose
# PASS: [canary] OK for the versioned directory endpoint.
```

The second command is the permitted public MCP canary, not `tests/test_uptime_canary_layer2.py`. The forbidden Windows layer-2 uptime canary was not run.

## Completion statement

Batch B forward grounding is complete: **73/73 requirements and 179/179 scenarios are BUILT as written**. Full-platform OpenSpec coverage is not complete until the four reverse-direction backfill findings above have canonical owners and the five known red focused tests (three from the original grouped audit plus two metadata rerun failures) have been repaired or intentionally realigned through their active changes.

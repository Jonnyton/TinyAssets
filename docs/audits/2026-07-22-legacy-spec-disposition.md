# Legacy specification disposition

- **Date:** 2026-07-22
- **Baseline:** reconciled after PR #1622 merged on `origin/main` at
  `35817a3e8463c095f63fe2ea7d739728f67a4679`; original grounding began at
  PR #1619 (`2b6188bf`) and the first disposition landed in PR #1620
- **Scope:** all 52 Markdown files under `docs/specs/`, including the index
- **Authority rule:** `openspec/specs/` is as-built behavioral truth,
  `openspec/changes/` is in-flight target truth, and PLAN.md owns architecture.
  A legacy file is evidence or provenance only; its embedded `status:` value
  does not make it current.

## Disposition meanings

- **CANONICAL** — the file's surviving shipped substance has a named canonical
  OpenSpec owner. The legacy wording, action names, and implementation plan are
  historical evidence, not an additional contract.
- **ACTIVE** — the surviving future behavior is owned by a named active
  OpenSpec change. It must not be counted as shipped until that change lands.
- **CLAIMED** — material shipped or target residue lacks a complete current
  owner but has an exact successor in STATUS or in the successor table below.
  A table-only successor is inventory, not build authority, until promoted to
  a literal STATUS Files claim. The successor must create/sync the OpenSpec
  owner; this legacy file itself grants no build authority.
- **HISTORY** — superseded, research, fixture, domain exemplar, draft fragment,
  or parked input with no current behavioral authority. Revival requires a new
  OpenSpec change rather than changing the embedded status back to active.

For mixed files, unresolved material residue takes precedence: classify the
file CLAIMED even when other slices are canonical or active. ACTIVE applies
only when every surviving future requirement is owned by named active changes;
CANONICAL applies only when every surviving shipped requirement is canonically
owned and no material target residue remains.

## Result

| Disposition | Files |
|---|---:|
| CANONICAL | 12 |
| ACTIVE | 0 |
| CLAIMED | 27 |
| HISTORY | 13 |
| **Total** | **52** |

## File-by-file matrix

| Legacy file | Disposition | Current owner or reason |
|---|---|---|
| [`2026-04-10-investigation-findings.md`](../specs/2026-04-10-investigation-findings.md) | HISTORY | Explicit historical incident/evaluator findings; source/test history, not a live contract. |
| [`2026-04-18-daemon-host-tray-changes.md`](../specs/2026-04-18-daemon-host-tray-changes.md) | CLAIMED | `desktop-host-runtime` owns the installed `tinyassets` GUI entry point plus the source-tray singleton, checkout-local lock, harmless second launch, and tunnel-default-off behavior. One-click cross-OS packaging and richer host UX remain in `complete-full-platform-target-specs`; signed/paid hosting remains active in `distributed-execution` and `build-forward-platform-capabilities`. |
| [`2026-04-18-export-sync-cross-repo.md`](../specs/2026-04-18-export-sync-cross-repo.md) | CLAIMED | Export/portability target is incomplete and canonical-store direction is a recorded PLAN host decision; owned by the full-platform target lane after that decision. |
| [`2026-04-18-full-platform-schema-sketch.md`](../specs/2026-04-18-full-platform-schema-sketch.md) | CLAIMED | Postgres/RLS/private-data prescriptions conflict with current PLAN tensions; collaborative control-plane target stays in the host-decision plus full-platform target lanes. |
| [`2026-04-18-load-test-harness-plan.md`](../specs/2026-04-18-load-test-harness-plan.md) | CLAIMED | This is target proof infrastructure, not shipped behavior; the full-platform target lane must preserve the Forever Rule concurrency/load gate. |
| [`2026-04-18-mcp-gateway-skeleton.md`](../specs/2026-04-18-mcp-gateway-skeleton.md) | HISTORY | Superseded gateway topology/action catalog. Current behavior is canonical in `live-mcp-connector-surface` and `identity-auth-and-access-control`; `reconcile-external-connector-manifests` and `retire-legacy-live-mcp-tools` are successor context, not surviving behavior owned by this file. |
| [`2026-04-18-moderation-mvp.md`](../specs/2026-04-18-moderation-mvp.md) | CLAIMED | Moderation, abuse response, appeals, and moderation/abuse rate limits are an uncovered `complete-full-platform-target-specs` group. |
| [`2026-04-18-paid-market-crypto-settlement.md`](../specs/2026-04-18-paid-market-crypto-settlement.md) | CLAIMED | `paid-market-economy` owns the current flag-off/prelaunch actions, atomic bid claim, prototype settlement limits, treasury math, and pure market oracles. `build-forward-platform-capabilities` owns future transaction/price/training slices and `distributed-execution` owns signed execution evidence. Production inbox-to-matching-to-delivery/dispute/launch workflow remains in `complete-full-platform-target-specs`. |
| [`2026-04-18-remix-and-convergence-detail.md`](../specs/2026-04-18-remix-and-convergence-detail.md) | CLAIMED | Local Goal/convergence primitives are canonical, but realtime node discovery/remix/convergence collaboration remains an uncovered target group. |
| [`2026-04-18-web-app-landing-and-catalog.md`](../specs/2026-04-18-web-app-landing-and-catalog.md) | CLAIMED | Static public surface is canonical; authenticated catalog/control-plane behavior remains in the PLAN-decision and full-platform target lanes. |
| [`2026-04-19-connectors-two-way-tool-integration.md`](../specs/2026-04-19-connectors-two-way-tool-integration.md) | CLAIMED | Canonical `credential-vault` and `external-effect-receipts` own shipped secret/consent pieces; the active `build-forward-platform-capabilities` boundary-layer delta already owns revocable grants, credential-blind proxies, caps, replay/batch behavior, reviewed adapters, and typed edges. `reconcile-external-connector-manifests` owns TinyAssets distribution products. Remaining connection-management UX, structurally necessary service-auth brokerage, and third-party review/deprecation lifecycle stay in `complete-full-platform-target-specs`; the fixed service catalog is historical. |
| [`2026-04-19-handoffs-real-world-pipeline.md`](../specs/2026-04-19-handoffs-real-world-pipeline.md) | CLAIMED | `external-effect-receipts` and `evaluation-outcomes-and-attribution` own current effect/outcome evidence; the active `build-forward-platform-capabilities` boundary-layer delta and `distributed-execution` own future durable/signed execution. Only explicit handoff-to-outcome correlation/verification may remain, and `complete-full-platform-target-specs` must first test whether it composes from those primitives rather than assuming a new platform capability. |
| [`2026-04-19-plan-b-selfhost-migration-playbook.md`](../specs/2026-04-19-plan-b-selfhost-migration-playbook.md) | CLAIMED | `uptime-and-alarms` owns shipped backup/DR, `oss-clone-and-install` owns clone/install, and `brain-okf-canonical-store` owns brain-bundle portability only. After the store decision, complete account/content portability, deletion/succession, and whole-platform migration remain in `complete-full-platform-target-specs`; the old vendor command plan is historical. |
| [`2026-04-19-track-n-vibe-coding-authoring-sandbox.md`](../specs/2026-04-19-track-n-vibe-coding-authoring-sandbox.md) | CLAIMED | `graph-execution-substrate` owns current Branch/Node, source-approval/hash, in-process execution, and unwired `NodeSandbox` limits; `evaluation-outcomes-and-attribution` owns edit suggestions and `distributed-execution` owns future confinement. Authoring UX/session lifecycle, safe file-I/O/tool capability, and any evaluator/autoresearch composition that clears the minimal-primitives test remain in `complete-full-platform-target-specs`; retired tool names are historical. |
| [`2026-04-27-hyperparameter-importance-evaluator-node.md`](../specs/2026-04-27-hyperparameter-importance-evaluator-node.md) | CLAIMED | `HyperparameterImportanceEvaluator` already ships in `tinyassets/outcomes/evaluators.py` and is tested, but its `run_results`/`top_n`, RF/correlation, and `EvalResult.details` contract materially differs from this legacy `sweep_results`/`top_k`, permutation/ANOVA/model-based envelope. `reconcile-hyperparameter-importance-evaluator` must backfill, move, or retire the shipped contract; generic evaluator OpenSpec is insufficient. |
| [`2026-04-27-hyperparameter-importance-fixture-pack.md`](../specs/2026-04-27-hyperparameter-importance-fixture-pack.md) | CLAIMED | Current tests use inline synthetic runs and no promised fixture/golden files. The `reconcile-hyperparameter-importance-evaluator` successor owns shipped RF/correlation, minimum-run, categorical, dependency, and empty-input truth; named snapshots and absent warning/envelope promises remain historical guidance. |
| [`2026-04-27-recency-and-continue-branch-primitives.md`](../specs/2026-04-27-recency-and-continue-branch-primitives.md) | CLAIMED | Standalone recency/continue verbs are superseded, but §§2.1–2.4 preserve shipped `run_branch resume_from=<run_id>` behavior: a new same-Branch run, terminal visible source, merged inputs with caller overrides, and recorded lineage. `backfill-graph-mutation-and-resume-contracts` owns exact coverage; `retire-legacy-live-mcp-tools` must preserve routing through canonical `run_graph`. |
| [`2026-04-27-recency-continue-fixture-pack.md`](../specs/2026-04-27-recency-continue-fixture-pack.md) | CLAIMED | Shipped `resume_from` behavior has inline tests but no named fixture/golden files and incomplete promised default/invalid-state coverage. `backfill-graph-mutation-and-resume-contracts` owns the behavior; fixture filenames and snapshots remain historical guidance. |
| [`2026-04-27-runtime-memory-graph-minimal-schema-v1.md`](../specs/2026-04-27-runtime-memory-graph-minimal-schema-v1.md) | CLAIMED | The promoted runtime-fiction target still depends on this four-entity schema freeze; the `runtime-fiction-memory-graph` successor lane owns its disposition alongside the broader target. |
| [`2026-04-30-classic-game-restoration-branch.md`](../specs/2026-04-30-classic-game-restoration-branch.md) | HISTORY | Community-built domain/Branch exemplar with no new platform primitive; retained as project evidence. |
| [`2026-05-02-acceptance-scenario-minimal-schema.md`](../specs/2026-05-02-acceptance-scenario-minimal-schema.md) | CANONICAL | `evaluation-runtime-and-scenarios` owns validation, registry dispatch, normalization, and current MCP-call limits. |
| [`2026-05-02-experience-pool-minimal-schema.md`](../specs/2026-05-02-experience-pool-minimal-schema.md) | CANONICAL | `knowledge-retrieval-and-memory` owns the accepted `experience_lesson` kind and generic review/search lifecycle; the file's field tables are non-enforced composition guidance. |
| [`2026-05-02-session-trace-minimal-schema.md`](../specs/2026-05-02-session-trace-minimal-schema.md) | CANONICAL | `knowledge-retrieval-and-memory` owns the `session_trace_summary` kind, generic lifecycle, visibility tags, retrieval, and limitations; its detailed metadata shape remains guidance. |
| [`2026-05-03-dual-key-auto-ship-acceptance.md`](../specs/2026-05-03-dual-key-auto-ship-acceptance.md) | HISTORY | Superseded governance proposal; current dry-run/PR-open boundaries are canonical in `community-patch-loop`, and no dual-key contract is current. |
| [`2026-05-04-loop-autonomy-roadmap.md`](../specs/2026-05-04-loop-autonomy-roadmap.md) | HISTORY | Superseded roadmap for the retired cheat-loop direction; current as-built loop boundaries are in `community-patch-loop`. |
| [`2026-05-27-authority-resolver-contract-v1.md`](../specs/2026-05-27-authority-resolver-contract-v1.md) | CANONICAL | `development-coordination-runtime` owns the shipped v1 schema, taxonomy, validation, evidence preservation, and deterministic resolution outcomes. This diagnostic resolver remains distinct from authenticated permission authority. |
| [`2026-06-10-brain-v2-research-implications.md`](../specs/2026-06-10-brain-v2-research-implications.md) | HISTORY | Research provenance. Current memory is canonical and `brain-okf-canonical-store` owns only the OKF target; other adopted future mechanics are inventoried through the CLAIMED first-principles and primitive-contract successors rather than made authoritative by this research file. |
| [`2026-06-10-primitive-basis-audit.md`](../specs/2026-06-10-primitive-basis-audit.md) | CLAIMED | PLAN owns the six-name vocabulary and canonical OpenSpec owns as-built subsets, but proposed CLAIM/SEAL, joins, cancellation/suspension, terminal events, completion tokens, and forever-tests have no current behavioral owner. `reconcile-primitive-contract-targets` must obtain the PLAN decision and explicitly adopt or retire each target. |
| [`2026-06-10-tiny-first-principles-spec.md`](../specs/2026-06-10-tiny-first-principles-spec.md) | CLAIMED | Cross-cutting source mixes canonical behavior; active `brain-okf-canonical-store`, `build-forward-platform-capabilities`, `distributed-execution`, `reconcile-universe-personification-relay`, `universe-creation`, and `universe-visibility`; PLAN conflicts; full-platform gaps; and primitive-contract residue owned by `reconcile-primitive-contract-targets`. Private tiers, T0/T1/T2 auth, quarantine/redaction, sandbox, complete journal/provider receipts, and regulated-industry posture remain unbuilt target claims, not current guarantees. |
| [`2026-07-15-riscv-fpga-vertical-proof.md`](../specs/2026-07-15-riscv-fpga-vertical-proof.md) | HISTORY | Explicitly paused first-device candidate with no implementation authority; general hardware outcomes remain active in `build-forward-platform-capabilities`, but this exact RISC-V proof is not current. |
| [`auto-ship-rollback-v0.md`](../specs/auto-ship-rollback-v0.md) | HISTORY | `community-patch-loop` now owns the surviving read-only `auto_ship_health`, rollback-recommendation, packet-recovery, and completed-run reuse behavior. The proposed autonomous rollback executor never shipped and the cheat loop was retired 2026-06-25. |
| [`community_branches_phase2.md`](../specs/community_branches_phase2.md) | CANONICAL | Surviving graph/state substrate is in `graph-execution-substrate`; obsolete fat-tool names are bounded by `live-mcp-connector-surface`. |
| [`community_branches_phase3.md`](../specs/community_branches_phase3.md) | CANONICAL | Shipped graph runner, validation, state, checkpoints, and terminal outcomes are in `graph-execution-substrate`. |
| [`community_branches_phase4.md`](../specs/community_branches_phase4.md) | CANONICAL | Shipped iteration/evaluation substance is split across `graph-execution-substrate`, `evaluation-runtime-and-scenarios`, and `evaluation-outcomes-and-attribution`. |
| [`community_branches_phase5.md`](../specs/community_branches_phase5.md) | CLAIMED | `shared-goals-and-convergence` owns Goal/binding/version/leaderboard/convergence primitives, but direct and derived Goal/Gates reads currently expose private Goal records to nonowners. `enforce-private-goal-read-visibility` owns the dedicated request-identity, fail-closed read correction; draft #1554 is incomplete provenance, not authority. |
| [`composite_branch_actions.md`](../specs/composite_branch_actions.md) | CLAIMED | `graph-execution-substrate` owns Branch validation and `live-mcp-connector-surface` owns routing/envelopes, but exact shipped strict suggestions, transactional batch rollback, one-ledger-entry, receipt/text, and Mermaid behavior remain unspecced. `backfill-graph-mutation-and-resume-contracts` owns them; old public action placement stays historical. |
| [`daemon-liveness-watchdog.md`](../specs/daemon-liveness-watchdog.md) | CLAIMED | `daemon-runtime-and-dispatch` and `uptime-and-alarms` own heartbeat/watchdog/restart/re-probe, but shipped `get_status.supervisor_liveness` payload semantics remain unspecced. `backfill-daemon-control-and-status-contracts` owns the exact status contract; optional Prometheus remains historical. |
| [`INDEX.md`](../specs/INDEX.md) | HISTORY | Coordination index rewritten to point at OpenSpec and this disposition; it is not itself a behavioral spec. |
| [`loop-outcome-rubric-v0.md`](../specs/loop-outcome-rubric-v0.md) | CANONICAL | Deterministic KEEP/rubric rules and auto-ship envelope are in `evaluation-outcomes-and-attribution` and `community-patch-loop`. |
| [`multi-provider-tray-runtime.md`](../specs/multi-provider-tray-runtime.md) | CANONICAL | Shipped source-tray provider controls and health behavior are in `desktop-host-runtime`; packaging remains separately claimed. |
| [`outcome_gates_phase6.md`](../specs/outcome_gates_phase6.md) | CANONICAL | Gate ladders, claims, evidence, leaderboard, and bonus lifecycle are in `shared-goals-and-convergence` and `evaluation-outcomes-and-attribution`. |
| [`phase_d_preflight.md`](../specs/phase_d_preflight.md) | HISTORY | Explicit historical/superseded preflight; current fantasy dispatch behavior is bounded by canonical runtime specs. |
| [`phase_e_preflight.md`](../specs/phase_e_preflight.md) | CLAIMED | Selector/locking/lease behavior is canonical, but shipped terminal queue GC and still-callable `recover_claimed_tasks` lack exact coverage. `backfill-local-daemon-lease-queue-contracts` owns that residue; rollout prose is historical. |
| [`phase_f_preflight.md`](../specs/phase_f_preflight.md) | HISTORY | Explicit historical/superseded preflight; current Goal subscription/pool behavior is canonical. |
| [`phase_g_preflight.md`](../specs/phase_g_preflight.md) | HISTORY | Explicit historical/superseded preflight; current pre-launch bid subset is canonical. |
| [`phase_h_preflight.md`](../specs/phase_h_preflight.md) | CLAIMED | Broad tray/dashboard health is canonical, but shipped/reachable `daemon_overview`, `set_tier_config` persistence, and tier controls lack exact coverage. `backfill-daemon-control-and-status-contracts` owns that residue; old rollout prose is historical. |
| [`phase7_github_as_catalog.md`](../specs/phase7_github_as_catalog.md) | CLAIMED | Historical implementation plan represents one side of the unresolved store decision. `Resolve target-spec PLAN conflicts` chooses the architecture; `complete-full-platform-target-specs` must then create/sync any surviving behavior. GitHub-canonical implementation details are non-authoritative unless selected. |
| [`runtime-fiction-memory-graph.md`](../specs/runtime-fiction-memory-graph.md) | CLAIMED | Promoted fiction-domain target with active planning evidence but no OpenSpec owner; a new STATUS successor now owns conversion to an active change. |
| [`scene-packet.md`](../specs/scene-packet.md) | CLAIMED | `domain-plugin-runtime` owns the shipped `ScenePacket` shape, normalization, aliases, and companion-file emission. The unbuilt Phase 1c prior-scene query, future validation output, and ledger target remain with `runtime-fiction-memory-graph`; mixed-file unresolved residue therefore keeps this file CLAIMED. |
| [`taskproducer_phase_c.md`](../specs/taskproducer_phase_c.md) | CANONICAL | `daemon-runtime-and-dispatch` owns the generic `WorkTarget`, permissive origin, producer ordering/failure isolation/stamping, and fantasy routing. `domain-plugin-runtime` is adjacent integration, not the TaskProducer contract owner. |
| [`tier-1-routing-closure-draft.md`](../specs/tier-1-routing-closure-draft.md) | HISTORY | Draft narrative fragment, not a requirement set or active target owner. |
| [`tool_return_shapes.md`](../specs/tool_return_shapes.md) | CANONICAL | The normative structured/text envelope is in `live-mcp-connector-surface`; remaining presentation advice is non-normative guidance. |

## Successor impact

The 27 CLAIMED files resolve through these exact owners. Rows already present in
STATUS are build/decision lanes; table-only rows remain inventory until a
provider promotes one literal directory after collision and review checks.

| Exact successor | Legacy residue | Promotion gate |
|---|---|---|
| STATUS `Resolve target-spec PLAN conflicts` → `complete-full-platform-target-specs` | Store/private-data choice, catalog/collaboration, moderation, packaged tray, market workflow, portability, authoring, connectors/handoffs, and load proof. | Host selects coherent PLAN positions; successor applies the minimal-primitives test before adding platform behavior. |
| STATUS `enforce-private-goal-read-visibility` | Private Goal visibility across direct, derived, alias, and aggregate reads using signed owner request identity only. | Retire or supersede incomplete draft #1554; caller/env identity grants no authority; any signed host exception requires a separate decision; opposite-provider review before implementation or sync. |
| STATUS `harden-canonical-absolute-guarantees` | Money/attribution/birth/learning/receipt absolutes. | Private Goal visibility lands first on the shared market/test files; active paid/universe/relay owners merge before their remaining slices. |
| STATUS `runtime-fiction-memory-graph` | Runtime-fiction schema, ScenePacket Phase 1c prior-scene query/validation residue, and any future ledger target. | Brain-OKF authority/shape dependencies settle first. |
| STATUS `reconcile-hyperparameter-importance-evaluator` | Exact shipped evaluator and inline-test truth versus incompatible legacy evaluator/fixture promises. | Science-domain owner review; decide backfill, move, or retirement without silently rewriting runtime. |
| `backfill-graph-mutation-and-resume-contracts` | `resume_from` and composite mutation validation/rollback/receipt behavior. | Coordinate `graph-execution-substrate`, legacy-tool retirement, and distributed execution; no remote-authority implication. |
| `backfill-daemon-control-and-status-contracts` | `supervisor_liveness`, `daemon_overview`, tier-config persistence and tier controls. | Coordinate daemon runtime, live-MCP status variants, desktop host, identity/reset, and connector retirement. |
| `backfill-local-daemon-lease-queue-contracts` | Terminal queue GC and still-callable legacy recovery alongside local lease/cancellation behavior. | Host-pool and distributed-execution authority review; local receipts are not signed remote leases. |
| `reconcile-primitive-contract-targets` | CLAIM/SEAL, joins, cancellation/suspension, terminal events, completion tokens, and forever-tests. | Host PLAN decision; explicitly adopt, map to existing primitives, or retire each target before creating behavior. |

No file's surviving material is exclusively owned by active OpenSpec changes,
so the ACTIVE count is zero. The 13 HISTORY files are explicitly not current
targets; their ideas may be revived only through the normal OpenSpec proposal
gate.

## Verification

- `rg --files docs/specs -g '*.md'` returns 52 files.
- The matrix contains each basename exactly once, including `INDEX.md`.
- Every CANONICAL owner named above exists under `openspec/specs/`.
- Every ACTIVE owner named above exists under `openspec/changes/` and remains
  unarchived.
- Every CLAIMED row maps to a live STATUS owner or an exact successor and
  promotion gate in the table above rather than an untracked chat-only intent.
- Three read-only range reviews covered all 52 rows. Their ADAPT findings plus
  the post-PR-#1622 domain/security reviews were reconciled into the
  12/0/27/13 matrix and exact successor table. The separate
  `correct-independent-backfill-authority` lane owns the two canonical wording
  defects and full-coverage-certainty downgrade found by that security review.
- `tests/test_outcome_evaluators.py -k HyperparameterImportanceEvaluator`:
  5 passed, 3 skipped; `tests/test_branch_evaluation_iteration.py -k
  resume_from`: 5 passed.
- Strict OpenSpec validation remains the repository gate; this documentation
  disposition changes no runtime behavior and requires no uptime canary.

# Legacy specification disposition

- **Date:** 2026-07-22
- **Baseline:** PR #1624 merge on `origin/main` at `dff6795e`, plus archived
  changes `2026-07-23-backfill-independent-shipped-contracts` and
  `2026-07-23-backfill-runtime-memory-shipped-contracts`
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
  owner but is already bounded by a STATUS successor lane. That lane must
  create/sync the OpenSpec owner; this file itself grants no build authority.
- **HISTORY** — superseded, research, fixture, domain exemplar, draft fragment,
  or parked input with no current behavioral authority. Revival requires a new
  OpenSpec change rather than changing the embedded status back to active.

## Result

| Disposition | Files |
|---|---:|
| CANONICAL | 18 |
| ACTIVE | 0 |
| CLAIMED | 18 |
| HISTORY | 16 |
| **Total** | **52** |

## File-by-file matrix

| Legacy file | Disposition | Current owner or reason |
|---|---|---|
| [`2026-04-10-investigation-findings.md`](../specs/2026-04-10-investigation-findings.md) | HISTORY | Explicit historical incident/evaluator findings; source/test history, not a live contract. |
| [`2026-04-18-daemon-host-tray-changes.md`](../specs/2026-04-18-daemon-host-tray-changes.md) | CLAIMED | Shipped entrypoint/tunnel behavior is now canonical in `desktop-host-runtime`; the surviving one-click cross-OS packaging target remains in the full-platform target lane. |
| [`2026-04-18-export-sync-cross-repo.md`](../specs/2026-04-18-export-sync-cross-repo.md) | CLAIMED | Export/portability target is incomplete and canonical-store direction is a recorded PLAN host decision; owned by the full-platform target lane after that decision. |
| [`2026-04-18-full-platform-schema-sketch.md`](../specs/2026-04-18-full-platform-schema-sketch.md) | CLAIMED | Postgres/RLS/private-data prescriptions conflict with current PLAN tensions; collaborative control-plane target stays in the host-decision plus full-platform target lanes. |
| [`2026-04-18-load-test-harness-plan.md`](../specs/2026-04-18-load-test-harness-plan.md) | CLAIMED | This is target proof infrastructure, not shipped behavior; the full-platform target lane must preserve the Forever Rule concurrency/load gate. |
| [`2026-04-18-mcp-gateway-skeleton.md`](../specs/2026-04-18-mcp-gateway-skeleton.md) | HISTORY | Superseded deployment skeleton. Current behavior is in `live-mcp-connector-surface`, with remaining distribution/retirement work in active connector changes. |
| [`2026-04-18-moderation-mvp.md`](../specs/2026-04-18-moderation-mvp.md) | CLAIMED | Moderation, abuse response, appeals, and rate limits are an uncovered full-platform target group. |
| [`2026-04-18-paid-market-crypto-settlement.md`](../specs/2026-04-18-paid-market-crypto-settlement.md) | CLAIMED | `build-forward-platform-capabilities` owns transaction/oracle slices, but production inbox, matching, claims, delivery, disputes, and launch flow still need the full-platform target owner. |
| [`2026-04-18-remix-and-convergence-detail.md`](../specs/2026-04-18-remix-and-convergence-detail.md) | CLAIMED | Local Goal/convergence primitives are canonical, but realtime node discovery/remix/convergence collaboration remains an uncovered target group. |
| [`2026-04-18-web-app-landing-and-catalog.md`](../specs/2026-04-18-web-app-landing-and-catalog.md) | CLAIMED | Static public surface is canonical; authenticated catalog/control-plane behavior remains in the PLAN-decision and full-platform target lanes. |
| [`2026-04-19-connectors-two-way-tool-integration.md`](../specs/2026-04-19-connectors-two-way-tool-integration.md) | CLAIMED | Active connector-manifest/boundary deltas cover product distribution and generic adapters, not the launch catalog, per-service OAuth/PKCE, consent/revocation, privacy filtering, or third-party connector lifecycle; that residue belongs to the full-platform target lane. |
| [`2026-04-19-handoffs-real-world-pipeline.md`](../specs/2026-04-19-handoffs-real-world-pipeline.md) | CLAIMED | `distributed-execution` owns generic signed execution/effect authority; explicit handoff/outcome linkage remains an uncovered full-platform target. |
| [`2026-04-19-plan-b-selfhost-migration-playbook.md`](../specs/2026-04-19-plan-b-selfhost-migration-playbook.md) | CLAIMED | Data portability, account deletion/succession, and complete self-host migration remain in the full-platform target lane after store decisions. |
| [`2026-04-19-track-n-vibe-coding-authoring-sandbox.md`](../specs/2026-04-19-track-n-vibe-coding-authoring-sandbox.md) | CLAIMED | Node authoring/file-I/O/evaluator-catalog/autoresearch behavior is an uncovered full-platform target group. |
| [`2026-04-27-hyperparameter-importance-evaluator-node.md`](../specs/2026-04-27-hyperparameter-importance-evaluator-node.md) | CLAIMED | Promoted, science-lane-blocked domain target; a new STATUS successor now owns conversion to an active OpenSpec change. Generic evaluator behavior remains canonical separately. |
| [`2026-04-27-hyperparameter-importance-fixture-pack.md`](../specs/2026-04-27-hyperparameter-importance-fixture-pack.md) | CLAIMED | Fixture companion to the promoted hyperparameter target; the same domain-target OpenSpec successor owns it. |
| [`2026-04-27-recency-and-continue-branch-primitives.md`](../specs/2026-04-27-recency-and-continue-branch-primitives.md) | CANONICAL | `graph-execution-substrate` owns the surviving `run_branch resume_from=<run_id>` terminal-source guards, input merge, distinct-run, and lineage contract; retired standalone actions remain historical. |
| [`2026-04-27-recency-continue-fixture-pack.md`](../specs/2026-04-27-recency-continue-fixture-pack.md) | CANONICAL | `graph-execution-substrate` owns the shipped and tested terminal-run-seeded new-run behavior; the fixture pack remains evidence rather than authority. |
| [`2026-04-27-runtime-memory-graph-minimal-schema-v1.md`](../specs/2026-04-27-runtime-memory-graph-minimal-schema-v1.md) | CLAIMED | The promoted runtime-fiction target still depends on this four-entity schema freeze; the `runtime-fiction-memory-graph` successor lane owns its disposition alongside the broader target. |
| [`2026-04-30-classic-game-restoration-branch.md`](../specs/2026-04-30-classic-game-restoration-branch.md) | HISTORY | Community-built domain/Branch exemplar with no new platform primitive; retained as project evidence. |
| [`2026-05-02-acceptance-scenario-minimal-schema.md`](../specs/2026-05-02-acceptance-scenario-minimal-schema.md) | CANONICAL | `evaluation-runtime-and-scenarios` owns validation, registry dispatch, normalization, and current MCP-call limits. |
| [`2026-05-02-experience-pool-minimal-schema.md`](../specs/2026-05-02-experience-pool-minimal-schema.md) | CANONICAL | `knowledge-retrieval-and-memory` owns the accepted `experience_lesson` kind and generic review/search lifecycle; the file's field tables are non-enforced composition guidance. |
| [`2026-05-02-session-trace-minimal-schema.md`](../specs/2026-05-02-session-trace-minimal-schema.md) | CANONICAL | `knowledge-retrieval-and-memory` owns the `session_trace_summary` kind, generic lifecycle, visibility tags, retrieval, and limitations; its detailed metadata shape remains guidance. |
| [`2026-05-03-dual-key-auto-ship-acceptance.md`](../specs/2026-05-03-dual-key-auto-ship-acceptance.md) | HISTORY | Superseded governance proposal; current dry-run/PR-open boundaries are canonical in `community-patch-loop`, and no dual-key contract is current. |
| [`2026-05-04-loop-autonomy-roadmap.md`](../specs/2026-05-04-loop-autonomy-roadmap.md) | HISTORY | Superseded roadmap for the retired cheat-loop direction; current as-built loop boundaries are in `community-patch-loop`. |
| [`2026-05-27-authority-resolver-contract-v1.md`](../specs/2026-05-27-authority-resolver-contract-v1.md) | CANONICAL | `development-coordination-runtime` now owns the shipped schema, taxonomy, validation, evidence, and deterministic resolution outcomes. |
| [`2026-06-10-brain-v2-research-implications.md`](../specs/2026-06-10-brain-v2-research-implications.md) | HISTORY | Research provenance. Current shipped memory is canonical and `brain-okf-canonical-store` owns the unbuilt OKF migration. |
| [`2026-06-10-primitive-basis-audit.md`](../specs/2026-06-10-primitive-basis-audit.md) | HISTORY | Design/audit evidence; PLAN owns the architectural vocabulary and OpenSpec owns behavior. |
| [`2026-06-10-tiny-first-principles-spec.md`](../specs/2026-06-10-tiny-first-principles-spec.md) | CLAIMED | Cross-cutting source mixes shipped, active, conflicted, and uncovered targets. Surviving pieces are split across canonical specs, active Brain/forward changes, the PLAN host-decision lane, and the full-platform target lane. |
| [`2026-07-15-riscv-fpga-vertical-proof.md`](../specs/2026-07-15-riscv-fpga-vertical-proof.md) | HISTORY | Explicitly paused first-device candidate with no implementation authority; general hardware outcomes remain active in `build-forward-platform-capabilities`, but this exact RISC-V proof is not current. |
| [`auto-ship-rollback-v0.md`](../specs/auto-ship-rollback-v0.md) | HISTORY | The proposed rollback primitive never shipped and the cheat loop was retired 2026-06-25; surviving read-only `auto_ship_health`/recommendation behavior is canonical in `community-patch-loop`. |
| [`community_branches_phase2.md`](../specs/community_branches_phase2.md) | CANONICAL | Surviving graph/state substrate is in `graph-execution-substrate`; obsolete fat-tool names are bounded by `live-mcp-connector-surface`. |
| [`community_branches_phase3.md`](../specs/community_branches_phase3.md) | CANONICAL | Shipped graph runner, validation, state, checkpoints, and terminal outcomes are in `graph-execution-substrate`. |
| [`community_branches_phase4.md`](../specs/community_branches_phase4.md) | CANONICAL | Shipped iteration/evaluation substance is split across `graph-execution-substrate`, `evaluation-runtime-and-scenarios`, and `evaluation-outcomes-and-attribution`. |
| [`community_branches_phase5.md`](../specs/community_branches_phase5.md) | CANONICAL | Goals, bindings, canonical versions, leaderboards, and convergence primitives are in `shared-goals-and-convergence`. |
| [`composite_branch_actions.md`](../specs/composite_branch_actions.md) | CANONICAL | Surviving build/patch validation substrate is in `graph-execution-substrate`; old public action placement is historical. |
| [`daemon-liveness-watchdog.md`](../specs/daemon-liveness-watchdog.md) | CANONICAL | `daemon-runtime-and-dispatch` and `uptime-and-alarms` own supervisor, heartbeat, watchdog, restart, and re-probe behavior. |
| [`INDEX.md`](../specs/INDEX.md) | HISTORY | Coordination index rewritten to point at OpenSpec and this disposition; it is not itself a behavioral spec. |
| [`loop-outcome-rubric-v0.md`](../specs/loop-outcome-rubric-v0.md) | CANONICAL | Deterministic KEEP/rubric rules and auto-ship envelope are in `evaluation-outcomes-and-attribution` and `community-patch-loop`. |
| [`multi-provider-tray-runtime.md`](../specs/multi-provider-tray-runtime.md) | CANONICAL | Shipped source-tray provider controls and health behavior are in `desktop-host-runtime`; packaging remains separately claimed. |
| [`outcome_gates_phase6.md`](../specs/outcome_gates_phase6.md) | CANONICAL | Gate ladders, claims, evidence, leaderboard, and bonus lifecycle are in `shared-goals-and-convergence` and `evaluation-outcomes-and-attribution`. |
| [`phase_d_preflight.md`](../specs/phase_d_preflight.md) | HISTORY | Explicit historical/superseded preflight; current fantasy dispatch behavior is bounded by canonical runtime specs. |
| [`phase_e_preflight.md`](../specs/phase_e_preflight.md) | HISTORY | Explicit historical/superseded preflight; current queue/dispatcher behavior is canonical. |
| [`phase_f_preflight.md`](../specs/phase_f_preflight.md) | HISTORY | Explicit historical/superseded preflight; current Goal subscription/pool behavior is canonical. |
| [`phase_g_preflight.md`](../specs/phase_g_preflight.md) | HISTORY | Explicit historical/superseded preflight; current pre-launch bid subset is canonical. |
| [`phase_h_preflight.md`](../specs/phase_h_preflight.md) | HISTORY | Explicit historical/superseded preflight; current tray/status behavior is canonical. |
| [`phase7_github_as_catalog.md`](../specs/phase7_github_as_catalog.md) | CLAIMED | Historical implementation plan still represents one side of the unresolved Postgres-versus-GitHub canonical-store decision; the existing PLAN host-decision lane owns its disposition. |
| [`runtime-fiction-memory-graph.md`](../specs/runtime-fiction-memory-graph.md) | CLAIMED | Promoted fiction-domain target with active planning evidence but no OpenSpec owner; a new STATUS successor now owns conversion to an active change. |
| [`scene-packet.md`](../specs/scene-packet.md) | CANONICAL | `domain-plugin-runtime` now owns the exact fantasy episodic-coordinate registration, ScenePacket shape, normalization, aliases, and emission path. |
| [`taskproducer_phase_c.md`](../specs/taskproducer_phase_c.md) | CANONICAL | Producer protocols, domain registration, dispatch scoring, and generic work targets are in `daemon-runtime-and-dispatch` and `domain-plugin-runtime`. |
| [`tier-1-routing-closure-draft.md`](../specs/tier-1-routing-closure-draft.md) | HISTORY | Draft narrative fragment, not a requirement set or active target owner. |
| [`tool_return_shapes.md`](../specs/tool_return_shapes.md) | CANONICAL | The normative structured/text envelope is in `live-mcp-connector-surface`; remaining presentation advice is non-normative guidance. |

## Successor impact

This disposition creates two bounded successors for promoted domain targets.
The eighteen CLAIMED files fold into live STATUS work:

- the remaining credential-vault shipped-contract backfill; the prompt/status,
  universe-switch, uptime, runtime, host-pool, graph, OKF-export, and
  `resume_from` residue is now canonical;
- the PLAN-conflict host decision (schema/store/private-data/public-surface
  portions of the April/June cross-cutting specs plus the Phase-7 store plan);
- the eight-group full-platform target change (catalog/collaboration,
  moderation, packaged tray, market workflow, portability, authoring, and
  handoffs/connectors, with its load-proof obligation); and
- the two promoted-domain successors (runtime-fiction memory graph and
  hyperparameter-importance evaluator/fixtures).

No legacy file itself is an ACTIVE owner. The 16 HISTORY files are explicitly
not current targets; their ideas may be revived only through the normal
OpenSpec proposal gate.

## Verification

- `rg --files docs/specs -g '*.md'` returns 52 files.
- The matrix contains each basename exactly once, including `INDEX.md`.
- Every CANONICAL owner named above exists under `openspec/specs/`.
- Every ACTIVE owner named above exists under `openspec/changes/` and remains
  unarchived.
- Every CLAIMED row maps to a live STATUS successor rather than an untracked
  chat-only intention.
- Strict OpenSpec validation remains the repository gate; this documentation
  disposition changes no runtime behavior and requires no uptime canary.

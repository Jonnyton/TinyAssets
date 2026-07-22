# Specs Index

Formal feature or change specs live here when a task needs explicit acceptance
criteria before implementation. `AGENTS.md` § Project Files points every provider
at this page as the directory surface for `docs/specs/`, so a spec that is
missing here is effectively invisible to the next session.

## How this index is maintained

- **Every `.md` in `docs/specs/` gets a line.** Current count: **51 specs + this
  index = 52 files**. Verify with:
  ```
  ls docs/specs/*.md | grep -vc INDEX.md          # expect 51
  grep -coE '\]\([^)]*\.md\)' docs/specs/INDEX.md # expect >= 51
  ```
  If the first number exceeds the second, this index has drifted — add the
  missing entries rather than assuming the spec does not exist.
- **Grouping follows the `status:` frontmatter lifecycle** defined in
  `docs/conventions.md` § "Frontmatter `status:` field" (`active`, `shipped`,
  `superseded`, `research`, `historical`). Group counts as of 2026-07-21:
  24 `active`, 13 with no frontmatter, 7 `historical`, 6 `shipped`,
  1 `superseded`.
- **Each line says what the spec decided and what state it is in** — not just
  its title. Landed work carries its commit; unbuilt work says so.
- When a spec's status changes, move its line to the matching section in the
  same commit. A spec in the wrong section is the same failure as a missing one.

## Relationship to `openspec/specs/`

`AGENTS.md` § Spec-driven development makes `openspec/specs/<capability>/spec.md`
the **as-built requirement truth** (22 capabilities on `main`). `docs/specs/`
holds the older feature/change specs. The two are easy to confuse, so state the
relationship precisely:

- **An OpenSpec capability does not automatically or wholly supersede a
  `docs/specs/` entry.** The capability specs are as-built baselines — each opens
  with "describes landed behavior on `main` at baseline time". Most entries below
  are forward-looking pre-drafts that explicitly say "No code yet", and what got
  built is frequently narrower than what the pre-draft proposed. **But landed
  behavior can still partially obsolete or outright contradict parts of a draft.**
  So neither doc overrides the other by default: revalidate the entry against the
  capability baseline before building from it, and record what survived.
- Verified 2026-07-21: **no file under `openspec/specs/` cites any `docs/specs/`
  path, and no entry below cited a capability.** The cross-references below were
  added by this index; they are domain pointers, not supersession claims.
- **How to read the pointers.** `→ as-built: <capability>` means "if you want to
  know what exists on `main` in this domain today, read that capability spec
  first; read the entry below for the intent that has not been built." Entries
  with no pointer have no close as-built capability.
- Genuine supersession is recorded the way `docs/conventions.md` requires — a
  `status: superseded` frontmatter plus a `superseded_by:` path — and appears in
  the *Superseded* section below.

---

## Active — full-platform track pre-drafts (2026-04-18 / 2026-04-19)

Thirteen pre-draft specs written against
`docs/design-notes/2026-04-18-full-platform-architecture.md` as a single
dispatchable set, one per track. **All of them state "Pre-draft spec. No code
yet."** in their own headers, and they assume a Postgres/Supabase + RLS
substrate. Treat them as design intent to re-validate against current
architecture before building, not as a queue.

- [`2026-04-18-full-platform-schema-sketch.md`](2026-04-18-full-platform-schema-sketch.md) — Track A/H. Working SQL sketch for the whole platform: core tables, RLS model, `discover_nodes` RPC, optimistic-CAS `version` column. Carries `OPEN:` flags where answers were unknown. Unbuilt; gated on host Q1.
- [`2026-04-18-mcp-gateway-skeleton.md`](2026-04-18-mcp-gateway-skeleton.md) — Track C. OAuth 2.1 + PKCE handshake, bearer validation, per-user rate limiting, RLS context setup, structured error envelope. Unbuilt as specified. → as-built: `live-mcp-connector-surface`, `identity-auth-and-access-control`.
- [`2026-04-18-web-app-landing-and-catalog.md`](2026-04-18-web-app-landing-and-catalog.md) — Track B. Landing page, node catalog, per-tier onboarding funnel. Unbuilt.
- [`2026-04-18-daemon-host-tray-changes.md`](2026-04-18-daemon-host-tray-changes.md) — Track D. Tier-2 tray as primary surface: multi-daemon spawn, host pool, capabilities, wallet registration, <5min install budget. Unbuilt. → as-built: `daemon-runtime-and-dispatch`.
- [`2026-04-18-paid-market-crypto-settlement.md`](2026-04-18-paid-market-crypto-settlement.md) — Track E. Bid lifecycle state machine, Base L2 testnet settlement, 1% treasury fee, "swap tokens later without a rewrite" constraint. Unbuilt as specified. → as-built: `paid-market-economy`, `token-architecture`.
- [`2026-04-18-moderation-mvp.md`](2026-04-18-moderation-mvp.md) — Track F. Community-flagged, volunteer-triaged, host-backstopped moderation; auto-soft-hide at threshold; contributor-owned rubric. No ML, no CAPTCHA, no pre-review. Unbuilt.
- [`2026-04-18-export-sync-cross-repo.md`](2026-04-18-export-sync-cross-repo.md) — Track G. Bridge from live content to the `TinyAssets/` + `TinyAssets-catalog/` repos, with private-field stripping. Both failure modes (broken clone, leaked private data) called unrecoverable at scale. Unbuilt.
- [`2026-04-18-remix-and-convergence-detail.md`](2026-04-18-remix-and-convergence-detail.md) — Tracks I + K. `remix_node` with provenance preservation and `converge_nodes` with editor-threshold approval; RPC bodies and edge cases. Unbuilt as specified. → as-built: `shared-goals-and-convergence`.
- [`2026-04-18-load-test-harness-plan.md`](2026-04-18-load-test-harness-plan.md) — Track J. Load-test stack selection (k6 vs alternatives), scenarios with success thresholds, cost, revised dev-day estimate. Notes a track-label conflict (dispatch said "track K"; design note says J). Unbuilt.
- [`2026-04-19-connectors-two-way-tool-integration.md`](2026-04-19-connectors-two-way-tool-integration.md) — §28. `ConnectorProtocol`, connector registry, `connector_invoke` RPC, consent model, audit log. Framing: completion happens at the user's tool boundary, not a download page. Unbuilt as specified. → as-built: `boundary-layer`.
- [`2026-04-19-handoffs-real-world-pipeline.md`](2026-04-19-handoffs-real-world-pipeline.md) — §30. Handoffs as a connector subtype: `declare_handoff` routing plus auto-written real-world outcome claims. Unbuilt. → as-built: `boundary-layer`.
- [`2026-04-19-track-n-vibe-coding-authoring-sandbox.md`](2026-04-19-track-n-vibe-coding-authoring-sandbox.md) — Track N. Nine-tool `/node_authoring.*` family plus execution sandbox; called the largest remaining design surface (~2.5–4d). Unbuilt. → as-built: `graph-execution-substrate`.
- [`2026-04-19-plan-b-selfhost-migration-playbook.md`](2026-04-19-plan-b-selfhost-migration-playbook.md) — Exit option from managed services (Supabase + Fly.io) to self-hosted (Hetzner + Docker). Four named triggers. Contingency, not queued work.

## Active — current and standing

- [`2026-06-10-tiny-first-principles-spec.md`](2026-06-10-tiny-first-principles-spec.md) — **TINY first-principles spec** (host + Fable, 9 ratification rounds): rename, mind anatomy, Brain v2 context engine, operations/failure/attention layers, governance/redaction/compliance, build-boundary + basis-quest laws, 2-week execution order. Host-ratified DIRECTION; build not started. Supersedes conflicting PLAN.md sections pending truth sweep.
- [`2026-06-10-brain-v2-research-implications.md`](2026-06-10-brain-v2-research-implications.md) — Memory-systems research behind spec §5 (Karpathy LLM Wiki, MemPalace, OB1, Hermes, OpenClaw + 5 landscape sweeps); 12 adopted mechanics. Names one unsolved gap: a public multi-writer commons is a 1-to-N prompt-injection channel. Codex ADAPT 2026-06-10: stubs + read-only `assemble()` unblocked, six pre-build gates. → as-built: `knowledge-retrieval-and-memory`.
- [`2026-06-10-primitive-basis-audit.md`](2026-06-10-primitive-basis-audit.md) — Six-primitive vocabulary audited against 50 years of theory: six confirmed, none added, all amended with contracts; state laws L1–L12; live `_dict_merge` L4 violation found (still an open STATUS Work row). Codex ADAPT 2026-06-10: names locked, contracts open. → as-built: `graph-execution-substrate`.
- [`2026-05-27-authority-resolver-contract-v1.md`](2026-05-27-authority-resolver-contract-v1.md) — Freezes the `resolver-decision-v1` decision payload (inputs, status enum, confidence, evidence handles, source-role map) as a contract, deliberately not a policy engine. Fixture pack `tests/fixtures/resolution/resolver_decision_v1.json`; Python contract `workflow.resolution`. Source: live wiki PR-139 CHILD-4. **Directly relevant to the unified authority-derivation program.** → as-built: `identity-auth-and-access-control`.
- [`2026-05-02-acceptance-scenario-minimal-schema.md`](2026-05-02-acceptance-scenario-minimal-schema.md) — Slice-1 contract shape for `AcceptanceScenario`, a typed record (not a memory_kind) that compiles into `EvalResult` evidence. Storage deferred to Slice 2. Authority: Claude review APPROVE. → as-built: `evaluation-outcomes-and-attribution`.
- [`2026-05-02-experience-pool-minimal-schema.md`](2026-05-02-experience-pool-minimal-schema.md) — Slice-1 content shape for the `experience_lesson` memory_kind: a `daemon_brain_entries` row, no migration. Authority: Claude review APPROVE. → as-built: `knowledge-retrieval-and-memory`.
- [`2026-05-02-session-trace-minimal-schema.md`](2026-05-02-session-trace-minimal-schema.md) — Slice-1 content shape for `session_trace_summary`: narrative summary plus references back to raw artifacts in their existing homes. Authority: Claude review ADAPT. → as-built: `knowledge-retrieval-and-memory`.
- [`2026-04-27-runtime-memory-graph-minimal-schema-v1.md`](2026-04-27-runtime-memory-graph-minimal-schema-v1.md) — Pre-implementation schema freeze: four entity types (`world_truth`, `event`, `epistemic_claim`, `narrative_debt`) with provenance and confidence on every row. Deliberately no ontology expansion in v1. → as-built: `knowledge-retrieval-and-memory`.
- [`runtime-fiction-memory-graph.md`](runtime-fiction-memory-graph.md) — Parent goal for the typed-memory work: scene packets, entity records, temporal/promissory/epistemic ledgers, generated human-readable indexes. Explicit non-goals (no big-bang rewrite, no backfill before the path is proven). → as-built: `knowledge-retrieval-and-memory`.
- [`scene-packet.md`](scene-packet.md) — ScenePacket schema (`fantasy_author/packets.py`): identity, position, POV/setting, participants, facts, promises, editorial verdict. Phase 1a — schema defined, not yet emitted.
- [`tool_return_shapes.md`](tool_return_shapes.md) — **Standing checklist** for every MCP tool return: parallel `text` + `structuredContent` channels, `annotations.audience` as a display hint never access control, shape-the-data-to-match-the-question. Read before adding any MCP action. → as-built: `live-mcp-connector-surface`.
- [`multi-provider-tray-runtime.md`](multi-provider-tray-runtime.md) — Draft r6: concurrent multi-provider daemons in the tray, provider pinning via env var, `~/.tinyassets/preferences.json` as per-host-operator scope. Revision notes record two corrections made against landed code. → as-built: `provider-routing`.
- [`outcome_gates_phase6.md`](outcome_gates_phase6.md) — Outcome-gate ladder for Goals (#56): ordered rungs, self-reported progress, `goals leaderboard metric=outcome`. Automation (DOI crawl, docket scrape) explicitly deferred. Reviewer audit passed; 6.1 landed. → as-built: `evaluation-outcomes-and-attribution`.
- [`tier-1-routing-closure-draft.md`](tier-1-routing-closure-draft.md) — Closing paragraph drafted for the live wiki page `tier-1-investigation-routing-resolver`, arguing BUG-019/021/022 are one conditional-edge root cause. Migrates to the wiki on redeploy; scope is the closing paragraph only.
- [`2026-04-30-classic-game-restoration-branch.md`](2026-04-30-classic-game-restoration-branch.md) — Live v0 branch built through the MCP surface (goal `62f977e7ff0c`, branch `cc727837fe8a`, 8 nodes / 9 edges). Community-built workflow, no new platform primitive. Records BUG-037: `get_branch_version` returns an empty snapshot, so fork from the `branch_def_id`, not the version.
- [`2026-04-27-recency-continue-fixture-pack.md`](2026-04-27-recency-continue-fixture-pack.md) — Fixture datasets and golden snapshots for `run_branch resume_from=<run_id>` (success, not-found, forbidden, invalid-state, branch-mismatch). Updated 2026-05-01 to track the accepted F2 shape. Pairs with the open STATUS Work row.
- [`2026-04-27-hyperparameter-importance-evaluator-node.md`](2026-04-27-hyperparameter-importance-evaluator-node.md) — Science-domain evaluator node ranking which sweep parameters drive a target metric. Domain-node parity feature, not a core primitive; v1 observational not causal. Engine changes out of scope until the scientific-computing lane opens.
- [`2026-04-27-hyperparameter-importance-fixture-pack.md`](2026-04-27-hyperparameter-importance-fixture-pack.md) — Companion fixtures, golden outputs, determinism rules, and test mapping for the evaluator node above.

## Proposals — community patch loop

Four coupled proposals for the auto-ship lane. None carries frontmatter status;
each declares `Status: proposal` in its body.

- [`2026-05-04-loop-autonomy-roadmap.md`](2026-05-04-loop-autonomy-roadmap.md) — Roadmap from the dry-run validator to full loop autonomy: PR creation, keyed auto-merge, ship-class graduation, observation, rollback, empty-queue self-seeking. Deliberately kept as one entry because the parts share a control loop. → as-built: `community-patch-loop`.
- [`2026-05-03-dual-key-auto-ship-acceptance.md`](2026-05-03-dual-key-auto-ship-acceptance.md) — Codex + Cowork double-key acceptance gate at step 4. The loop parks at the gate rather than shipping or losing state; assisted vs autonomous is policy, not a separate code path. → as-built: `community-patch-loop`.
- [`auto-ship-rollback-v0.md`](auto-ship-rollback-v0.md) — Slice C. Rollback primitive interface, decision rules, and evidence: the last safety net beneath the validator and the observation gate, so a regressed canary reverts without an operator. → as-built: `community-patch-loop`.
- [`loop-outcome-rubric-v0.md`](loop-outcome-rubric-v0.md) — Shared vocabulary for "is this loop variant better and safe enough to promote": evidence classes, promotion definitions, and the drift that produced BUG-051. Referenced by loop content, release gates, and observability surfaces. → as-built: `community-patch-loop`.

## Proposals — other

- [`daemon-liveness-watchdog.md`](daemon-liveness-watchdog.md) — Substrate proposal from a BUG-050 probe: the container healthcheck is a **false positive** — it reports "container alive" when "container alive AND daemon claiming pickable work" is what matters. Documents a case where three deploys reported success while the daemon was dead-or-wedged, with no activity for 42 minutes. → as-built: `daemon-runtime-and-dispatch`.
- [`2026-07-15-riscv-fpga-vertical-proof.md`](2026-07-15-riscv-fpga-vertical-proof.md) — Chatbot-built physical vertical proof: RISC-V soft CPU + ML accelerator on FPGA, quantized keyword-spotting model, custom carrier PCB, open firmware — originated and steered entirely through a live connector conversation. **Paused** as first-device candidate (host proposed a conversational-cookbook pivot 2026-07-15); candidate successor `ideas/2026-07-15-conversational-cookbook-device.md`. No implementation authority; a Claude-family reviewer must re-check sources before any build or purchase. → as-built: `hardware-creation`.

## Shipped

- [`community_branches_phase2.md`](community_branches_phase2.md) — Graph + state-design MCP tools. Decided to extend the existing `extensions` tool rather than add a coarse new one. Shipped `c85efa1` (2026-04-12). → as-built: `graph-execution-substrate`.
- [`community_branches_phase3.md`](community_branches_phase3.md) — Generic graph runner: `BranchDefinition → StateGraph` as a pure function, TypedDict synthesized at runtime with `Annotated` reducers (honors hard rule #5). Shipped `c85efa1`. → as-built: `graph-execution-substrate`.
- [`community_branches_phase4.md`](community_branches_phase4.md) — Eval + iteration hooks: plain-English judgment attaches to the node that produced weak output, closing build → run → judge → edit → rerun. Shipped `c85efa1`. → as-built: `evaluation-outcomes-and-attribution`.
- [`community_branches_phase5.md`](community_branches_phase5.md) — Goal as a first-class shared primitive; many Branches bind to one Goal so discovery works on intent, not `branch_def_id`. Shipped `c85efa1`. → as-built: `shared-goals-and-convergence`.
- [`composite_branch_actions.md`](composite_branch_actions.md) — `build_branch` / `patch_branch` composites, cutting a workflow build from 15–20 round trips to 1–2 after Claude.ai's per-turn tool limit was hit. Fine-grained actions retained for surgical edits. Shipped `c85efa1`. → as-built: `graph-execution-substrate`.
- [`taskproducer_phase_c.md`](taskproducer_phase_c.md) — Pluggable TaskProducer protocol + registry, turning the hardcoded "what next" decision into a seam. Reviewer audit passed; C.1–C.5 landed, protocol in `ba83254`. → as-built: `daemon-runtime-and-dispatch`.

## Superseded

- [`2026-04-27-recency-and-continue-branch-primitives.md`](2026-04-27-recency-and-continue-branch-primitives.md) — Recency + continue-branch action contracts. **Superseded 2026-05-01** by [`docs/design-notes/2026-04-25-extend-run-continue-branch.md`](../design-notes/2026-04-25-extend-run-continue-branch.md): host accepted F2 on 2026-04-28 — drop Recency as a platform primitive and fold continuation into `run_branch` as `resume_from=<run_id>`. Do not implement the three retired verbs listed in its §1.

## Historical

Retained for decision history. Each carries a "do not edit, do not extend, do not
cite as live" banner; current architecture lives in `PLAN.md`.

- [`phase_d_preflight.md`](phase_d_preflight.md) — Phase D preflight: fantasy universe-cycle as a registered BranchDefinition, unifying the autonomous loop with the Branch executor. Called the highest-blast-radius change on the board. Landed at `c5f29bb`.
- [`phase_e_preflight.md`](phase_e_preflight.md) — Phase E preflight: tier-aware DaemonController + persisted BranchTask queue; first user-visible scheduling surface. Landed at `29a71a7`.
- [`phase_f_preflight.md`](phase_f_preflight.md) — Phase F preflight: goal subscription + pool producer — the first cross-universe signal, and the first phase where a design bug could leak across universe boundaries. Landed at `1d02903`.
- [`phase_g_preflight.md`](phase_g_preflight.md) — Phase G preflight: NodeBid executor + paid-market priority weights; ships the structural slot with no wallet or crypto. Shipped; retire-with-stamp applied 2026-04-26.
- [`phase_h_preflight.md`](phase_h_preflight.md) — Phase H preflight: aggregated `daemon_overview` MCP action + tray/dashboard surfacing, consolidating ~15 accumulated Concerns from Phases D–G into observable surfaces.
- [`phase7_github_as_catalog.md`](phase7_github_as_catalog.md) — Phase 7: git-tracked YAML/Markdown as canonical shared state, SQLite demoted to cache, three tables retired in favor of git log / refs / history. Superseded by current PLAN.md architecture.
- [`2026-04-10-investigation-findings.md`](2026-04-10-investigation-findings.md) — Root-cause record for cross-universe contamination: CWD-relative `--db` default loaded a repo-root `knowledge.db` (449 stale entities) for every universe. Five numbered bugs with locations and fixes.

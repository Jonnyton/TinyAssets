# Idea Inbox

Quick capture surface for loose ideas, user nudges, possible features, and
half-formed experiments.

## Rules

- Capture first, refine later.
- Keep one idea per entry.
- If an idea becomes work, a design note, or a plan, add the destination in
  `Links` instead of deleting the capture history.
- Merge duplicates during triage in `ideas/PIPELINE.md`, not during capture.

## Inbox

- [2026-07-30] (source: host, owner: codex-gpt5-desktop, status:
  promoted-active, priority: uptime-platform, size: large) **Fully
  customizable agents in each user's universe.** Users publish and remix
  public component-level agent definitions, bind them privately to their
  universe and subscriptions, talk to them through Slack or other apps, and
  let them create, test, evaluate, and iterate user-authored automations.
  OpenClaw-like operators, Hermes-like assistants, coding agents, common
  configurations, and multi-user blends are examples rather than fixed
  platform types. The composition contract must have no power-user ceiling;
  TinyAssets wins through commons discovery, lineage/eval evidence,
  host-independent operation, plug-and-play governed bindings, and
  collaboration. The active first slice builds definitions, component
  provenance, private bindings, interchange, and canonical graph-handle
  targets. Live Slack effects wait for the outbound boundary layer; arbitrary
  managed-cloud code waits for the Engine OS sandbox.
  Links: `PLAN.md` Custom-agent corollary; `openspec/changes/universe-custom-agents/`;
  `STATUS.md` custom-agent lane.

- [2026-07-24] (source: host full-product vision + Codex navigator, owner: unassigned, status: captured-review-blocked, priority: post-control-plane, size: large) **Organization-owned shared brains and work through existing company systems.** Define an organization/workforce authority successor before adding Slack/Teams adapters: canonical organization, membership and group binding, scoped roles, offboarding, audit/export, shared-universe ownership, and requester-scoped execution authority bundles with immutable audit receipts and live revocation checks. Slack/Teams remain conformance adapters over the same command/inbox/effect boundary, never a second policy engine. Required order: PostgreSQL tenant authority -> identity/universe visibility -> organization/RBAC lifecycle -> generic connector boundary -> Slack/Teams adapters -> rendered and concurrent acceptance. Opposite-provider review required before promotion.

- [2026-07-24] (source: host regulated-industry vision + Codex navigator, owner: unassigned, status: captured-research-review-blocked, priority: post-authority, size: large) **Regulation-neutral workflow assurance composition, with HIPAA as the first profile.** Candidate successor `compose-regulated-workflow-controls` / capability `regulated-workflow-assurance`: versioned community control profiles map cited requirements to frozen capability gates, scoped evidence references, independent assessments, expiring exceptions, and fail-closed routing. Never add a “HIPAA mode,” infer legal status, copy PHI/PII into public evidence, or claim certification from self-attestation. Extend the same data model to GDPR/SOX without regulation-specific runtime branches or a new MCP action. Requires opposite-provider primary-source review plus organization authority, Postgres tenancy, BYOC isolation, immutable artifacts/evidence, effect receipts, retention/deletion, incident evidence, and counsel/assessor-owned acceptance.

- [2026-05-05] (source: host, owner: unassigned, status: superseded-by-user-automation, priority: archived, size: large) **Loop self-stewardship: historical privileged-loop framing retired.** Host direction 2026-07-26 removes the platform-owned cheat/community-patch loop. The useful residue—manual-intervention ledgers, self-correction rates, review memory, and promotion rules—belongs in user-authored, copyable, remixable automation designs built from generic primitives, not in a privileged product loop.

- [2026-05-02] (source: host, owner: unassigned, status: capture, priority: uptime, size: small) **Review open-source Claude Code / agent-team implementations for persistence lessons.** User flagged `https://github.com/SafeRL-Lab/nano-claude-code` (redirects to `SafeRL-Lab/cheetahclaws`), `https://github.com/SafeRL-Lab/cheetahclaws`, and `https://github.com/instructkr/claw-code` (redirects to `ultraworkers/claw-code`) as possible inspiration. Evaluate against TinyAssets' target advantages: 24/7 persistence without humans online, truthful daemon identity, user-authored/remixable automation without a privileged platform loop, and multi-provider durable coordination.

- [2026-05-02] (source: host, owner: unassigned, status: promoted, priority: post-#18, size: medium) **Daemon mini OpenBrain per soul-bearing daemon.** Research Nate B. Jones / Open Brain and adapt the pattern so each daemon controls an atomic, searchable memory backend that works with its existing daemon wiki. Direction captured in `docs/design-notes/2026-05-02-daemon-mini-openbrain.md`: wiki stays the curated face; mini brain is daemon-scoped capture/search/review/promote storage; observable memory traces query/retrieve/inject/write/promote/compact; no one flat pool, no soul copying, no Supabase/OpenRouter dependency by default.
- [2026-05-01] (source: host, owner: unassigned, status: reframed-user-automation, priority: commons-pattern, size: medium) **Patch-request incentives + requester-directed daemon work.** The incentive/routing idea remains available as a user-authored marketplace/workflow design composed from generic primitives; it does not authorize a TinyAssets-owned patch loop, privileged merge path, or platform policy. Users may copy/remix it and direct their own daemons, while acceptance and release remain separately governed.
  Links: `PLAN.md` Section Community-build over platform-build; `openspec/changes/retire-cheat-loop/`.

- [2026-04-27] (source: navigator-userim-review, owner: none, status: retired-community-composition, priority: post-uptime, size: medium) **`extensions action=my_recent_runs` + `goals action=my_recent` — user-scoped recency primitives.** Priya Session 2 (2026-04-20) signal #1: chatbot needs one tool call to answer "show me what I built recently" instead of fishing through `list_branches` + `query_runs` with author filter. Workspace-memory continuity gap — distinct from chatbot_assumes_workflow first-chat principle (this is N-th chat continuity).
  Resolution 2026-05-01: retired as platform primitives after freshness check. Use existing query-run plus optional goal/branch lookup composition; do not dispatch `_action_my_recent_*` code work.
  Triaged 2026-04-27; refreshed 2026-05-01: PIPELINE row "Recency primitives" records supersession by composition.
  Promoted 2026-04-27: pre-implementation contract now serves as supersession record in `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`.
  Historical fixture pack + implementation cards remain at `docs/specs/2026-04-27-recency-continue-fixture-pack.md` and `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`; do not treat the recency portions as pending engine work.
  Links: navigator's 2026-04-27 chain-break review (chat record); persona memory `priya_ramaswamy/`; `ideas/PIPELINE.md` "Recency primitives" row; `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`; `docs/specs/2026-04-27-recency-continue-fixture-pack.md`; `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`.

- [2026-04-27] (source: navigator-userim-review, owner: dev post-#18, status: dev-ready-after-18, priority: post-uptime, size: medium) **`run_branch resume_from=<run_id>` — explicit "extend prior run" parameter.** Priya signal #6 + Devin Session 2 echoed. "Extend the sweep" / "continue branch" has no clean TinyAssets path — chatbot has to semantically infer "clone this branch, add nodes, re-run with extended inputs." Same root concern as INBOX 2026-04-24 entry but with concrete API shape proposal.
  Files (when scoped): `tinyassets/api/runs.py` (add `resume_from=<run_id>` to existing `run_branch`); tests.
  Depends: #18 lock clears.
  Verification: persona replay plus live MCP `run_branch` call with `resume_from` proves chatbot routes to the existing run surface instead of re-scaffolding.
  Triaged 2026-04-27; refreshed 2026-05-01: MERGED with 2026-04-24 "Extend run / continue branch" entry into PIPELINE row "Continue-run resume primitive". No standalone `continue_branch` action; active dev-ready row is in `STATUS.md`.
  Promoted 2026-04-27: semantics + v1 envelope landed in `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md` (sibling-branch mode, carry-over contract, deterministic errors), then retargeted to `run_branch resume_from=<run_id>`.
  Promoted 2026-04-27 (execution-ready): fixture pack + implementation cards landed at `docs/specs/2026-04-27-recency-continue-fixture-pack.md` and `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`.
  Links: 2026-04-24 INBOX entry (merged into same PIPELINE row); navigator's 2026-04-27 chain-break review; `ideas/PIPELINE.md` "Continue-run resume primitive" row; `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`; `docs/specs/2026-04-27-recency-continue-fixture-pack.md`; `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`.

- [2026-04-27] (source: navigator-userim-review, owner: navigator, status: reframed-community-build, priority: domain-skill, size: medium) **Methods-prose evaluator class — publication-grade methods correctness.** Priya signal #2: when chatbot generates publication-grade methods paragraph (library versions + CV description + algorithm config), nothing checks correctness. Cross-layer chain-break (pitch-vs-product gap): platform pitches "Evaluator-driven workflows" but methods-section prose has no evaluator.
  Triaged 2026-04-27; refreshed 2026-04-28: host declined a new platform primitive. Next slice is a docs-only reframe of `docs/design-notes/2026-04-27-methods-prose-evaluator.md` to preserve the intent as chatbot + wiki composition guidance. No `EvaluatorKind` extension.
  Promoted 2026-04-27 (content-ready): wiki rubric starter content landed at `docs/notes/2026-04-27-methods-prose-rubric-starter-pack.md`.
  Links: navigator's 2026-04-27 chain-break review; `ideas/PIPELINE.md` "Methods-prose evaluator" row; `docs/notes/2026-04-27-methods-prose-rubric-starter-pack.md`.

- [2026-04-27] (source: navigator-userim-review, owner: unassigned, status: triaged, priority: knowledge-graph, size: large) **Cross-algorithm methodological-parity guidance — `node action=compatibility_with` or wiki concept page.** Priya signal #4: RF needs pseudo-absences, MaxEnt doesn't. Less-experienced users submit papers with flawed cross-algorithm comparisons because chatbot doesn't surface the differences. Lower urgency than recency / continue_branch primitives but real safety surface.
  Triaged 2026-04-27: PIPELINE row "Cross-algorithm methodological-parity guidance" — needed design-note first to choose surface (verb vs wiki).
  Promoted 2026-04-27: wiki-first template path selected in `docs/design-notes/2026-04-27-cross-algorithm-methodological-parity-guidance.md`; next step is a concrete wiki concept page + one user-sim retrieval pass.
  Promoted 2026-04-27 (content-ready): wiki publish template + RF-vs-MaxEnt seed landed at `docs/notes/2026-04-27-cross-algorithm-parity-wiki-template.md`.
  Promoted 2026-04-27 (publish-ready): publication checklist landed at `docs/notes/2026-04-27-cross-algorithm-parity-publication-checklist.md`.
  Links: navigator's 2026-04-27 chain-break review; `ideas/PIPELINE.md`; `docs/design-notes/2026-04-27-cross-algorithm-methodological-parity-guidance.md`; `docs/notes/2026-04-27-cross-algorithm-parity-wiki-template.md`; `docs/notes/2026-04-27-cross-algorithm-parity-publication-checklist.md`.

- [2026-04-27] (source: navigator-userim-review, owner: unassigned, status: triaged, priority: observability, size: small) **Trust-graduation observability — "% users skipping dry-inspect on session N" as retention proxy.** Priya signal #7: skipped dry-inspect on Session 2 after using it on Session 1. No surface tracks this today. Platform-instrumentation, not chain-break per se.
  Triaged 2026-04-27: PIPELINE row "Trust-graduation observability" — observability backlog.
  Promoted 2026-04-27: metric/event pre-spec landed at `docs/design-notes/2026-04-27-trust-graduation-observability-metric.md` (`pct_skip_dry_inspect_on_session_n` + event contract). Implementation remains observability-lane blocked.
  Promoted 2026-04-27 (query-ready): SQL/dashboard pack landed at `docs/notes/2026-04-27-trust-graduation-query-pack.md`.
  Links: navigator's 2026-04-27 chain-break review; `ideas/PIPELINE.md`; `docs/design-notes/2026-04-27-trust-graduation-observability-metric.md`; `docs/notes/2026-04-27-trust-graduation-query-pack.md`.

- [2026-04-25] (source: navigator-audit, owner: unassigned, status: triaged) CONTRIBUTORS.md authoring surface — a canonical file listing node/branch authors with GitHub handles for Co-Authored-By attribution, seeded from the designer-royalties model (`project_designer_royalties_and_bounties`). Chatbot can read it to credit contributors in commit messages and pull request bodies.
  Triaged 2026-04-27: PIPELINE row "CONTRIBUTORS.md authoring surface" — needed design-note (standalone-file vs. daemon_server.py table + MCP surface).
  Promoted 2026-04-27: file-first canonical decision landed in `docs/design-notes/2026-04-27-contributors-authoring-surface.md`; daemon/MCP API explicitly deferred behind volume/pain triggers.
  Promoted 2026-04-27 (ops-ready): maintenance/hygiene runbook landed at `docs/notes/2026-04-27-contributors-maintenance-runbook.md`.
  Links: `ideas/PIPELINE.md`; AGENTS.md Hard Rule #10; `docs/design-notes/2026-04-27-contributors-authoring-surface.md`; `docs/notes/2026-04-27-contributors-maintenance-runbook.md`.

- [2026-04-20] (source: host, owner: navigator-followup, status: triaged,
  priority: post-uptime, size: large)
  **Agent-teams-on-TinyAssets: open-source-Claude-Code-analog as a user
  project, backed by our primitives.**
  Host framing: the Claude Code system prompt leaked; a Python open-source
  analog is growing fast on GitHub and trending toward one of the fastest-
  growing repos. Opportunity — build "Claude Code agent teams" where each
  teammate is another TinyAssets node invoked via a daemon-request, and the
  teammates live in another branch of the workflow. **This is a USER
  project, not ours to build.** Our job is to make sure the primitives
  exist on the platform so the user's chatbot can compose this — daemon
  requests across branches, teammate roles as nodes, inter-teammate
  messaging via the paid-market / free-queue bid layer, per-teammate
  provenance + audit.
  Why this matters: validates the "daemon economy + convergent commons"
  thesis with a concrete, viral-shaped use case that isn't fantasy-
  authoring. If the OSS Claude-Code-analog audience can compose their
  agent teams on TinyAssets, the platform rides that wave.
  Required primitives (load-bearing, to check against existing roadmap):
  (a) node → daemon-request invocation with typed inputs/outputs,
  (b) cross-branch teammate spawning without per-teammate auth friction,
  (c) teammate identity + soul-file attachment per `project_terminology_daemon`,
  (d) per-teammate provenance in the activity log, (e) inter-teammate
  messaging — bid market OR free-queue fan-out, probably both,
  (f) graceful partial-failure when one teammate's daemon is down
  (handled by daemon-economy fallback paths).
  Open questions to answer at triage time (NOT now): does this need a
  dedicated MCP verb set for teammate orchestration, or does it compose
  from existing `submit_request` + branch primitives? Is the OSS Claude-
  Code-analog's data model mappable to our node-type taxonomy without
  forcing a schema change? How does convergent-commons apply — should
  popular teammate definitions be wiki-shared, forkable, autoresearch-
  optimizable?
  Dependencies: uptime-track (all 14 self-host rows) lands first;
  daemon-economy first-draft (Track A + bid + settlement) lands first;
  then this becomes a scoping exercise.
  Triaged 2026-04-27: PIPELINE row "Agent-teams-on-TinyAssets" — research-note
  landed at `docs/notes/2026-04-20-agent-teams-on-tinyassets-research.md`
  (11-seam gap analysis, foundation/UX/commons rankings, nano-claude-code
  as recommended Python reference base — ~40K LoC, ~85 files, architectural
  seams map cleanly onto our primitives — claw-code now Rust-primary, less
  ideal base). Blocked on uptime-track close + daemon-economy first-draft.
  Scoping exercise opens after both unblock.
  Promoted 2026-04-27: post-unblock execution checklist landed at `docs/notes/2026-04-27-agent-teams-post-uptime-scoping-checklist.md` (entry gates + phase checks + escalation criteria).
  Links:
  - **`docs/notes/2026-04-20-agent-teams-on-tinyassets-research.md` —
    navigator research + thinking note. 11-seam gap analysis, viral-
    moment considerations, foundation/UX/commons work item ranking.**
  - `docs/notes/2026-04-27-agent-teams-post-uptime-scoping-checklist.md`
  - `project_daemon_product_voice.md` — "summoning the daemon" brand fit.
  - `project_convergent_design_commons.md` — teammate-definition sharing.
  - `project_daemon_default_behavior.md` — multi-spawn policy needs
    re-read in light of "one user spawning many teammates."
  - `docs/design-notes/2026-04-18-full-platform-architecture.md` — check
    §10 track decomposition for whether this falls under Track N
    (vibe-coding authoring) or needs its own track.

- [2026-04-24] (source: user-sim/Priya-Session2, owner: navigator, status: triaged,
  priority: post-uptime, size: medium)
  **"Extend run" / "continue branch" as a first-class primitive.**
  User-sim signal: Priya Session 2 ask "add BIOCLIM + RF for comparison on the same 14 species"
  has no clean TinyAssets verb. "New branch" implies fresh scaffolding. "New run" implies same
  algo-set. Chatbot must semantically infer "clone this branch, add algorithm nodes, re-run
  same species set." No existing primitive surfaces this as an intent. Chain-break: Interface 1
  primitive gap — chatbot improvises where it should have a clear tool.
  Scoping questions: (a) clone-branch-and-add-nodes vs. re-run-with-additional-params vs.
  new sibling branch? (b) does this need a new MCP verb (`extend_branch`/`continue_run`) or
  is it composable from `submit_request` + `clone_branch`? (c) what state carries over from
  the original run (params, results, species set)?
  Dependencies: in-flight run recovery part 2 (#6) should land first (resume semantics
  inform extension semantics).
  Triaged 2026-04-27; refreshed 2026-05-01: MERGED with 2026-04-27
  `run_branch resume_from=<run_id>` entry into PIPELINE row "Continue-run resume
  primitive". Same root primitive gap; this entry's scoping questions carry
  forward as the design-note's open questions.
  Links:
  - `docs/audits/user-chat-intelligence/2026-04-24-competitor-trials-sweep.md` Signal 2
  - `ideas/PIPELINE.md` "Continue-run resume primitive" row

- [2026-04-24] (source: user-sim/Priya-W&B-trial, owner: navigator, status: triaged,
  priority: domain-skill, size: small)
  **`hyperparameter_importance` evaluator node for scientific/ML domain.**
  W&B Sweeps computes hyperparameter importance (which knobs matter most across a sweep)
  automatically. TinyAssets has no equivalent. User-sim rates it "cheap to add, high-value
  for scientific users." Domain-specific — belongs in the scientific-computing skill module,
  not the engine. CV-as-first-class-primitive is the structural moat; this is a parity win.
  Triaged 2026-04-27: PIPELINE row "hyperparameter_importance evaluator node" — waitlist
  until science-domain skill catalog exists. Cheap-to-add parity win.
  Promoted 2026-04-27: domain pre-spec landed at `docs/specs/2026-04-27-hyperparameter-importance-evaluator-node.md` (inputs/outputs/errors/tests frozen); implementation remains module-lane blocked.
  Promoted 2026-04-27 (execution-ready): fixture pack + implementation cards landed at `docs/specs/2026-04-27-hyperparameter-importance-fixture-pack.md` and `docs/exec-plans/active/2026-04-27-hyperparameter-importance-implementation-cards.md`.
  Links:
  - `docs/audits/user-chat-intelligence/2026-04-24-competitor-trials-sweep.md` Signal 4
  - `ideas/PIPELINE.md` "hyperparameter_importance evaluator node" row
  - `docs/specs/2026-04-27-hyperparameter-importance-evaluator-node.md`
  - `docs/specs/2026-04-27-hyperparameter-importance-fixture-pack.md`
  - `docs/exec-plans/active/2026-04-27-hyperparameter-importance-implementation-cards.md`
- [2026-06-24] (source: audit 2026-06-24 SDLC/vibe-coding + Claude-large-codebases best practices (G1), owner: navigator, status: captured) Eval + trajectory-evaluation discipline for daemon OUTPUT quality (rubric'd golden runs + output-eval + trajectory-eval gate). Whitepaper's central thesis: generation solved, verification is the remaining work. Deepest agentic-engineering gap; aligns with existing Evaluator frame.
  Next: idea-refine -> navigator design -> opposite-provider review gate before any build
  Links: docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md, PLAN.md (Evaluator), .claude/agents/critic.md
- [2026-06-24] (source: audit 2026-06-24 best-practices (G2b), owner: host-decision, status: captured) Committed home for shared Claude Code config: .claude/settings.json is gitignored, so deny-lists/hook-registrations/permissions can't propagate across machines/providers (contradicts blog's version-controlled exclusions). Commit settings.shared.json or a seed-from-template setup step.
  Next: decide shared-config story; unblocks team-wide deny-list (G2) + reflection hook (G3)
  Links: docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md, .gitignore:22, .claude/settings.json
- [2026-06-24] (source: audit 2026-06-24 best-practices (G3), owner: engineering, status: captured) Automated session-reflection Stop/SessionEnd hook: continuous-learning + REFLECTION.md norm is manual and lapses (project's own feedback_hooks_enforce_session_norms says automatic norms become hooks). When a session changed durable state, prompt one-line reflection + propose AGENTS.md/memory/skill update while context is fresh.
  Next: author .claude/hooks/session_reflection.py; depends on G2b for shared registration
  Links: docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md, .claude/hooks/
- [2026-06-25] (source: user-chat, owner: claude-code, status: RESOLVED — Slice 3) BUG-029 chain-drain tests went red after FEAT-006. RESOLUTION: it was a STALE-TEST bug, NOT a production bug. The tests cooled *unregistered* provider names; effective_chain (correctly) strips absent providers, so the drain check saw a local-only chain. In production a provider can only be in cooldown after being registered+attempted, so cooled⟹registered⟹survives effective_chain⟹drain detected correctly. The captured hypothesis ("drain check should use the pre-effective_chain chain") was WRONG — that would let an unregistered, never-cooled provider in FALLBACK_CHAINS block the all()-cooled check and silently disable BUG-029 backoff on cloud hosts. Fix: register the cooled providers in the 3 stale fixtures + add a regression guard (test_drain_runs_on_effective_chain_unregistered_api_does_not_block). Router unchanged. Verified 65 bug029 tests green on origin/main 3530cedc.
  Next: none — resolved in branch claude/bug029-chain-drain-fix.
  Links: -
- [2026-06-25] (source: user-chat, owner: unassigned, status: captured) PRE-EXISTING (not mine): 11 tests in tests/test_dispatcher_queue.py fail on clean origin/main b4e3f31b — universe_loop_not_declared on submit + IndexError/empty-queue on cancel/list/clamp invariants. Likely a soul-loop-declaration fixture drift (queue ops now require a declared universe loop). Found during loop-lease-reclaim work; unrelated to lease reclaim. Triage separately.
  Next: triage and choose whether this belongs in STATUS.md, PLAN.md, a design note, or an exec plan
  Links: -
- [2026-06-27] (source: user-chat, owner: codex-gpt5-desktop, status: promoted) **Tiny/TinyAssets naming and Workflow retirement.**
  Host decision: Tiny is the personified intelligence users and developers interact with; TinyAssets is the website, platform, GitHub/repository, distribution, and app/listing brand; Workflow/workflow is only a migration compatibility name and retires after staged replacement.
  Promoted to: `PLAN.md` Canonical Naming Boundary; `docs/design-notes/2026-06-27-tinyassets-hard-rename.md`; `docs/exec-plans/active/2026-06-27-tinyassets-hard-rename.md`; STATUS.md Work row "TinyAssets hard rename plan".
- [2026-07-29] (source: user-chat + automatic-drain live evidence, owner: unassigned, status: captured) **Separate OpenSpec backlog refinery from the delivery drain.** The repaired sequential drain can now deliver continuously, but the fresh inventory is 33 active changes / 833 unchecked tasks with only 4 claimable, 31 blocked, and 9 host-owned rows. A delivery worker cannot drain policy/dependency debt by coding harder. Explore a bounded, evidence-producing refinery that periodically identifies oversized changes, refreshes stale blocker labels, proposes dependency/slice corrections, and promotes only reviewed claimable slices; it must not silently rewrite PLAN authority, invent implementation permission, or bypass opposite-provider gates. Measure claimable-pressure gain before proposing parallel Codex+Claude workers or provider rotation.
  Next: `idea-refine` -> OpenSpec proposal -> opposite-provider review; define read-only report vs. mutation authority and §14 concurrency/load proof before any multi-worker mode.
  Links: `docs/ops/2026-07-28-openspec-drain-supervisor.md`; archived change `openspec/changes/archive/2026-07-29-harden-drain-progress-orchestration/`; live run `output/openspec-drain-auto-20260729-132507/`.
- [2026-07-29] (source: drain exact-head review attempts, owner: unassigned, status: captured) **Make read-only peer review a true single-provider budget boundary.** `scripts/peer_agent.py claude` claims a read-only review path, but project/user hooks spawned nested Claude/Codex process trees even when the brief explicitly forbade delegation, burning both subscriptions. Claude `--bare` prevented hooks but also disabled OAuth/keychain auth; `--safe-mode --tools Read,Glob,Grep` preserved auth and prevented nesting, but the account-wide spend limit then blocked review. Harden the wrapper with a tested safe-mode/read-tool contract, child-process audit/fail-closed behavior, and a clear subscription-limit result so drains never mistake recursive review work for bounded verification.
  Next: `auto-iterate` + `idea-refine` -> focused OpenSpec change; test CLI command construction, child-tree policy, authentication behavior, and provider-budget diagnostics without changing write-mode semantics.
  Links: `scripts/peer_agent.py`; draft PR #1880; `openspec/changes/enforce-durable-drain-blockers/tasks.md`.
- [2026-08-04] (source: claude-code session 2026-08-04 worktree teardown, owner: unclaimed, status: captured) wt.py done still refuses squash-merged lanes when the branch has merged main into itself — git_squash_merge.is_merged_into exists to fix exactly this pile-up, but claude/quarantine-wave2 (PR #2257 MERGED, 0 commits unpublished, rev-list main..branch = 10) was still refused, and only --force cleared it. Habituating to --force on a script that deletes work is the risk. UNVERIFIED hypothesis: the cherry-based detection compares the branch's cumulative tree, which for a branch that merged main several times also carries main's own changes, so the synthesized patch matches nothing. Re-test on a fresh branch that merges main twice before proving it.
  Next: reproduce on a throwaway branch that merges main twice, then fix git_squash_merge.is_merged_into or fall back to gh pr state==MERGED plus a zero-unpublished-commits check
  Links: scripts/git_squash_merge.py; scripts/wt.py:170; docs/design-notes/2026-06-24-branch-lifecycle-automation.md

## Expose Trigger as a user primitive (2026-08-04)

Found while activating the cloud drain. `write_graph` targets are `goal, request,
branch, universe, automation, agent, agent_binding`; `read_graph` adds
`runs/run/automations/connections/agents/...`. **Neither exposes `trigger`.**
`CloudAutomationSliceTrigger` exists only inside the cloud-automation lane.

So `target=automation` is the pre-built complex thing, and the primitive
underneath it is not available. A user who wants a scheduled workflow must take
our opinionated automation lane whole, and when its scheduler wedges they have no
composable way out — they can run a branch on command (`run_graph`, verified
live) but cannot express "run this branch version on this cadence" themselves.

Proposal: expose Trigger as a first-class primitive (bind to a branch version,
schedule/fire/cancel, list). Then a scheduled automation is *composed* from
Branch + Trigger by the user, our automation lane becomes one shareable design
rather than the only road, and unwedging is something the owner can do.

Do NOT add a `run_once` verb to `target=automation` — that was drafted and
rejected 2026-08-04 as redundant with `run_graph` and as more pre-built
complexity. The gap is the missing primitive, not a missing convenience.

Needs promotion to an OpenSpec change before any build.

## 2026-08-07 — Custom agent needs hands: governed workflow actions, not MCP tools

Host (Slack live test): the custom agent should manage workflows — build new
ones, remix from other designs, iterate, test. **Today it cannot.**
`_ENGINE_ALLOWED_TOOLS = ("WebFetch",)` and `_ENGINE_DISALLOWED_TOOLS` wildcards
`mcp__*`, so `write_graph`/`run_graph`/`read_graph` are all denied to the
universe turn (`tinyassets/universe_intelligence.py:61-93`). Only side effect
available is `commit_learning` (soul/canon/wiki).

The denial is the 2026-07-03 host-leak P0 fix and cannot be made surgical: the
logged-in claude.ai account's MCP connectors load regardless of
`--setting-sources`, so "allow only the TinyAssets MCP" is not expressible via
the CLI's name-based deny.

**Host correction 2026-08-07: `commit_learning` is the WRONG shape to build on.**
It is not agency — it is a post-hoc transcript miner. `converse` generates the
reply with NO tools, then a SECOND LLM call (`extract_learning`) re-reads the
transcript and emits a HARDCODED JSON schema (name + five fixed soul files +
canon[]), which `commit_learning` writes after the turn ends
(`universe_intelligence.py:525-556`). The agent never decides to write, is never
told what was written, and can never produce a file outside that schema. Live
evidence: it truthfully reported "my founder status is not-learned" while the
extractor wrote `founder.md` moments later behind its back.

**Wanted shape: talking to an OpenClaw-style agent.** In-turn tool use, its own
working directory, real-time writes, and it tells you what it did.

**Therefore the OS engine sandbox IS on the critical path** (correcting an
earlier note in this entry that said otherwise). Real-time writes require real
in-turn tools; in-turn tools require real confinement, which a CLI name-denylist
cannot give — `Read` is not scopeable to a directory and account MCP connectors
load regardless of `--setting-sources` (see the comment block at
`universe_intelligence.py:45-93`).

A container unlocks BOTH blockers at once:
- mount only `/data/u-tiny` → the kernel confines `Read`/`Write`/`Edit`, no name list needed;
- control `HOME` → no logged-in claude.ai account → no ambient connectors → "allow
  exactly the TinyAssets MCP and nothing else" becomes expressible, which is what
  makes `write_graph`/`run_graph`/`read_graph` grantable in-turn.

`commit_learning` then becomes unnecessary rather than a foundation.

Related: `universe-is-account-not-workflow`, `enabling-primitives-not-prebuilt-complexity`,
`user-subscription-runs-the-universe`, STATUS P1 "No OS engine sandbox".

## 2026-08-07 — `reset.py` predates the chat surface: clean slate is a BROKEN slate

Host asked whether the test-round clean-slate reset was ever built. It was —
`tinyassets/reset.py` (confirm-gated, preserves branch/wiki commons). But it was
written before the Slack/app ingress existed, so `_RESET_TABLES` does not know
those tables. Verified empirically against the PRODUCTION db 2026-08-07:

    CLEARED   universes, universe_acl, founder_home, branches, author_*
    SURVIVES  app_principal_mappings (1)   <- founder<->Slack mapping
    SURVIVES  app_channel_bindings   (1)   <- channel -> u-tiny routing
    SURVIVES  agent_definitions (5), agent_bindings (5)
    SURVIVES  app_event_admissions   (9)   <- replay ledger
    SURVIVES  agent_component_lineage, agent_conversion_receipt*, agent_import_stages,
              agent_interchange_idempotency

Consequence: after a reset the universe and its admin ACL are gone, but Slack
still ROUTES to `u-tiny` and still holds a founder mapping naming a deleted
universe + dead binding. The next test round cannot "reteach it who it is" —
first contact never happens because routing resolves to a corpse.

Fix: extend `_RESET_TABLES` with the chat-surface tables, and decide
deliberately per table. Recommended: `app_channel_bindings` and
`app_principal_mappings` BOTH cleared, so first contact re-teaches identity from
scratch (that is the point of the round). `app_event_admissions` cleared too, or
stale event ids block replay. Custom-agent definitions/bindings are arguably
commons-like — decide explicitly rather than by omission.

Blocks: next testing round. Related: memory `s6-clean-slate-reset-authorized`,
STATUS row "R2-2 repeatable test identity" (files already name
`openspec/changes/test-identity-and-reset/`, `tinyassets/reset.py`).

## 2026-08-07 — LIVE: a build request overwrote the universe's identity

Reproduced in one Slack message. Asked Tiny to *build* an OpenClaw-style agent;
`extract_learning`/`commit_learning` overwrote `body.md` from "My body is the
repository at github.com/Jonnyton/TinyAssets" to "An OpenClaw-style autonomous
agent that can browse the web, write code, and run tasks on its own schedule."

A request to BUILD became a claim about WHAT IT IS. Replace, not merge. No
confirmation. The agent never chose it — `converse` had already returned and the
second-pass extractor filled the `body.md` slot of its hardcoded schema.

The SAME turn wrote `wiki/drafts/projects/openclaw-style-autonomous-agent.md`
correctly ("The founder intends to build..."). Canon path understood the intent;
soul path did not; the destructive one won silently. Recoverable only via
`soul_versions/0002.md` — nothing surfaces it to the user.

Requirements this puts on the rebuild (see also the `commit_learning` entry
above): the agent DECIDES its own writes and is told what was written; identity
files merge with provenance instead of replacing; an ambiguous self-description
change requires confirmation. Prompt-tuning the extractor is not the fix.

Host framing: OpenClaw/Hermes/Claude Code/Codex are HARNESS TEMPLATES for the
agent's project folder (what the instruction file is called, memory/skills
layout, conventions). Browse/code/schedule are BASELINE for every agent. The
universe dir IS the harness, and its layout is currently hardcoded to our OKF
startup-agent shape for every user.

## 2026-08-07 — HOST ACTION: the DM surface is dead, and DMs are how users actually talk

Host: "if they were intending to talk to it directly and work with it alone for
a while they wouldn't bother writing the @name over and over, they would just
message direct." The DM tab shows Slack's own refusal: **"Slack couldn't send
this message"** — the message never left the client.

Our side is READY, nothing to build:
- `slack_socket_mode.CONVERSATIONAL_EVENT_TYPES = {"app_mention", "message"}`
  already accepts DMs (a DM arrives as event type `message`).
- Workspace-scope channel binding already routes any channel in `T0BN5LK57FT`.

Evidence it has never worked: the agent has forwarded **7 `app_mention` events
and 0 of anything else, ever** (`docker logs tinyassets-slack-agent`).

Two toggles at api.slack.com/apps → Demo App (`A0BN1Q98MTQ`), host-only:
1. **App Home → Messages Tab** → enable "Allow users to send Slash commands and
   messages from the messages tab". Without it Slack rejects the send outright.
2. **Event Subscriptions → Subscribe to bot events** → add **`message.im`**. The
   bot holds the `im:history` SCOPE, but a scope is not a subscription — without
   this the DM is accepted and then never delivered to us.

Until both are set, every test has to be an `@mention` in a channel, which is
not how anyone works with their own agent.

## 2026-08-07 — A created agent needs its OWN Slack app, not a channel rebind

Host correction: "you would need to add them like you added demo app." Talking
to a created agent directly means addressing it BY ITS OWN NAME in Slack, which
means its own Slack app installed alongside Demo App — a second bot user.

What I built instead (`connect_agent_to_chat` → `chat_surface.bind_channel`)
re-points the EXISTING Demo App bot at a different agent binding. The founder
still types `@Demo App`; only the brain behind it changes. Worse, the agent bound
workspace-wide rather than to one channel, so Tiny became unreachable until I
rebound it. Useful primitive, wrong answer to this request.

**Good news — the routing table is already right.** `app_channel_bindings` keys
on `installation_id = f"{api_app_id}:{workspace_id}"`, so two apps in the SAME
workspace route independently with no schema change.

**What is actually missing:**
1. **Per-agent Slack app credentials.** A second app means a second bot token +
   app-level token deposited under a NEW connection id (`slack-openclaw`), not
   `slack-main`. `chat_surface.connect_account` does NOT do this — it maps an
   external ACCOUNT to a universe (the founder mapping).
2. **Multi-connection worker.** `slack_agent_worker` takes ONE
   `--connection` / `TINYASSETS_SLACK_CONNECTION` for all universes
   (`serve_all(universe_ids, connection)`), so it holds one socket per universe.
   Per-agent presence needs N sockets: a list of connections per universe.
3. **App creation itself is a human/OAuth step.** Creating a Slack app and
   installing it is not something the platform can do headlessly; the realistic
   shape is a connect-flow the founder completes, then deposits the tokens —
   the same custody question as `credential-vault-modular-architecture`.

Until 1 and 2 exist, "create an agent I can talk to" can only mean re-pointing
the one bot. Say that plainly rather than implying a second presence exists.

## 2026-08-07 — Self-modification chain: CORRECTED — compute enrollment is an env var, not missing code

**I claimed twice that requester-owned compute enrollment was "unbuilt platform
work" and that "nobody can create an automation, agent or human". Both wrong.**
`RequesterProviderEnrollmentResolver.from_environment()` reads
`TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` and returns an EMPTY resolver
when it is unset — so "requester-owned provider enrollment is unavailable" means
*this deployment has no enrollment document*, not *this feature does not exist*.

Proven locally end-to-end: with the document set, `bind_provider` returns
`status: provider_bound`, `state: active`, `binding_id: pwb_...`, and the
prerequisites message changes from "enroll requester-owned compute" to "bind one
enrolled requester-owned provider".

**The document shape, with the two traps that silently reject it.** The parser
`continue`s on any mismatch and logs nothing, so a wrong field looks identical to
no configuration at all:

- `credential_reference_digest` / `assignment_digest` must be
  **`sha256:<64 hex>`**. A bare hex digest is refused ("must be a canonical
  sha256 digest") and so is `v1:<hex>`.
- `expires_at` must be **`...Z`-suffixed or bare**, NEVER `+00:00`.
  `_not_expired` does `value.removesuffix("Z") + "+00:00"`, so a correctly
  formatted ISO-8601 offset becomes `+00:00+00:00`, fails to parse, and is
  treated as EXPIRED. A valid future date silently reads as stale.

All 12 keys in `_FIELDS` must be present exactly — no more, no less.

**What actually remains for the full chain:** `connection.connect` requires
WorkOS Pipes and a real WorkOS user (`cloud_connections` constructs
`WorkOSPipesClient`). On production it stops at "WorkOS user identity is
invalid" because the founder mapping names `u-tiny-operator`, a synthetic actor
created by hand on 2026-08-07. That one is genuinely external — re-provision the
mapping against the host's real WorkOS subject.

**To enable on production:** the daemon reads the env at call time, but
`docker restart` does NOT pick up a new `env_file` entry — the container must be
recreated. Given three deploy-caused outages on 2026-08-07, that is a host
decision, not something to do unilaterally.


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

- [2026-05-05] (source: host, owner: unassigned, status: capture, priority: uptime-loop, size: large) **Loop self-stewardship: trend manual checker intervention to zero.** Long-term target is users plus the loop, without Codex/Cowork manually brokering PR notes, ordering, refactors, or acceptance decisions. Every manual PR comment, requested change, merge-order correction, duplicate-lane catch, or checker-key refusal is a "medical attention" signal: the loop should learn to surface the same critique, revise the branch, reorder/supersede alternatives, and produce cleaner code before human/operator review. The loop has access to the same LLM families as the operators; the advantage should come from evolving state, review memory, lean context, tests, and explicit stewardship feedback. Next triage should convert this into measurable observability: manual-intervention ledger, intervention classes, loop self-correction rate, and promotion rules that turn repeated checker objections into substrate improvements rather than permanent operator labor.

- [2026-05-02] (source: host, owner: unassigned, status: capture, priority: uptime-loop, size: small) **Review open-source Claude Code / agent-team implementations for persistence lessons.** User flagged `https://github.com/SafeRL-Lab/nano-claude-code` (redirects to `SafeRL-Lab/cheetahclaws`), `https://github.com/SafeRL-Lab/cheetahclaws`, and `https://github.com/instructkr/claw-code` (redirects to `ultraworkers/claw-code`) as possible inspiration. Evaluate against Workflow's target advantages: 24/7 persistence without humans online, truthful daemon identity, connector-driven public loop, and multi-provider durable coordination.

- [2026-05-02] (source: host, owner: unassigned, status: promoted, priority: post-#18, size: medium) **Daemon mini OpenBrain per soul-bearing daemon.** Research Nate B. Jones / Open Brain and adapt the pattern so each daemon controls an atomic, searchable memory backend that works with its existing daemon wiki. Direction captured in `docs/design-notes/2026-05-02-daemon-mini-openbrain.md`: wiki stays the curated face; mini brain is daemon-scoped capture/search/review/promote storage; observable memory traces query/retrieve/inject/write/promote/compact; no one flat pool, no soul copying, no Supabase/OpenRouter dependency by default.
- [2026-05-01] (source: host, owner: unassigned, status: promoted, priority: uptime-loop, size: medium) **Patch-request incentives + requester-directed daemon work.** Users may attach optional incentives to patch/feature requests to make independent daemons more likely to pick them up earlier than other queued requests, but incentives must not influence whether a patch is accepted, released, or merged. Users may also direct their own daemons to work on a specific patch request to speed up their own iteration. This can produce faster proposals/evidence, not a landing guarantee. Promoted immediately to `PLAN.md` Multi-User Evolutionary Design and `STATUS.md` loop work because the live community patch loop is uptime-related.
  Links: `PLAN.md` Section Multi-User Evolutionary Design; `STATUS.md` Work row "Patch-request incentives + requester-directed daemon routing".

- [2026-04-27] (source: navigator-userim-review, owner: none, status: retired-community-composition, priority: post-uptime, size: medium) **`extensions action=my_recent_runs` + `goals action=my_recent` — user-scoped recency primitives.** Priya Session 2 (2026-04-20) signal #1: chatbot needs one tool call to answer "show me what I built recently" instead of fishing through `list_branches` + `query_runs` with author filter. Workspace-memory continuity gap — distinct from chatbot_assumes_workflow first-chat principle (this is N-th chat continuity).
  Resolution 2026-05-01: retired as platform primitives after freshness check. Use existing query-run plus optional goal/branch lookup composition; do not dispatch `_action_my_recent_*` code work.
  Triaged 2026-04-27; refreshed 2026-05-01: PIPELINE row "Recency primitives" records supersession by composition.
  Promoted 2026-04-27: pre-implementation contract now serves as supersession record in `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`.
  Historical fixture pack + implementation cards remain at `docs/specs/2026-04-27-recency-continue-fixture-pack.md` and `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`; do not treat the recency portions as pending engine work.
  Links: navigator's 2026-04-27 chain-break review (chat record); persona memory `priya_ramaswamy/`; `ideas/PIPELINE.md` "Recency primitives" row; `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`; `docs/specs/2026-04-27-recency-continue-fixture-pack.md`; `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md`.

- [2026-04-27] (source: navigator-userim-review, owner: dev post-#18, status: dev-ready-after-18, priority: post-uptime, size: medium) **`run_branch resume_from=<run_id>` — explicit "extend prior run" parameter.** Priya signal #6 + Devin Session 2 echoed. "Extend the sweep" / "continue branch" has no clean Workflow path — chatbot has to semantically infer "clone this branch, add nodes, re-run with extended inputs." Same root concern as INBOX 2026-04-24 entry but with concrete API shape proposal.
  Files (when scoped): `workflow/api/runs.py` (add `resume_from=<run_id>` to existing `run_branch`); tests.
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
  **Agent-teams-on-Workflow: open-source-Claude-Code-analog as a user
  project, backed by our primitives.**
  Host framing: the Claude Code system prompt leaked; a Python open-source
  analog is growing fast on GitHub and trending toward one of the fastest-
  growing repos. Opportunity — build "Claude Code agent teams" where each
  teammate is another Workflow node invoked via a daemon-request, and the
  teammates live in another branch of the workflow. **This is a USER
  project, not ours to build.** Our job is to make sure the primitives
  exist on the platform so the user's chatbot can compose this — daemon
  requests across branches, teammate roles as nodes, inter-teammate
  messaging via the paid-market / free-queue bid layer, per-teammate
  provenance + audit.
  Why this matters: validates the "daemon economy + convergent commons"
  thesis with a concrete, viral-shaped use case that isn't fantasy-
  authoring. If the OSS Claude-Code-analog audience can compose their
  agent teams on Workflow, the platform rides that wave.
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
  Triaged 2026-04-27: PIPELINE row "Agent-teams-on-Workflow" — research-note
  landed at `docs/notes/2026-04-20-agent-teams-on-workflow-research.md`
  (11-seam gap analysis, foundation/UX/commons rankings, nano-claude-code
  as recommended Python reference base — ~40K LoC, ~85 files, architectural
  seams map cleanly onto our primitives — claw-code now Rust-primary, less
  ideal base). Blocked on uptime-track close + daemon-economy first-draft.
  Scoping exercise opens after both unblock.
  Promoted 2026-04-27: post-unblock execution checklist landed at `docs/notes/2026-04-27-agent-teams-post-uptime-scoping-checklist.md` (entry gates + phase checks + escalation criteria).
  Links:
  - **`docs/notes/2026-04-20-agent-teams-on-workflow-research.md` —
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
  has no clean Workflow verb. "New branch" implies fresh scaffolding. "New run" implies same
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
  automatically. Workflow has no equivalent. User-sim rates it "cheap to add, high-value
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

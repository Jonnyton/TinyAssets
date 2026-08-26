# AVO versus the harness reset -- independent Codex research pass

**Date:** 2026-08-26  
**Initial provider:** Codex  
**Independent snapshot:** `harness-reset` at `bb47960e`, 26 commits over
`origin/main` at `8cbf9769`  
**Post-freeze comparison:** founder pass landed at `2cc32f01`, 27 commits over
the same base  
**Scope:** research and recommendations only; no product or harness changes  
**Independence:** I froze this report before reading the founder's parallel
`docs/audits/2026-08-26-avo-alignment.md`; the explicit comparison near the end
was added afterward.

## Bottom line

The reset removed a great deal, but the surviving harness still mistakes
documented procedure for useful control. AVO's load-bearing architecture is
smaller: an objective, an edit/evaluate loop, scored lineage, enough memory to
resume that loop, and a supervisor that intervenes when the **score trajectory**
stalls. TinyAssets has many gates and event logs, but its supervisor cannot see a
task objective or whether the task improved. Two of its three predicates are
therefore theatre.

The next pass should be deletion-led:

1. remove the 47,555-line in-repo recovery dump after extracting anything still
   unique;
2. archive most of the 67 OpenSpec changes and delete the umbrella target queues;
3. delete the retired fleet's `command_center/`;
4. remove retired one-off scripts and collapse overlapping operational CLIs;
5. cut the always-loaded set again, especially `CLAUDE.md`;
6. delete three hooks and two supervisor predicates.

Do **not** add an AVO-style memory database. The git history, specs, concerns,
PR/test evidence, and task artifacts already cover the durable information AVO
keeps. The missing part is not storage. It is a small, machine-readable outcome
attached to the work being supervised.

**Research verdict: Adapt.** Keep AVO's evaluated-feedback/supervision boundary,
but use TinyAssets' existing gates and git lineage. Reject a new memory system,
generic score, or orchestration layer.

## Sources and claim checks

### 1. NVIDIA AVO -- primary material

- [NVIDIA's AVO ARC-AGI-3 announcement](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/)
  verifies 100 RHAE on all 25 public environments / 183 public levels, using
  Claude Opus 5, with 6,624 environment actions. It reports VISTA at 7,542
  actions. The arithmetic is 12.17% fewer actions.
- [The AVO paper](https://arxiv.org/abs/2603.24517) and its
  [PDF](https://arxiv.org/pdf/2603.24517) verify the architecture in its original
  GPU-kernel setting: inspect/plan/edit/evaluate, compiler and profiler feedback,
  persistent conversation history, git candidate lineage with scores, and a
  supervisor that redirects stalled or unproductive search.
- [VISTA's public result and replays](https://vista-research.github.io/) verify
  its 183/183 and 7,542-action denominator.
- [ARC Prize's Claude Opus 5 result](https://arcprize.org/results/anthropic-claude-opus-5)
  verifies the 30.16% public baseline, but not a controlled AVO ablation.

What is verified:

- AVO's public-set result and the 6,624 action count.
- The approximately 12% action reduction relative to VISTA.
- The five relevant pieces: memory, tools, evaluation feedback, recovery through
  retained lineage, and trajectory supervision.
- In the kernel paper, AVO persists a candidate only after correctness checks and
  when its benchmark matches or improves the best known candidate; the commit is
  coupled to the score.

What is **not** verified:

- That AVO would score 100 on ARC-AGI-3's semi-private or private set.
- That the harness alone caused a 30-to-100 improvement. NVIDIA explicitly says
  the comparison is not a controlled ablation; backend, observations, memory,
  context management, and reasoning settings differ.
- A memory-only, supervisor-only, or tools-only AVO ablation on ARC-AGI-3.
- AVO's supervisor thresholds or implementation. The primary material names no
  equivalents of 3, 5, or 40.
- A public, reproducible AVO ARC harness implementation or action traces comparable
  to VISTA's replays.

One related result is useful but must not be relabelled AVO. NVIDIA's later
[NOOA harness article](https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/)
reports +11.8 RHAE for curated SQLite memory over file notes on ARC-AGI-3. Its
[paper](https://arxiv.org/abs/2607.20709) and
[repository](https://github.com/nvidia-nemo/labs-OO-Agents) describe a different,
typed object-oriented harness. That is evidence that memory design can matter in
that benchmark, not evidence that TinyAssets needs another memory store.

### 2. Anthropic -- primary engineering guidance

- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  says context is finite, recommends the smallest high-signal token set, calls
  ambiguous/overlapping tools an anti-pattern, and recommends external notes for
  long horizons.
- [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
  recommends clear tool boundaries, namespacing, high-signal outputs, and
  evaluation-driven tool design.
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
  says to start with the simplest solution and add complexity only when it
  demonstrably improves outcomes.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
  recommends incremental features, git commits, a progress artifact, and
  end-to-end verification.
- [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
  says every harness component encodes a model weakness and documents removing
  stale constructs as models improve.
- [Steering Claude with rules, skills, and hooks](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)
  distinguishes concise always-needed project facts, on-demand skills, and
  deterministic hooks for true always/never constraints.

These sources support cutting duplicated prose and overlapping tools. They do
not supply the numerical compliance claims discussed below.

### 3. Recent independent research

- [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988) studies 300
  SWE-bench Lite and 138 project tasks. LLM-generated context files changed
  success by -0.5% and -2% while adding roughly 20% and 23% cost. Human-written
  files averaged +2.4% success, not statistically significant, with up to 19%
  cost. The appendix reports **no clear relation between file length and either
  success or cost**.
- [Context files for coding agents](https://arxiv.org/abs/2607.27250) finds no
  measurable correctness effect from context strategy across 288 runs. It is a
  small study, so it supports restraint rather than a universal rule.
- [Harness-IF](https://arxiv.org/abs/2608.11727) reports instruction-following
  accuracy of 72.1--85.9%, and 66.1--78.6% when instructions conflict with model
  priors. It does not report 25--40% prose compliance or compare the same rule as
  a runtime hook.
- [Stop Means Stop](https://arxiv.org/abs/2607.14166) finds barrier/control
  semantics failing across six agent frameworks and shows that complete
  mediation can repair those failures. This is a warning that merely having a
  hook is not proof that every path is covered.
- [Catastrophic Remembering](https://arxiv.org/abs/2608.11095) reports prompt
  instruction accumulation across 1,867 repositories and improved compliance
  after adding rationale and deleting superseded rules. It is recent preprint
  evidence, not settled law, but it directly argues against `CLAUDE.md`'s
  continuous-accumulation instruction.

### The two disputed numbers

**“Beyond about 150 lines”: not verified.** I found the number repeated by
vendor and practitioner pages, but no primary experiment establishing a
150-line threshold. The strongest directly relevant primary study found no
clear length relationship. Use 150 as a review prompt if useful, not as a gate.

**“20--23% inference cost”: verified only for a different comparison.** The
ETH study measured the cost of adding LLM-generated repository context versus
no such file. It did not measure the marginal cost after line 150. Applying the
number to “AGENTS.md beyond 150 lines” is a category error.

**“25--40% prose versus about 95% hooks”: not verified.** I found no formal
source for either percentage. Anthropic says prompt rules can be missed and
hooks are deterministic; that supports the direction, not those numbers.
Harness-IF's measured instruction accuracy is materially higher than 25--40%.
A blocking hook with complete mediation should enforce its condition by
construction, while a warning hook has no compliance guarantee at all.

## Local architecture versus AVO

| AVO component | TinyAssets today | Judgment |
|---|---|---|
| Evaluation feedback | Tests, CI, canaries, rendered proof, deployment SHA | Strong evidence exists, but `supervisor.py` does not consume it. |
| Candidate lineage / recovery | Git, PRs, OpenSpec, concerns | Enough. A second lineage store would duplicate truth. |
| Persistent memory | Git, specs, concerns, activity log; no current `.claude/agent-memory/` directory | Enough durable state, weak retrieval. Do not add storage without a measured resume failure. |
| Tools | 97 current top-level Python scripts after four concurrent deletions; many are manual entrypoints, not exposed model tools | File count alone is not tool count, but the flat namespace has real overlaps and retired one-offs. |
| Supervisor | Repeated exit signature, repeated file edits, command count since commit | Only repeat failure resembles AVO recovery. The other predicates do not measure task progress. |
| Objective / score | No general task fitness supplied to supervisor | This is the decisive difference. AVO supervision is meaningful because it sees evaluated candidate progress. |

## CUT list -- ranked

### 1. Remove `docs/audits/harness-reset-preserved/`

**Current cost:** 65 files, 47,555 lines, 2.12 MB.

This is an in-repository recovery bundle containing duplicated source, tests,
plugin material, and orphaned worktree captures. It reverses the reset's search
and context hygiene even though it is not always loaded. It will pollute `rg`,
retrieval, audits, and future agents' judgments about canonical code.

Do not blindly delete unique user work. Extract or port the files named by its
manifest, preserve the raw bundle in a recovery branch or external artifact if
needed, and then delete the directory from this PR. Git is the recovery system;
the main tree should not be one.

### 2. Collapse `openspec/changes/` from 67 active changes to single digits

**Current cost:** 651 completed tasks, 1,000 remaining, 25 delivery-WIP changes,
43 oversized changes, and one complete-but-unarchived change.

Keep `openspec/specs/` as as-built behavioral truth. Cut the active queue. AVO
keeps one evaluated candidate lineage; it does not maintain 67 speculative
searches. Anthropic's long-running guidance likewise favors one incremental,
verified feature at a time.

Immediate actions:

- Archive `reconcile-stale-retired-fleet-artifacts` now; it is complete.
- Archive target-only umbrella queues rather than syncing them into as-built
  truth: `build-forward-platform-capabilities`,
  `complete-independent-full-platform-targets`,
  `complete-plan-gated-platform-targets`, `data-commons-contribution`,
  `demand-side-signals`, `harden-production-load-evidence`,
  `moderation-and-abuse-response`, `per-user-goal-canonicals`, and
  `retire-cheat-loop` unless one is explicitly selected as the current lane.
- Archive old zero-progress changes: `activate-hosted-preview-publication`
  (0/15), `demand-side-signals` (0/49),
  `harden-background-provider-execution-authority` (0/33),
  `authorize-app-replies` (0/6), `issue-app-custody-grants` (0/6), and
  `owner-operable-automation` (0/9). Re-proposal is cheap if demand returns.
- Merge `activate-custom-agent-runtime-core` and
  `activate-custom-agent-runtimes` into one owned lane.
- Merge the BYO family: `byo-llm-connect-flow`,
  `byo-llm-deposit-browser-form`, `byo-llm-deposit-surface`, and any overlapping
  `provision-http-connection-channel` work.
- Merge the outbound family: `channel-agnostic-outbound`,
  `outbound-boundary-layer`, `deliver-async-action-results`, and
  `stream-app-conversation-turns`.
- Merge the distributed execution family around one current slice:
  `distributed-execution`, `harden-background-branch-execution-authority`,
  `harden-background-provider-execution-authority`, and
  `execute-assigned-queue-consumer`.

The new AGENTS text says idle changes should be archived, then immediately
repeats “finish before starting” from the old delivery flow. Delete that
contradiction. “Finish or archive the selected lane; inactive changes do not
block new work” is sufficient.

### 3. Delete `command_center/` and its retired coordination surface

**Current cost:** 18 files, 4,324 physical lines, 273 KB, plus
`tests/command_center/`.

It is an Agent Village/fleet visualization and hiring surface in a repository
whose current rule says there is no standing team. No live product path calls
it. Delete:

- `command_center/`
- `tests/command_center/`
- the retired coordination requirements in
  `openspec/specs/development-coordination-runtime/spec.md`
- remaining Agent Village claims in `PLAN.md` and shipped-idea records where
  they incorrectly imply a live surface

If an operator view later earns demand, build it against the actual queue and
runtime. Do not preserve the old fleet's UI as an architectural promise.

### 4. Remove the permanent `retire_cheat_loop_*` program

These three top-level scripts account for roughly 11,000 lines:

- `scripts/retire_cheat_loop_github_state.py`
- `scripts/retire_cheat_loop_github_state_test.py`
- `scripts/retire_cheat_loop_deploy_fence.py`

There is also `tests/test_retire_cheat_loop_deploy_fence.py`. A retirement
campaign is a bounded migration, not a permanent general-purpose tool family.
Complete or abandon the associated OpenSpec change, retain only the enduring
deploy invariant in a normal gate, and delete the campaign machinery. At
minimum move it out of the flat tool namespace into the active change while it
is still running.

### 5. Cut the always-loaded set again -- by content, not a magic line count

The live branch is now `AGENTS.md` 255 lines / 14,767 bytes plus `CLAUDE.md`
115 lines / 6,429 bytes: 21,196 bytes combined. This passes the locally chosen
budget but remains repetitive.

Cut `AGENTS.md` to roughly 140--180 lines as an editorial target, not an
empirical threshold:

- Delete retirement history and measured-rationale narratives. Keep the current
  rule and link the audit.
- Replace the OpenSpec lifecycle and delivery sections with: hard-to-reverse
  changes use the skill before code; other changes sync as-built specs on land;
  inactive changes are archived.
- Move Quality Gate procedure back to its existing reference documents. Keep
  only the non-inferable risk boundary and final proof requirement.
- Move module-specific rules -- `SqliteSaver`, LanceDB, reducers,
  `FactWithContext`, plugin mirror, environment resolvers -- to scoped files or
  executable checks near the code they govern. They do not belong in every
  documentation or website task's context.
- Delete the Project Files catalogue and generic `pytest`/`ruff` advice. Keep
  only unusual traps not already enforced, such as the Windows temp-root ACL.
- Reverse “when in doubt, put it in AGENTS.md.” In doubt, do not add it; add only
  a cross-provider fact needed in most tasks and not cheaply discoverable.

Cut `CLAUDE.md` to 25--40 lines:

- Compress the 30-line background merge limitation to one fact, one consequence,
  and one workaround.
- Replace the 46-line Codex dispatch tutorial with a pointer to
  `.agents/skills/peer-agents/SKILL.md`.
- Delete duplicated session-start, verification, skills, memory, and site-loop
  prose.
- Delete `### Continuous Learning`. “After every significant learning, refine a
  prompt/rule/memory/skill” is the exact ratchet that recreates the 46,000 lines.
  Durable findings already have typed homes.

### 6. Reduce six hooks to two or three

Delete:

- `.claude/hooks/codex_dispatch_nudge.py` -- regex prompt injection duplicates
  AGENTS, CLAUDE, and the peer skill; it is advisory and keyword-triggered, not a
  deterministic safety gate.
- `.claude/hooks/latest_model_guard.py` -- it blocks a retired in-process Agent
  spawning path while current policy uses cross-family subprocess peers. If that
  path is still authorized, document the measured failure; otherwise remove it.
- `.claude/hooks/supervisor_resume.py` -- added by the parallel pass after this
  report was frozen. It cannot deliver its stated cross-session behavior: it
  filters to the current session ID, and its own test requires previous-session
  events to be excluded. At `SessionStart`, a fresh session has no current-session
  events to surface. It is therefore normally silent by construction.

Keep `.claude/hooks/session_sync_gate_hook.py`: it caught a measured
825-commit-stale checkout.

For `.claude/hooks/supervisor_record.py` and `supervisor_check.py`, keep them
only if `scripts/supervisor.py` is reduced as described next. Otherwise delete
all three and their tests rather than preserving a supervisor in name only.

### 7. Cut two of the supervisor's three predicates

- Keep a smaller `repeat_failure` detector only if it triggers an actionable
  recovery instruction. Three repeats is locally traceable to the repository's
  “stuck 3+ iterations” rule, but it is not supported by AVO research.
- Delete `edit_thrash`. Five edits to one file may be entirely productive; no
  outcome signal distinguishes that case.
- Delete `no_landing`. Forty commands without a commit is normal for research,
  review, diagnosis, and many safe work units. A commit can also contain no
  improvement. AVO commits evaluated candidates; TinyAssets merely counts
  commands since any commit.

Also fix or delete the recorder's stderr-based exit inference: a successful
command that writes a warning to stderr can currently be recorded as failure.

Threshold verdict: **3 is a local convention, not research-defensible; 5 and 40
are arbitrary.** There is no supervisor state or firing history in this
checkout, so there is no local efficacy evidence for any threshold. The 21
supervisor unit tests prove implementation consistency, not usefulness.

### 8. Collapse overlapping script families

The branch began this pass with 101 top-level Python scripts. A concurrent commit
deleted four sound targets -- `checkpoint_retention.py`, `claude_chat_read.py`,
`migrate_fix_e_cleanup.py`, and `timestamp_lint_run.py` -- leaving 97. Continue.

**Peer dispatch:** move the two still-used path-resolution helpers from
`scripts/codex_review.py` into `scripts/peer_agent.py`, migrate callers, and
delete `codex_review.py`. One cross-family dispatcher is enough.

**MCP canaries:** `_canary_common.py`, `mcp_public_canary.py`, `mcp_probe.py`,
`mcp_tool_canary.py`, `uptime_canary.py`, and `selfhost_smoke.py` independently
implement overlapping session, transport, initialization, and tool-list logic.
Keep one MCP client module and one CLI with `public`, `tool`, `probe`, and
`selfhost` subcommands. Delete migrated wrappers. Keep
`uptime_canary_layer2.py` separate because real browser proof is a different
surface, but move it under `scripts/canaries/` and name it accordingly.

**Dead/retired wrappers:** delete `scripts/always_allow_watch.py`; its own
docstring says the detector was folded into `claude_chat.py`. Delete
`scripts/navigator_wiki_sweep.py`; its standing-navigator cadence belongs to the
retired fleet.

**One-time migrations:** after verifying their effects are present, delete or
move out of the flat namespace:

- `scripts/migrate_canon.py`
- `scripts/migrate_design_008_selector_backfill.py`
- `scripts/migrate_secrets_to_vault.py`
- `scripts/rebuild_sporemarch_kg.py`

Git preserves completed migrations. If one must remain runnable for old
installations, put it in a versioned `scripts/migrations/` namespace with an
explicit supported-version boundary.

**Decorative checks:** `scripts/check_plan_drift.py`,
`check_background_authority_inventory.py`, and
`pre_commit_invariant_author_server.py` have tests or assertions but no current
hook/workflow/invariant wiring. A check that does not run is documentation with
an exit code. Wire it to a measured gate or delete it; the default is delete.

**Slack operations:** combine `deposit_slack_credentials.py`,
`run_slack_agent.py`, and `slack_live_test.py` behind one `slack_ops.py` CLI or
move them under a clearly named `scripts/ops/slack/` namespace. They are valid
manual operations, but the current names make selection ambiguous.

**Infra operations:** group `cf_access_cutover.py`, `cf_access_rollback.py`,
`site_apex_cutover.py`, and `emergency_dns_flip.py` behind the `infra-ops` skill
and a fail-closed namespaced CLI. Do not erase their distinct safeguards; erase
the flat, overlapping discovery surface.

This is not an argument that 97 files means 97 model tools. Most are not exposed
as MCP handles. The problem is that AGENTS, skills, and operators present a flat
script directory as a toolbox, and several families require reading code to know
which entrypoint is canonical.

### 9. Reduce ten skills to seven, then shorten the survivors

Delete or fold:

- `.agents/skills/security-and-hardening/` -- generic secure-coding guidance a
  current model can infer; project-specific authority gates belong in specs and
  executable checks.
- `.agents/skills/browser-testing-with-devtools/` -- generic browser mechanics
  overlap `website-editing` and `ui-test`; fold the few project-specific setup
  facts into those skills.
- `.agents/skills/implementation-precedent-scout/` -- external repository
  precedent is a mode of `external-research-implications`, not a distinct
  project capability.

Then shorten:

- `external-research-implications` currently forces a durable audit, pickup
  packet, context feeds, and worktree landing packet even for a read-only answer.
  Keep source hierarchy and opposite-family implementation review; make the rest
  conditional on an authorized build.
- `ui-test` is 353 lines. Keep the real-chatbot/no-bypass invariant and move
  provider-specific browser recipes to references.

Mirror the canonical deletions into `.claude/skills/`; do not leave provider
copies as a second source.

### 10. Stop treating `.agents/activity.log` as memory

It is currently 483,933 bytes of session narrative and is not surfaced as useful
task outcome memory by the claim feed. Rotate or archive the existing history,
stop appending generic events, and retain only short cross-session facts that do
not already live in a concern, change, PR, or commit. Do not replace it with a
database.

### 11. Correct the causal AVO claim in `PLAN.md`

The current harness architecture language says, in effect, that harness changes
alone raised the same model from 30% to 100%. NVIDIA's primary source expressly
disclaims that controlled inference. With founder approval, rewrite it as:
AVO achieved 100 on the public set in a different full system; its architecture
is relevant precedent, while component causality is unmeasured.

This is a correction, not a new principle.

## ADD list -- one conditional change, no new subsystem

### 1. If the supervisor survives, attach one existing evaluation outcome

**AVO components:** evaluation feedback + supervisor.  
**Measured failure prevented:** warning about “stagnation” when work is actually
progressing, or missing stagnation because an empty commit reset a counter.

Replace command-count-as-progress with a compact receipt already produced by the
work's real gate: evaluation/test name, pass/fail or scalar score where one
exists, candidate commit, and next action. The supervisor may intervene only
when comparable evaluations fail to improve or the same failure repeats.

Do not invent a universal score, event database, or outcome journal. Many tasks
have binary gates; research tasks may have no comparable sequence. If the
existing gates cannot supply a meaningful outcome, the supervisor should stay
off for that task.

No other addition clears the bar. In particular:

- no AVO memory database;
- no more hooks to compensate for long prose;
- no tool registry over the script registry;
- no new orchestration layer over OpenSpec;
- no replacement for `command_center/`.

## Where the founder's read is wrong

1. **The 150-line threshold is not established research.** Cutting toward it is
   reasonable because the remaining prose duplicates skills, references, and
   checks -- not because line 151 causes a measured cliff.
2. **The 20--23% number is real but attached to the wrong independent variable.**
   It compares generated context files with no context file, not long with short
   `AGENTS.md` files.
3. **The 25--40% / 95% compliance split is unsupported.** The direction is
   sensible; the precision is not. A warning hook is not enforcement, and even
   blocking framework controls can miss paths without complete mediation.
4. **There are no longer 101 scripts on the live branch.** Four were deleted in
   `bb47960e` during this pass, leaving 97 top-level Python scripts. The original
   101 count was correct at the start.
5. **The current `AGENTS.md` is no longer 316 lines.** It is 255 lines and 14,767
   bytes at `bb47960e`; the always-loaded pair is 21,196 bytes. The outcome audit
   and request describe an earlier commit.
6. **`command_center/` is larger than 2,330 lines under a physical-line count.**
   The current tree contains 4,324 lines across 18 files. The exact metric does
   not change the deletion verdict.
7. **AVO's “persistent memory” is not evidence for a new TinyAssets store.** In
   the paper it is mainly conversation history plus evaluated git lineage and
   tool feedback. TinyAssets already has more durable stores than AVO describes;
   it lacks outcome-centered retrieval.
8. **The local supervisor is not an AVO-like supervisor yet.** Matching the nouns
   “memory” and “supervisor” is not architectural equivalence. AVO supervises
   search fitness; TinyAssets supervises edit and command counts.
9. **NVIDIA's public result is impressive but not an independent causal proof.**
   It is NVIDIA's own public-set report, with no component ablation and no claim
   about hidden ARC sets. VISTA publishes replays; the AVO ARC harness is not yet
   comparably reproducible.
10. **The script count is not the model's exposed tool count.** Anthropic's tool
    ambiguity warning applies directly only where an agent or operator must
    choose among these entrypoints. The concrete overlapping families above are
    the evidence; “101 files” alone is not.

## Post-freeze comparison with the founder pass at `2cc32f01`

The independent passes agree on one important point: **do not build a new memory
store**. They disagree on whether the existing supervisor event log is useful
AVO memory. It is not.

The new pass adds `.claude/hooks/supervisor_resume.py`, 84 lines to
`scripts/supervisor.py`, and 67 lines of tests. Cut that delta.

Why:

1. `resume()` filters events to `session_id()`. A fresh session has a new ID.
   `test_resume_is_session_scoped` explicitly asserts that another session's
   dead ends are invisible. The implementation therefore contradicts the audit's
   claim that a fresh session learns what the last session tried.
2. The hook runs at `SessionStart`, before the new session has recorded edits or
   commands. Its “silent in the common case” behavior is effectively “silent for
   every fresh session.” It can only help a harness continuation that preserves
   the same session ID.
3. The event log is pruned after 24 hours and reset after any commit. AVO's
   load-bearing memory survives long enough to guide a multi-day evaluated
   search; this view deliberately discards that history.
4. Exit codes and edit counts are not prior implementations, evaluation results,
   or accumulated reasoning. The renderer does not even show successful commands.
   It shows failed command strings and files touched.
5. The cited local measurements -- fast PR merges and 23-day-idle OpenSpec work --
   do not measure sessions repeating failed attempts. They establish queue debt,
   not a memory failure. The addition clears the “names an AVO component” half of
   the founder's bar but not the “implements that component or prevents a measured
   failure” half.
6. The hook catches all exceptions and exits silently, so a broken memory view is
   indistinguishable from an empty one. That conflicts with this repository's
   fail-loudly principle and makes efficacy unobservable.

The parallel audit also repeats two claims the primary material does not support:

- “30% to 100% on harness changes alone” -- NVIDIA explicitly says this is not a
  controlled ablation;
- “Supervisor: aligned” -- counting commits and edits without an evaluated
  objective is not AVO trajectory supervision.

It also says the post-reset harness has five hooks while its own implementation
adds the sixth.

If a future measured resume failure justifies another attempt, key it to an
explicit branch/work item and retain compact evaluation receipts, not raw session
identity. That is the conditional ADD already described above. Until then: cut.

## Verification and implementation gate

Independent-snapshot checks run 2026-08-26 in the Windows `harness-reset`
worktree at `bb47960e`:

- `git rev-list --count origin/main..HEAD` -> 26
- `python scripts/check_context_budget.py --json` -> 255-line `AGENTS.md`,
  115-line `CLAUDE.md`, 21,196 combined bytes, current local budgets green
- `python scripts/openspec_flow.py audit` -> 67 active, 651 complete / 1,000
  remaining, 25 delivery WIP, 43 oversized
- filesystem inventory -> 97 top-level Python scripts, 10 canonical skills, 5
  Claude hooks, 47,555 lines in the preserved recovery directory
- `python -m pytest tests/test_supervisor.py -q` -> 21 passed; this validates
  behavior against current thresholds, not threshold efficacy

Post-freeze comparison at `2cc32f01`:

- `git rev-list --count origin/main..HEAD` -> 27
- `.claude/hooks/` -> 6 hooks after `supervisor_resume.py` was added
- the new tests verify same-session rendering and explicitly exclude prior
  sessions; they do not prove cross-session resume

This artifact recommends only. Research-derived implementation requires an
opposite-family source/context review before build or rollout.

### Conditional pickup packet -- not build authority

- **Source / research artifact:** this file; primary URLs above
- **Review artifact:** not yet created
- **Initial / review provider:** Codex / Claude
- **Review status:** pending; gates implementation
- **Worktree / branch:** `C:\Users\Jonathan\Projects\wf-harness-reset` /
  `harness-reset`
- **First scoped change if adopted:** extract any unique user work from
  `docs/audits/harness-reset-preserved/`, preserve it outside the main tree as
  needed, then delete the in-repo recovery bundle
- **Requirements / docs / migration:** update its manifest and any canonical
  pointers; no product spec or data migration
- **Tests / ship condition:** prove every unique file has an explicit disposition,
  `rg` finds no canonical dependency on the bundle, and repository gates remain
  green
- **Abandon condition:** any file is recoverable only from this checkout and no
  safe external recovery location is available
- **Deployed state:** not applicable; repository hygiene only
- **Next action:** founder compares the independent passes and explicitly selects
  a cut; then Claude re-checks the selected sources and current tree before edits

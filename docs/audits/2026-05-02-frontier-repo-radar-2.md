# Frontier Repo Radar 2: AgencyBench

Freshness stamp: 2026-05-02. Initial provider: Codex.

This scan used current web research, GitHub API metadata, and a read-only
shallow clone into `%TEMP%\workflow-research-agencybench` at commit
`ec65324be69e81bd4fe394ef6a86d48b8fa5da56`.

## Executive Judgment

The next repo with the strongest Workflow implication is:

**GAIR-NLP/AgencyBench** - https://github.com/GAIR-NLP/AgencyBench

Paper: **AgencyBench: Benchmarking the Frontiers of Autonomous Agents in
1M-Token Real-World Contexts** - https://arxiv.org/abs/2601.11044

Why this matters: Workflow cannot be a living, community-evolvable system
unless improvements are judged in conditions that look like real user work.
AgencyBench is not just another benchmark table. Its useful primitive is a
long-horizon acceptance scenario: user-like iterative feedback, many tool
calls, rubric-scored deliverables, visual artifacts, and task outputs persisted
as reviewable evidence.

For Workflow, the implication is:

> Optimization and branch evolution need reusable acceptance scenarios, not
> only unit tests, one-shot evaluator scores, or manual Claude.ai checks.

## Source Freshness

| Source | Evidence |
|---|---|
| GitHub repo | `GAIR-NLP/AgencyBench`, MIT, Python, latest API commit `ec65324be69e81bd4fe394ef6a86d48b8fa5da56`, pushed 2026-01-23 |
| arXiv paper | `arXiv:2601.11044`, submitted 2026-01-16, describes 32 scenarios, 138 tasks, 1M-token contexts, user simulation, Docker sandbox, visual/functional rubric assessment |
| Local clone | Commit `ec65324be69e81bd4fe394ef6a86d48b8fa5da56`, top-level `AgencyBench-v1`, `AgencyBench-v2`, `README.md`, `AgencyBench.pdf` |

Candidate comparison:

| Candidate | Why considered | Decision |
|---|---|---|
| `GAIR-NLP/AgencyBench` | Long-horizon real-work agent evaluation, user simulation, Docker visual sandbox, MCP scenarios | **Choose** |
| `MemTensor/MemRL` | Runtime RL over episodic memory; strong fit for ExperiencePool utility scoring | Watch as companion to GEA review |
| `matrixorigin/Memoria` | Git-like memory branching/rollback, MCP-compatible memory layer | Watch; overlaps Workflow's native branch/version primitives |
| `EverMind-AI/EverOS` | Self-organizing long-horizon memory OS with Claude Code plugin | Watch; useful memory-system comparator |
| `agiresearch/AIOS` | Agent OS kernel, scheduling, MCP server and VM controller | Watch; broader runtime architecture, less immediate than eval proof |

## Outside-System Map

Entrypoints:

- Each `AgencyBench-v2/<domain>/scenario*/eval_task.py` is a scenario runner.
- Each scenario has a `description.json` containing subtasks, deliverables, and
  rubric requirements.
- The README describes six domains: Backend, Code, Frontend, Game, MCP, and
  Research.

Execution loop:

- Load `.env` for target model, scaffold, evaluator credentials, sandbox URL,
  and attempt limits.
- Keep an agent session alive across subtasks.
- Ask the candidate agent to complete one subtask at a time.
- After each attempt, verify artifacts and feed failures back into the agent
  until pass or attempt limit.
- Persist final metadata into a model-named `meta_eval.json`.

Evaluation:

- Text checks validate structured deliverables and rubric compliance.
- UI/game scenarios use browser automation, screenshots, videos, and visual
  scoring.
- MCP scenarios verify external side effects such as issue, branch, file, label,
  comment, and pull-request state through APIs.
- Results are evidence-rich: traces, screenshots, videos, DOM snapshots,
  workspaces, and score rationales.

Storage and artifacts:

- Scenario folders include `description.json`, `eval_task.py`, `.env`, and
  reference `claude/meta_eval.json`.
- Runs create per-model workspaces and final metadata artifacts.
- Artifacts are evaluation payloads, not just pass/fail booleans.

Safety and operations:

- Frontend/game scenarios depend on a Docker sandbox image.
- GitHub/MCP scenarios depend on real credentials and external API state.
- The README's Docker example uses `--security-opt seccomp=unconfined`; that is
  a caution flag for Workflow, not a pattern to copy blindly.

## Workflow Comparison

Workflow already has stronger primitives in some places:

- `EvalResult` now has evidence, artifacts, cost, freshness, and evaluator IDs.
- `ui-test` already treats live Claude.ai behavior as final public MCP proof.
- Public-surface canaries and production evidence are required for live changes.
- Branch definitions, runs, versions, and lineage are native primitives.

Workflow gaps AgencyBench exposes:

- No reusable `AcceptanceScenario` contract for long-horizon user-like tests.
- No common schema that binds user simulation, rubric, artifact capture, and
  branch/run outcome into one portable evaluator package.
- No first-class way for a branch optimizer to say: "candidate must pass these
  scenario packs before merge."
- Public-surface verification is strong but mostly bespoke per change; it is
  not yet a remixable scenario library that the community can extend.

## Implications

### Adopt: Acceptance Scenario Packs

Add a Workflow-native concept for scenario packs:

```text
AcceptanceScenario
  scenario_id
  target_surface
  user_story
  setup
  allowed_tools
  evaluator_chain
  artifact_requirements
  pass_threshold
  privacy_scope
  cost_budget
```

This should compile into existing evaluators and `EvalResult` artifacts, not a
new sidecar runner.

### Adapt: User Simulation As Evaluator Input

AgencyBench uses user simulation to replace expensive human-in-the-loop
feedback. Workflow should adapt this as a daemon-owned evaluator mode:

- simulated user role,
- expected conversation/workflow path,
- allowed clarifications,
- rubric-backed acceptance checks,
- artifact capture,
- typed `EvalResult` evidence.

The user still steers through MCP chat. The simulated user exists to test a
branch before real users pay the cost.

### Adapt: Visual And Functional Artifact Bundles

AgencyBench's strongest practical move is keeping screenshots, videos, DOM
state, API state, and text scores together. Workflow should treat these as
first-class evaluator artifacts attached to a run, branch, or candidate.

### Avoid: Copying The Harness

Do not import AgencyBench wholesale. Do not depend on its SII Agent SDK, its
scenario folder layout, or `seccomp=unconfined` Docker default. Workflow needs
its own scenario contracts, host-pool execution, privacy boundaries, and
provenance.

### Defer: Full Benchmark Compatibility

Running AgencyBench itself is not the first slice. The first slice is a small
Workflow-native scenario contract that can express one MCP or UI acceptance
case and emit `EvalResult` artifacts.

## Integration Roadmap

Slice 1: Review and design only.

- Claude independently reviews this finding.
- If approved, create a design note for `AcceptanceScenario`.

Slice 2: Minimal scenario schema.

- Define `AcceptanceScenario`, `ScenarioStep`, `ScenarioArtifact`, and
  `ScenarioVerdict`.
- Map the verdict to existing `EvalResult`.

Slice 3: One MCP acceptance scenario.

- Encode a small scenario for a real Workflow MCP user action.
- Store trace evidence in `output/`.
- Emit a structured `EvalResult`.

Slice 4: Branch optimization gate.

- Let an `OptimizationRun` require one or more scenario packs before merge.
- Candidate branches must keep evaluator harness files locked.

Slice 5: Community scenario library.

- Let users publish/remix scenario packs with attribution and visibility policy.
- Public scenarios become commons; private scenario data stays private.

## Cross-Provider Review Gate

Codex made the initial finding. Claude must independently research/review
AgencyBench before implementation, git push, live rollout, or acceptance testing
based on this finding.

Required review artifact:

`docs/audits/2026-05-02-agencybench-claude-review.md`

Review verdict must be one of:

- `approve`
- `adapt`
- `defer`
- `reject`

The review must re-check primary sources, inspect Workflow's current evaluator
and UI/public-surface proof rules, and decide whether `AcceptanceScenario` is
the right Workflow-native shape.

## Pickup Packet

Concept: Acceptance Scenario Packs.

Initial provider: Codex.

Required reviewer: Claude.

Applies when touching:

- `workflow/evaluation/*`
- `workflow/api/runs.py`
- `workflow/api/branches.py`
- `ui-test`
- public MCP acceptance proof
- branch optimization or merge gates
- frontend/game/browser verification
- host-pool sandbox execution

Shared queues:

- `STATUS.md` Work row: "Claude review gate: AgencyBench acceptance scenario
  finding".
- `ideas/PIPELINE.md` Active Promotion: "Acceptance Scenario Packs
  (AgencyBench radar)".

Next artifact:

`docs/audits/2026-05-02-agencybench-claude-review.md`

Post-review build files, only if review approves:

- `docs/design-notes/2026-05-02-acceptance-scenario-packs.md`
- `docs/specs/2026-05-02-acceptance-scenario-minimal-schema.md`

Exit check:

- Claude review exists and is linked from `STATUS.md`.
- Design note/spec defines how scenario packs compile into `EvalResult`.
- No AgencyBench code is vendored.
- First implementation uses one small Workflow MCP or UI scenario.

## Worktree Landing Packet

The host approved the direction on 2026-05-02, but build advancement is still
blocked on the Claude review gate because Codex made the initial finding. The
implementation lane should still be visible in git/worktree coordination now:
it may be created or reserved before review, but must not advance beyond
blocked handoff metadata until the review returns `approve` or `adapt`.

Review handoff:

- Proposed branch: `claude/agencybench-review`
- Proposed worktree: `../wf-agencybench-review`
- Base/dependency: current main with this radar artifact and the host-approved
  PLAN note available
- Files: `docs/audits/2026-05-02-agencybench-claude-review.md`
- First slice: independent source re-check plus verdict
  (`approve`, `adapt`, `defer`, or `reject`)
- Verification: review cites AgencyBench primary repo/paper and current
  Workflow evaluation, ui-test, public-surface proof, and sandbox context
- Fold-back: merge review artifact, update `STATUS.md` / `ideas/PIPELINE.md`,
  then create or revise the implementation row

Review-blocked implementation handoff:

- Proposed branch: `claude/acceptance-scenario-packs` or
  `codex/acceptance-scenario-packs`
- Proposed worktree: `../wf-acceptance-scenario-packs`
- Base/dependency:
  `docs/audits/2026-05-02-agencybench-claude-review.md`
- STATUS dependency: review artifact verdict is `approve` or `adapt`
- Initial write-set:
  `docs/design-notes/2026-05-02-acceptance-scenario-packs.md`,
  `docs/specs/2026-05-02-acceptance-scenario-minimal-schema.md`
- First implementation slice after review: design/spec only; no AgencyBench
  vendoring and no runtime scenario executor
- Verification: doc/spec diff check, schema examples compile mentally against
  `EvalResult`, and no public-surface acceptance claim without `ui-test`
- Fold-back: PR to main, retire the review row, and add the next concrete
  implementation row with exact runtime/test files

## Skill Iteration

This pass adds a durable skill rule: when the user asks for another or next
frontier repo, the radar must check existing promoted reports and avoid
returning the same concept unless the new repo changes the implementation path.

# Frontier Project Radar

Freshness stamp: 2026-05-02. Initial provider: Codex. This scan used current
web research plus GitHub API metadata gathered on 2026-05-02. It extends
`external-research-implications` with frontier-radar mode.

## Executive Judgment

The most important frontier project for Workflow right now is:

**Group-Evolving Agents: Open-Ended Self-Improvement via Experience Sharing**
(`arXiv:2602.04837`).

Reason: it shifts the unit of evolution from an isolated agent or isolated
branch to a **group with a shared experience pool**. That is the paradigm
Workflow should align with early. Workflow is already trying to become a
community-evolvable ecology of branches, nodes, evaluators, daemons, goals,
outcomes, and MCP users. GEA is the cleanest current research signal that this
is not just product taste; it is likely the stronger architecture.

The immediate implementation companion is **EvoSkill**:
`https://github.com/sentient-agi/EvoSkill`. EvoSkill is narrower than GEA, but
it shows a practical SkillOps loop: mine failures, propose skills, materialize
skill folders, evaluate held-out performance, and keep a Pareto frontier.

So the frontier bet is:

> Workflow should evolve groups of branches/skills/evaluators through shared
> typed experience pools, not only evolve one node, one prompt, or one agent at
> a time.

## Sources

- Group-Evolving Agents: https://arxiv.org/abs/2602.04837
- EvoSkill paper: https://arxiv.org/abs/2603.02766
- EvoSkill repo: https://github.com/sentient-agi/EvoSkill
- EvoAgentX repo: https://github.com/EvoAgentX/EvoAgentX
- EvoAgentX paper: https://arxiv.org/abs/2507.03616
- Darwin Godel Machine blog: https://sakana.ai/dgm/
- Darwin Godel Machine repo: https://github.com/jennyzzt/dgm
- Agentic Evolution position paper / A-Evolve: https://arxiv.org/abs/2602.00359
- EvoMaster paper: https://arxiv.org/abs/2604.17406

## Candidate Radar

| Candidate | Signal | Why It Matters | Workflow Judgment |
|---|---|---|---|
| Group-Evolving Agents | Treats a group of agents as the evolutionary unit; reports 71.0% vs 56.7% on SWE-bench Verified and 88.3% vs 68.3% on Polyglot against self-evolving methods. | Directly attacks isolated-branch waste. Shared experience converts early diversity into sustained progress. | **Top frontier bet.** Adopt the group/experience-pool primitive. |
| EvoSkill | Open-source skill discovery from failed trajectories; current GitHub metadata: Apache-2.0, Python, 656 stars, pushed 2026-05-01. | Directly maps to our `.agents/skills` and this session's self-iteration. | **Immediate implementation reference.** Adapt SkillOps loop; do not copy branch-control model blindly. |
| EvoAgentX | Open-source evolving agentic workflows; current metadata: Python, 2925 stars, pushed 2026-04-30. | Shows layered workflow/evaluation/evolution architecture. | Useful reference, but less decisive than GEA because Workflow already has richer branch/MCP/community primitives. |
| Darwin Godel Machine | Official Sakana work; code at `jennyzzt/dgm`, Apache-2.0, 2010 stars, last pushed 2025-08-13. | Shows self-modifying agent archives and open-ended stepping stones. | Important ancestor; less aligned than GEA because it is still mainly tree/archive evolution of coding agents. |
| A-Evolve | Position paper says deployment-time improvement should be goal-directed optimization over persistent state; repo active. | Strong conceptual support for agentic evolution. | Watch/adapt. Less concrete for Workflow than GEA + EvoSkill. |
| EvoMaster | 2026 agentic science framework; Apache-2.0 repo active. | Domain-agnostic evolving science agents. | Watch for scientific-domain patterns; not the main platform primitive. |

## Why GEA Beats The Runners-Up

### 1. It Matches Workflow's Community Shape

Workflow's product is not one agent improving itself in a lab. It is a public
engine where many users and daemons create, remix, evaluate, and evolve many
branches under shared goals.

DGM asks: "How does one agent lineage improve?"
GEA asks: "How does a group convert diversity into sustained progress?"

Workflow needs the second question.

### 2. It Fixes The Weakness In Tree Evolution

Our ASI-Evolve analysis already pointed toward quality-diversity search and
preserving rejected candidates. GEA sharpens that: isolated tree branches waste
diversity because lessons remain trapped in branches. The next primitive is a
shared typed experience pool that lets one branch's failure become another
branch's stepping stone.

### 3. It Is The More Likely Industry Landing Point

The industry is moving from:

```text
single prompt -> single agent -> agent workflow -> self-evolving agent ->
group-evolving agent/workflow ecosystem
```

The last step is where Workflow's architecture already points. Over the next
6-36 months, strong platforms will likely stop treating agent runs as isolated
events and start treating production failures, traces, skills, evaluations, and
workflow topology as reusable evolutionary material.

### 4. It Makes Users More Powerful

GEA-style Workflow means users can say through any MCP chatbot:

- "Fork these three approaches and let them share lessons."
- "Evolve this goal's evaluator pool from the last 50 failed runs."
- "Show me which branch family discovered the useful pattern."
- "Apply the lesson from the invoice workflow to contract review, but do not
  expose private evidence."

That is a stronger user surface than "run optimizer on this prompt."

## What To Adopt

### Adopt: Experience Pools

Create a native concept for reusable, typed experience across candidate runs:

```text
ExperiencePool
  goal_id
  branch_family_ids
  visibility_policy
  lesson_refs
  candidate_refs
  evaluator_result_refs
  failure_modes
  reusable_skills
  outcome_refs
```

This sits above individual optimization runs. It is the shared substrate that
lets branches cross-pollinate.

### Adopt: Group Evolution Runs

Add a future run type:

```text
GroupEvolutionRun
  goal_id
  parent_branch_refs[]
  experience_pool_ref
  evaluator_chain_ref
  diversity_policy
  budget
  merge_policy
```

This should be MCP-facing but simple for users. The chatbot can translate:
"try a few approaches and let them learn from each other."

### Adopt: SkillOps From Failures

EvoSkill's strongest immediate lesson:

1. collect failed trajectories;
2. cluster failure modes;
3. propose skill edits or new skills;
4. evaluate on held-out tasks;
5. keep only variants that improve;
6. materialize skills as auditable folders.

Workflow already has `.agents/skills`, mirrors, validation, and this new skill.
The missing piece is held-out evaluation before skill changes become canonical.

## What To Adapt

### Adapt GEA To Community Branches

GEA is framed around coding agents. Workflow should adapt the group unit to:

- branch families under one Goal;
- evaluator chains;
- domain skills;
- MCP tool behavior;
- daemon policies;
- memory/retrieval strategies;
- public node libraries.

### Adapt EvoSkill To Cross-Provider Skills

EvoSkill writes `.claude/skills`. Workflow's canonical source is
`.agents/skills` mirrored into `.claude/skills`. Any SkillOps loop must write
canonical `.agents/skills` first and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1
python scripts/validate_skills.py
python scripts/check_cross_provider_drift.py
git diff --check -- .agents/skills .claude/skills
```

### Adapt Frontier Selection Into This Skill

The skill now has frontier-radar mode. Future scans should not merely pick the
newest paper. They should ask which project changes the design unit, which
implementation gravity is likely to pull the industry, and what Workflow-native
primitive we can build before that consensus is obvious.

## What To Avoid

- Do not build a separate local-only self-evolution harness.
- Do not optimize skills or branches against one fixed validation set without
  holdouts or rolling validation.
- Do not let private failures become public reusable lessons without per-piece
  privacy review.
- Do not copy EvoSkill's `.claude`-first layout; Workflow is cross-provider.
- Do not copy DGM's isolated coding-agent focus as the platform shape.
- Do not conflate benchmark progress with real-world outcome progress.

## Workflow Integration Plan

### Slice 1: Experience Lesson Schema

Build on the `EvalResult` evidence/artifact contract already started.

Add a typed lesson shape:

```text
ExperienceLesson
  source_run_id
  source_candidate_id
  goal_id
  branch_id
  lesson_kind
  failure_mode
  intervention
  observed_delta
  evidence_refs
  visibility
  confidence
```

This is the atom of group evolution.

### Slice 2: Experience Pool Read Model

Before adding writes, expose a read-only aggregation over existing artifacts:

- failed runs,
- evaluator results,
- process artifacts,
- rollback notes,
- skill edits,
- outcome claims.

Goal: let an MCP user ask "what has this branch family learned?"

### Slice 3: SkillOps Guarded Trial

Apply EvoSkill-style failure mining to project skills:

- pick one skill with repeated failures;
- create a held-out validation checklist;
- propose a skill edit;
- run validation and mirror checks;
- keep or reject the edit with evidence.

This current session is the manual prototype.

### Slice 4: Group Evolution Run Spec

Add a dormant spec model for group runs, without broad execution:

- parent branches,
- experience pool,
- diversity policy,
- evaluator chain,
- budget,
- merge policy.

### Slice 5: MCP Surface

Expose a coarse chatbot action:

```text
evolve action=group_improve goal=<goal> branches=<ids|search> budget=<cap>
```

The chatbot can keep the interface conversational. The engine owns the exact
run spec.

## Pickup Packet

Concept: ExperiencePool + GroupEvolutionRun.

Initial provider: Codex.

Required reviewer: Claude. Because Codex made the initial finding, Claude must
independently research and review the Group-Evolving Agents / EvoSkill
implication before any build, git push, live rollout, or acceptance test starts.

Applies when touching:

- optimization runs or evaluator contracts;
- branch evolution, convergence, or merge policy;
- project or domain skills;
- MCP `evolve` / branch improvement surfaces;
- shared learning, failure mining, or experience replay.

Shared queues:

- `STATUS.md` Work row: "Claude review gate: ExperiencePool +
  GroupEvolutionRun frontier finding".
- `ideas/PIPELINE.md` Active Promotion: "ExperiencePool + GroupEvolutionRun
  (GEA/EvoSkill frontier radar)".

Next artifact:

`docs/audits/2026-05-02-experience-pool-claude-review.md`

Review exit check:

- re-check primary GEA and EvoSkill sources;
- compare against Workflow's current `EvalResult` / native optimization slice;
- verdict is `approve`, `adapt`, `defer`, or `reject`;
- if approved or adapted, create the next build/design row with concrete files;
- if deferred or rejected, update `ideas/PIPELINE.md` with the reason.

Probable post-review build files, only if review approves:

- `docs/design-notes/2026-05-02-experience-pool-and-group-evolution.md`
- `docs/specs/2026-05-02-experience-pool-minimal-schema.md`

## Worktree Landing Packet

Build advancement is blocked on the Claude review gate, but the implementation
lane should still be visible in git/worktree coordination now. The lane may be
created or reserved before review; it must not advance beyond blocked handoff
metadata until the review returns `approve` or `adapt`.

Review handoff:

- Proposed branch: `claude/experience-pool-review`
- Proposed worktree: `../wf-experience-pool-review`
- Base/dependency: current main with this radar artifact available
- Files: `docs/audits/2026-05-02-experience-pool-claude-review.md`
- First slice: independent source re-check plus verdict
  (`approve`, `adapt`, `defer`, or `reject`)
- Verification: review cites primary GEA/EvoSkill sources and current Workflow
  optimization/evaluation context
- Fold-back: merge review artifact, update `STATUS.md` / `ideas/PIPELINE.md`,
  then create or revise the implementation row

Review-blocked implementation handoff:

- Proposed branch: `claude/experience-pool-slice-1` or
  `codex/experience-pool-slice-1`
- Proposed worktree: `../wf-experience-pool-slice-1`
- Base/dependency:
  `docs/audits/2026-05-02-experience-pool-claude-review.md`
- STATUS dependency: review artifact verdict is `approve` or `adapt`
- Initial write-set:
  `docs/design-notes/2026-05-02-experience-pool-and-group-evolution.md`,
  `docs/specs/2026-05-02-experience-pool-minimal-schema.md`
- First implementation slice after review: design/spec only; no runtime
  group-evolution executor
- Verification: doc/spec diff check plus any schema examples the reviewer
  requires
- Fold-back: PR to main, retire the review row, and add the next concrete
  implementation row with exact runtime files

## Implications For The Current Optimization Work

The `OptimizationRun` work should not stop at individual node candidates. It
should be designed so a future `GroupEvolutionRun` can reuse:

- `EvalResult`,
- candidate lineage,
- artifact side-channel,
- analyzer lessons,
- visibility policy,
- merge policy,
- host-pool execution.

If the individual optimizer cannot feed a shared experience pool, it is aimed
too low.

## Skill Iteration Made From This Scan

`external-research-implications` now includes `Frontier Radar Mode`:

- scan multiple candidates;
- penalize hype;
- rank by paradigm shift, Workflow fit, implementation gravity, evidence, and
  integration leverage;
- choose one frontier bet;
- record what to adopt/adapt/avoid/defer/watch.
- require opposite-provider research review before build;
- leave pickup packets in `STATUS.md` or `ideas/PIPELINE.md`.

## Final Call

The frontier is not "agents that write code." It is **communities of agents,
skills, workflows, evaluators, and users that evolve through shared experience
while preserving provenance, privacy, and outcome evidence.**

Workflow should build that first.

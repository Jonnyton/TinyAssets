# Frontier Repo Radar 3: OpenTraces

Freshness stamp: 2026-05-02. Initial provider: Codex.

This scan used current web research, PyPI metadata, GitHub page inspection, and
a read-only shallow clone into `%TEMP%\workflow-research-opentraces` at commit
`2e44d2017594734508bb8f2d2d988ab1daf99ff1`.

## Executive Judgment

The next repo with the strongest distinct implication for Workflow is:

**JayFarei/opentraces** - https://github.com/JayFarei/opentraces

Project site: https://www.opentraces.ai/

PyPI: https://pypi.org/project/opentraces/

Why this matters: Workflow's living system depends on useful work becoming
durable, reviewable, reusable evidence. OpenTraces treats agent sessions as a
first-class data asset: capture the session, enrich it, redact it, review it,
link it to commits, and export it as an open trace dataset.

For Workflow, the implication is:

> The project needs a private-by-default trace commons: every useful agent,
> daemon, evaluator, and user-sim run should be able to become a reviewed,
> redacted, attributed learning artifact.

This is a different frontier axis from the prior picks:

- ASI-Evolve: evaluator-driven optimization loop.
- Group-Evolving Agents / EvoSkill: shared experience pools.
- AgencyBench: long-horizon acceptance scenarios.
- OpenTraces: trace capture, review, attribution, and data flywheel.

## Source Freshness

| Source | Evidence |
|---|---|
| GitHub repo | `JayFarei/opentraces`, public repo, GitHub page showed MIT license, 374 commits, 74 stars, 3 forks on 2026-05-02 |
| Local clone | Commit `2e44d2017594734508bb8f2d2d988ab1daf99ff1`, timestamp 2026-04-28T14:23:41+01:00, message `Add ASCII art to README.md` |
| PyPI | `opentraces` 0.3.3 current on project page, released 2026-04-20; PyPI states "Crowdsource agent traces to HuggingFace Hub" and Python >=3.10 |
| Project site | Describes local inbox review, redaction tiers, HF JSONL publishing, quality scoring, blame/graph, and agent-native CLI |

GitHub API metadata was rate-limited/403 during this pass, so repo details use
the GitHub web page plus local clone evidence instead.

## Candidate Radar

| Candidate | Why considered | Decision |
|---|---|---|
| `JayFarei/opentraces` | Agent trace capture + review + redaction + commit attribution + HF export | **Choose** |
| `open-thoughts/OpenThoughts-Agent` | Agent training data recipes, trace viewer, eval infrastructure | Watch as downstream consumer of trace commons |
| `AgentOpt/OpenTrace` | Tracing/optimization workflow library | Watch; more optimizer-oriented and less provider/session-native |
| `future-agi/traceAI` | OpenTelemetry instrumentation for LLM apps | Watch for production observability alignment |
| `SHU-XUN/TraceSIR` | Trace analysis/reporting over execution traces | Watch for trace summarization and diagnosis |
| `agiresearch/AIOS` | Agent OS kernel, memory/tool/context managers, MCP/VM controller | Watch for runtime scheduling architecture |

OpenTraces wins because it operationalizes the missing first mile: collect the
real multi-provider work we are already doing, keep it private by default,
review/redact it, and make it usable by future agents.

## Outside-System Map

Entrypoints:

- CLI in `src/opentraces/cli/`.
- Repo-local setup via `opentraces setup` and `opentraces init`.
- Local review via `opentraces web`, `opentraces tui`, and CLI trace commands.
- Agent-facing skill installation in `skill/` and capture integrations in
  `src/opentraces/capture/`.

Capture:

- Captures supported coding-agent sessions, with an explicit Claude Code
  parser/hook path in the inspected repo.
- Imports external datasets through parsers such as `hermes`.
- Keeps local runtime state under a machine-local project store while writing a
  small committable `.opentraces.json` marker.

Schema:

- `packages/opentraces-schema` defines Pydantic `TraceRecord` models.
- The schema records task, agent, environment, steps, tool calls,
  observations, snippets, token usage, outcome, attribution, git links,
  dependencies, metrics, and security metadata.
- It intentionally borrows from ATIF, ADP, Agent Trace, and OTel GenAI.

Security and review:

- Pipeline applies context-aware regex and entropy scanning.
- Optional TruffleHog scan can add broader secret detection.
- Optional LLM review can provide semantic review.
- Human review is a first-class stage through web/TUI/CLI inboxes.
- Redaction preserves stable placeholders where possible.

Enrichment:

- Derives language ecosystems and dependencies from steps and project files.
- Computes metrics from step data.
- Builds attribution from edit/write tool calls and patches.
- Correlates traces to commits with evidence tiers:
  `tool_emitted`, `tool_emitted_with_divergence`, `overlapping`, `orphan`.

Publish/export:

- Publishes reviewed traces as sharded JSONL datasets on Hugging Face.
- Exports into downstream formats such as ATIF and Agent Trace.
- Provides `blame` and `graph` views to connect commits back to sessions.

## Workflow Comparison

Workflow already has related primitives:

- `AGENTS.md`, `PLAN.md`, and `STATUS.md` preserve process/design/live state.
- `.agents/activity.log` preserves session coordination.
- `output/claude_chat_trace.md` and `output/user_sim_session.md` preserve live
  MCP proof.
- `EvalResult` now carries artifacts and evidence.
- `workflow.evaluation.process` evaluates trace handoff, tool use, retrieval,
  grounding, and stopping behavior.
- Attribution/royalty machinery already links branch/node artifacts to actors.

Workflow gaps OpenTraces exposes:

- No unified cross-provider `SessionTrace` schema for Codex, Claude, Cursor,
  daemon, user-sim, and MCP runs.
- No explicit trace inbox with review/redact/reject/stage lifecycle.
- No trace-to-commit or trace-to-branch attribution query.
- No private-by-default trace commons that can later feed evaluators, scenario
  packs, skill iteration, or training datasets.
- No standard export shape for community-shared traces.

## Implications

### Adopt: Trace Commons As A Workflow Primitive

Add a Workflow-native concept:

```text
SessionTrace
  trace_id
  provider
  model
  task
  repo_ref
  steps
  tool_calls
  observations
  artifacts
  eval_results
  outcome
  attribution_refs
  privacy_review
  visibility
```

The first implementation should be a contract and review lifecycle, not a data
lake.

### Adapt: Private-By-Default Trace Inbox

OpenTraces' review model matches Workflow's privacy stance: collect locally,
review before sharing, redact before export. Workflow should adapt this as:

- capture into a private local inbox;
- classify sensitive fields;
- allow approve/redact/reject;
- attach approved trace summaries to branches, runs, skills, and evals;
- only export public trace records when visibility is explicitly public.

### Adapt: Trace-To-Artifact Attribution

The `blame` and `graph` pattern is directly relevant. Workflow should support:

- "which session produced this branch version?"
- "which user prompt caused this evaluator change?"
- "which trace explains this failed run?"
- "which accepted community artifact came from which agent/user combination?"

This strengthens contributor credit, debugging, rollback, and learning.

### Adapt: Trace-Derived Training/Eval Data

OpenThoughts-Agent and AgencyBench need data. OpenTraces shows the capture path.
Workflow should treat approved traces as inputs to:

- acceptance scenario packs;
- skill improvement;
- experience pools;
- evaluator regression fixtures;
- optional community training datasets.

### Avoid: Automatic Public Trace Upload

Do not add automatic trace publishing. Trace data can contain secrets, customer
data, private project paths, provider prompts, and sensitive work. The first
Workflow slice must be private, local, review-gated, and explicit.

### Avoid: Raw Hidden Reasoning As A Requirement

The useful trace is tool use, observations, artifacts, outcomes, and public
agent responses. Workflow should not require storing hidden chain-of-thought or
provider-private reasoning. When reasoning-like text is explicitly available,
store it only under privacy review and prefer summaries for public traces.

## Integration Roadmap

Slice 1: Claude review.

- Claude independently reviews OpenTraces and this implication.
- Decide whether `SessionTrace` is the right Workflow-native shape.

Slice 2: Minimal trace schema design.

- Define `SessionTrace`, `TraceStep`, `TraceArtifact`, `TracePrivacyReview`,
  and `TraceAttribution`.
- Map existing `EvalResult.artifacts`, `quality_trace`, live MCP proof files,
  and `.agents/activity.log` into the shape.

Slice 3: Private trace inbox.

- Create a local-only trace review directory or table.
- Add approve/redact/reject/stage lifecycle.
- Add no public export.

Slice 4: Trace-to-run/branch lookup.

- Link traces to run IDs, branch versions, node IDs, evaluator IDs, and commits.
- Expose a read-only lookup for debugging and future MCP inspection.

Slice 5: Community trace commons.

- Only after privacy review works: allow public, redacted, attribution-aware
  trace export for community learning and benchmark/scenario generation.

## Cross-Provider Review Gate

Codex made the initial finding. Claude must independently research/review
OpenTraces before implementation, git push, live rollout, or acceptance testing
based on this finding.

Required review artifact:

`docs/audits/2026-05-02-opentraces-claude-review.md`

Review verdict must be one of:

- `approve`
- `adapt`
- `defer`
- `reject`

The review must re-check primary sources, inspect Workflow's current trace,
artifact, privacy, attribution, and evaluation paths, and decide whether
`SessionTrace` / private trace inbox is the right Workflow-native shape.

## Pickup Packet

Concept: Private Trace Commons / SessionTrace.

Initial provider: Codex.

Required reviewer: Claude.

Applies when touching:

- `.agents/activity.log`
- `output/*trace*` or user-sim artifacts
- `workflow/evaluation/*`
- `workflow/runs.py`
- `workflow/api/runs.py`
- attribution, contributor, or royalty code
- provider/session harnesses
- privacy/redaction/export paths
- skill iteration and cross-provider review flows
- training/eval dataset generation

Shared queues:

- `STATUS.md` Work row: "Claude review gate: OpenTraces private trace commons
  finding".
- `ideas/PIPELINE.md` Active Promotion: "Private Trace Commons
  (OpenTraces radar)".

Next artifact:

`docs/audits/2026-05-02-opentraces-claude-review.md`

Post-review build files, only if review approves:

- `docs/design-notes/2026-05-02-private-trace-commons.md`
- `docs/specs/2026-05-02-session-trace-minimal-schema.md`

Exit check:

- Claude review exists and is linked from `STATUS.md`.
- No public trace export exists in the first implementation.
- Design note defines review/redaction/visibility gates.
- Minimal schema maps current Workflow evidence artifacts without requiring
  hidden reasoning capture.

## Worktree Landing Packet

Build advancement is blocked on the Claude review gate, but the implementation
lane should still be visible in git/worktree coordination now. The lane may be
created or reserved before review; it must not advance beyond blocked handoff
metadata until the review returns `approve` or `adapt`.

Review handoff:

- Proposed branch: `claude/opentraces-review`
- Proposed worktree: `../wf-opentraces-review`
- Base/dependency: current main with this radar artifact available
- Files: `docs/audits/2026-05-02-opentraces-claude-review.md`
- First slice: independent source re-check plus verdict
  (`approve`, `adapt`, `defer`, or `reject`)
- Verification: review cites OpenTraces primary repo/site/PyPI and current
  Workflow trace, artifact, privacy, attribution, and evaluation context
- Fold-back: merge review artifact, update `STATUS.md` / `ideas/PIPELINE.md`,
  then create or revise the implementation row

Review-blocked implementation handoff:

- Proposed branch: `claude/private-trace-commons` or
  `codex/private-trace-commons`
- Proposed worktree: `../wf-private-trace-commons`
- Base/dependency:
  `docs/audits/2026-05-02-opentraces-claude-review.md`
- STATUS dependency: review artifact verdict is `approve` or `adapt`
- Initial write-set:
  `docs/design-notes/2026-05-02-private-trace-commons.md`,
  `docs/specs/2026-05-02-session-trace-minimal-schema.md`
- First implementation slice after review: design/spec only; private-by-default
  trace inbox contract, no public export
- Verification: doc/spec diff check, explicit privacy/redaction/visibility
  gates, and no hidden reasoning capture requirement
- Fold-back: PR to main, retire the review row, and add the next concrete
  implementation row with exact runtime/test files

## Skill Iteration

This pass adds a trace/data-flywheel lens to `external-research-implications`:
future trace projects must be evaluated for capture surfaces, schema shape,
review/redaction/consent gates, attribution links, and whether data stays
private, becomes a community artifact, or feeds evaluator/training datasets.

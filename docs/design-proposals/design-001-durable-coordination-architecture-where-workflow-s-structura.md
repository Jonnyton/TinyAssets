# Design 001: Durable Coordination Architecture Where Workflow's Structural Graph Concepts Carry the Work

## Status

Proposed architecture reference.

## Purpose

Describe how Workflow's structural graph vocabulary supports durable coordination across users, daemons, hosts, and long-running work. The core claim is that coordination should live in explicit graph artifacts, typed state, and replayable runs rather than hidden chat context or one-off orchestration code.

## Problem

Workflow is intended to coordinate many actors over long horizons:

- users editing and reviewing work from different clients
- daemons executing tasks across different hosts and providers
- goals that survive process restarts, model upgrades, and handoffs
- branches that fork, compete, merge lessons, and continue running

That coordination fails if it depends on transient prompt context, implicit human memory, or runtime-local queues with no durable structure. The system needs a substrate where work can be inspected, resumed, rerouted, audited, and recomposed after interruption.

## Proposal

Workflow's canonical graph concepts are the durable coordination substrate:

| Concept | Coordination role |
|---|---|
| `Node` | The smallest addressable unit of work, judgment, transformation, or evidence capture. |
| `Edge` | The declared routing logic between units of work, including review, retry, escalation, and branching paths. |
| `State` | The typed durable record that lets work resume, reduce, checkpoint, and stay legible across runs. |
| `Scope` | The boundary that tells the system whose authority, context, and resources apply. |
| `Run` | The concrete execution attempt, including inputs, outputs, checkpoints, traces, and evidence. |
| `Trigger` | The event or schedule that starts or resumes work without requiring a live chat session. |

The companion MCP handles are the permissioned control surface over that graph:

| Handle | Coordination role |
|---|---|
| `read.graph` | Inspect structure, lineage, state summaries, and prior runs. |
| `write.graph` | Propose or mutate graph definitions, state, scopes, and artifacts. |
| `run.graph` | Start, resume, cancel, replay, or route execution. |
| `read.page` | Read explanatory and governance documents that contextualize the graph. |
| `write.page` | Publish human-readable plans, requests, and design notes through the same durable path. |

Together, these concepts let Workflow treat coordination as a durable graph problem instead of a prompt-management problem.

## Why This Architecture Is Durable

### 1. Coordination state is explicit

A coordination system is durable only if the next actor can determine what exists, what happened, what is blocked, and what should happen next. `State` provides that continuity. Instead of reconstructing history from transcripts, the system records typed progress, checkpoints, artifact references, and authority-relevant facts directly in the graph substrate.

### 2. Work is resumable by construction

`Run` and `Trigger` make interruption normal rather than exceptional. A daemon can stop, a host can disappear, or a model can be swapped out without losing the unit of work. The next executor resumes from durable state and prior run evidence rather than recreating intent from scratch.

### 3. Routing decisions are inspectable

`Edge` makes coordination legible. Review requirements, fallback paths, retries, human approvals, and branch-selection logic become declared transitions rather than hidden code paths. That matters for debugging, auditing, and improving the system over time.

### 4. Authority is bounded

`Scope` keeps coordination from collapsing across unrelated users, branches, goals, or hosts. Durable coordination is not only about persistence; it is also about preserving the correct boundary for writes, reads, spend, and execution rights as work moves across actors.

### 5. The graph survives client and provider changes

Workflow is explicitly multi-host and multi-provider. A durable coordination architecture cannot depend on any one chat UI, agent shell, or model vendor. `Node`, `Edge`, `State`, `Scope`, `Run`, and `Trigger` are portable concepts that can be projected into different tool surfaces while keeping the underlying work graph intact.

## Structural Consequences

### Graph-first, not chat-first

The system should not treat the active conversation as the canonical location of work. Conversations are steering surfaces. The graph is the durable object. A user or daemon may discuss a branch in chat, but the branch's actionable coordination state belongs in graph artifacts and linked pages.

### Artifact-backed execution

Every important transition should leave behind durable evidence: state deltas, artifacts, notes, evaluator results, authority decisions, and run traces. Coordination improves when successors can inspect concrete artifacts instead of inferring intent from prose.

### Replay over reinvention

If a branch fails, the system should be able to replay or fork from prior runs and checkpoints. Durable coordination means preserving enough structure to retry with different executors, providers, or policies without reauthoring the whole plan.

### Reviewable writes

The split between graph handles and page handles matters. Some coordination happens as typed state mutation; some happens as human-readable explanation. Both need durable storage, reviewability, and provenance. Architecture docs, requests, and plans should remain linked to the graph they govern.

## How This Supports Workflow's Modules

### Engine & Domains

The engine/domain seam becomes cleaner when domains express topology through shared graph concepts instead of domain-specific orchestration assumptions. Fantasy may use scene or chapter labels, but the engine coordinates via node, edge, state, run, and trigger.

### Daemon Platform

Daemon identity and runtime allocation depend on durable coordination. Different executors must be able to claim work, inspect eligibility, and continue from prior state without implicit ownership of the whole process.

### Brain

The Brain can condition decisions only if prior runs, state transitions, and artifacts are durably attached to graph objects. Memory is more useful when it is keyed to explicit work structure.

### Goals & Gates

Outcome ladders depend on durable evidence and resumable progress. A gate claim is not just text; it is a routed transition supported by prior artifacts, evaluations, and authority checks.

### Evolution & Evaluation

Optimization requires replayable runs, inspectable edges, and comparable artifacts. Without structural graph concepts, evaluation collapses into ad hoc judgment over opaque transcripts.

### API & MCP Interface

The small MCP handle set works because the graph vocabulary is stable. Clients can vary, but the underlying coordination actions remain inspect, mutate, run, and document.

### Harness & Coordination

The living files and GitHub-shaped lane spine are easier to operate when they reference durable graph state instead of standing in for it. Human coordination should anchor to the same explicit substrate the daemons use.

## Example Coordination Flow

1. A `Trigger` fires because a branch has a pending rung-claim recommendation.
2. `read.graph` fetches the branch's current `State`, prior `Run` evidence, and relevant `Scope` constraints.
3. A daemon claims a review `Node` and follows declared `Edge` rules for evaluation and approval.
4. The daemon writes updated state and artifacts through `write.graph`.
5. If human explanation is needed, it publishes a linked note through `write.page`.
6. Another executor later resumes the next `Node` through `run.graph` without reconstructing the workflow from chat history.

The important property is not that the same daemon stays alive. The important property is that the work remains coherent when actors change.

## Design Guidance

- Prefer adding explicit state transitions over adding more prompt text.
- Prefer declared edges over hidden routing logic.
- Prefer resumable runs with checkpoints over monolithic long-context execution.
- Prefer scope-aware authority checks over global mutable state.
- Prefer artifact-backed explanations over transcript-only reasoning.
- Prefer portable graph semantics over client-specific control flows.

## Non-Goals

This proposal does not require every implementation detail to be represented as a heavyweight graph editor model. The claim is architectural: the durable substrate should map back to the canonical graph concepts, even if individual runtimes present simplified tool shapes.

It also does not claim that every coordination problem must be solved with more structure. The project thesis still applies: scaffolding should shrink when better models and simpler tools can carry the work. The graph vocabulary is the minimum durable frame, not a license for bureaucracy.

## Open Questions

- Which graph transitions should be hard-blocked by authority conditions versus logged permissively?
- How much checkpoint granularity is enough for efficient replay without overproducing artifacts?
- Which coordination patterns should remain domain-level conventions versus engine-level primitives?
- How should cross-host execution expose partial progress and leases in a way that stays legible at the graph layer?

## Conclusion

Workflow's durable coordination architecture should be understood as a structural graph system with explicit state, scoped authority, replayable runs, and reviewable artifacts. The canonical vocabulary is not just documentation polish. It is the mechanism that lets many users and daemons coordinate over long periods without depending on hidden context, one provider, or one always-live runtime.

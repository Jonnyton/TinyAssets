# Community-Evolvable Optimization Integration

Status: accepted direction by host message on 2026-05-02; implementation not
started. This note integrates the ASI-Evolve implications report into the
Workflow product and architecture frame.

Primary reference:
`docs/audits/2026-05-02-asi-evolve-architecture-implications.md`.

## Decision

Workflow will take the ASI-Evolve / AlphaEvolve lesson as a native platform
pattern, not as a vendored subsystem.

The platform will grow an evaluator-driven optimization loop that can improve
nodes, branches, evaluators, prompts, policies, topology, memory/retrieval
behavior, and other platform pieces through normal Workflow primitives:

- MCP-facing user requests,
- branch and node lineage,
- evaluator chains,
- host-pool execution,
- versioned merge-back,
- privacy and visibility policy,
- attribution and outcome gates.

We will not create a separate ASI-style pipeline that bypasses those primitives.

## User Frame

The primary Workflow user is anyone with an MCP-connected chatbot. They may be
using Claude.ai, ChatGPT, Open WebUI, LibreChat, an IDE, or a future MCP client.
They should not need to clone the repo, install a research harness, write Python
experiment scripts, or keep the maintainer online.

The user-facing pattern should be conversational:

- "Improve this branch overnight. Spend at most $10. Ask me before merging."
- "Try three different approaches to this invoice workflow and keep the best
  two for review."
- "Make this evaluator stricter, but test it against these examples first."
- "Fork this public research-paper workflow and evolve it for legal briefs."

The chatbot is the control station. The daemon and host network execute.

## Product Frame

The project should feel alive:

- users can redesign and evolve branches,
- users can create or remix evaluators,
- daemon hosts can contribute execution capacity,
- public branches can cross-pollinate,
- successful patterns become reusable primitives,
- real-world outcomes decide what matters over time.

This is not "one best workflow wins." The ecosystem keeps many competing
solution families alive when they serve different users, constraints, domains,
privacy needs, or outcome ladders.

## Architectural Commitments

### Optimization Is A Run Type

Optimization belongs under Workflow's existing run/event/version/provenance
system. The first implementation should create or prepare contracts for:

- `OptimizationRun`: target, baseline, editable surface, evaluator chain,
  search policy, budget, stop conditions, merge policy, visibility.
- `OptimizationCandidate`: parent ids, candidate artifact, score vector,
  evaluator result refs, cost, host identity, status.
- `OptimizationLesson`: hypothesis, change mechanism, result delta, failure
  mode, reusable principle, applicability scope, confidence, evidence refs.

### Evaluation Is The Truth Anchor

An optimization run is only as good as its evaluator chain. The first code slice
should normalize evaluator output before adding broad optimization execution.

Minimum `EvaluatorResult` shape:

- score and score vector,
- verdict,
- rationale,
- structured evidence,
- artifact side-channel,
- evaluator id,
- cost,
- freshness stamp.

The artifact side-channel is required because later candidates need to learn
from stderr, warnings, traces, profiler output, human comments, LLM judge
notes, and external verification results.

### Mutation Scope Is Locked

Candidate generation can mutate only declared editable surfaces. The generator
cannot edit the evaluator, locked harness, gold set, budget, or merge policy
that determines success for the same run.

For branch/node optimization, editable surfaces should prefer structured paths
over raw whole-file mutation:

- node concept JSON pointers,
- prompt fields,
- graph edge choices,
- evaluator chain parameters,
- domain-declared safe knobs,
- versioned branch specs.

Raw code mutation can exist, but only inside an explicit sandbox and scope.

### Community Evolvability Beats Central Control

Users and daemons are sufficient for the engine to run. Maintainers should not
be on the critical path for normal evolution. The platform should allow users to
propose goals, fork branches, define evaluators, run optimization budgets,
review merge candidates, and publish outcomes from any MCP client.

Maintainers provide defaults, safety rails, uptime surfaces, and public
infrastructure. They should not be required as operators for ordinary work.

### Privacy Is Per-Piece

Optimization must preserve the existing per-piece privacy model. Private
instance data can improve that user's private branch, but it cannot silently
become public reusable cognition or a public evaluator example.

Reusable lessons need explicit visibility classification:

- private-to-user,
- private-to-branch,
- public concept-level,
- public with redacted evidence,
- blocked from promotion.

### Real-World Outcomes Sit Above Local Metrics

ASI-style benchmark improvement is not enough. Workflow optimizes for real
world effect. Local evaluator wins are candidate evidence; outcome gates and
verified use decide long-term ranking.

Discovery and leaderboards should show:

- lineage,
- evaluator evidence,
- cost/reliability,
- diversity family,
- real-world outcome badges.

## First Integration Slice

The first implementation slice should be contract-first and low blast radius:

1. Define `EvaluatorResult` as a typed return shape in the existing evaluation
   layer.
2. Add an artifact side-channel to evaluator outputs.
3. Add tests proving deterministic, editorial, and process evaluators can emit
   the normalized shape without changing their current behavior.
4. Add a dormant `OptimizationRun` spec model or design stub only after
   evaluator output is normalized.

Do not start by building a full optimizer. The platform needs the truth anchor
first.

## Non-Goals

- No vendoring `GAIR-NLP/ASI-Evolve`.
- No local-only research CLI as the primary user surface.
- No optimizer that requires the host/maintainer to be online.
- No auto-merge for public/high-risk changes from noisy evaluator results.
- No private-data promotion into public cognition without privacy approval.
- No greedy convergence into a single canonical workflow family.

## Open Implementation Questions

- Whether `OptimizationRun` lives inside `workflow/runs.py` initially or in a
  new `workflow/runtime/optimization.py` once the runtime package exists.
- Whether `EvaluatorResult` belongs in `workflow/evaluation/__init__.py`,
  `workflow/evaluation/schema.py`, or `workflow/protocols.py`.
- How much of the first candidate store can live in SQLite before the
  Postgres-canonical control plane ships.
- Which deterministic toy optimizer should become the first green proof.

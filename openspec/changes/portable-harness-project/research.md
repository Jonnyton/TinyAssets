# Research and implementation handoff

Research date: 2026-09-14, primary documents read through web access.
Initial provider: Codex. Required implementation reviewer: Claude.
Status: research-backed proposal; no external implementation vendored.

## Judgment

Keep the existing native definition and Branch substrate. Add a reviewed project
profile and a narrow semantic bridge that lets a harness and UI vary independently.
The useful precedent is separation of typed content, execution and presentation.
None of the sources establishes TinyAssets compatibility, a universal agent-loop
format, or reliable phone delivery.

## Source map: evidence, implication, and limits

| Primary source / version | What the source establishes | Proposed TinyAssets implication | Limit / disposition |
| --- | --- | --- | --- |
| [MCP tools, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), with [resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) and [prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts) | Discoverable tools have input schemas and may define output schemas; resource and prompt interfaces are distinct | Adapt: typed discoverable contracts, schema-validated results, separate resource data from execution | A deliberately pinned reference version, not a claim it is latest. MCP alone does not encode our full harness or carry grants between installations |
| [MCP Apps overview, displayed package v1.1.2](https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html) | Host-mediated UI resources, sandboxed views, capability negotiation and structured communication | Adapt: isolate custom views and expose only an explicit governed bridge; provide declared device alternatives | Dynamic documentation snapshot; re-pin the implementation/spec revision during review. An iframe is one web adapter, not an earbud/native renderer or a proof of sufficient isolation |
| [W3C SCXML, Recommendation 2015-09-01](https://www.w3.org/TR/2015/REC-scxml-20150901/) | Event-driven state transitions and explicit execution semantics | Adapt: describe input/event transitions and deterministic fixture behavior explicitly | Use our existing graph/compiler; do not introduce an SCXML interpreter or require XML |
| [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md) | Event identity is scoped by source; matching source and id identifies duplicates | Adapt: distinguish event identity, delivery identity and interaction identity | Event envelopes do not provide authorization, ordering, durable delivery or exactly-once effects |
| [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | Versioned validation vocabulary and bundled schema references | Adapt: package schemas, pin identities, validate bridge data at both boundaries | Schema validation cannot prove semantic compatibility or grant access; no remote schema fetch during import |
| [RFC 8785, June 2020](https://www.rfc-editor.org/rfc/rfc8785) | Canonical JSON requires defined serialization, property ordering and numeric/string constraints | Adapt: use a specified canonical encoding for the new project digest, with cross-language test vectors | Do not change native fingerprints; Python sorted JSON is not automatically JCS. Reuse existing encoding for native definitions |
| [WCAG 2.2, W3C Recommendation](https://www.w3.org/TR/WCAG22/) | Testable accessibility criteria include keyboard access, focus behavior and alternatives to non-text content | Adapt: semantic actions remain operable through accessible alternatives in the first rendered proof | A schema or a fallback label does not prove accessibility; manual rendered checks remain necessary |

These are design inferences, not endorsements or implementation results from the
source authors. No source code is copied. Source licenses must be rechecked if a
future slice imports a library; this round depends on no third-party code package.

## Existing code makes the extension point concrete

The inspected custom_agents._normalize_components accepts user-named component
objects and retains their payloads while requiring a non-empty kind.
_normalize_definition_payload reconstructs a fixed outer envelope. Therefore,
arbitrary new top-level fields are the wrong place to carry project/UI metadata:
place the proposed profile within components and keep larger assets in the project
inventory. This is a code-backed integration decision, subject to profile review.

custom_agents separates immutable definitions from revision-guarded private bindings.
agent_interchange validates adapter responses and conversion reports, stages imports,
and creates receipts. Extend those paths where their current contracts fit; do not
create an unrelated UI store/exporter with different privacy and lineage rules.

agent_runtime_compiler.GovernedComponentDescriptor already pins adapters and
declares typed ports, requirements, confinement and budgets. Its compiler reports
ambiguous/unavailable adapters and unsupported confinement. Its configuration
schema is a typed-field map; general JSON Schema ports are a proposed extension,
not current behavior. A descriptive_only runtime mode exists, but cannot satisfy
a required executable dependency in the proposed project profile.

The graph compiler, existing run/read-output paths, current relay spec, and
onboarding/desktop surfaces provide integration anchors. They do not prove that an
arbitrary exported source project is locally runnable or that a general experience
renderer exists. A handler inventory is not a live acceptance result.

## Alternatives considered

| Alternative | Decision and reason |
| --- | --- |
| One new MCP tool per component or UI feature | Avoid: increases the control surface; most behaviors compose under current handles |
| A fixed menu of agent types, office/game/board types, or memory tiers | Avoid: makes current product taste a permanent ceiling |
| Export just native JSON | Insufficient: cannot establish source completeness or local execution |
| Copy an entire private workspace | Avoid: accidental data inclusion and implicit dependencies |
| Build a universal foreign-agent runtime | Defer: weakens the bounded native portability proof |
| Full CRDT-based cross-device state | Defer: existing revision checks are the starting point; simultaneous rich-text editing needs a separate demonstrated requirement |
| MCP Apps as the entire cross-device model | Avoid: use as a web adapter precedent; semantic identity/actions must outlive a particular renderer |
| Automatic personalization that edits a live definition | Avoid: propose a diff and retain a user-controlled activation boundary |

## Worktree landing and pickup packet

- Concept: independently replaceable harness and experience compositions.
- Existing review lanes: #3840, branch tiny/u-01kxm1vszd/portable-harness-project;
  #3841, branch tiny/u-01kxm1vszd/composable-ui-experiences. Continue these lanes;
  do not create a third competing proposal.
- Workspace: governed scratch checkout of the corresponding remote branch.
  A local contributor may use ../wf-portable-harness-project or
  ../wf-composable-ui-experiences with the same branch ownership.
- Current write boundary: only the corresponding openspec/changes directory.
  Public API, canonical specs, PLAN.md and runtime code are unchanged.
- Read dependencies: PLAN scoping rules; Daemon Platform, Brain, Providers,
  Engine & Domains, API & MCP Interface, Distribution & Discoverability;
  custom_agents.py, agent_interchange.py, graph_compiler.py, current relay,
  custom-agent and desktop specs; companion PR.
- Session context: the existing two proposals and current founder request.
  Provider memory/feed output is context only, never approval.
- Claimable next action: Claude reviews primitives.md, this source map, and the
  companion experience contract; rechecks primary sources and code; records
  approve/adapt/defer/reject with AGREE / DISAGREE_EVIDENCE / DISAGREE_CONCERN
  findings. Record the verdict in the corresponding change's review.md and
  resolve the affected implementation task before code work on that seam.
- First harness implementation: the project adapter and deterministic offline
  fixture, using current native validation and receipt machinery.
- First experience implementation: one ordinary composition with desktop/phone
  projections and a governed action bridge; second-account remix evidence.
- Before commit/push: admission, scoped diff checks, applicable conformance tests,
  independent shape/research review for implementation. Proposal publication is
  the review artifact; it claims no implementation approval.
- Before acceptance: retain exact revision, environment, fixture results and
  rendered interaction/effect evidence. A failed or unavailable adapter stays
  visibly unsupported.
- Fold-back: update the owning PR, sync only implemented behavior to canonical
  specs on landing, archive only completed changes. Do not mark the combined
  toolset complete until primitives.md P1-P5 evidence exists.
- Applies when touching: custom-agent components, interchange, context/memory
  strategies, run lifecycle, UI rendering, voice relay or notification routing.

No new skill convention emerged from this study. Existing source mapping,
typed evidence and cross-family review rules cover it.

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
- Current review lanes: #3840, branch tiny/u-01kxm1vszd/portable-harness-project;
  UI refinement #3842, branch tiny/u-01kxm1vszd/refine-experience-primitives.
  Original UI proposal #3841 merged during this round at 2026-09-14T00:23:29Z;
  #3842 continues that change on main. Continue these lanes without a competing proposal.
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
- First experience implementation (proposal refined in #3842): one ordinary composition with desktop/phone
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

## Second refinement: composition, evolution and failure proofs

Research checked 2026-09-14. The following are design inferences for review;
none establishes an implemented TinyAssets feature.

- [Bytecode Alliance, WIT worlds](https://component-model.bytecodealliance.org/design/worlds.html):
  a component declares provided and required interfaces, and composition fulfills
  imports with exports. Adapt this separation to our existing descriptor/compiler
  and require complete dependency-closure diagnostics. Defer adopting Wasm/WIT as
  the package format: an interface description alone does not establish the
  behavior or portability of our Python/Branch runtime.
- [JSON Schema object reference](https://json-schema.org/understanding-json-schema/reference/object):
  properties are optional unless required, and additional properties are permitted
  unless constrained; schema composition has specific closure rules. Explicitly
  test omitted fields and extra fields in bridge contracts. A declaration of
  "2020-12" is insufficient if the chosen validator lacks required vocabulary.
  Schema compatibility and behavioral compatibility remain separate decisions.
- [Ink & Switch, Local-first software](https://www.inkandswitch.com/essay/local-first/):
  local data, collaboration, ownership and longevity motivate a stronger user
  ownership test. Our proposed test is continued editing/execution of exported
  source after hosted access is unavailable. It does not promise offline access
  to remote tools or make shared approval state safely mergeable.
- Revisited [SCXML 2015](https://www.w3.org/TR/2015/REC-scxml-20150901/)
  for explicit transitions and completion semantics, and
  [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
  for source-scoped event identity. Separate presentation transitions, canonical
  operation transitions and transport delivery. A delivery receipt cannot stand
  in for completed work; a deduplicated event cannot stand in for an idempotent effect.

The second refinement adds ordered composition admission, directional replacement
compatibility, staged activation, state migration/rollback limits and H-C1–H-C10
conformance traces in primitives.md. These are proposed requirements. No runner,
migration machinery, descriptor extension or new public handle is implemented.

Review questions with concrete decision outputs:
1. Which existing compiler result should carry each admission diagnostic, and
   which checks truly require a new profile validator?
2. Where can the existing installation revision make activation atomic, and what
   old-adapter retention is actually supported? Choose refusal/drain if unavailable.
3. Which effect outcomes can the existing receipt store reconcile? List unsupported
   destinations instead of asserting universal idempotency.
4. Which H-C vectors belong to the first slice, with the command and fixture path
   that will produce evidence? Keep unimplemented vectors visibly pending.

### Code verification for this refinement

Inspected the existing PR head in a governed Linux workspace on 2026-09-14:
- `tinyassets/agent_runtime_compiler.py:358`, `compile_agent_components`,
  iterates public component keys, resolves governed adapters, supports
  descriptive_only, validates confinement/configuration, and returns no compiled
  components when diagnostics exist. This function does not itself traverse a
  project dependency graph or validate schema-to-schema connections. Those are
  proposed checks, not an existing compiler capability.
- `tinyassets/custom_agents.py:1106`, `update_binding`, already guards the
  database update with universe, binding id and expected revision, raising
  AgentConflictError on mismatch. Reuse that precondition; this is not proof of
  atomic migration across arbitrary domain stores or retention of old adapters.
- Rechecked PLAN scoping rules and Engine/Daemon/API/Distribution principles:
  user strategies stay compositions, unknown kinds remain portable, browser
  users receive the same artifact, and runtime enforcement retains authority.

The inspection workspace provides Python 3 but no Claude CLI, Codex CLI or OpenSpec
CLI on PATH. The existing Claude review task remains claimable and uncompleted;
no independent review result is asserted. OpenSpec's documented manual layout is
used. The proposal is the review artifact; implementation remains gated.

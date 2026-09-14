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

## Third refinement: construction and truthful action contracts

Primary sources rechecked 2026-09-14; proposals below are design inferences.

| Source | Evidence | Adaptation and limit |
| --- | --- | --- |
| [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) | Automatic retry of non-idempotent requests requires knowledge of idempotent semantics or that the prior request was not applied | Expose adapter-specific retry/reconciliation support. This RFC does not supply an application deduplication ledger |
| [RFC 9110 §13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1) | If-Match preconditions prevent stale mutation at the resource boundary | Require real owner-side revision checks where advertised; do not emulate atomicity with a prior client read |
| [SCXML §3.13](https://www.w3.org/TR/2015/REC-scxml-20150901/#SelectingTransitions) | The event processor specifies transition selection and run-to-completion behavior | Separate pure input transitions from asynchronous work. Retain the existing graph runtime; deterministic local transitions do not make external effects deterministic |

Request-key binding, expiry behavior and extraction diagnostics are our proposed
contracts, not claims these standards define TinyAssets behavior.

### Fresh code evidence

Inspected existing proposal checkouts in a governed Linux workspace on 2026-09-14:
- `tinyassets/api/runs.py:1545`, `_action_cancel_run`, checks reachability and
  write authority, requests cooperative cancellation, then rereads status. It
  returns terminal and cancel_requested separately. Reuse this distinction;
  do not promise cancellation can prevent an already-dispatched effect.
- `tinyassets/runs.py:2357`, `list_events`, reads events ordered by step_index,
  using the last observed cursor rather than a count of completed nodes.
  `await_run_events` returns next_cursor and terminal/timeout reasons. This is
  a per-run read contract, not an atomic multi-resource projection snapshot.
- `tinyassets/agent_runtime_compiler.py:358` accepts existing component,
  runtime/configuration and governed registry inputs. Its diagnostics anchor
  readiness reporting. It does not establish a complete authoring editor,
  automatic subgraph extraction or universal action deduplication.

The new construction exercise makes inspect/edit/connect/validate/simulate/export/
bind/observe reviewable. H-C11–H-C14 add targeted dependency and action checks.
Keep the first inert package/offline fixture slice small; later capabilities have
their own evidence gates rather than expanding the first implementation indefinitely.

Before action implementation, the reviewer must name the native handler and
receipt lookup for each offered operation, its actual request-key/precondition
support, and how expiry/unknown delivery is exposed. Absence of support is an
acceptable explicit outcome; a generic wrapper that claims support is not.

Verification boundary: documentation-only refinement. Python is present; OpenSpec,
Claude and Ruff CLIs are absent on PATH in this governed workspace. The manual
OpenSpec layout remains applicable. Independent review remains pending; no new
Claude verdict, executed conformance vector or live capability is asserted.

## Review follow-up: Pi, lab harnesses and open interoperability

Checked primary pages on 2026-09-14. These are comparisons and design inferences;
no external dependency is adopted. Pin concrete revisions before implementation.

| Primary source | Supported comparison | Implication and limit |
| --- | --- | --- |
| [Pi coding harness](https://github.com/earendil-works/pi/tree/main/packages/coding-agent) (the former badlogic/pi-mono URL redirects here) | Extensions, skills, templates and themes can be packaged; interactive, print/JSON, RPC and SDK modes expose different integration levels | A useful benchmark for user-built behavior and sharing. Packages alone do not prove confinement, private-state separation or whole-harness compatibility in TinyAssets |
| [Anthropic Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) | Exposes Claude Code's loop/context facilities, hooks, tools and sessions; direct model API use leaves loop implementation to the application | Compare reusable vendor harness integration with owning the loop. A vendor hook is not proof every internal boundary is replaceable; this is research, not a switch away from current writer policy |
| [Google ADK workflows](https://adk.dev/agents/workflow-agents/) | Documents deterministic sequential/loop/parallel templates and newer graph/dynamic workflow options | Support user-authored control flow without freezing today's template taxonomy; shared source still needs an execution and state mapping |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Low-level stateful orchestration, durable execution and human input integration | Reuse the Branch runtime's actual contracts; a framework capability is not evidence that every TinyAssets adapter exposes it |
| [Agent Skills specification](https://agentskills.io/specification) | Packages instructions plus optional scripts, references and assets; tool declarations are implementation-dependent | Partial import/export option for instructional components. Does not define the complete loop, state stores, lifecycle or portable grants |
| [Open Agent Spec](https://github.com/oracle/agent-spec) and [language specification 26.1.2](https://oracle.github.io/agent-spec/26.1.2/agentspec/language_spec_26_1_2.html) | Describes agents/flows for execution by supporting runtimes | Partial semantic interchange option. Each adapter must report supported mappings and losses; framework-agnostic description is not universal executable harness portability |

A comparison must distinguish source availability, replaceable strategy boundaries,
runtime dependencies, state ownership and deployment confinement. None of these
sources supplies our required proof that a user can replace the first-party served
harness and experience while retaining their own data.

### One-to-two-year forecast (inference, September 2027–September 2028)

Moderate-confidence expectation: composable skills, tool protocols and embeddable
harnesses will make sharing individual components easier. Lower-confidence
expectation: adapters will cover a growing useful subset of cross-framework
agent/flow semantics. It remains uncertain whether state migration, cancellation,
provider session internals and effect guarantees will converge enough for lossless
whole-harness interchange. These are planning hypotheses, not source claims,
announced roadmaps or delivery promises.

Design for that uncertainty with preserved source, versioned interfaces, full
dependency diagnostics, explicit conversion loss and replaceable execution adapters.
Revisit the forecast with real two-runtime round-trip and execution evidence;
do not hardcode a vendor's current loop or unsupported numeric package ceiling.
MCP transport reconnection, application run cursors and destination effect
deduplication remain three independent contracts regardless of protocol adoption.

The posted review and author dispositions are recorded in review.md. The historical
failed Claude dispatches above describe earlier attempts; the posted coordinated
review now reports ADAPT. These revisions still require reviewer confirmation and
do not constitute implementation or live-user approval.

### Pending-request implementation evidence for this correction

Rechecked in the governed Linux proposal checkout on 2026-09-14 using
scripts/docview.py lines: api/pending_requests.py answer_request (line 1251)
applies _owner_gate, loads the existing request and rejects an already-resolved
record. storage/pending_requests.py resolve_request (line 284) conditionally
updates only a pending row; supported stored outcomes are answered or dismissed.
Its projected record has request_id/status and creation/resolution times, not a
global cursor or general action revision. Correlating a request with a paused
operation and validating that operation's target remain explicit adapter work.
Do not reinterpret answered as proof that the requested job completed.

graph_compiler.py exposes compile_branch and source-code/invoke/await node builders;
agent_runtime_compiler remains a separate component admission layer. No executable
project result follows merely from either symbol existing. The code inventory
was produced with a Python definition scan; runtime and rendered proof remain pending.

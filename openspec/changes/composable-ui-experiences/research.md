# Research notes and pickup boundary

Date: 2026-09-14. Initial provider: Codex.
Status: proposal refinement; required implementation reviewer: Claude.
No external source code or new runtime dependency is included.

## Evidence and proposed use

| Primary source | Evidence | Inference for this proposal | Limit |
| --- | --- | --- | --- |
| [MCP Apps overview, displayed v1.1.2](https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html) | UI resources are rendered through a host-mediated sandbox and negotiated capabilities | Adapt its host/view separation to the web renderer and explicit semantic bridge | Not a complete native/earbud or cross-device state system; pin the exact spec/library revision before implementation |
| [SCXML, W3C Recommendation 2015-09-01](https://www.w3.org/TR/2015/REC-scxml-20150901/) | Inputs and events drive explicit state transitions | Make input commitment, view lifecycle and event processing testable | Use existing Branch execution; no separate SCXML engine |
| [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md) | Source plus event id identifies an event and its duplicates | Separate event, destination delivery and action identities | No delivery, ordering, authorization or exactly-once guarantee follows from this envelope |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Accessibility can be tested through keyboard, focus and non-text alternatives | Require equivalent semantic controls in non-spatial and assistive paths | Actual rendered testing is required; a component declaration is not compliance evidence |
| [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | Explicit schema dialect and bundled references support data validation | Validate projection and intent payloads through locked packaged schemas | Validation does not establish authority or behavioral equivalence |

Primary pages were read on the date above. Dynamic documentation must be pinned
during implementation review. These are design inferences; no source asserts that
TinyAssets implements or passes these contracts. Recheck licenses before adopting
a library; this proposal copies no source code.

The broader harness comparison, digest research and alternatives are in
[companion PR #3840](https://github.com/Jonnyton/TinyAssets/pull/3840), under
portable-harness-project/research.md. The experience proposal remains independently
reviewable and does not assume the project exporter is shipped.

## Repository grounding and unresolved integration

- custom_agents._normalize_components preserves user-defined kinds/payloads;
  _normalize_definition_payload fixes the outer envelope. Keep experience profile
  data inside components; do not add unchecked top-level fields.
- agent_runtime_compiler already owns governed component descriptors and compilation.
  Reuse it where possible; a namespaced experience profile must not become an
  independent authority/adapter registry.
- api/runs.py exposes read/control handlers, and api/run_outputs.py supports bounded
  output reads. Surface availability must be checked separately; existence of a
  Python handler does not prove every device can invoke it.
- graph_compiler.py owns graph execution, state and child invocation. Routing policy
  remains an ordinary composition.
- conversation_store.py, the current universe-personification-and-relay spec, and
  existing onboarding surface anchor canonical conversation continuity.
- desktop/notifications.py is a desktop integration anchor, not evidence of phone
  push support.
- Existing concerns about served tool parity, voice endpointing and provider
  portability must be reverified before claiming combined acceptance. Their listed
  presence is a review dependency, not a fresh reproduction of those issues.

## Pickup packet

PR #3841 merged during this refinement (2026-09-14T00:23:29Z), so continue in
successor branch tiny/u-01kxm1vszd/refine-experience-primitives from main,
with a draft follow-up PR. Use a governed scratch checkout (or local
../wf-composable-ui-experiences). The write boundary
for this review is this change directory. No PLAN, canonical spec or runtime
migration is included.

Claimable review: Claude independently checks sources and existing handlers,
reviews primitives.md plus the companion harness contract, and records a verdict
and structured disagreements in review.md. The before-implementation task depends
on that artifact. No independent approval is claimed by this refinement.

First implementation: ordinary desktop board/phone list composition, governed
bridge, inert preview/import, private rebinding and rendered second-account
evidence. Office/game/native voice adapters follow with their own proofs.
Read PLAN scoping rules, Daemon Platform, Providers, API & MCP Interface and
Distribution & Discoverability before implementation; inspect the latest native
definition/compiler, relay and run contracts. Provider context was scanned at
plan/foldback; it confers no build authority.

Before implementation commit/push: settle bridge/profile/storage seams, record
cross-family research/shape review, run admission and relevant conformance tests.
Before acceptance: actual rendered keyboard/touch/voice checks, replay-gap and
revocation scenarios, delivery receipts, source/private-state exclusion and exact
revision/environment evidence. Unsupported native adapters remain explicit.

Fold back through the successor PR to #3841; sync only verified behavior into canonical specs on landing.
Applies when touching UI composition, custom-agent components, canonical conversation,
voice, event routing, instance controls, private bindings or renderer adapters.

## Second refinement: ownership, authoring fidelity and multi-device races

Research checked 2026-09-14; all adaptations below are design judgments.

- [Ink & Switch, Local-first software](https://www.inkandswitch.com/essay/local-first/)
  motivates ownership and continued use of source/data independently of a vendor.
  Translate that into lossless editor round-trip, private overlay preservation and
  a usable pinned/forked experience when an upstream upgrade conflicts. This does
  not establish safe offline merging for canonical approvals or remote effects.
- [W3C SCXML 2015](https://www.w3.org/TR/2015/REC-scxml-20150901/)
  distinguishes state transitions and completion. Use explicit voice/input/playback
  states and keep renderer lifecycle separate from run lifecycle. Do not implement
  a second scheduler or assume "parallel" requires threads.
- [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
  supplies source-scoped event identity. It does not solve snapshot/subscription
  races, cursor retention or delivery guarantees; those must be specified by the
  projection/channel adapter and tested with interrupted traces.
- [W3C technique G219](https://www.w3.org/WAI/WCAG22/Techniques/general/G219)
  illustrates non-drag pointer alternatives. Apply it to an office/board action
  alongside separate keyboard and focus checks. The technique is informative;
  these checks alone are not a claim of complete WCAG conformance.

The added E-C1–E-C12 vectors in primitives.md make editor fidelity, upstream conflict,
snapshot gaps, revocation, notification grouping, earbud interruption and recovery
observable. Pair E-C12 with H-C10 in #3840 rather than treating two independent
demonstrations as proof that harness and experience are interchangeable.

Before implementation, review must choose the actual snapshot/cursor owner,
private-overlay storage mapping and activation revision boundary. Reuse current
stores and handlers wherever their contracts suffice. Where no existing primitive
can express the needed behavior, document the failed composition and smallest
missing seam. No new service, universal CRDT, UI archetype registry, or native
voice adapter is selected by this refinement.

The existing `custom_agents.update_binding` revision-guarded update and
`agent_runtime_compiler.compile_agent_components` diagnostics are reusable
anchors, inspected in the companion proposal checkout. They do not implement
three-way overlay merge, a projection cursor protocol or renderer recovery.
PLAN's scoping and browser-user rules support keeping those as narrowly mapped
contracts over ordinary compositions. The required Claude review remains pending;
the governed inspection workspace has no Claude CLI on PATH.

A bounded Claude critique was also attempted through the registered subscription
provider route during this round. Execution refused before producing a review:
provider access was not bound for this universe. A registered descriptor is not
routable subscription authority. No review verdict was produced or inferred.
The existing review task remains the handoff for both proposals.

## Third refinement: editable intent, confined messaging and useful status

Primary sources rechecked 2026-09-14; these are proposed adaptations.

| Source | Evidence | Adaptation and limit |
| --- | --- | --- |
| [WHATWG HTML, cross-document messaging security](https://html.spec.whatwg.org/multipage/web-messaging.html#security-postmsg) | Receivers must check message origin and data; confidential messages must not use wildcard target origins | Specify source/port/session bootstrap as well as payload validation. Opaque-origin frame handling is an explicit implementation decision; an origin string alone is insufficient |
| [W3C capability URL guidance](https://www.w3.org/TR/capability-urls/) | URLs that confer authority can leak through history, logs, referrals and other intermediaries | Use non-authorizing handoff references with fresh authentication. This guidance is informative, not proof of our link implementation |
| [WCAG 2.2 §4.1.3](https://www.w3.org/TR/WCAG22/#status-messages) | Status messages can be programmatically determined without taking focus | Include pending/refusal/uncertainty in rendered assistive checks; one status role is not complete accessibility conformance |
| [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) | Retrying non-idempotent work needs knowledge beyond a lost response | Offer retry only through a documented adapter contract; remount and reconnect must not manufacture new work |

The complete control trace connects an editable input mapping to an installed
operation, symbolic target and evidence-backed outcome. Prepared intent invalidation
and remount recovery are TinyAssets design proposals, not features supplied by these
standards. E-C13–E-C16 are pending acceptance vectors for those boundaries.

### Current code and first-build decisions

Rechecked `tinyassets/api/runs.py:1545` and `tinyassets/runs.py:2357` in the
companion governed checkout. Cancellation returns status, terminal and
cancel_requested distinctly. Run events use an opaque per-run step_index cursor;
one node can emit several events. The experience must pass the returned cursor,
never compute it from visible node/card count. Existing polling reads do not prove
an atomic snapshot across instances, conversation and notifications. Preserve
separate stream cursors or document the adapter's reconciliation boundary.

Before the first rendered slice, review must specify:
1. The prepared-intent representation and which existing request/run reference
   survives renderer replacement; no second run registry.
2. The host-created frame/port handshake and isolation that keeps recovery usable
   when custom code never yields.
3. The canonical outcome-to-accessible-status mapping, with an actual uncertain
   delivery fixture and manual observations.
4. Which ordinary board/phone composition is exported for first-party parity;
   inspect its actual action names and resource roles for privileged shortcuts.

Do not block that first usable slice on a 3D engine, automatic component extraction,
native earbud integration or the complete future conformance catalog. Keep those
unsupported until proven. The builder still exposes the same source and semantic
contracts, preserving the path to those user-authored experiences.

This round changes proposal artifacts only. Independent Claude review remains
pending; no fresh provider execution or review verdict is claimed.

## Current review disposition

The posted coordinated Claude research/architecture feedback reports ADAPT;
[review.md](review.md) records its source and author dispositions. Earlier failed
provider attempts above remain historical evidence, not the current review status.
The added requirements still need reviewer confirmation; no new independent
verdict or executed acceptance result is claimed.

The companion harness research now compares Pi, Anthropic's harness integration,
Google ADK, LangGraph, Agent Skills and Open Agent Spec, and labels a one-to-two-year
forecast as inference. These are partial interoperability precedents, not proof
of complete setup portability or native device capability.

Current integration mapping uses conversation_store.py, runs.py, and the separate
storage/pending_requests.py plus api/pending_requests.py. The latter expose
create_request/get_request/list_pending/resolve_request and guarded
request_from_user/list_requests/answer_request handlers. These stores require
separate freshness and state reconciliation; handler existence does not prove
an atomic composite projection or universally resumable pending run.

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

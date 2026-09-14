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

First implementation: board/office/phone composition, governed bridge, inert
preview/import, private rebinding and rendered second-account evidence.
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

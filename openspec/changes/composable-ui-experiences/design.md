## Contract map

Read [primitives.md](primitives.md) for concrete port responsibilities, bridge
lifecycle, event identities, recovery semantics, accessibility and a worked
cross-device trace. [research.md](research.md) records evidence and the next
implementation review. The companion harness PR #3840 owns the shared source
project contract and evidence ladder.

These details refine the semantic responsibilities below. They are proposed
contracts to map onto existing handlers and the governed component compiler,
not a new tool catalog or a claim that native device adapters already exist.

## Context

Repository inspection on 2026-09-14 used a governed Linux checkout of main,
AGENTS.md, PLAN.md, the OpenSpec skill, delivery audit, and searches of current
specs. The audit reported zero claimed delivery WIP. The OpenSpec CLI was absent,
so this proposal uses the skill's documented manual layout.

PLAN.md already requires minimal primitives, community-built compositions,
replaceable agent components, private bindings, and first-class browser users.
It also requires voice to use canonical conversation and the user's serving
provider. These principles apply to the experience around the agent.

Existing integration anchors:
- `openspec/specs/universe-custom-agents/spec.md`: immutable public component
  compositions and private bindings.
- `openspec/specs/universe-personification-and-relay/spec.md`: canonical reply
  text and voice relay.
- `openspec/specs/desktop-host-runtime/spec.md`: existing dashboard, tray, and
  best-effort desktop notifications. This does not prove phone push delivery.
- `tinyassets/onboarding/app.html`: existing app surface, not proof of a generic
  experience interpreter.

The gap this proposal targets is a documented, verifiable composition contract
for the whole interaction experience. This inspection is not an exhaustive
absence audit of every UI extension.

## Scope and first proof

The long-term experience includes command centers, games, spatial offices,
voice-first earbuds, and combinations nobody has named yet. These remain
user-authored designs, never platform enums.

The first proof is one editable experience with a desktop instance board and a
compact phone list, preserving the same semantic instance bindings and actions.
An office layout, authorized speech adapter and actual phone notification route
are subsequent capability proofs using the same event identity. Their absence
must remain visible and must not block the first ordinary rendered composition.

A production 3D editor, every native device adapter, marketplace ranking, and
automatic personalization are outside the first implementation. The format must
preserve unsupported components so this initial renderer does not set a ceiling.

## Composition model

The following are semantic responsibilities, not a proposed list of MCP tools.
primitives.md specifies their data flow and lifecycle; research.md maps them to
existing native component, graph, run, conversation and desktop anchors.
Before implementing, settle the concrete bridge handler for each responsibility
and document only the irreducible gaps. Preserve governed descriptor requirements;
public component metadata cannot weaken adapter authority or confinement.

| Responsibility | Replaceable composition | Enforced boundary |
|---|---|---|
| Presentation | Layout, scene, theme, text, audio and accessibility alternatives | Governed renderer and resource limits |
| Input | Touch, keyboard, voice, gestures and event mappings | Authenticated source and schema validation |
| State binding | Which instance or artifact a component represents | Universe-scoped authorized reads |
| Action binding | Intent mapped to an existing Branch or control operation | Existing action authority and current target |
| Event routing | Filtering, grouping, quiet hours, destination and handoff | Existing channel grants and delivery receipts |
| Device adaptation | Capability predicates and declared alternatives | Honest availability and no silent privilege gain |

Components have stable user-named identifiers, typed inputs and outputs, explicit
references, versioned dependencies, and preserved lineage. A room, avatar, or
notification card has no authority of its own. Executable custom components use
governed adapters; imported HTML or scripts never execute in the authenticated
application's origin with ambient access.

Prefer a namespaced experience representation carried by the existing native
composition/interchange pipeline. Shape review must settle the extension and
renderer contract before adding fields or a new registry. Experience source and
assets should follow the inventory/integrity approach proposed in #3840 when
available; this proposal does not silently depend on an unshipped exporter.

## Definition, installation, and session

A shareable definition contains component source, deliberate demo assets,
capability requirements, schemas, dependency identities, and lineage. It contains
no real instance IDs, device tokens, credentials, conversations, notification
history, learned preferences, or private content. Only explicit publication makes
a definition public. Inspecting or importing a definition does not activate it.

A private installation maps symbolic roles such as `primary-instance` and
`phone-alerts` to the receiving user's authorized resources and channels.
This slice assumes the user's selected private-universe custody mode for these
bindings, without settling private custody for every deployment. Definitions and
private configuration remain separately exportable under that mode's authority.

Session state includes selection, focus, presentation progress and event cursors.
It is separate from authoritative instance/run state. Changing a view cannot
create a new agent identity, reset the conversation, or imply that background work
has stopped. Device-local focus need not synchronize to every other device.

## Devices, actions, and continuity

Each renderer declares available capabilities. A definition declares required
capabilities and intentional alternatives. Missing optional 3D, speech, or push
support selects a declared alternative with a visible explanation. Missing a
required capability prevents activation on that device. Preserve unknown
components for export/remix and identify them as unsupported; never silently
discard them or claim equivalent execution.

A desktop click, phone tap, or committed voice command resolves through the same
semantic action binding. The trusted boundary derives the user and universe;
a component-supplied identity is not authority. Validate the target and current
revision at action time. Denied, revoked, stale, or ambiguous actions return a
visible outcome and do not become an automatic alternate action.

Handoff carries references to the current universe, conversation, instance and
event, not copied authority or a second conversation writer. Voice output preserves
the canonical reply; any optional summary is explicitly labeled and cannot
replace the canonical record. Losing earbuds does not imply permission to read
private text aloud through a speaker.

## Events and notifications

Routing policy is editable composition. Quiet hours, grouping, interruption
preferences, and escalation are user choices. The substrate owns authenticated
delivery, revocation and receipts, not a fixed preference taxonomy.

Use a stable event ID and per-destination delivery identity. Reconnect can replay
events, but presentation must deduplicate within its documented retention window.
An acknowledgment updates the shared event state under a revision check; viewing
a toast is not acceptance of an action. Notification actions reauthenticate and
revalidate the target; an old notification never replays an already-completed
effect. Distinguish queued, delivered, acknowledged, expired, and failed outcomes
only when the underlying adapter provides evidence. Best-effort delivery is not
an exactly-once guarantee.

## Evolution and recovery

Users may edit source or ask their agent to propose a revision. Preview uses
fixture data and cannot invoke live actions, subscribe to private feeds, or send
notifications. Show the definition diff and changed capability requirements.
Activation replaces a selected installation revision under compare-and-swap;
concurrent edits yield a conflict rather than losing a user's changes.

Existing installations pin versions. Publishing a remix or updating a dependency
does not upgrade somebody else's active experience. A rollback restores a prior
compatible definition/binding revision after current permission checks, and
cannot reverse real-world actions already taken. Keep a trusted recovery control
outside custom content so a broken composition can be disabled.

## Acceptance and review decisions

Prove the same first-party composition can be exported, remixed by a second
account, privately rebound, and rendered on desktop and phone with canonical
conversation continuity. Retain rendered interaction evidence and effect receipts;
a schema round-trip alone is insufficient.

Before implementation, settle:
1. The existing native extension point, component schemas, asset bounds and
   governed renderer/adapter isolation contract.
2. The minimal semantic state/action/event interfaces and revision storage,
   based on actual existing handlers rather than a parallel control plane.
3. Capability negotiation and the honest fallback for each supported device.
4. Notification event IDs, replay window, acknowledgment semantics and adapter
   availability; no claim that phone push exists until proved.
5. Cross-family shape review, with AGREE / DISAGREE_EVIDENCE /
   DISAGREE_CONCERN findings and code citations where applicable.

## Review correction boundary

[review.md](review.md) maps the posted ADAPT findings to the updated contract.
The added primitive sections distinguish conversation/run/pending-request stores,
source-specific freshness, existing guarded request answers, ordinary authorized
learning, and actual confinement/device evidence. [Shared acceptance S-1](setup-acceptance.md)
requires UI-only, harness-only, whole-setup and mixed adoption over retained user
data and customizations. A declarative first-party layout remains a limited first
slice; it does not prove arbitrary executable views or native delivery.

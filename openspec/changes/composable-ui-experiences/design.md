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
compact phone view. A user replaces the board with an office layout while keeping
the same semantic instance bindings and actions. An event can be represented in
the office, announced through an available authorized speech adapter, or routed
to the user's phone notification destination. The same event identity connects
these representations.

A production 3D editor, every native device adapter, marketplace ranking, and
automatic personalization are outside the first implementation. The format must
preserve unsupported components so this initial renderer does not set a ceiling.

## Composition model

The following are semantic responsibilities, not a proposed list of MCP tools.
Before implementing, map each responsibility to existing primitives and document
only the irreducible gaps.

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

---

## Implementation slice: executable UI bundles (2026-09-26)

The proposal above describes the whole contract. This section settles item 1 of
"Before implementation" — **the governed renderer isolation contract** — and
scopes the first slice that actually ships. Everything the proposal defers
(device negotiation, notification routing, voice handoff) stays deferred.

### What already exists, and what it cannot do

`tinyassets/onboarding/app_layout.js` reads one `tinyassets.app-layout.v1`
component and *moves the app's own nodes*. It deliberately carries no HTML, CSS,
script or URL, because nothing in the app can safely execute imported code.
`openspec/specs/governed-agent-consumers/spec.md` states that limitation as a
requirement: the first adapter "SHALL NOT claim arbitrary executable UI".

That is the gap. A user who wants an office-building simulation cannot express it
by reordering four surfaces. The missing primitive is not another fixed surface —
it is a place to put arbitrary code plus a boundary strong enough to run it.

### The boundary, not a sanitizer

A shared UI is hostile input. Sanitizing markup or script is a losing game and is
explicitly **not** attempted. The bundle runs as arbitrary code inside a boundary
that holds regardless of what the code does:

1. **Opaque origin, enforced by response header.** `/mcp/app/ui-frame` serves a
   fixed bootstrap document under
   `Content-Security-Policy: sandbox allow-scripts`. The CSP `sandbox` directive
   applies to the document however it was loaded, so even a direct top-level
   navigation to that URL gets an opaque origin. `allow-same-origin` is never
   granted, so the document cannot reach `sessionStorage` (where `ta_access_token`
   lives, `app.html:710`), `localStorage`, cookies, or the parent DOM.
2. **No network of its own.** The same header sets `connect-src 'none'`,
   `default-src 'none'`, `form-action 'none'` and `img-src data:`. A bundle cannot
   fetch, cannot post a form, and cannot exfiltrate through an image URL. Every
   capability it has arrives through the bridge and nothing else.
3. **No nesting out.** `frame-src` falls back to `default-src 'none'`, so the
   bundle cannot embed a frame to shop for a weaker context, and
   `frame-ancestors 'self'` keeps the bootstrap from being framed off-origin.
4. **The bundle is never in the app's document.** The parent posts bundle source
   into the frame; it is never assigned to any node the app owns. The app's CSP
   gains exactly one term, `frame-src 'self'`, and keeps its nonce-only
   `script-src` — so even a bug that inserted bundle script into `app.html` would
   still not execute it.

Both sandboxes apply: the `<iframe sandbox="allow-scripts">` attribute and the
response-header CSP. Either alone is sufficient; the pair means a mistake in one
is not a breach.

### The bridge is the whole capability surface

`app_ui.js` owns the parent half. A message is considered only when
`event.source === frame.contentWindow`; the action is looked up in a frozen map
and an unlisted action is refused by name, never guessed. Each handler builds its
own `MCP.callTool` arguments — a bundle cannot supply `graph_id`, because the
handler pins it to the **viewing** user's current home, captured at enable time
and re-checked against `fetchMe()`. Cross-user reach is therefore not refused by
a check that could be bypassed; it is unrepresentable.

Replies are assembled field by field from picked values. No server payload is
spread into a reply, so a field added upstream later cannot ride out to a bundle.

MVP allowlist: `whoami` (universe id and display name only), `list_agents`,
`send_message`, `read_conversation`. `send_message` addresses a named agent in the
viewer's own universe, which is what makes "click a room, talk to that agent"
work. One `send_message` in flight at a time.

### Where a bundle lives

Two stores already have bounds, ownership, privacy, revision guards and a
publish/remix path; a third file store would be new storage shape needing its own
migration, so it is not introduced here.

- **Private, unpublished:** the existing non-serving `app_experience`
  `AgentBinding` configuration (`ui_library`, `ui_selection`), written through
  `write_graph target:agent_binding` — which the universe's own agent can call.
  Private by default: publishing is a separate, explicit act.
- **Shared:** a `tinyassets.app-ui.v1` component inside a public agent
  definition, via the `publish`/`remix` path `app_layout.js` already uses. A
  remix copies the component into the remixer's *own* binding, where it runs
  against the remixer's bridge. The author's universe is never addressed.

`ui_library` is a **list**, not an object: `_check_binding_content_fields`
rejects reserved key names like `messages`, and a list has no user-chosen keys to
collide. Bundle bytes are bounded so a full library cannot exceed
`MAX_AGENT_JSON_BYTES` (`tinyassets/custom_agents.py:26`); a test ties the JS
constants to that Python constant rather than restating it.

### One system, not two

The switcher is the existing "App design" surface, and the UI selection lives in
the same binding configuration as `turn_consumer`, read and written through
`AppLayout`'s existing read-back-and-CAS helpers. The layout editor keeps
working; a user with no bundle sees exactly what they see today.

### Deferred, and named so it is not mistaken for shipped

Device capability negotiation, notification routing, voice handoff, multi-file
bundles with binary assets, and a real per-universe file store. A rendered
real-browser proof through `ui-test` is required before this is called
user-ready; test-harness evidence is not that proof.

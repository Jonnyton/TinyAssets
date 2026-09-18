## Context

The existing `read_graph` agents/agent and private agent_bindings/agent_binding
targets discover public definitions and the current user's installations.
`write_graph` agent publish/remix and agent_binding create/update already provide
immutable component lineage and revision-guarded private configuration.
`custom_agents.py` preserves arbitrary component kinds. The current app has no
consumer for them. Baseline63 custom-agent/interchange tests pass September18.

Read dependencies: PLAN (especially public definition/private binding, no power
user ceiling, browser-only parity), `composable-ui-experiences` proposal/design,
the September13 Fable architecture review and lead disposition in
`docs/audits/2026-09-13-harness-experience-review-handoff.md`. Those proposals
remain their authors' lanes. This is a new, bounded platform consumer reviewed
before implementation, not authority to implement the private proposals.

## Goals / Non-Goals

Goals: discover another user's layout, preview it without writes, apply it to the
same user's live app, customize/publish a remix, restore the prior/default layout,
and retain that user's conversation, draft, attachments, requests and model choice.

Non-goals: imported script/HTML/CSS execution; a new action broker; new private
data storage; provider/harness replacement; voice or phone notification expansion;
claims that this limited renderer completes whole-setup portability.

## Decisions

### Public component

Any user-named component key may contain exactly:

```json
{"kind":"tinyassets.app-layout.v1","version":1,
 "surfaces":["conversation","requests","models","status"],
 "density":"comfortable"}
```

The renderer accepts one layout component, a nonempty ordered subset of the four
unique names, and density `comfortable` or `compact`. Unknown layout fields,
duplicate/unknown surfaces, missing/ambiguous layout components or unsupported
versions are visible unsupported results, never silently equivalent execution.
Other native components remain preserved in the definition/remix; this renderer
does not execute or claim support for them. No component field can specify DOM,
HTML, code, styles, URLs, identities, resource IDs or actions. Metadata uses
textContent. Tag `tinyassets-app-layout-v1` assists discovery but is not validation.
The four names identify the current adapter's controls, not a permanent ceiling
on native component kinds or future governed renderers.

### Private installation

Use a dedicated non-serving AgentBinding with `configuration.role` equal to
`app_experience`, retaining the selected public definition in the existing
`agent_definition_id` field. Its configuration begins with schema_version/name
and role, and may contain private user configuration preserved verbatim on update.
Updates clone only the receiving user's current configuration and supply its
exact revision; they never copy another owner's binding or data.

Do not use the serving binding: its server-only provider_ref is reserved by
normal binding validation, and changing/removing it risks serving authority.
No provider binding/enable call is made by the layout consumer. The existing
universe ACL authorizes reads/writes; the client additionally fences owner/home
changes and never presents a collaborator's binding as an automatic user choice.
The authenticated `/mcp/app/me` response adds `principal_id`, derived only from
the current authenticated identity, including empty/degraded home responses.
This caller-only, no-store self projection reveals no other user's identity and
accepts no identity parameter. It grants no authority. The client compares every
binding's created_by and universe_id against that principal and current home,
requires configured status, app_experience role, and no provider_ref field.
Exactly one eligible installation can be consumed. Several eligible rows or a
saturated unpaginated 100-row list disable Apply and selection entirely. A fresh
complete list and authenticated self projection are required before every Apply;
read-back revalidates all fields, binding ID, definition ID, and revision.

Enable the layout interface after connected sign-in. An empty universe receives
no automatic layout binding, because first-time model setup currently treats
any existing binding as recovery. This preserves OpenRouter onboarding.
Reading/previewing never creates an installation. Apply creates it only after
an explicit gesture. No uncertain create/update/publish is automatically replayed;
read current state first. Read-back confirms the selected definition/revision
before the consumer reports saved. Concurrent updates retain the old layout and
show a conflict. This uses the selected private-universe control-plane custody
mode already used by AgentBinding, without expanding custody to content.

### Consumed renderer and recovery

Trusted fixed controls are moved, never reconstructed from imported markup:
conversation includes thread/composer/attachments; requests uses existing rail;
models uses existing model bar/dialog; status uses existing conversation status.
Existing closures/listeners and their governed MCP calls remain the owners of
actions and state. Moving a view neither sends chat nor answers an approval.

Retain original DOM anchors so Restore default returns every surface to its
existing position without resetting data. Keep account/sign-out, layout chooser,
critical errors and Restore default outside the configurable slots. Compact
density is one trusted class, not arbitrary CSS. Selection may hide a surface;
the always-visible restore control makes every surface recoverable. Pending
approval remains pending if its view is hidden. Voice/security notices remain
trusted and visible outside custom selection.

The fixed Layouts dialog offers public search, inspect/local live preview, apply,
surface up/down and selection controls, density, explicit public publish/remix,
and separate apply. Editing clones the full native definition, replacing only
its chosen layout component and adding its native lineage; unknown components
and metadata survive. Publication states that design metadata becomes public;
it never serializes live DOM, private configuration, messages or resource IDs.

### Implementation boundary

Prefer a separate trusted onboarding controller source included by the existing
HTML rendering path with its existing CSP nonce, plus small app markup/hooks.
No public script route is required. Coordinate app.html hooks with the lead's
connection-progress integration. Existing `MCP.callTool` performs ordinary graph
reads/writes with explicit graph_id and captured revision; no raw REST or new MCP
schema. Async loads check an epoch and the current owner/home before DOM changes.

## Risks / Trade-offs

- A layout-only binding can look like existing model setup: expose install only
  after powered sign-in; regress unchanged model serving and new-user bootstrap.
- Imported executable components may coexist: preserve them inertly, clearly
  label unsupported capabilities, and render only the exact supported component.
- Layout changes while a reply is streaming: moving the same nodes preserves
  references; test draft, queued input, attachment and response continuity.
- Multiple installations or uncertain writes: disable apply and require fresh read-back,
  no automatic mutation replay or guessed winner.
- Native DOM shape can drift: controller tests execute the actual rendered app
  hooks; desktop and phone-width visual acceptance remains required.

## Migration Plan

No migration. Absent installation retains the current app. Rollback stops
consuming the inert layout definition/binding without deleting user records.
Lead owns exact-head review, CI, deployment, canary and live two-user acceptance.

## Open Questions

Focused Fable clearance must confirm the component schema, dedicated binding,
power-only installation boundary, trusted recovery and publication distinction.
The initial Fable shape verdict was ADAPT, not final release approval. The lead
authorized completion with the stricter caller identity and ambiguity corrections
above; an exact-head independent review still gates release.

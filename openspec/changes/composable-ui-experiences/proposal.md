## Why

Users should be able to build, customize, share, and evolve an entire way of
working with their universe across their chosen devices. A command center,
gamified experience, office simulation, and earbud conversation are different
compositions over shared capabilities. Their layouts and interaction behavior
must be editable, including instance selection and phone notification routing.

## Refinement: buildable behavior through a concrete toolset

[primitives.md](primitives.md) specifies projection, view, input, action,
event-routing and device contracts, with a complete desktop/office/phone/earbud
trace. [research.md](research.md) records primary-source evidence, existing code
anchors, limits and the cross-family implementation handoff.

The harness and experience are independently replaceable compositions over the
same Node, Edge, State, Scope, Run and Trigger substrate. This proposal requires
behavioral customization and source-level remix, not only themes or layouts.

## What Changes

- Specify an inspectable, versioned experience composition with replaceable
  presentation, input, state binding, action, and event-routing components.
- Require first-party experiences to use the same authoring and runtime contracts
  available to users, with no privileged instance-control path.
- Separate shareable definitions from private installation bindings and live state.
- Define device capability negotiation, continuity, revision conflicts, and
  explicit preview/activation behavior.
- Bound the first implementation proof to one experience remixed between a
  desktop view and a phone view, with voice and notification handoff scenarios.

This is a proposal for review, not an implemented UI builder. The public format
and private binding contract need shape review before implementation.

## Capabilities

### New Capabilities

- `composable-ui-experiences`: portable, remixable interaction compositions
  rendered across device capabilities under existing universe authority.

### Modified Capabilities

None in this proposal. Implementation must add reviewed deltas to affected
existing contracts before changing their API or storage behavior.

## Impact

Owner: tiny, working through Codex. One intent: define the contract for a
user-buildable experience spanning multiple devices. One companion PR to
[portable harness proposal #3840](https://github.com/Jonnyton/TinyAssets/pull/3840);
this proposal can be reviewed independently and does not assume #3840 has landed.

Expected integration areas: native agent composition/interchange, the onboarding
app, desktop rendering, canonical conversation relay, and governed event delivery.
No new top-level MCP handle, runtime service, or fixed catalog of UI archetypes
is proposed. No runtime behavior or canonical as-built spec changes in this PR.

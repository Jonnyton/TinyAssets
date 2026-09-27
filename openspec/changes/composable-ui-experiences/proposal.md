## Why

Users should be able to build, customize, share, and evolve an entire way of
working with their universe across their chosen devices. A command center,
gamified experience, office simulation, and earbud conversation are different
compositions over shared capabilities. Their layouts and interaction behavior
must be editable, including instance selection and phone notification routing.

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

**Implementation status (2026-09-26).** The shape review settled the renderer
isolation contract, so the first slice is now built rather than proposed:
executable `tinyassets.app-ui.v1` bundles, an isolated sandboxed renderer with a
closed message bridge acting as the viewing user, an on-the-fly switcher, and
sharing through the existing publish/remix path. See design.md, "Implementation
slice: executable UI bundles". Device negotiation, notification routing and voice
handoff remain proposed only.

## Capabilities

### New Capabilities

- `composable-ui-experiences`: portable, remixable interaction compositions
  rendered across device capabilities under existing universe authority.

### Modified Capabilities

- `governed-agent-consumers`: its "SHALL NOT claim arbitrary executable UI"
  limitation is the gap this closes, so that claim is narrowed to the
  layout/turn-consumer adapter it was written about, and the private installation
  requirement now states that its reference to a public definition is optional —
  a receiver that has published nothing still has somewhere of its own to install
  into.

## Impact

Owner: tiny, working through Codex. One intent: define the contract for a
user-buildable experience spanning multiple devices. One companion PR to
[portable harness proposal #3840](https://github.com/TinyAssets/TinyAssets/pull/3840);
this proposal can be reviewed independently and does not assume #3840 has landed.

Expected integration areas: native agent composition/interchange, the onboarding
app, desktop rendering, canonical conversation relay, and governed event delivery.
No new top-level MCP handle, runtime service, or fixed catalog of UI archetypes
is proposed. No runtime behavior or canonical as-built spec changes in this PR.

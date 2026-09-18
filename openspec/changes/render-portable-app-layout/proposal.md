## Why

Public agent definitions already preserve shareable components, but the signed-in
app consumes no layout component. Users cannot apply another person's arrangement
of their own conversation, pending requests, model controls and status.

## What Changes

- Render a small declarative layout component using the app's existing trusted
  controls, with selection, ordering and comfortable/compact density.
- Discover, inspect, publish/remix and privately apply designs through the
  existing agent-definition and AgentBinding graph operations.
- Preserve conversation, model authority, private configuration and custom
  component data. Keep an independent restore-default control.
- Scope this delivery to a consumed layout MVP. Portable harness replacement,
  arbitrary executable views and whole-setup adoption remain outstanding.

## Capabilities

### New Capabilities

- `portable-app-layout`: trusted app rendering of a public declarative layout
  selected through a private, revision-guarded AgentBinding.

### Modified Capabilities

None. Existing public graph operations and binding authority remain unchanged.

## Impact

- Add caller-only `principal_id` to authenticated `/mcp/app/me`, never accepting
  a requested identity or exposing collaborator details; responses remain no-store.
  This supplies the existing private binding owner comparison, not new authority.

Owner: Codex. Branch: `codex/portable-app-layout-mvp`. One platform delivery PR.
Files: onboarding app/controller/template composition, targeted tests and plugin
mirror/provenance. No new endpoint, handle, store, grant or provider action.
This bounded platform consumer follows the September13 review's first-party
layout slice and September18 user reprioritization. It does not edit or complete
the user's proposal PR3840/3842 or private workflows.

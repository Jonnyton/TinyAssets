## Why

An unpowered user cannot find a connection removal control in the app. The existing
`remove_http` primitive deletes HTTP credentials and grants, but does not complete
the dependent provider/setup lifecycle, so guided reconnection remains recovery.

## What Changes

- Add authenticated, unpowered-safe connection inventory and disconnect controls
  in TinyAssets, composing the existing owner-scoped HTTP removal primitive.
- Fence dependent provider authority before destroying local custody; preserve
  other connections, user content, preferences and historical receipts.
- Permit explicit guided reconnection after deliberate removal, with fresh
  authority and fresh approval rather than reviving grants or replaying effects.
- State honestly that already dispatched effects may finish and that disconnect
  removes TinyAssets access, not the upstream account or its independent key.

## Capabilities

### New Capabilities

- `universe-connection-lifecycle`: owner-controlled app removal and safe reconnect.

### Modified Capabilities

None.

## Impact

Existing `remove_http`, vault/assignment lifecycle, onboarding connection control,
model setup classification and hosted bootstrap. No new MCP handle; browser-only
and connector users share the same removal primitive. No live account actions
until reviewed general fixes are deployed and end-to-end readiness is established.

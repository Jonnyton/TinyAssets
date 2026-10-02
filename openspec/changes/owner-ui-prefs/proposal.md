# Owner UI preferences follow the owner across devices

## Why

The chat cloud (#4277, founder 2026-10-02) remembers where the owner put the
chat with their agent: position, size, and whether it is open or a bubble. It
"starts out big but gets small if and when you have a command center or how you
last had it". Today it remembers that only in the browser's `localStorage`,
because the platform has no store for UI preferences. So the founder's
placement on the desktop app does not exist on a second browser, and a reinstall
or cleared storage loses it.

The brief asked for server-side persistence where an owner UI-prefs store
exists. None exists. Adding one is a new storage shape, and the repo rule is
proposal first.

## What Changes

- A new private **owner UI-preferences record** in platform state. It is keyed by
  the authenticated owner, an `agent_id` (default `main`) and a viewport class
  (`phone` | `wide`), and holds one small JSON document per key (the chat cloud's
  `{v, mode, open, bubble}` today).
- Two app routes through the owner door: `GET /app/ui-prefs` reads the caller's
  own records, and `POST /app/ui-prefs` writes one. The owner is always the
  authenticated subject; no body field names an owner.
- The chat cloud reads the server record first, keeps `localStorage` as the
  offline and failure fallback, and writes both on every placement the owner
  makes.
- Account deletion removes the owner's records (they live in a root store keyed
  by `owner_user_id`, which the schema-derived deletion sweep already covers).

Not changing: what the chat cloud does, its defaults, or anything about the
custom-UI library (`app-ui-library`). No MCP surface changes.

## Capabilities

### New Capabilities
- `owner-ui-preferences`: a private per-owner, per-agent, per-viewport-class UI
  preference record, read and written only by its owner through the app, and
  deleted with the account.

### Modified Capabilities
- `onboarding-web-app`: once #4277 is on main, its chat-cloud requirement's
  persistence clause changes from "this device" to "the owner's record, with
  this device as fallback". That delta is written at apply time (task 4.3),
  because the requirement is not on main yet.

## Impact

- New root store `.owner_ui_prefs.db` (registered in
  `tinyassets/storage_accounting.py` ROOT_ENTRIES), with a module
  `tinyassets/storage/owner_ui_prefs.py`.
- `tinyassets/onboarding/__init__.py`: two route registrations and handlers
  (identity-gated like `/app/notify`).
- `tinyassets/onboarding/app.html`: the chat cloud's load/save gain the server
  read and write.
- Tests: the store, the routes (owner isolation, size bound, refusals), account
  deletion, and the app's server-first, local-fallback order.

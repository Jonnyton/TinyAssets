# Design: owner UI preferences

## Context

- The chat cloud (#4277) keeps `{v:1, mode, open:{x,y,w,h}, bubble:{x,y}}` in
  `localStorage` under `app.chatCloud.v1:<owner>:<agent>:<viewport>`.
- Per-owner platform state already lives in root stores keyed by the owner, for
  example `.owner_devices.db` (`tinyassets/storage/owner_devices.py`) with its
  `owner_notify_settings` table. Per-universe platform state does not belong
  inside the provider-writable universe directory (concern filed in #4258), so
  this store sits at the data root.
- Account deletion sweeps every root `*.db` and deletes rows by the principal
  columns in `PRINCIPAL_KEYS` (`tinyassets/account_deletion.py`), which includes
  `owner_user_id`. A store keyed that way is deleted with the account without
  being named anywhere.
- App routes are identity-gated by `_app_identity_required()` and take the
  owner from the resolved identity (`tinyassets/onboarding/notifications.py`
  is the pattern).

## Goals / Non-Goals

**Goals:** the owner's chat-cloud placement follows them to any browser or app
install they sign into, per viewport class; it is private to them; it goes away
with their account; the app still works offline or when the route fails.

**Non-Goals:** syncing in real time between two open devices (last write wins on
the next load is enough); a general settings system; anything an agent or a
custom UI can read or write; preferences for other people.

## Decisions

### D1. One table, one row per (owner, agent, viewport, key)

```
CREATE TABLE owner_ui_prefs (
  owner_user_id TEXT NOT NULL,
  agent_id      TEXT NOT NULL DEFAULT 'main',
  viewport      TEXT NOT NULL CHECK (viewport IN ('phone','wide')),
  pref_key      TEXT NOT NULL,          -- 'chat_cloud' today
  value_json    TEXT NOT NULL,
  updated_at    REAL NOT NULL,
  PRIMARY KEY (owner_user_id, agent_id, viewport, pref_key)
);
```

`pref_key` keeps the record from being chat-cloud-only without inventing a
settings system: a later per-agent preference is a new key, not a new table.
`owner_user_id` is the column name on purpose: it is in `PRINCIPAL_KEYS`, so
the deletion sweep covers it.

*Alternative rejected:* a column on `owner_notify_settings`. Different lifecycle
and size, and it would couple notifications to layout.

### D2. Values are bounded and validated per key

The server accepts only known `pref_key`s (`chat_cloud`). The body is at most
2 KiB of JSON, and for `chat_cloud` it is validated to the same shape the page
parses (`v == 1`, `mode` open or bubble, finite numbers). Anything else is a 400
with a reason. This is a preference, not storage: it cannot be used to park
data.

### D3. Routes through the owner door, owner from identity only

- `GET /app/ui-prefs?agent=<id>&viewport=<class>` returns
  `{"prefs": {"chat_cloud": {...}}}` for the caller, or `{"prefs": {}}`.
- `POST /app/ui-prefs` with body `{agent, viewport, key, value}` upserts the
  caller's row and returns `{"saved": true}`.
- No body or query field names an owner. A different owner's row is
  unreachable: every statement binds `owner_user_id` from the authenticated
  identity. `agent` is validated as a short id (`main` or a custom agent id),
  never resolved to anything.

### D4. The page: server first, local fallback, write both

On `refreshChatCloud` the page uses the server record when the read succeeds,
and the `localStorage` copy when it fails or is offline. On each placement it
writes `localStorage` immediately and posts the server record afterwards, so the
local copy stays valid if the post fails. The page never blocks on the server:
the cloud lays out from the local copy, then corrects once if the server
answer differs, and never after the owner has started dragging.

### D5. Deletion and accounting

Registered in `ROOT_ENTRIES` as "platform: owner UI preferences". Account
deletion covers it through the schema-derived sweep. A test deletes an account
and asserts the rows are gone and another owner's rows remain.

## Risks / Trade-offs

- **Two devices placing the cloud at once:** last write wins at the next load.
  Acceptable for a layout preference.
- **A late server answer moving the cloud under the owner's hand:** D4 applies the
  server value only before the first owner gesture of the page.
- **Store growth:** at most two viewport rows per agent per key per owner, each
  under 2 KiB.

## Migration Plan

Additive: a new root store and two routes. Existing `localStorage` copies keep
working, and the first placement after deploy writes the server record.
Rollback deletes the routes and leaves the page on its local copy.

## Open Questions

None. Per-viewport keys, owner-door routes and deletion through the existing
sweep follow established patterns.

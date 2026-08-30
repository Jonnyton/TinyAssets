# Owner controls on schedule rows reach the handler from the owner's own session

## Why

`#2690` gave every schedule row an owner and made `pause_schedule` / `unpause_schedule` /
`unschedule_branch` refuse anyone without a current admin ACL on the row's universe. Live on
2026-08-30 (production `0ac34796`, founder session in the web app) the founder registered a
schedule with `schedule_branch` and could not remove it: the three undo actions sat in
`_EXTENSIONS_ADMIN_ACTIONS` (`tinyassets/auth/provider.py`), so the OAuth scope gate refused
`Missing OAuth scope: tinyassets.extensions.admin` before the handler's check ever ran. Production
grants every authenticated founder coarse `costly` (`tinyassets/auth/workos_provider.py`) and keeps
platform `admin` explicit, so the only people who could stop a schedule were platform admins — not
the user whose subscription runs it. `docs/concerns/2026-08-30-owner-cannot-pause-or-delete-own-schedule-from-app.md`.

## What Changes

- `pause_schedule`, `unpause_schedule`, `unschedule_branch` move to `_EXTENSIONS_COSTLY_ACTIONS`, the
  tier of the `schedule_branch` they undo. Their `effect`, OAuth metadata scope and `cost_tier`
  become `costly`; they were already in the mutation `extension_writes` set. No budget, billing,
  rate-limit or advertised-scope change (Protected Resource Metadata advertises OIDC scopes only).
- Authorization is unchanged and is the handler: `_schedule_control_context`
  (`tinyassets/api/runtime_ops.py`) requires an authenticated request-local identity and a CURRENT
  admin ACL on the row's own universe. A revoked owner is refused; a delegated universe admin is
  accepted; a legacy row whose `owner_actor` cannot establish a universe is refused for everyone.
- This is a permission-tier change on an AUTHORITY path, built before its proposal under the
  delivery rule "build it, prove it live, write the spec from what shipped"; the delta below is
  that spec, synced and archived in the landing PR.

## Capabilities

### Modified Capabilities

- `user-owned-automations` — ADDED requirement pinning the two-layer contract for schedule
  controls: coarse scope admits the call, the handler's current-admin check authorizes it.

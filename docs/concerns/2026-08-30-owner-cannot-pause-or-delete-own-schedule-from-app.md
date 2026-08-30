# An owner can register a schedule from the app but cannot pause or delete it

**Filed:** 2026-08-30 (found during the live proof of `user-owned-automations` 2.2) ·
**Verified:** 2026-08-30T02:26Z, founder session in the web app against production `0ac34796` ·
**Severity:** P2 — the owner control that `#2690` built is unreachable from the surface owners use

## Source (verbatim)

`schedule_branch` from the founder's web-app session (`MCP.callTool("extensions", {...})`,
2026-08-30T02:24:45Z) succeeded:

```json
{"status":"scheduled","schedule_id":"9a331b73-b28b-41b6-b900-8019e5eef446","branch_def_id":"44d9cf94ee25","universe_id":"u-01kxm1vszd8hwp7em418asq8h9","cron_expr":"","interval_seconds":300}
```

`unschedule_branch` from the same session, 2026-08-30T02:26:53Z, was refused before the owner
check ran:

```json
{"error":"Missing OAuth scope: tinyassets.extensions.admin for action extensions.unschedule_branch (user=user_01M160DTZ9AQS64FNR224RMEV7, capabilities=['read', 'write', 'costly', 'submit_request', 'list'])","auth_scope_required":true,"tool":"extensions","action":"unschedule_branch"}
```

## The finding

`tinyassets/auth/provider.py` places `schedule_branch` and `subscribe_branch` in
`_EXTENSIONS_COSTLY_ACTIONS` but `pause_schedule`, `unpause_schedule`, and `unschedule_branch`
in `_EXTENSIONS_ADMIN_ACTIONS`. The admin set maps to the `tinyassets.extensions.admin` OAuth
scope, which an ordinary founder session does not carry (its capabilities are
`read, write, costly, submit_request, list`).

That split predates `#2690`. Before it, schedule rows had no owner, so "only an admin may delete a
schedule" was the only safe rule. `#2690` gave every row an `owner_principal_id` and made
`_action_pause_schedule` / `_action_unpause_schedule` / `_action_unschedule_branch`
(`tinyassets/api/runtime_ops.py`) refuse anyone but the row's owner or a universe admin. The
scope gate now sits in front of an owner check that already does the work, and it is the coarser
of the two: an owner can create a recurring run on their own subscription from the app and then
cannot stop it from the same app.

The automations surface does not have this problem: `write_graph target=automation
operation=pause|resume|delete` rides the `write` capability and relies on the row-owner check in
`tinyassets/api/automations.py`.

## What would fix it

Move `pause_schedule`, `unpause_schedule`, and `unschedule_branch` from
`_EXTENSIONS_ADMIN_ACTIONS` to `_EXTENSIONS_COSTLY_ACTIONS` (the same tier as the registration
they undo), keeping the owner-or-admin check in the handlers as the authority. `tinyassets/auth/`
is an AUTHORITY path: the change needs the Codex exact-head receipt
(`Drain-Review-Verdict` / `Drain-Review-Head` / `Drain-Review-Artifact`) and a test that drives the
real scope resolver with a `costly`-only principal against a row it owns (accepted) and a row it
does not (refused) — not a monkeypatched capability set (see
`.claude/agent-memory` note "env-var identity switching is a no-op").

## Why it was not fixed in the lane that found it

The lane was a documentation close-out of a landed change; an authority-path edit needs its own
branch, its own cross-family review, and the scope-guard receipt.

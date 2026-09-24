# Non-Source event subscriptions are stored but never fire

**Filed:** 2026-09-02, from Codex's review of the status-truth change (T2), as
"event subscriptions fire without the owner's identity".
**Re-verified and narrowed:** 2026-09-24 at `origin/main` 7d567926, by reading
the source (change `served-inbound-webhook-triggers`).
**Severity:** P3. No user has a subscription today: production
`branch_subscriptions` holds zero rows (read-only, 2026-09-24).

## What was resolved

The identity half no longer holds. A Source event now carries the hook
owner's principal (`webhook_inbound._emit_source_event`,
`SchedulerEvent.owner_principal_id`). The scheduler passes that principal to
the run function (`scheduler.py` event loop, `principal_id=event.owner_principal_id`).
`_inbound_event_run_fn` (`universe_server.py`) refuses a non-`universe:` actor
or an empty principal. An event cannot run as nobody.

## What remains

`VALID_EVENT_TYPES` (`scheduler.py`) admits `canon_change`,
`branch_run_completed`, `canon_upload` and `pr_open`, and
`_action_subscribe_branch` (`api/runtime_ops.py`) registers subscriptions to
them. **Nothing in `tinyassets/` emits any of them.** `emit_event` has exactly
one caller, the Source path. A subscription to those types is stored and never
fires. This is the silent-storage failure that Hard Rule 8 and the
`user-owned-automations` "a registration that cannot fire is refused loudly"
requirement forbid. If an emitter were added, its events would also carry no
owner, and `_inbound_event_run_fn` would refuse them.

## The fix

Choose one:

- Refuse registration of the four un-emitted types with a named reason, and
  keep `source:<id>` as the one event trigger.
- Wire a real emitter that stamps the owning universe's principal.
  `branch_run_completed` is the one with a clear use: "run B when A finishes".

The first option is the smaller and more honest change. The second belongs to
whoever builds run-completion chaining.

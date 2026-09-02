# Event subscriptions fire without the owner's identity

**Filed:** 2026-09-02, from Codex's review of the status-truth change (T2).
**Severity:** P2 — a graph a user wires to an event (a Source, a
`branch_run_completed`, a canon change) fires on the scheduler's event thread
with no `principal_id`, so provider binding falls back to that thread's
anonymous request identity instead of the universe owner's serving
provider. Automations and schedules carry the owner explicitly; subscriptions
do not.

## The finding

`tinyassets/scheduler.py` (the event-thread dispatch, ~`:1291`) calls the run
function without `principal_id`. `tinyassets/api/runs.py` (~`:89`) then
resolves the provider from the current request identity, which on that thread
is anonymous. Schedules go through the owner-bound path
(`register_schedule(owner_principal_id=...)`, `_run_fn` with the principal);
subscriptions (`register_subscription`) have no `owner_principal_id` column at
all (`branch_subscriptions` schema, `scheduler.py:~326`).

## Why it matters for the agnostic goal

Inbound events are how a user's universe reacts to the outside world 24/7
(Slack events, Stripe webhooks, a Source's `source:<id>` event). If the graph
they wire to an event does not run as them, it runs as nobody, and the "your
own compute" promise breaks at exactly the trigger the founder described as
"nothing special".

## The fix

Give `branch_subscriptions` an `owner_principal_id` (and `universe_id`) like
`branch_schedules`, record it at `register_subscription` from the
authenticated caller, and pass it through the event thread's run call. Until
then the status text must not claim subscriptions fire on the owner's
provider; it names automations and schedules only.

## Also from the same review

When this loop finds no audience it skips the whole legacy pump, including
terminal receipt reconciliation for legacy control tasks
(`assigned_queue_consumer.py` `:318`, `:963`), not just their execution. That
is more reason to delete the loop than to describe it.

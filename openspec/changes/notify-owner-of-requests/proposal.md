# A request reaches the owner on their devices, and holds several answerable items

## Why

The requests system is already the general "the universe asks its owner
something and waits" primitive (`tinyassets/storage/pending_requests.py`,
founder 2026-08-27). Its own module docstring names the two things it never
got:

> "it should also have a way for it to be a **notification on the phone** and
> addressible from there also"

and

> "A phone *notification* additionally needs device registration, which does
> not exist yet."

A grep confirms it: there is no device registry, no push transport, and
`mobile/package.json` has no `@capacitor/push-notifications`. So a request is
only ever seen by an owner who happens to open the app. A universe that wants
to reach its person has nothing to reach them *with* — the founder's universe
built a "Morning focus note" branch (`ef8d1f6bec0f`) and then stopped on
exactly this, raising a card that said its saved run "won't make the note show
up".

The second gap is shape: one request is one question with one answer. A note
listing six things to do today is six answers. Today that is six tabs in the
rail, which destroys the grouping that made it a note.

This change closes both gaps **inside the existing requests system**. It adds
no new primitive: the morning note is then something a universe builds itself —
an automation whose run raises one request carrying task items. Nothing in this
change knows what a morning note is.

## What changes

**1. A request may carry items.** `write_graph target="pending_request"
operation="ask"` accepts an optional `items` list, each with an agent-chosen
stable `item_id`, a title, a body and its own fields. The owner answers the
whole request, or one item at a time; the request stays pending until it is
answered as a whole or every item is resolved. Item answers flow through the
existing `answer_request` path and read back through the existing
`read_graph target="pending_requests"`.

*The rule that keeps "however he likes" safe is unchanged and extended:* a
`secret` field is only permitted on a deposit request, and **an item never
carries a `secret` field at all**. A request with items must have
`action.type == "answer"`, so an item can never be the thing that deposits a
credential or widens a grant.

**2. A request is delivered to the owner's registered devices.** A per-user
device registry (`owner_sub` from the authenticated request, never from a
payload), an owner on/off control, and a dispatch path that pushes a bounded
notification when a *genuinely new* request is raised — from a chat turn or
from a background run — and a silent clear to the owner's *other* devices when
it is answered there. Android via FCM, browser/desktop via web push. The
transport is a server-owned callback: no caller supplies a token, URL,
credential or destination. No usage meter and no rate limit: one notification
per request per device, `MAX_PENDING` bounds the pile, and the runs that raise
requests hold the seats that are the account limit.

**3. The notification is answerable.** Its data carries the request id (and the
item ids), so tapping opens the app at that request. Android carries
`Accept` / `Deny` / `Reply` actions; `Reply` takes typed text inline.
Per-item answers are in the app view — Android allows three notification
actions, which a multi-item note exceeds by construction.

**4. A background run raising a request is a tested contract.** The engine
surface already exposes `write_graph target="pending_request" operation="ask"`
and a branch run already binds the owner (`permissions.owner_run_identity`), so
this is believed to work today and has no test. This change tests it and fixes
it if it does not, because it is the path the whole feature rests on.

## Scope boundary

Not in scope, and deliberately: any morning-note automation, template or seed;
a platform-composed notification body (the agent composes the words, the
platform composes the identity); any notification to anyone but the request's
own owner; a device-scoped credential that would let a notification action
answer without the app's own session.

## Impact

- Specs: `live-mcp-connector-surface` (items on the ask, `item_id` on the
  answer), `user-owned-automations` (`pending_request_answered` carries
  `item_id`), new capability `owner-request-notifications`.
- Code: `tinyassets/storage/pending_requests.py` (items + per-item answers),
  `tinyassets/api/pending_requests.py` (validation, answering, dispatch seam),
  new `tinyassets/storage/owner_devices.py`, new
  `tinyassets/owner_notifications.py` + `tinyassets/notify/` transports,
  `tinyassets/automation_events.py` (one filter key), app routes and rail UI
  under `tinyassets/onboarding/`, `mobile/` (Capacitor push plugin + Android
  reply action); plugin mirror + tests.
- Two PRs. Slice 1 is server-side and route-free so it does not collide with
  the in-flight app-URL move (#4112). Slice 2 adds the `/app` routes, the
  service worker, the rail UI and the native release, and depends on #4112.
- Founder ask: FCM needs a Firebase project on the founder's Google account
  (`docs/host-actions.md`). Web push needs nothing — it is self-issued VAPID —
  so the whole chain can be proven live before Firebase exists.

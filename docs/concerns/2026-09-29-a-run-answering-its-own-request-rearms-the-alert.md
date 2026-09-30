# A run answering its own request re-arms the notification latch

Found by `gpt-6-astra` on PR #4122 (`notify-owner-of-requests` slice 1), round
1, and **partly** fixed there. This is the part that is not fixed.

## What is bounded now

Notification volume is bounded by three things, all verified:

- the delivery key is the **ask** (a digest of the request's dedupe key), not
  the request id, so an identical ask/withdraw/re-raise loop delivers once —
  astra reproduced 101 pushes from 101 cycles before this;
- **one outstanding alert per device** (`device_alert_latch`), so a loop that
  varies the ask cannot storm either;
- withdrawal neither pushes nor re-arms, so the agent cannot reset the latch by
  taking back its own ask.

## What is not

The latch is released when the request it holds is **resolved**
(`owner_notifications.clear_request`), and a background run bound by
`permissions.owner_run_identity` can answer its own request, because it acts as
the owner and `answer_request` correctly admits the owner. So a run can cycle:
raise (1 push) → answer itself (1 silent clear, latch released) → raise a
*different* ask (1 push) → ... at two pushes per cycle, unbounded, with the
owner never engaging.

`tests/test_owner_notifications.py::test_answering_rearms_the_device` pins the
release; nothing pins that it should not be reachable from a run.

## Why it is not fixed here

The fix needs a signal the platform does not currently have: **whether the
identity resolving a request is a live person or a background run acting as
them.** `owner_run_identity` happens to bind a narrowed
`capabilities=["read", "list"]`, but inferring "this is a background run" from
that is deriving identity from adjacent state — the class of mistake that has
already cost this repo real bugs. The honest version is an explicit
background-bound marker set by `owner_run_identity` itself, which is a change
to `tinyassets/api/permissions.py` — authority-path code that deserves its own
lane and its own review, not a fourth round on this PR.

## The fix when it is taken

1. `owner_run_identity` sets an explicit contextvar marking the identity as
   background-bound, and `permissions` exposes reading it. This is useful well
   beyond notifications.
2. Latch release requires either a device-attested acknowledgement
   (`owner_devices.acknowledge_alert`, which a run cannot produce because it
   has no device and no `/app` route) or a resolution from an identity that is
   **not** background-bound.
3. A run's own resolution still clears the notification from the devices — the
   person should not be left looking at a stale alert — it just does not
   re-arm them.

Acceptance: a loop of raise → self-answer → raise delivers **one** push, and a
real owner answering in the app still receives the next request's notification.

## Severity

Not a cross-user or data-loss floor: every push still goes only to the
request's own owner, and nothing leaks. It is a nuisance-cost bound that an
owner's own agent can defeat, on a surface that is **dark** until slice 2 ships
the device-registration route — so no user can be affected before the fix lands.

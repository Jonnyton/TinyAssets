# Tasks: notify-owner-of-requests

Two PRs. Slice 1 (1.x, 2.x) is route-free and native-free so it does not
collide with the app-URL move (#4112). Slice 2 (3.x) depends on #4112.

## 1. Slice 1 — items and the delivery core

- [x] 1.1 Items: `items_json` (via `_ADDED_COLUMNS`) and
      `request_item_answers`; `_validated_items` on the ask (id pattern,
      uniqueness, bound of 50, no `secret` field, `action.type == "answer"`
      only); `item_id` on the answer path, resolving once, closing the request
      on the last item, reporting the rest unanswered; projections join item
      state; `item_id` joins `EVENT_FILTER_KEYS[pending_request_answered]`.
- [x] 1.2 Device registry: `tinyassets/storage/owner_devices.py` — owner-derived
      subject, token-moves-on-reregistration, retirement, the per-owner on/off
      setting, and the content-free `request_notifications` ledger.
- [x] 1.3 Dispatch + transports: `tinyassets/owner_notifications.py`
      (server-composed identity, bounded agent body, no field values,
      idempotency on request/item/device/kind, bounded failure classes,
      `no_transport` degrade, the `clear` to other devices; no usage meter and
      no rate limit) over a server-owned callback, with `tinyassets/notify/fcm.py`
      (HTTP v1, service account from the secret loader),
      `tinyassets/notify/webpush.py` (self-issued VAPID) and the test fake.
- [x] 1.4 Wire the seams: `request_from_user` dispatches on a genuinely new
      pending row only (not a dedupe hit, not a settled reply), carrying the
      owner from `_owner_gate`; the answer paths dispatch the clear.

## 2. Slice 1 — prove

- [x] 2.1 Tests through the real handlers with real stores: items end to end,
      the credential boundary on items, per-item answer routing and the
      last-item close, and a background run raising a request under
      `owner_run_identity` (the contract nothing tests today).
- [x] 2.2 Tests for delivery, with push dispatch exercised at the HTTP layer
      against a fake FCM transport: cross-user refusal, the account-switch
      token move, request content cannot select a destination, identity is
      server-composed, no field value in a payload, notifications-off,
      dedupe-does-not-renotify, idempotent retry, gone-device retirement,
      `no_transport`, and the clear.
- [x] 2.3 Mutation-check the owner gate, the token move, the secret-in-item
      refusal, the item-resolves-once guard, the new-row-only dispatch gate,
      the identity composition, and every round-1 fix. **35 of 36 went red**;
      the only green was a comment-only decoy. Informative greens along the
      way, all now closed:
      - the store-layer "is this item on this request" check (the API layer
        refuses the same input first) — `resolve_item` is a public store
        function and now has its own test at that layer;
      - three round-2 guards were masked by a sibling guard, so no test could
        tell them apart: the claim-time token (the ownership re-check already
        refused the send), the ask-keyed delivery (the latch already stopped
        the loop), and the clear-only-holders rule. Each now has a test that
        isolates it — re-registration refreshes a row in place so a token can
        change under a live device id; acknowledging between cycles releases
        the latch so only the ask key is left; a device registered after the
        alert holds nothing;
      - three had no test at all: the moved handset's latch, owner-scoped
        acknowledgement, and clears reaching devices that never got the alert.
- [x] 2.4 `gpt-6-astra` refute round on cross-user delivery, spoofing and
      runaway notification cost. **Round 1: REJECT**, six
      `DISAGREE_EVIDENCE` findings, each reproduced. All six fixed, each with
      the test that would have caught it:
      1. a web subscription could alias past an ownership move (identity
         hashed the whole document, not the endpoint the transport addresses);
      2. dispatch sent to a snapshot, so a handset reassigned mid-dispatch got
         the previous owner's title;
      3. 101 ask/withdraw cycles = 101 pushes (delivery keyed on the request
         id, which is fresh per row);
      4. a 50-item note cost 51 pushes per device (a clear per item);
      5. the unnamed-universe title fallback was the bare product name, so an
         ask could read as a platform notice;
      6. the "exception leaks nothing" test never checked the log, where
         `exc_info=True` put a bearer token.
      Plus a dedupe-key migration finding: appending an empty item list to
      every key broke existing pending rows and standing decisions.
      **Round 2: REJECT**, five more `DISAGREE_EVIDENCE` — two of them defects
      the round-1 fixes introduced, which is the loop AGENTS.md warns about.
      All fixed:
      1. the endpoint was hashed verbatim, so a URL fragment, host case or the
         default port still aliased one destination into two;
      2. the digest namespace was shared across platforms, so an FCM token
         spelling a web endpoint deleted that web device and its latch;
      3. **(introduced in round 1)** the latch was written before the replay
         check, so a replayed raise left a phantom latch and the device went
         quiet;
      4. `retired_reason` persisted transport text, readable back from
         `list_devices`;
      5. the title claim was too strong — a soul-learned universe name is
         agent-influenced, and invisible or suffix-doubling names rendered;
      6. **(introduced in round 1)** composition bounded characters while the
         web-push record is bytes, so accepted emoji input exceeded it and was
         refused at the transport — the notification was simply lost;
      7. item answers returned before `displayed_row_matches`, so an edited
         itemised row could still be answered.
      Astra AGREED that claim-time ownership, the fifty-item clear fix and the
      itemless dedupe compatibility all hold.
      Two residuals filed, not fixed:
      `docs/concerns/2026-09-29-a-run-answering-its-own-request-rearms-the-alert.md`
      and `docs/concerns/2026-09-29-a-universe-can-name-itself-anything.md` —
      the second belongs to the naming lane, because the only place to fix it
      is where a display name is accepted, with its provenance in hand.
      **Round 2 is the second of three. One round remains.**

## 3. Slice 2 — surfaces and the native release (depends on #4112)

- [ ] 3.1 App surface: `/app` routes for device register / list / retire, the
      notification on/off and the service worker — each added to #4112's
      enumerated `_is_app_path`, with a negative test that a new app route
      never answers anonymously; and the rail rendering items as a checklist
      with per-item Accept / Deny / Reply, a `?request=<id>` deep link, and the
      on/off row listing the owner's own devices.
- [ ] 3.2 Native: `@capacitor/push-notifications`, a committed Java plugin plus
      `mobile/scripts/configure_android_push.py`, `google-services.json`
      materialised from a secret and never committed, tap-through to
      `/app?request=<id>`, and Accept / Deny / Reply actions that submit
      through the app's own session. Desktop allows only the `notifications`
      permission for the app origin.
- [ ] 3.3 Deploy, then `python scripts/deployed_sha.py --assert-contains <sha>`
      and `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
      --assert-handles`. Live proof: the founder's universe wires its own
      morning note to request items and answers it from the phone.

## 4. Land

- [ ] 4.1 Sync the three deltas into `openspec/specs/`, then archive.

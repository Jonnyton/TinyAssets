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
      refusal, the item-resolves-once guard, the new-row-only dispatch gate and
      the identity composition. **21 of 22 went red**; the only green was a
      comment-only decoy. The first pass had one real green — removing the
      store-layer "is this item on this request" check, because the API layer
      refuses the same input first — so `resolve_item` is a public store
      function and now has its own test at that layer.
- [ ] 2.4 `gpt-6-astra` refute round on cross-user delivery, spoofing (can
      anything make a notification look like it came from the platform or
      another user?) and runaway notification cost. Fold the verdict in; max
      three rounds.

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

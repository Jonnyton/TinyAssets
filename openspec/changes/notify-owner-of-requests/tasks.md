# Tasks: notify-owner-of-requests

Two PRs. Slice 1 (1.x, 2.x) is route-free and native-free so it does not
collide with the app-URL move (#4112). Slice 2 (3.x) depends on #4112.

## 1. Slice 1 — items and the delivery core

- [x] 1.1 Items, the device registry, dispatch + transports, and the seams --
      all landed in #4122. Items: `items_json`, `request_item_answers`,
      `_validated_items` (id pattern, uniqueness, 50 bound, no `secret`,
      `answer` actions only), `item_id` on the answer path, and `item_id` as a
      `pending_request_answered` filter key. Delivery:
      `storage/owner_devices.py`, `owner_notifications.py`, `notify/fcm.py` +
      `notify/webpush.py` over a server-owned callback, wired at
      `request_from_user` (new rows only) and the resolution seam.

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

      Two rounds ran and **both returned REJECT**, the second finding defects
      the first round's fixes had introduced. Slice 1 merged (#4122) before
      either verdict was folded in, so **main carries the reviewed-and-rejected
      code** and the findings became fixes to landed behaviour. Lead's call:
      split, and simplify the delivery half rather than review it again.
- [x] 2.5 Items fixes on landed code, scoped to items (this PR): an itemless
      request keeps its original five-element identity, so live pending rows
      still deduplicate and standing decisions still match; and an item answer
      goes through `displayed_row_matches`, which it previously returned before
      reaching. Both were reproduced by `gpt-6-astra`.
- [x] 2.6 Delivery, simplified (separate PR, depends on this one). The
      per-device outstanding-alert latch is dropped: it is a rate limiter in
      disguise, and account limits are seats and storage only (founder,
      2026-09-30). Delivery is one notification per
      `(request_id, item_id, destination, kind)` with the ledger primary key as
      the only dedupe, claimed inside the send transaction; cost is bounded by
      seats and `MAX_PENDING`, and ask/withdraw churn is the agent's own seat
      time. Carries the review fixes that stand on their own: endpoint
      canonicalisation, platform-namespaced destination digests, byte-budgeted
      payloads, closed-set `retired_reason`, title sanitisation, and the
      claim-time destination re-verification. One fresh astra round.

## 3. Slice 2 — surfaces and the native release (depends on #4112)

- [x] 3.1 App surface: `/app` routes for device register / list / retire, the
      notification on/off and the service worker — each added to #4112's
      enumerated `_is_app_path`, with a negative test that a new app route
      never answers anonymously; and the rail rendering items as a checklist
      with per-item Accept / Deny / Reply, a `?request=<id>` deep link, and the
      on/off row listing the owner's own devices.
      Browser slice: permission + subscription registration, exact app click
      navigation, request/item deep links, item answers through the existing
      answer path, status-only poll updates preserving drafts, and clear handling.
      Native Android and Electron delivery remain in 3.2, a separate PR.
- [x] 3.2 Native Android (this PR; Electron desktop permission is still open):
      `@capacitor/push-notifications`; `TinyAssetsMessagingService` draws the
      notification from the server's DATA-ONLY FCM message (so it can carry an
      inline Reply) and cancels it on a silent clear; a tap opens
      `/app?request=<id>[&item=<id>]`; a Reply's text is handed to the page by
      `NotificationReplyPlugin` and submitted through the app's own session --
      no device-scoped credential, and the exported `MainActivity` only honours
      a Reply carrying a per-install secret. The phone POSTs its FCM token to
      `/app/devices` as platform `fcm` (filed under `android`). `google-services.json`
      is materialised from `ANDROID_GOOGLE_SERVICES_JSON_B64` by
      `mobile/scripts/materialize_google_services.py` and never committed;
      unconfigured builds succeed with push disabled. Founder steps:
      `docs/host-actions.md`. Desktop allows only the `notifications` permission
      for the app origin -- not done here.
- [ ] 3.3 Deploy, then `python scripts/deployed_sha.py --assert-contains <sha>`
      and `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
      --assert-handles`. Live proof: the founder's universe wires its own
      morning note to request items and answers it from the phone.

## 4. Land

- [ ] 4.1 Sync the three deltas into `openspec/specs/`, then archive.

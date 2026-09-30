# PR #4138 browser request notifications review

Reviewed commit: `6df104a5d812412115e02e050982bbeada44cf86`.
Reviewer: Claude fable through `scripts/peer_agent.py`, read-only, one round.
Verdict: **ADAPT**, not an approval receipt for the corrected head.

## Disposition

- **AGREE**: a notification click can reject when navigating an uncontrolled
  window. Added activation-time `clients.claim()` and an `openWindow` fallback
  on navigation rejection. The regression test exercises the rejected promise.
- **AGREE**: polling a pending item must not re-enable its in-flight answer.
  Status painting now only disables controls; the answer handler owns pending
  button state. The regression test preserves a disabled pending item's button.

No floor finding was reported. Native Android, Electron delivery and deployment
remain outside this browser slice. A published exact-head approval is still
required by the PR scope guard; this ADAPT report is not represented as APPROVE.

## Verification

- 220 app/account tests passed before the final review corrections.
- 212 delivery/browser tests passed before the final review corrections.
- 71 affected browser, route, rail and layout tests passed after corrections.
- Ruff passed on every changed canonical Python file and test.
- Four key-gate mutants were killed: all-app anonymous carve-out, prefix worker
  exception, substituted registration subject, and disabled browser account fence.
- Local real Chromium registered and activated the worker under the actual app
  CSP with `/app` scope. A 390px rendered app check kept draft focus through an
  item resolution poll, kept all action buttons inside the rail and disabled
  resolved-item controls, with no page errors. These are local checks, not a
  production push delivery or real-user proof.
- No production environment or keys were changed. Both plugin mirror and brand
  receipt were regenerated.

## Peer report (verbatim)

I'll diff HEAD against origin/main, then read the canonical files in the named scope areas.

Reading the remaining pieces of the item-answer path now: the client helpers and the server answer handler.

Now checking the last dependencies: how the pending list serializes item status, what a second answer to the same item returns, and what the OAuth decorator does with an item-shaped request.

Review complete. Two concrete defects, one of them in the worker's click path that the test stub cannot see.

**Finding 1 (correctness, confirmed by spec): notification click is dead in the session that enabled push.**
`tinyassets/onboarding/notifications.py:81-84` calls `windows[i].navigate(target)` on every window returned by `matchAll({includeUncontrolled: true})`. A `WindowClient.navigate()` on a client the worker does not control rejects with a TypeError. The page that just registered the worker is exactly that client: the worker has no `activate` handler calling `clients.claim()`, so the tab stays uncontrolled until reload. Trigger: turn notifications on, receive a push, click it while the same /app tab is open. Effect: `event.notification.close()` already ran, the rejected promise skips the `openWindow` fallback, and nothing opens. The user sees the notification vanish with no request focused. The test at `tests/test_app_browser_notifications.py:170` stubs `navigate` as always resolving, so it cannot catch this. Minimal correction: add `.catch(function(){ return clients.openWindow(target); })` after the `navigate(...).then(...)`, and optionally add `self.addEventListener('activate', e => e.waitUntil(clients.claim()))` so subsequent clicks focus in place.

**Finding 2 (correctness, low): a poll re-enables an item's verbs while its answer is in flight.**
`tinyassets/onboarding/app.html` in `updateRailItems` sets `el.disabled = el.id === "check_" + id || done` for every control in the item box. For a still-pending item that sets `disabled=false`, which undoes the `buttons.forEach(b=>b.disabled=true)` that `answerRail` applied before awaiting `MCP.answerRequest`. Trigger: click Accept on an item and a rail poll lands before the answer returns. Effect: a second click submits again, the store answers `item_already_resolved`, and the error overwrites the "Sent." note after a successful answer. Minimal correction: only ever disable in `updateRailItems` (`if(done) el.disabled=true;`), leaving in-flight state to `answerRail`.

**Checked and found sound:**
- `/app/sw.js` carve-out is an exact-equality test placed before the `_is_app_path` sweep, the worker body holds no key or identity, and `handle_service_worker` still honours the dark flag.
- `/app/devices` and `/app/notify` derive the owner solely from the resolved identity, pass it explicitly to the store, never return token material on GET, and treat not-found and not-yours identically on retire.
- Rebinding on login reuses the store's cross-owner token re-own rule, so a shared browser cannot keep receiving the previous owner's pushes. Sign-out unsubscribes under an epoch fence.
- `worker-src 'self'` is the correct directive given nonce-only `script-src`; `connect-src 'self'` already covers the new fetches.
- Per-item answers route through the existing answer API with `item_id`, item Deny maps to `dismiss`, values are validated against the item's declared fields, and the signature excludes item status so a poll does not rebuild the card or lose sibling drafts.
- No rate limiter introduced; the only bound is the 8 KiB body cap.

VERDICT: ADAPT

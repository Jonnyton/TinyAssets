# Upload / composer account-boundary correction — evidence

Date: 2026-09-20. Branch `codex/file-upload-release`, worktree
`wf-file-upload-release`. Base `9bec906d`. Windows 11, Python 3.11 venv, node
present (no tests skipped in the cohort).

Three concrete defects closed. Every test below was run against the UNFIXED
tree first and observed RED; the per-repro red runs are recorded here.

## 1. The composer was not part of the account boundary

`clearAccountScopedState` took the thread, the queue and the "already restored"
marks, and left the composer. With account A holding an unsent private draft and
a Send disabled by A's in-flight turn, sign-out then B left both intact: B saw
A's words and a dead button. `activeTurn` also survived, so A's `finally` still
believed it held the composer and would re-enable, re-time and rewrite B's
screen.

Fix (`tinyassets/onboarding/app.html`): `clearComposerState()` — value, height,
`btn-send.disabled`, `turnStartedAt`, `activeTurn`, status line — called from
`clearAccountScopedState`. Nothing durable is touched (asserted). The spoken
turn's `finally` now takes the same `activeTurn===myTurn` test the typed turn
already had, so a retired turn of either kind cannot alter the next account.

## 2. A late upload callback erased the recovery `abort()` had kept

Fable's finding, confirmed. `abort()` deliberately does not persist — the row
belongs to the account that made it. But a late upload/observe rejection still
reaches `abortItem` → `changed()` → `remember(records())` → `records()` is now
empty → `rememberUploadRecords([])` → `localStorage.removeItem(key)`. The
recovery is gone. After an account switch the same callback erases the NEW
pair's row instead.

Root's existing `test_upload_recovery_record_survives_pending_check_and_account_exit`
read `afterExit` BEFORE `await check`, which is why it stayed green.

Fix: `abortItem` persists only when the item was still attached (`idx>=0`).
Detached and old-identity callbacks still repaint, never write. Stored ownership
is unchanged and unweakened.

## 3. The connect gate returned before the page learned who it was

`enterSignedIn` seeded `setQueueScope`/`setQueueOwner` only on the *connected*
path. A first session — which lands on Connect by design — reached chat through
`onEngineConnected` with both halves empty, so `readUploadRecords`,
`restoreQueue` and `restoreInflight` were all no-ops: first-session recovery was
disabled entirely.

Fix: both halves are taken from the verified `/mcp/app/me` as soon as it
resolves, before the gate can return — from the authenticated `me`, never from a
caller- or provider-supplied identity. A `me` that lands after the login changed
is rejected by captured `MCP._loginEpoch` before it mutates identity. The gate's
hand-off to chat now also calls `loadHistory()`/`restoreUploadRecords()`, the
same arrival a direct sign-in gets. `setQueueScope` resets `uploadsRestored` on
a same-account home change (the row is keyed by the pair, not the owner alone).
No new authentication mechanism; no legacy row migration.

## Red / green

| Test | Unfixed | Fixed |
|---|---|---|
| `test_sign_out_takes_the_composer_with_the_rest_of_the_account` | RED | pass |
| `test_a_plain_draft_with_no_pending_send_is_cleared_too` | RED | pass |
| `test_the_previous_turns_cleanup_cannot_touch_the_next_account` | RED | pass |
| `test_the_same_account_moving_home_is_offered_the_new_homes_attachments` | RED | pass |
| `test_the_connect_gate_still_learns_the_verified_owner_and_home` | RED | pass |
| `test_connecting_at_the_gate_reaches_chat_with_its_own_state_restorable` | RED | pass |
| `test_a_me_that_lands_after_the_login_changed_stamps_no_identity` | RED | pass |
| `test_a_late_rejection_after_abort_does_not_erase_the_stored_recovery` | RED | pass |
| `test_a_late_resolution_after_abort_does_not_erase_the_stored_recovery` | RED | pass |
| `test_a_late_answer_after_an_account_switch_touches_neither_pairs_row` | RED | pass |

The abortItem three were red with ONLY the `abortItem` guard reverted; the other
seven were red with the whole `app.html` delta set aside. The four pre-existing
account-transition tests stayed green in both directions.

## Harness notes

- Distinct DOM elements: `composer-input`, `btn-send` and the fallback are three
  different objects, so no test can pass by writing one and reading another.
- The upload tests drive the page's REAL durable path
  (`readUploadRecords`/`rememberUploadRecords` over a fake `localStorage`) keyed
  by the page's own owner/home pair, not a `remember` spy. A spy proves a
  callback ran; this proves what is left on disk, for both pairs.
- The durability key is LIFTED from the page in both harnesses and executes:
  exactly one occurrence of `ta_app_uploads_v1` per generated script, declared
  before use. A copied literal would keep the assertion green against a key the
  page had stopped writing.

## Frozen runtime

    pytest tests/test_app_account_transition.py tests/test_app_file_upload_ui.py \
           tests/test_app_file_upload.py tests/test_onboarding_app.py \
           tests/test_brand_parity.py tests/test_mirror_parity_gate.py
    216 passed, 0 failed, 0 skipped (43.69s)

    ruff check tests/test_app_account_transition.py tests/test_app_file_upload_ui.py
    All checks passed

    python packaging/claude-plugin/build_plugin.py   # 496 files, probe-ok
    python WebSite/brand/render_marks.py             # receipt re-bound to app.html

`WebSite/brand/generated-assets.json` pins a hash of
`tinyassets/onboarding/app.html`, so the brand receipt moves with any app edit;
regenerating changed that one line and did not revert the delta (verified).

## Not done

No push, no deploy, no peer dispatch, no browser, no full suite — all out of
scope for this bounded lane. Root reviews this delta and obtains the bounded
Fable verification of the concrete finding and the combined head.

## Independent corroboration (read 2026-09-20, after the delta landed)

A review dispatched from the `0a7f` worktree against `579d5009`
(`output/claude-upload-root-delta-review-result.md`, finished 01:57) reaches the
same conclusions independently, from a static read plus its own node probe:

- Same defect, same smallest fix, arrived at separately: *"in `abortItem`,
  persist only when the item was still attached (`idx>=0`), otherwise
  `changed(false)`; add a test that awaits the late response after `abort()`."*
  Its probe read `{'afterAbortSync': 1, 'afterLateResponse': 0}` — the same
  erasure this delta's tests now pin.
- It names the same reason root's test could not see it: `afterExit` is measured
  before the pending promise resolves.
- It independently flags the connect-gate owner seeding ("recovery is dead until
  reload") and `uploadsRestored` resetting only on owner change. Both are fixed
  here.

That is two families on the same three findings, so the concrete finding is not
in doubt; what still needs Fable is the *fix*, not the diagnosis.

### Carried forward, deliberately not done here

Two nonblocking items from that review, re-verified against THIS head (its line
numbers had rotted — `recordFor` is now `app.html:3966`, not `3888`):

1. **`recordFor` keeps definitively-refused attempts.** Any item with a header
   and label is persisted, including one whose attempt ended in a
   non-retryable 4xx. After a reload those return as "check it" chips that can
   only fail again. Noise, not a leak, and outside this bounded correction.
2. **The legacy unscoped key is orphaned.** Every read and write is
   `UPLOAD_RECORDS_KEY + ":" + JSON([owner,scope])` (`app.html:3921`, `3931`);
   nothing reads or removes the bare `ta_app_uploads_v1`, so a pre-upgrade row
   (filename, size, sha, header) stays in localStorage forever. Migrating
   unknown-owner legacy rows was explicitly excluded from this lane — it is a
   deletion question with an ownership answer nobody has given yet, and
   guessing one is how a row gets attributed to the wrong account.

Neither blocks this delta. Both want their own lane and a host decision on (2).

# Tasks: owner-ui-prefs

Design approval gates task 1 onward. Depends on the chat cloud (#4277) being on main.

## 1. Store

- [ ] 1.1 `tinyassets/storage/owner_ui_prefs.py`: the `owner_ui_prefs` table (D1) in root `.owner_ui_prefs.db`; `read_prefs(owner, agent, viewport)` and `write_pref(owner, agent, viewport, key, value)`, with key, size and shape validation (D2). Register in `storage_accounting.py` ROOT_ENTRIES.
- [ ] 1.2 Tests: round trip; owner isolation; refusals (unknown key, over 2 KiB, malformed `chat_cloud`), each leaving the stored value unchanged.

## 2. Routes

- [ ] 2.1 `GET`/`POST /app/ui-prefs` in `tinyassets/onboarding/__init__.py`, identity-gated, owner from identity only (D3). Rebuild the plugin mirror.
- [ ] 2.2 Tests: no identity gives 401; a body naming another owner changes nothing of theirs; the route list test includes the new path.

## 3. Account deletion

- [ ] 3.1 Test: deleting an account removes its rows and leaves another owner's rows (covered by the schema-derived sweep; no code expected).

## 4. The page

- [ ] 4.1 `app.html` chat cloud: server read first, `localStorage` fallback, write both on each placement, and no late server answer after the first owner gesture (D4).
- [ ] 4.2 Tests: Node controller (server value wins over local; failed read uses local; late answer ignored after a gesture) and one real-browser reload test that starts with a server record and no local copy.
- [ ] 4.3 Update the `onboarding-web-app` chat-cloud requirement's persistence clause. Sync this change's spec and archive on land.

## 5. Verify

- [ ] 5.1 Linux oracle on the touched suites plus `tests/test_app_*.py`, a cross-family refute, and a live check: place the cloud on the desktop app, then open the web app at the same width and see the same placement.

# Tasks: notification-is-the-setup (Slice 6)

Owner: claude-code. One PR. Tier 2 (see proposal). Cross-family review owed.

- [x] 1. `sys_connect_llm` uses the `connect` action with `setup.primary`
  (from the installed preset, unpowered only) and `setup.shapes`.
- [x] 2. Delete the full-page connect view, vendor cards, raw-deposit select
  and their JS; unpowered sign-in lands in chat with the request open first.
- [x] 3. Guided sign-in panel inside the request: begin, callback redemption,
  automatic finish of the returned free-model request, one-tap Finish
  connecting, key shortcut.
- [x] 4. Only `status: "answered"` is success; re-read serving either way.
- [x] 5. API key / own-server shapes: one `connect` ask answered in the same tap.
- [x] 6. Fold the single pending free-model request into the setup while unpowered.
- [x] 7. Grant sentence without internal ids; `setup_required` for a turn
  refused before any call; Account `label`.
- [x] 8. Tests: server round trip with no model call, reconnect after
  disconnect, rail executed under node, endpoint shape executed, red on main.
- [ ] 9. Cross-family review (owed).
- [ ] 10. Live acceptance on the free-only second account (see design.md).
- [ ] 11. Sync the delta into `openspec/specs/onboarding-connection-progress` and archive.

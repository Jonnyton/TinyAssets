# Tasks

- [ ] 1. `user_accounts.timezone` column + `set_account_timezone` /
      `get_account_timezone`, validated against `zoneinfo`.
- [ ] 2. `POST /mcp/app/account/timezone`, identity-required, refusing an
      unresolvable name rather than clearing the stored one.
- [ ] 3. App reports `Intl.DateTimeFormat().resolvedOptions().timeZone` on
      sign-in/load.
- [ ] 4. `automations.timezone` + `automations.last_due_local` columns.
- [ ] 5. Resolve the zone at create (passed → account → UTC); refuse an unknown
      name naming the field.
- [ ] 6. `_due_instant` cron: resolve the local slot through the zone, with the
      decided gap/ambiguous policy; dedupe on the local slot.
- [ ] 7. `next_due_at` cron: same resolution, so both surfaces agree.
- [ ] 8. Report `timezone` + a `7:00 AM America/Los_Angeles` schedule string
      wherever an automation is returned or displayed.
- [ ] 9. `write_graph.branches` handbook example shows the zone.
- [ ] 10. Tests: both 2027 transitions for `0 1`/`0 2`/`0 7`, the
      default-from-owner path, override, unknown-zone refusal, and the
      ambiguous-slot single fire.
- [ ] 11. One cross-family review round; fold P0/P1.
- [ ] 12. Sync the spec delta into `openspec/specs/` and archive on land.

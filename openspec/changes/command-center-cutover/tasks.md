# Tasks: command-center-cutover

Prerequisite: C4a (#4234) is in production for at least one day.

- [ ] 1. `scripts/command_center_inventory.py` (read-only, E1), with fixture
      tests. Attach a production-copy report.
- [ ] 2. Codemod `scripts/rename_command_center.py`: identifiers, modules, env
      vars and the plugin id. Deterministic, with a non-mechanical report.
- [ ] 3. Migration phase 1 (names), including stored branch fields,
      custom-UI bundle bridge keys, and default-definition re-points.
- [ ] 4. Migration phase 2 (ids, `u-` to `cc-`), including derived
      identities and folders.
- [ ] 5. Phase 3 verification: zero operational old names and ids, decoded
      round trips, digest integrity, independent deletion and export counts.
- [ ] 6. Phase 4 external: Stripe checkout drain, metadata and claim rewrite,
      late-event map, refusing an unknown home before storage. Recorded
      inverse.
- [ ] 7. Layout 2 in `tinyassets/storage_layout.py`, plus a
      `deploy_fail_safe.sh` that asks the image which layouts it knows.
- [ ] 8. Dry run on a consistent production copy; attach the row-count and
      reader report.
- [ ] 9. Rollback runbook in `docs/ops/`, rehearsed on the dry-run copy.
- [ ] 10. Freeze window (E3.6). Evidence: canary `--assert-handles`,
      `deployed_sha.py`, and an inventory re-run on production showing zero.
- [ ] 11. Delete C1's edge translation, keeping the retired-name refusals.
      Land the ids-never-shown guard (E5, after notify-prompt's header fix).
- [ ] 12. Sync specs and archive both changes.

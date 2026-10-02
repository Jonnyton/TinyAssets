# Tasks: command-center-cutover

Prerequisite: C4a (#4234) is in production for at least one day.

- [ ] 1. `scripts/command_center_inventory.py` (read-only, E1), with fixture
      tests. It classifies every home entry by the E6 layout, and an entry it
      cannot classify fails the run. Attach a production-copy report.
- [ ] 2. First, commit old-layout fixtures built by the pre-cutover creators
      (26-character ids) with a creator-coverage manifest (E4). Then the codemod
      `scripts/rename_command_center.py`: identifiers, modules, env vars and the
      plugin id. Deterministic, with a non-mechanical report.
- [ ] 3. Migration phase 1 (names), including stored branch fields,
      custom-UI bundle bridge keys, and default-definition re-points. Each
      home entry moves to its target place (E6): user content in
      `cc-<ulid>/`, platform state in `.platform/cc-<ulid>/`, and an empty
      `.platform/accounts/`. One resolver builds every path, and mixed
      consumers (soul edit, self-model, config, dispatcher, vault lookup) get
      both roots explicitly. Database families move journaled, and the run
      crash-resumes between every pair of moves (E6).
- [ ] 4. Migration phase 2 (ids, `u-` to `cc-`), including derived
      identities, folders and credential custody references (E4b).
- [ ] 5. Phase 3 verification: zero operational old names and ids, decoded
      round trips, digest integrity, independent deletion and export counts.
- [ ] 6. Phase 4 external: Stripe checkout drain, metadata and claim rewrite,
      late-event map, refusing an unknown home before storage. Recorded
      inverse.
- [ ] 7. Layout 2 in `tinyassets/storage_layout.py`, plus a
      `deploy_fail_safe.sh` that asks the image which layouts it knows.
- [ ] 8. Dry run on a consistent production copy. Attach the row-count and
      reader report, proof that every credential still resolves, and the
      measured duration that sets the cutover deploy's deadlines (E4).
- [ ] 9. Rollback runbook in `docs/ops/`, rehearsed on the dry-run copy.
- [ ] 10. Freeze window (E3.6). Evidence: canary `--assert-handles`,
      `deployed_sha.py`, and an inventory re-run on production showing zero.
- [ ] 11. Delete C1's edge translation, keeping the retired-name refusals.
      Land the ids-never-shown guard (E5, after notify-prompt's header fix).
- [ ] 12. Sync specs and archive both changes.

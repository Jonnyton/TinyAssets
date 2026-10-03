## 1. Decide (blocks everything below)

- [ ] 1.1 **Founder decision: D3(a) or D3(b).** Carry existing consent rows
      forward with a one-time disclosure to the owner (recommended -- the
      exposure window is "before this migration", which is the status quo), or
      carry nothing and make every owner re-grant (correct by construction,
      breaks every existing integration at once). One line of the migration
      differs. Nothing below should start until this is answered, because the
      migration's shape depends on it.

## 2. Move the consent database (closes the live authority hole)

- [ ] 2.1 `storage/effector_consents.py`: `consents_db_path` returns
      `<data>/.universe-sidecars/<cc>/.effector_consents.db`. Nothing else in
      the module changes.
- [ ] 2.2 Migration in `storage_layout.py`, under the exclusive lock, with the
      marker refusing a pre-move image: idempotent, resumable, and refusing a
      command center that has both copies (design D3). The in-folder file is
      renamed aside, not deleted.
- [ ] 2.3 The disclosure from 1.1, if (b): a one-time owner-facing list of the
      effects and destinations carried forward, revocable.
- [ ] 2.4 Tests: a command center that pre-creates the in-folder database gains
      no consent; a link planted at the old name changes no answer; the
      migration run twice is a no-op; both-copies refuses by name; killed
      mid-way it resumes. Linux oracle, since the link cases are POSIX-only.

## 3. Enumerate and follow (the cleanup, and what stops a recurrence)

- [ ] 3.1 The enumeration test (design D4): no platform path helper resolves
      inside a command-center folder, allowlisting the `.runtime` snapshots a
      provider child reads through its jail. This is the task that produces the
      real inventory -- `.runs.db` is already confirmed
      (`api/resource_usage.py`, `api/storage_observations.py:135`).
- [ ] 3.2 Move each store the enumeration finds, one commit per store, each
      with its own migration step and its own test.
- [ ] 3.3 Followers, derived from the same enumeration rather than listed:
      account deletion / `scoped_reset.py`, `storage_accounting.py`,
      `deploy/backup.sh`'s set. Assert deletion leaves no sidecar.
- [ ] 3.4 Cross-family refute of the migration specifically -- the path change
      is small, the one-way move over every command center is not.

## 4. Land

- [ ] 4.1 Prod: `deployed_sha.py --assert-contains`, plus a read-only check
      that the sidecar directory holds the consent database and the
      command-center folders no longer do.
- [ ] 4.2 Delete `docs/concerns/2026-10-03-a-universe-database-name-steers-the-
      daemon.md` and `docs/concerns/2026-10-01-platform-state-inside-the-
      universe-dir.md`, which this change resolves; spec sync and archive.
- [ ] 4.3 Follow-up, not part of this change: once
      `openspec/changes/per-role-uid-split` lands, a sticky bit on the parent
      stops a child uid renaming a daemon-owned entry. Useless before it
      (command-center processes share the daemon's uid), cheap after.

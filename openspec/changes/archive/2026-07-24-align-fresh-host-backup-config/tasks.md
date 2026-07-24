## 1. Contract

- [x] 1.1 Add the fresh-host backup configuration requirement and focused red test.

## 2. Alignment

- [x] 2.1 Replace unused template fields with `BACKUP_DEST`.
- [x] 2.2 Align deploy, cutover, and backup/restore runbooks with root's canonical rclone path and permissions.
- [x] 2.3 Correct the backup unit's false `STORAGEBOX_*` and ephemeral-rclone comments.

## 3. Verification

- [x] 3.1 Run the focused backup configuration and backup runtime tests.
- [x] 3.2 Strict-validate OpenSpec, independently review the diff, and sync the capability spec before archive.
- [x] 3.3 Record the required #1658 post-merge rebase and overlapping configuration/spec-delta removal handoff.

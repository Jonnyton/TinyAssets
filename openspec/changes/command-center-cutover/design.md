# Design: command-center-cutover

The safety contract is in `rename-universe-to-command-center/design.md`: D6
(code), D7.1-D7.7 (storage), D10 (one cutover), D11 (`cc-` ids). This file
covers execution: order, tooling, the freeze window, and the evidence each
step must produce.

## E1. Read-only first: the inventory is a deliverable

`scripts/command_center_inventory.py` runs read-only against a data root and
prints a machine-readable report:

- every SQLite table, column, `CHECK` / index / trigger / view clause, and TEXT
  or BLOB value naming `universe` or holding a `u-<ulid>`, decoded per
  encoding (D7.1, D11);
- LanceDB schemas, checkpoint payloads (via serde), JSON keys and values, and
  marker files and folders;
- derived identities: length-prefixed lease keys, hashed connection and grant
  ids, content digests over records that contain an id;
- the exempt verbatim stores (uploads, run outputs, conversation text, brain
  files), listed by name so the scan's skips are explicit.

Run it first on a production copy. Its counts are what the migration must
bring to zero, and what the dry run compares.

## E2. The migration is code with its own tests before it ever runs

`tinyassets/command_center_migration.py` runs phases 1-5 under the exclusive
`.layout.lock` that C4a introduced:

- it writes `{"layout": 1, "state": "migrating"}` before its first change;
- it makes one transaction per database and keeps a per-database progress
  table;
- every step is idempotent and resumable.

It is tested against fixture data roots built by every real schema creator.
Those tests cover crash and resume at every phase boundary, digest and
reference integrity, decoded round trips, independent deletion and export
counts, and a test that fails on any surviving operational old name or id.

## E3. Order of work

1. The inventory script, then a production-copy report attached to the PR.
2. The codemod: deterministic, plus its report of non-mechanical sites.
3. The migration module and its tests.
4. A dry run on a consistent production copy (SQLite online backup, never
   `backup-restore.sh`). The row-count and reader report is attached.
5. The rollback runbook in `docs/ops/`, rehearsed on the dry-run copy.
6. The freeze window, in the measured quiet window (18:00-20:00 UTC,
   re-measured the day before):
   - the lead pauses the other lanes;
   - stop the backup timer, take the quiesced backup and record its sha256;
   - deploy;
   - the migration runs and verifies before the port binds;
   - external phase;
   - reopen;
   - canary (`--assert-handles`) and `deployed_sha.py`;
   - rebase the lanes with the codemod.

## E4. What blocks the window

Any of these stops the cutover:

- an inventory category the migration does not handle;
- a dry-run count or reader mismatch;
- an unrehearsed rollback;
- C4a not in production for at least a day;
- a WorkOS record holding an id that the live check finds.

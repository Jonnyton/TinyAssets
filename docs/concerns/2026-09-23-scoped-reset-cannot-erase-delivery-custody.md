# Operator scoped reset refuses on any root that has ever accepted a delivery

**Filed:** 2026-09-23
**Verified:** 2026-09-23, this checkout (`codex/file-bridge-next` @ `fe57ee46`), Windows,
`python -m pytest -q tests/test_delivery_file_reset.py` — 1 passed.
**Severity:** P2 — fail-closed, not a data-loss or leak path. It removes an operator
capability rather than granting one.

## Finding

`tinyassets.scoped_reset.apply_test_identity_reset` deletes rows only from the main
database (`_validated_main_database`). Root run history (`.runs.db`) is classified
read-only: `_inspect_root_runs` compares its tables against `_KNOWN_ROOT_RUN_TABLES`
(`tinyassets/scoped_reset.py:218-246`) and emits an `unclassified root run-history table`
blocker for anything it cannot account for.

None of the five cross-user delivery tables are in that set. They are created by
`tinyassets.storage.deliveries.transaction()`, which runs the whole `_SCHEMA` on every
call — so they materialize on the *first* delivery-surface touch, not only when rows
exist. Measured on a freshly seeded root:

```
BEFORE: ()
AFTER:  ('unclassified root run-history table: graph_deliveries, graph_delivery_attempts,
          graph_delivery_files, graph_output_links, graph_receivers',)
```

Effect: scoped identity reset is unavailable for any data root that has ever opened the
delivery surface. `plan_test_identity_reset` still returns a plan; the apply raises
`ScopedResetBlocked`.

Four of the five tables predate the file-bridge slice; `graph_delivery_files` (receiver-owned
file custody provenance) is new in `connect-cross-user-nodes` and extends the same gap to
physical bytes.

## What is already pinned

`tests/test_delivery_file_reset.py` holds the current behaviour as the contract: with a real
transferred file present, the reset refuses **and** the provenance row, the receiver binding
and the bytes survive byte-identical with `PRAGMA foreign_key_check` empty.

## What NOT to do

Adding these tables to `_KNOWN_ROOT_RUN_TABLES` clears the blocker and deletes nothing —
the reset would report success while the subject's delivery custody and physical bytes
remain. That is loosening ownership to get green, and the test above is written to fail if
someone tries it.

## Real fix (unowned, out of the file-bridge slice)

A `.runs.db` reset adapter that deletes subject-owned delivery rows and settles physical
custody, the way `account_deletion._delete_satellite_rows` already does for account deletion
(`tinyassets/account_deletion.py:_delivery_deletion_targets` + `run_file_erasure`). Account
deletion is the only path that currently erases this data; it is proven by
`tests/test_delivery_file_transfer.py::test_sender_account_erasure_leaves_the_receiver_its_bytes`.

Scope decision needed from the host: whether operator scoped reset should gain that adapter
at all, or whether delivery-bearing roots are intended to be account-deletion-only.

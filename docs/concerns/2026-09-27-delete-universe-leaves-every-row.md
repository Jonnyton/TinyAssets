# `delete_universe` removes the directory and leaves every database row

**Severity:** P2 · **Filed:** 2026-09-27 · **Verified:** 2026-09-27 against `origin/main` 61c434d3
and the live droplet (deployed c8f66c6a)

## What is wrong

`fantasy_daemon/api.py:850` (`DELETE /v1/universes/{uid}`) is the only per-universe delete in
the codebase. It stops the daemon if it is running there, clears the active-universe marker, and
`shutil.rmtree`s the directory. It deletes no rows. `universes`, `universe_rules`, `branches`,
`branch_heads`, `universe_work_targets`, bindings, schedules, grants and every other table with a
`universe_id` column keep the id forever. Nothing records that the directory is gone.

## Evidence

The 2026-09-27 production cleanup found 13 ids with `universes`/`universe_rules`/`branches`
rows and no directory and no owner. The ids were `app_refresh_sessions`, `concordance`,
`default-universe`, `earthos`, `echoes-of-the-cosmos`, `grandma-bread-recipe`,
`local-bubble-galactic-survival-model`, `meridian-ashes`, `patch-loop-live`,
`team-standup-action-tracker`, `tiny`, `u-01ky3gkxg9qmz111v5qk7p2qbm` and `workflow-voice`.
They had to be removed by hand. Their rows are backed up in
`/data/_removed_universes_20260927/deleted_rows.sql` on the droplet.

## Fix shape

Reuse `tinyassets/account_deletion.py`'s schema-derived rule, scoped to one universe, instead of
writing a second table list (see `two-definitions-of-one-fact`). The pieces are:

- `deletion_plan(conn, principal=<matches nothing>, home=uid)`, taking only the `universe` keys;
- the indirect parent predicates inlined in `_delete_root_rows` (`branch_heads`, `vote_ballots`,
  `request_admissions`, `request_admission_events`, `branch_tasks_v2`), which would need to be
  lifted to a module constant so both callers share it;
- `_delivery_deletion_targets` for the satellite stores returned by `_root_databases`.

The row delete should count every targeted table first, then delete in one transaction, then
remove the directory. The foreign-owner and active-work blockers from `deletion_blockers` still
apply.

The 2026-09-27 cleanup script did exactly this and proved it out. It held a per-table
before/after count check inside `BEGIN IMMEDIATE` and rolled back on any unplanned cascade. It
removed 203 rows across `.tinyassets.db` and `outbound.db`, and the kept universes' rows were
unchanged. The script's body is the natural starting point.

A universe delete is storage-shape and authority work, so per `AGENTS.md` it needs an OpenSpec
change before code.

---
severity: P2
title: Scoped reset has no rule for owner-only rows such as universe_app_ui
filed: '2026-09-26'
summary: scoped_reset refuses any database holding a table it has not classified, and universe_app_ui is one of them; whoever classifies it must delete by owner only, never by universe, or a reset takes a collaborator's row
---

# Scoped reset has no rule for owner-only rows such as `universe_app_ui`

**Filed:** 2026-09-26
**Verified:** 2026-09-26, reading `tinyassets/scoped_reset.py` on `claude/custom-ui`
(PR #4038), and `python -c "from tinyassets.scoped_reset import
MAIN_DB_TABLE_CLASSIFICATIONS"` (49 tables classified; none of `agent_bindings`,
`agent_definitions`, `universe_model_preferences`, `universe_app_ui`).
**Severity:** P2. Nothing is lost today. The reset fails closed.

## Source (verbatim)

Lead, on PR #4038: "Leftover (3), scoped_reset sweeping by universe, gets filed as
one concern file in this PR."

That leftover was my own claim in the #4038 report: *"scoped_reset still sweeps
universe-scoped tables by universe, so a host reset of a universe would take a
collaborator's row about it."*

## Re-verification: the premise was wrong

Scoped reset does not sweep by universe. It deletes planned rows one at a time by
exact primary key (`_apply_database_actions`, `scoped_reset.py` around line 2254),
and only for tables listed in `MAIN_DB_TABLE_CLASSIFICATIONS`. Any other table in
the database raises `ScopedResetSchemaError("unclassified tables block scoped
reset: ...")` (around line 1311). `universe_app_ui` is unclassified, so a database
holding it blocks the reset instead of losing a row. So do `agent_bindings` and
`universe_model_preferences`, which already exist in every live database. The new
table therefore changes nothing about when a reset can run.

## What is still worth recording

When someone classifies these tables to make scoped reset usable again,
`universe_app_ui` needs the rule account deletion now uses (`OWNER_ONLY_TABLES` in
`tinyassets/account_deletion.py`). A row is the owner's own choice, even when its
`universe_id` names someone else's universe. So resetting a universe must delete
only the reset subject's rows, never every row carrying that `universe_id`.
Classifying it as `reset_home` would bring back the cross-user deletion that the
#4038 review reproduced for account deletion.

**What closes it:** a classification for `universe_app_ui` in
`MAIN_DB_TABLE_CLASSIFICATIONS` that plans rows by `owner_user_id = subject`, with a
test that a collaborator's row about the reset universe survives.

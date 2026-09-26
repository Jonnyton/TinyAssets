# Tasks: private by default

Owner: claude-code. One PR, Tier 2 (authority + live-record migration). One
blocking cross-family review before landing.

- [x] 1. `DEFAULT_CREATE_VISIBILITY = "private"`; module docstring states the
  founder rule and the date.
- [x] 2. `set_universe_visibility(universe_id, level, *, source)` — required
  keyword, validated against the known sources, written to
  `visibility_level_source`. Add `declared_level_source()` and
  `level_was_chosen_by_owner()` readers.
- [x] 3. `backfill_universe_visibility` declares `private` for every undeclared
  universe and no longer reads `public_read` to decide. Docstring says why the
  old derivation was wrong.
- [x] 4. `_action_create_universe` passes `source="owner"` when the caller chose
  a level and `source="default"` when the default applied.
- [x] 5. `_action_set_universe_visibility` in `tinyassets/api/universe.py`,
  owner-gated on write permission, registered as `set_visibility`.
- [x] 6. `write_graph target=universe operation=set_visibility` forwards
  `graph_id` + `visibility`; docstring tells the agent the verb exists and that
  a universe is private until it is used.
- [x] 7. `scripts/migrate_private_by_default.py` — dry-run default, `--apply`,
  `--json`, `--skip`; enumerates from the rules store unioned with discovery;
  deletes nothing; idempotent; logs every candidate and every write.
- [x] 8. `tests/test_private_by_default.py` — owner reads/writes/lists their own
  private universe; a second authenticated user is refused
  `read_content`/`read_metadata`/`discover_existence`; an explicitly public
  universe is readable by that same second user; the exposure verb is refused to
  a non-owner; the migration lists then flips and is idempotent.
- [x] 9. Backfill + provenance assertions in `tests/test_universe_visibility.py`
  (the module that opts out of the harness backfill double).
- [x] 10. Delete `docs/concerns/2026-08-06-founder-canon-defaults-public.md`,
  `docs/concerns/2026-09-02-migration-records-are-publicly-discoverable.md`, the
  `docs/host-actions.md` "what should be publicly discoverable" row, and every
  reference to them.
- [x] 11. `openspec/specs/universe-visibility/spec.md` as-built; one PLAN.md line
  for the founder rule.
- [x] 12. `python packaging/claude-plugin/build_plugin.py`; `ruff check`; pytest
  over the touched areas set-compared against `origin/main`.

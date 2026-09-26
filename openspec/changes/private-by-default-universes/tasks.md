# Tasks: private by default

Owner: claude-code. One PR, Tier 2 (authority + live-record migration). One
blocking cross-family review before landing.

**Review round 1 (Codex, 2026-09-26, head `a9cb80c0`): ADAPT.** Three
`DISAGREE_EVIDENCE` findings, all reproduced end-to-end, all fixed in this PR with
a mutation-proven test each:

1. A delegated `write` grant holder could publish someone else's universe and have
   it recorded as the owner's choice. `WRITE_ACTIONS` membership gates at write
   strength, and `_WRITE_PERMISSIONS` accepts `write` OR `admin`. Fixed: the
   handler now requires `source_channel.universe_owner_actor` (the canonical
   `admin` ACL predicate) on top of the central gate. Design D4.
2. The migration classified an *undeclared* universe as "already private", because
   the layered resolver reports `private` for undeclared — while the separate
   legacy `public_read` gate (column default `1`) kept it readable. Fixed: an
   undeclared universe, and a private declaration over an open legacy bit, are both
   candidates; `--apply` verifies both gates after each write. Design D5.
3. `metadata_only` disclosed raw `activity.log` lines through
   `get_memory_scope_status`, which gated on the legacy bit alone. Reachable only
   because this PR made the level selectable, so fixed here: the gate is now
   `visibility_permits(uid, "read_content")`. Design D7.

One `DISAGREE_CONCERN` (the repo-wide visibility test double) is filed as
`docs/concerns/2026-09-26-visibility-test-double-assumes-public.md` rather than
claimed as resolved — settling it is a mass fixture migration. Design D6a.

**Review round 2 (Codex, 2026-09-26, head `50802601`): ADAPT.** All three round-1
reproductions confirmed closed. Two new `DISAGREE_EVIDENCE` findings, both fixed
and mutation-proven; artifact `docs/audits/2026-09-26-pr4019-round2-review.md`:

4. The migration could not close an **unregistered bare directory** — the record
   that most needs closing, since with no rules row the legacy bit defaults open.
   `universe_rules` has an FK onto `universes`, so declaring before registering
   died with `FOREIGN KEY constraint failed` and the directory kept serving its
   `activity.log`; a second `--apply` repeated the failure. Fixed:
   `ensure_universe_registered` first, matching the boot backfill, plus
   `initialize_author_server` in `plan()` so a data dir of bare directories does
   not die on `no such table: universe_rules`.
5. `metadata_only` still leaked raw content through `_action_get_activity`, a
   sibling of the round-1 reader. Grepping the pattern found **six** such actions
   sharing one gate (`_universe_acl_error`, legacy bit only). Fixed by the
   reviewer's own second option — stop offering the unenforced levels:
   `_OFFERED_VISIBILITY_LEVELS = {"private", "public"}` at both writers (the verb
   AND birth, the latter reachable because the dispatcher now forwards
   `visibility`), with a `level_not_enforced` refusal naming
   `docs/concerns/2026-09-26-content-readers-gate-on-the-legacy-bit.md`. Design D7.
   Gating all six is that concern's job, deliberately not this PR's.

Round 2 also caught one of my own tests passing for the wrong reason: the
dispatcher-birth test was satisfied by a `tinyassets.universe.costly` scope refusal
rather than the level check. It now carries that scope and asserts the level error
text, with a positive sibling proving birth still works.

**Review round 3 (Codex, 2026-09-26, head `4f87c39a`): ADAPT — the cap.** Both
round-2 holes confirmed closed (bare directory flipped with `failed == []`,
`public_read` closed, `get_activity` refuses; reserved dirs and dotfiles still
excluded; `host_path` matches creation and backfill; both writers reject split
levels; no other production route producing them; docstring accurate). It also
checked the five tests I asked it to for the wrong-reason failure mode and found
none. Artifact `docs/audits/2026-09-26-pr4019-round3-review.md`.

6. One new `DISAGREE_EVIDENCE`, in **my own round-2 fix**: registering
   unconditionally destroyed registry data. `ensure_universe_registered` is an
   UPSERT whose conflict clause sets `display_name=excluded.display_name,
   metadata_json=excluded.metadata_json`, so an already-registered universe lost
   its owner's display name (replaced by the raw id) and its registry metadata
   (replaced by `{}`) — while the migration reported success. Fixed by
   `visibility.register_if_absent()`, one guarded predicate used by both callers.

   **The same defect was already in the boot backfill**, which registered every
   discovered universe unconditionally on EVERY BOOT — so a universe its owner had
   named lost that name at the next restart, silently. Pre-existing, worse than the
   migration instance, and closed by the same change with its own two tests.

**Cap reached.** AGENTS.md allows three rounds, so the round-3 fix is
**unreviewed by the peer** and no round 4 was opened. Two findings stay open by
choice, both agreed reasonable to defer by the reviewer:
`docs/concerns/2026-09-26-visibility-test-double-assumes-public.md` and
`docs/concerns/2026-09-26-content-readers-gate-on-the-legacy-bit.md`. The founder
decides whether the last fix wants another look.

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

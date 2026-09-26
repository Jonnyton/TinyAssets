# Design: private by default

## D1. Why the default is the whole fix, and the resolver already was right

`universe_visibility` has failed closed on an *undeclared* universe since the
universe-visibility change landed. The leak was never the resolver — it was the
two places that **declare**: creation (`DEFAULT_CREATE_VISIBILITY = "public"`)
and the backfill (`PUBLIC if bool(current.get("public_read", True))`). Both wrote
an open level nobody asked for. So this change touches the two writers and adds
one more, and leaves the read path alone.

## D2. There is no record of a chosen level, so every current one was defaulted

The migration has to answer "did the owner choose this?" and today nothing can.
`visibility_level` stores a level name and no provenance. The honest inference:

- The creation default was `public`, and the public `write_graph
  target=universe` create never forwarded a visibility, so **every** universe
  born through the connector holds a defaulted `public`.
- The backfill declared `public` from a `public_read` bit whose own default is
  `True`, so every legacy directory and every maintenance bucket holds a
  defaulted `public`.
- No production caller ever set a level on an owner's behalf, so no `public`
  declaration in the store can have come from an owner's decision.

Therefore: **every current non-`private` declaration was a default, and the
migration flips all of them.** This is stated so a reviewer can check the
inference rather than trust the script, and so a later reader knows the script
was not guessing about individual rows.

Going forward it stops being an inference. `set_universe_visibility` now takes a
required `source` and writes `visibility_level_source`. A level whose source is
`owner` is a decision; anything else, including a missing key (every row written
before this change), is a default. The migration's predicate is exactly that, so
re-running it after an owner has published something does not un-publish it.

`source` is required rather than defaulted on purpose — a default here is the
same shape of bug as the one being fixed, and a silent `source="owner"` would
make the next migration unable to tell a decision from a fallback.

## D3. Backfill: derive from nothing, not from `public_read`

The old derivation was defensible when it was written: "no universe changes
visibility, it only becomes declared". It is wrong now, because the bit it
derives from is itself an unchosen default, so "preserve current behaviour"
preserved a leak. The new rule is one line: an undeclared universe is declared
`private`, `source="backfill"`.

This keeps the startup gate's property intact — after boot, no universe is
undeclared, so an undeclared row still means genuine corruption and still fails
loud. What changes is that boot no longer opens anything.

A universe whose legacy `public_read` is already `False` was previously declared
`private` by derivation and is still declared `private`. Nothing regresses.

## D4. Exposure needs a verb, or private-by-default is a wall

`set_universe_visibility` had no production caller outside creation and the
backfill. Shipping private-by-default without an exposure path would satisfy the
first half of the founder's sentence and make the second half impossible, so the
change adds one verb and no more:

`write_graph target=universe operation=set_visibility`, taking the existing
`visibility` parameter and `graph_id`. It is gated on
`permissions.universe_access_allows(uid, write=True)` — the same gate that
protects every other owner-only universe write — and records `source="owner"`.
It reuses `set_universe_visibility`'s existing validation, so an unknown level
is refused with the known set rather than silently ignored.

Deliberately not built: per-page and per-branch exposure verbs. Pages already
narrow themselves through frontmatter (`page_content_permitted`) and branches
already carry their own `visibility` with an explicit `set_visibility` patch op.
Adding universe-level ones would be a second definition of the same fact.

## D5. Migration shape

`scripts/migrate_private_by_default.py`:

- **Dry run is the default.** `--apply` is the only thing that writes.
- **Deletes nothing.** The only write is an update to the universe's rules
  metadata through `set_universe_visibility(..., source="migration")`, which
  also keeps the legacy `public_read` ceiling consistent. The
  `_backup_subject_migration_*` and `_removed_universes_*` records stay exactly
  where they are — they are migration backups.
- **Enumerates from the rules store, not from the on-disk discovery helper.**
  `_discover_universe_ids` is being narrowed to *owned* directories by #4012, and
  the records that most need flipping (the maintenance buckets) are precisely the
  unowned ones. Reading `universe_rules` catches every declared universe
  regardless of ownership, and then unions the discovered ids so a universe with
  no rules row is still reported.
- **Idempotent.** A second run reports zero candidates, because the first run
  wrote `private`, and a level an owner later chose carries `source="owner"` and
  is skipped.
- **Logged.** Every candidate is printed with its current level and inferred
  source, and `--apply` logs each write. `--json` emits the same as a machine
  record for the host's evidence.

`--skip <id>` exists for one case: a record the host has already decided should
stay exposed. It is explicit per invocation, never a file the script reads.

## D6. The test harness emulates the old backfill, and that has to stay honest

`tests/conftest.py::_emulate_deployed_visibility_backfill` is an autouse fixture
that resolves an *undeclared* universe to `PUBLIC` for every module except
`test_universe_visibility`, because hundreds of pre-visibility tests build bare
directories and assert public-reader behaviour. After this change the production
backfill declares `private`, so the fixture no longer describes a deployed state.

It keeps its behaviour and changes its meaning: those modules' bare directories
now stand for *a universe whose owner chose public*, which is what each of those
tests is actually about. The docstring says so. Flipping the fixture to `private`
would silently rewrite what several hundred unrelated tests assert, which is the
failure mode, not the fix.

The new tests are not exposed to the double. They create through the real
`_action_create_universe`, which writes an **explicit** declaration, and the
fixture defers to the real strict resolver for any explicitly declared level.
That is why the mutation check works: reverting `DEFAULT_CREATE_VISIBILITY` to
`"public"` makes the created universe explicitly public and the cross-user
refusal assertion goes red. Backfill-level assertions live in
`test_universe_visibility`, which opts out of the fixture entirely.

## D7. What this does to `/commons`

`WebSite/shared/mcp/public-read-contract.js` already rejects any universe row
whose `visibility` is not in the discoverable set, and `_action_list_universes`
already gates enumeration on `discover_existence`. So the site needs no change
and cannot break: after the migration the list is empty until an owner uses the
new verb. That is the founder's stated outcome, and the existing "raw, not
curated" caption on the page becomes true rather than apologetic.

The concern file and the host-actions row are deleted by this change, because
the founder's sentence is the decision the row was waiting for.

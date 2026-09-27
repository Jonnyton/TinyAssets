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

**What the provenance does and does not mean.** `source="owner"` records that the
level was set *through the owner's own authority* — the explicit `admin` ACL row
on that universe. It is not evidence a human typed it: a universe's own agent
acting on its owner's credential is indistinguishable here from the owner, and
deliberately so, because that agent acts with the owner's authority by design
(Codex cross-family review, C4). The key's job is to separate an owner-authorized
decision from a *platform* default, which is exactly the distinction the migration
needs. It is a bookkeeping signal, never an authorization input: nothing reads it
to decide access, only to decide whether the migration should touch a row.

That bound only holds because the verb is owner-gated. The first cut relied on
`WRITE_ACTIONS` membership alone, and Codex reproduced a delegated *writer*
publishing someone else's universe and getting `chosen_by="owner"` back — see D4.

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
`visibility` parameter and `graph_id`. It reuses `set_universe_visibility`'s
existing validation, so an unknown level is refused with the known set rather
than silently ignored.

**Authority is OWNER, not write — and that took two goes.** The first cut relied
on `WRITE_ACTIONS` membership alone, which makes `_universe_acl_error` demand
`universe_access_allows(uid, write=True)`. That is necessary and not sufficient:
`permissions._WRITE_PERMISSIONS` accepts `write` OR `admin`, so the Codex
cross-family review granted a second principal only `write` and published the
owner's private universe through the public `write_graph` handle — returning
`status=updated` and `chosen_by="owner"`, after which the migration classified
that universe as owner-chosen and left it public. Reproduced end-to-end, not
theorised.

Editing a universe and deciding who else may SEE it are different authorities
once a universe has collaborators. So the handler adds the canonical
per-universe ownership predicate, `source_channel.universe_owner_actor` — the
explicit `admin` ACL row, the same signal `connect_llm`, `source_channel` and the
pending-request rail already use. This is a **narrowing on top of** the central
gate rather than a second copy of it: the ACL check still runs first and this can
only ever refuse more. Both refusals return the same `universe_access_denied`
envelope, so a delegated writer learns exactly what a reader learns.

Two gates therefore stand between a caller and publication: the derived OAuth
scope (`tinyassets.universe.write`, from `WRITE_ACTIONS` membership) and the
ownership predicate. Both are asserted, and the ownership one is mutation-proven.

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
- **An undeclared universe is a CANDIDATE, not "already closed".** The layered
  resolver reports an undeclared universe as `private`, and the first cut read
  that as "nothing to do". It is wrong, and Codex reproduced it: `public_read` is
  a **separate** read gate, `permissions.universe_access_allows` consults it
  alone, its column default is `1`, and readers that predate the visibility layer
  go through that path — so the migration reported zero candidates while an
  undeclared universe was still handing out content. Declaring it `private`
  closes both gates at once. A row declared `private` whose legacy bit is still
  open is a candidate for the same reason, and re-declaring is idempotent.
  Generally: **do not infer that every read path fails closed from the layered
  resolver's effective level.** Two gates exist; the migration has to satisfy
  both, and `--apply` verifies both after each write.
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

### D6a. What the review said about the double, and what is left open

Codex agreed the part that matters for *this* change: explicit creation
declarations bypass the double, and the two strict modules exercise the real
resolver, so the new tests are not reading a stand-in. It did not attribute any
concrete regression to the double.

Its remaining objection stands and is not resolved here: renaming the assumption
"an owner chose public" does not *establish* that several hundred legacy tests
model publication. Settling it means explicit public fixtures or opt-in marking
across those modules. That is a mass fixture rewrite with its own blast radius,
and doing it inside an authority change would mix a behaviour fix with a harness
migration. It is filed as its own concern
(`docs/concerns/2026-09-26-visibility-test-double-assumes-public.md`) rather than
claimed as done.

## D7. A level only promises what some reader enforces

`set_universe_visibility` turns the legacy `public_read` bit on whenever a level
grants a public visitor **any** capability. That is right as a *ceiling* for
`visibility_permits`, which ANDs the two — and wrong for any reader that consults
that bit alone. `get_memory_scope_status` did, and it returns raw `activity.log`
lines, so a `metadata_only` universe — whose entire point is that it withholds
content — disclosed its literal log lines to any authenticated principal. Codex
reproduced it.

That reader predates this change. What this change did was give an owner a way to
*select* `metadata_only`, turning a latent hole into a reachable one, so it is
fixed here rather than filed: the gate becomes
`visibility_permits(uid, "read_content")`, which is tighten-only and therefore
subsumes the legacy check instead of replacing it.

The general rule this leaves behind: **a level is a promise, and a promise with no
enforcing reader is decoration.** Before offering a level on an owner-facing verb,
find every reader of the capability it withholds.

So I did, and there are six more of the same shape. `_universe_acl_error` gates a
non-write universe action on the legacy bit ALONE, and six actions that return raw
content add nothing on top: `get_activity`, `read_premise`, `read_canon`,
`read_source`, `read_output`, `query_world` (plus `runs._run_read_allowed` for run
records). The actions that *do* add a capability gate — `inspect`
(`read_metadata`), `list` (`discover_existence`), `wiki` (`read_content`) — are
fine.

Two responses were available: gate all six, or stop offering the levels whose
promise they break. This change takes the second, for three reasons.

1. **The verb must not promise what the platform does not keep.** `metadata_only`
   withholds content and `unlisted` withholds metadata; both would be mis-served.
   `_OFFERED_VISIBILITY_LEVELS = {"private", "public"}` — the two the platform
   enforces end to end — and the refusal distinguishes "not offered because
   unenforced" from "unknown", naming the concern.
2. **It is what the founder actually said.** "Private unless they make them other
   user accessible" is a binary. `metadata_only`/`unlisted` are refinements nobody
   asked for, and they were unreachable in practice anyway: nothing in production
   ever produced them, because the creation default and the backfill only wrote
   `public` or `private`.
3. **Six more gated actions is a different change.** Doing it right means a
   `CONTENT_READ_ACTIONS` table beside `WRITE_ACTIONS` — one definition, not six
   sprinkled checks — with a per-action judgement about whether its payload is
   content or metadata (`get_ledger` and `list_canon` are genuinely arguable) and a
   test each. Folding that into an authority change would make both harder to
   review, which is how a review round creates the next round's findings.

Filed as `docs/concerns/2026-09-26-content-readers-gate-on-the-legacy-bit.md`,
naming every reader. When it closes, the other two levels belong in
`_OFFERED_VISIBILITY_LEVELS` and the `level_not_enforced` branch comes out.

Residual exposure, stated plainly: a dev/migration caller reaching
`set_universe_visibility` directly can still declare `metadata_only`, and five of
those six readers would serve its content. No production path does, and a test
pins the sixth (`get_memory_scope_status`) closed.

## D8. What this does to `/commons`

`WebSite/shared/mcp/public-read-contract.js` already rejects any universe row
whose `visibility` is not in the discoverable set, and `_action_list_universes`
already gates enumeration on `discover_existence`. So the site needs no change
and cannot break: after the migration the list is empty until an owner uses the
new verb. That is the founder's stated outcome, and the existing "raw, not
curated" caption on the page becomes true rather than apologetic.

The concern file and the host-actions row are deleted by this change, because
the founder's sentence is the decision the row was waiting for.

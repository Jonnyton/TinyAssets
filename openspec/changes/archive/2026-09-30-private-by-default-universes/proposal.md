# Private by default in a user's universe

**Tier 2: authority + a migration over live records.** One blocking
cross-family review is owed before landing.

## Why

Founder, 2026-09-26, verbatim:

> nodes in users universes should be private unless they make them other user
> accessible or visible or interactable in some way

The code says the opposite. `tinyassets/api/visibility.py` carries
`DEFAULT_CREATE_VISIBILITY = "public"`, consumed as the creation fallback in
`_action_create_universe`; the public `write_graph target=universe` create does
not forward a visibility at all, so **every** universe born through the
connector takes that default. `backfill_universe_visibility` derives an
undeclared universe's level from the legacy `public_read` bit, which defaults
`True`, so every legacy and every maintenance-created directory was declared
`public` by a migration rather than by an owner.

The consequence is observed, not predicted:

- `docs/concerns/2026-08-06-founder-canon-defaults-public.md` (P1, Codex
  REPRODUCED, re-verified 2026-09-03): founder-taught canon is committed into a
  universe that defaults to `public`, so any authenticated non-owner may read
  content nobody published.
- `docs/concerns/2026-09-02-migration-records-are-publicly-discoverable.md`
  (P2) plus the `docs/host-actions.md` row "Decide: what should be publicly
  discoverable": driving `/commons` live on 2026-09-02 returned twelve
  universes, all `visibility=public`, seven of which were maintenance buckets
  and IdP-migration backups. The founder's statement answers that host
  decision.

There is also no way to comply with the founder's sentence in the other
direction: **no production caller sets a universe's visibility after birth.**
`set_universe_visibility` is reachable only from the creation path and the
backfill. "unless they make them other user accessible" has no surface, so
private-by-default without this change would make exposure impossible rather
than deliberate.

## What changes

1. **`DEFAULT_CREATE_VISIBILITY` becomes `private`.** A creator may still pass
   an explicit level; an explicit level is still validated up front.
2. **The backfill stops inventing `public`.** An undeclared universe is
   declared `private`. It no longer reads the legacy `public_read` bit to
   decide, because that bit's own default is what produced the wrong answer.
3. **Declarations record their provenance.** `set_universe_visibility` takes a
   required `source` (`owner` / `default` / `migration` / `backfill`) written
   to `visibility_level_source` in the rules metadata. This is the record that
   does not exist today, and it is what makes the migration idempotent and
   every future one honest.
4. **An owner-facing exposure verb.** `write_graph target=universe
   operation=set_visibility` (action `set_visibility`), owner-gated on the
   universe's write permission, records `source="owner"`. This is the "make
   them other user accessible" half of the founder's sentence.
5. **A one-shot migration.** `scripts/migrate_private_by_default.py` —
   dry-run by default, `--apply` to write — lists every universe whose
   declaration was not chosen by its owner and is not already `private`, and
   flips those to `private`. It deletes nothing. The host runs `--apply` on
   production after this lands.

## What does not change

- The legacy `public_read` gate, `visibility_permits`' tighten-only
  composition, the page-level narrowing rules, and the boot startup gate's
  fail-loud contract are untouched.
- Owners and ACL grant holders are unaffected: `_reader_has_grant` short-circuits
  public-projection visibility, so a private universe is fully readable and
  writable by its owner and by anyone the owner granted.
- **Branch publishing is unaffected.** A Branch carries its own `visibility`
  field on the branch definition, resolved by `_resolve_readable_branch` /
  `list_branch_definitions(viewer=)` without consulting universe visibility at
  all; the public `write_graph target=branch` create already does
  `branch_spec.setdefault("visibility", "private")`. Publishing stays an
  explicit per-item choice (`set_visibility` patch op, `publish` operation).
- `/commons` already refuses any universe that is not explicitly
  `public`/`metadata_only` (`WebSite/shared/mcp/public-read-contract.js`), so it
  needs no change. It will list only universes an owner chose to expose — which
  is the point, and after the migration that is an empty list until someone
  chooses.

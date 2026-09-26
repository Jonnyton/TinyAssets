# Migration and scratch records are publicly discoverable universes

**Found** 2026-09-02, driving the rewritten `/commons` page against the live
endpoint (`read_graph target=graphs`, limit 100, through
`WebSite/shared/mcp/public-read-contract.js`).

**Severity** P2. Nothing leaks a credential or another user's contents — the
public projection is ids, phase, word count and a coarse timestamp — but the
public list is most of the way to being an internal changelog, and it is the
first thing a visitor sees on the commons page.

## What the endpoint returns

Twelve universes, every one `visibility=public`:

| id | what it looks like |
|---|---|
| `_backup_subject_migration_20260829T055340Z` | WorkOS subject-migration backup |
| `_removed_legacy_20260829` | removal bucket |
| `_removed_universes_20260828` | removal bucket |
| `_removed_universes_20260829` | removal bucket |
| `cloud-automation-inputs` | internal working bucket |
| `daemon_wikis` | internal working bucket |
| `scratch` | internal working bucket |
| `paper-notes` | founder's working universe |
| `u-tiny`, `u-01kxm1…`, `u-01ky3z…`, `u-01m160…` | real universes |

The four leading-underscore records date from the 2026-08-28/29 IdP subject
migration and the fleet/universe removals. They were created by maintenance,
not by a person choosing to publish, and they inherited `public` visibility.

## Why it matters

- **The commons is a library of shapes to remix.** Seven of twelve rows are
  not shapes anyone can remix, which makes the page read like an accident.
- **Publishing is supposed to be a choice.** These records were never
  published by a decision; they defaulted into a public projection.
- **It advertises internal history.** Bucket names disclose when removals and
  an identity migration happened, and that they were done by moving records
  into dated holding universes.

## What is NOT the fix

Filtering leading-underscore ids in the website. The site would then be
claiming a list is "what is publicly discoverable" while hiding part of it,
which is the exact dishonesty the public-read boundary exists to prevent. The
site now carries a note saying the list is raw rather than curated
(`WebSite/site-react/app/commons/page.tsx`); that is a caption on the problem,
not a resolution.

## Mostly answered by the ownership predicate (2026-09-26)

A universe now exists because an ownership row names it, not because a folder is
on disk (`openspec/specs/universe-lifecycle-and-soul/spec.md`, "A universe exists
because an ownership row names it"). All seven rows above are directories
maintenance created; none is named by a `universe_acl` grant or a `founder_home`
binding. So they stop being enumerated AND stop being readable by id — including
through `read_page` and explicit-id `get_status`, which previously reached them
because they asked only about visibility and the old boot backfill had already
written `visibility_level=public`.

That is a better answer than steps 1 and 2 below were: **it writes nothing to any
live universe record.** Nothing is deleted either — the migration backups stay on
disk exactly as `docs/host-actions.md` requires, they are simply not universes.

### What is left

1. **Confirm no real universe goes dark, before the deploy.** Ownership is
   matched exactly, so a universe with no row — a pre-migration one, or one
   restored under a different case — would also become invisible. `paper-notes`
   in the table above is the candidate to check.
   `python scripts/universe_ownership_inventory.py` is read-only, lists every
   directory with its owners, and exits 1 naming any directory that carries a
   universe signal and has no ownership row. Exit 0 is the go-ahead; a named
   directory needs its missing row written first.
2. **Still a founder call: should `visibility` default to `public` at all for a
   universe nobody published?** The public read contract already refuses
   anything not explicitly `public`/`metadata_only`, so the default is the only
   thing that ever made these visible. Independent of the above, and the reason
   this file is not deleted yet.

Delete this file when (1) is confirmed on the live root and (2) is decided.

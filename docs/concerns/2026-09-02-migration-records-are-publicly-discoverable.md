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

## Suggested fix (needs the founder, touches live data)

1. Decide the default: maintenance-created holding records should be created
   `private`, not `public`. Find where the migration and removal buckets are
   created and set visibility explicitly.
2. Flip the seven existing non-universe records to private. Per
   `verify-the-binding-in-the-destructive-step`, run the ownership query
   inside the same command that writes, and do not delete anything: these are
   backups of a migration.
3. Consider whether `visibility` should even default to `public` for a
   universe nobody published. The public read contract already refuses
   anything that is not explicitly `public`/`metadata_only`, so the default is
   the only thing making these visible.

Delete this file when the public list is universes people chose to publish.

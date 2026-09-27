# Four note/work-target helpers wipe a universe's display name on every call

**Filed:** 2026-09-26 | **Verified:** 2026-09-26 | **Severity:** P2
**Found:** while widening PR #4019's creation-path sweep — grepping every writer
of a universe row turned these up. Same defect class the Codex round-3 review
found in that PR's migration, in four more places, on hotter paths.

## The defect

`daemon_server.ensure_universe_registered` is an UPSERT whose conflict clause is:

```sql
ON CONFLICT(universe_id) DO UPDATE SET
    display_name=excluded.display_name,
    host_path=excluded.host_path,
    metadata_json=excluded.metadata_json
```

`display_name` defaults to `display_name or universe_id` and `metadata` to `{}`.
So calling it for an **already-registered** universe without passing those values
replaces the owner's display name with the raw universe id and wipes the registry
metadata — and reports success.

These four call it with only `universe_id` and `universe_path`:

| `tinyassets/daemon_server.py` | function |
|---|---|
| ~1952 | `list_note_dicts` |
| ~1985 | `add_note_dict` |
| ~2105 | `list_work_target_dicts` |
| ~2132 | `upsert_work_target_dict` |

Two of those are **reads** (`list_note_dicts`, `list_work_target_dicts`), so a
universe loses its name as a side effect of listing its own notes. These run far
more often than the boot path PR #4019 fixed, which makes this the worse instance
even though it is the same bug.

## Why it is P2 and not P1

Nothing leaks and nothing cross-user happens: `display_name` and the registry
`metadata_json` are presentation and bookkeeping, not authority. The blast radius
is "the universe's name reverts to its id", which is user-visible and annoying
rather than unsafe. It is also long-standing.

## The fix, which already exists

`tinyassets/api/visibility.py::register_if_absent(base, universe_id)` is the
guarded form PR #4019 introduced for exactly this: it checks
`SELECT 1 FROM universes WHERE universe_id = ?` and only registers when absent.
The four call sites become `register_if_absent(base_path, universe_id)`.

It was deliberately **not** done in #4019 for two reasons, both worth re-checking
before acting:

1. `daemon_server.py` was held by PR #4012 under a head-pinned review receipt, and
   every push to that branch voids the lead's stamp. Check whether #4012 has landed
   first.
2. #4019 was under an explicit velocity instruction to batch one push and send P2s
   to a concern file rather than widen.

Registration is all these helpers need — they call it to satisfy the
`universe_rules`/notes foreign key. A rename is a different operation with its own
caller, so "only if absent" loses nothing.

## Test to write with the fix

Seed a universe via `ensure_universe_registered(..., display_name="My name",
metadata={"keep": 1})`, call each of the four helpers, and assert both survive.
Then remove the guard and confirm each assertion goes red — PR #4019's three
equivalents (`test_it_does_not_overwrite_an_existing_registry_row`,
`test_backfill_does_not_wipe_an_owners_display_name_or_metadata`,
`test_the_startup_gate_does_not_wipe_it_either`) are the pattern to copy.

Delete this file when the four call sites are guarded and tested.

# Six universe content readers gate on the legacy bit, not on `read_content`

**Filed:** 2026-09-26 | **Verified:** 2026-09-26 | **Severity:** P2
**Found:** following the Codex cross-family review of PR #4019, which reproduced
one instance of this class (`get_memory_scope_status`); I grepped for the pattern
and found six more.

## The pattern

`set_universe_visibility` sets the legacy `public_read` bit to `True` whenever a
level grants an unauthenticated visitor **any** capability
(`tinyassets/api/visibility.py`, `any_anon_capability`). That is correct as a
*ceiling* for `visibility_permits`, which ANDs the legacy gate with the declared
level. It is wrong for any reader that consults `public_read` **alone**, because
such a reader sees `metadata_only` as fully open.

`_universe_acl_error` (`tinyassets/api/universe.py`) is that kind of reader. For a
non-write action it checks `permissions.universe_access_allows(uid, write=False)`
— the legacy bit — and nothing else. Actions that add their own capability gate on
top are fine: `_action_inspect_universe` adds `read_metadata`,
`_action_list_universes` adds `discover_existence`, and `wiki` adds `read_content`.

These six return raw universe **content** and add nothing:

| Action | What it returns |
|---|---|
| `get_activity` | raw `activity.log` lines |
| `read_premise` | the universe's premise / soul purpose |
| `read_canon` | a canon document's bytes |
| `read_source` | an ingested source document |
| `read_output` | generated output files |
| `query_world` | world-state contents |

`tinyassets/api/runs.py::_run_read_allowed` has the same shape for run records.

## Why it is P2, not P1

`metadata_only` and `unlisted` are currently **unreachable in practice**. Nothing
in production produced them: the creation default and the backfill only ever wrote
`public` or `private`, and before PR #4019 there was no owner-facing verb at all.
For the two levels that do occur, the legacy bit and the declared level agree, so
the missing check changes no outcome today.

It becomes live the moment anything can select those levels. PR #4019 therefore
**does not offer them** on the new owner verb
(`universe._OFFERED_VISIBILITY_LEVELS = {"private", "public"}`) and says why in
place. A dev/migration caller reaching `set_universe_visibility` directly can still
produce one, which is the residual exposure.

PR #4019 fixed the one instance the reviewer reproduced
(`get_memory_scope_status`, now `visibility_permits(uid, "read_content")`) because
its own change made that one reachable. It left the other six alone rather than
expanding an authority PR into six more actions.

## The fix

Do it in the ONE place, not six: `_universe_acl_error` already knows the action, so
add a `CONTENT_READ_ACTIONS` table beside `WRITE_ACTIONS` in the same module and
gate those actions on `visibility_permits(uid, "read_content")` instead of the
plain legacy read. Six sprinkled copies of the same check is the second-definition
failure mode.

Take care not to over-restrict: decide deliberately, per action, whether its
payload is content or metadata (`get_ledger` and `list_canon` are arguable and are
deliberately not in the table above), and give each decision a test. Then add
`metadata_only` and `unlisted` back to `_OFFERED_VISIBILITY_LEVELS` and drop the
`level_not_enforced` refusal branch.

Delete this file when the six are gated and the owner verb offers all four levels.

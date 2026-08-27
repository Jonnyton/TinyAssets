## Context

The April audit described three blocking gaps, but current code has moved:

- Goal action ownership is now `tinyassets/api/market.py`.
- Default canonical persistence is `goals.canonical_branch_version_id`, with an
  older `canonical_bindings` transition experiment also mirroring the default.
  That table has no supported personal set/get action and does not match the
  host-approved `goal_canonicals` contract.
- `tinyassets/api/runs.py::_action_run_branch_version` and
  `tinyassets/runs.py::execute_branch_version_async` already reconstruct and run
  an immutable published snapshot. `run_canonical` already delegates to it.
- `tinyassets/evaluation.EvalVerdict` now includes the landed route-back
  decision and typed patch-notes payload.

The implementation is additive and preserves existing author/capability
authority. The canonical MCP surface routes actor-scoped writes and runs through
the same Goal dispatcher; it adds no new advertised handle and does not change
`tinyassets/api/universe.py`.

## Goals / Non-Goals

**Goals:**

- Store one canonical per `(goal_id, scope_actor)`.
- Let an authenticated actor bind only their own personal scope on any visible
  Goal without gaining authority over the Goal default.
- Prefer the actor's binding when resolving or running a Goal canonical, then
  fall back to the default binding and legacy column.
- Keep default author/capability writes compatible throughout the transition.
- Define and implement the Goal-aware gate route-back and immutable-runner
  contract.
- Expose personal canonical binding and execution through the advertised
  canonical MCP handles.

**Non-Goals:**

- Removing `goals.canonical_branch_version_id` or the pre-existing
  `canonical_bindings` table.
- Adding team, tier, delegated, or arbitrary cross-actor canonical authority.
- Changing leaderboard selection policy or allowing it to overwrite personal
  actor bindings.
- Adding another MCP handle for Goal canonical operations.

## Decisions

### 1. Use the approved exact additive table

SQLite and migration 011 use:

```sql
goal_canonicals(
    goal_id,
    scope_actor,
    branch_version_id,
    set_at,
    set_by,
    PRIMARY KEY (goal_id, scope_actor)
)
```

`scope_actor=''` is the default canonical. A non-empty value is the exact
authenticated actor ID. The schema does not encode future tier/team policy.
This is narrower than reusing `canonical_bindings.scope_token`: the approved
contract is actor-only and therefore harder to misuse.

Alternative considered: adapt `canonical_bindings`. Rejected because its opaque
scope tokens, visibility policy, and binder fields expose a broader authority
model than the approved bundle and it lacks a supported per-user action.

### 2. Separate default and personal writes, share validation

`set_canonical_branch` remains the default author/host storage helper and
continues updating the legacy Goal column. It also upserts/deletes the
`scope_actor=''` row in `goal_canonicals`. A personal helper writes only the
caller's non-empty `scope_actor` row. Both helpers validate that the Goal exists
and any supplied version is a published active snapshot before mutation.

The existing `canonical_bindings` mirror remains temporarily updated by default
writes solely to preserve already-shipped readers/tests; it is not consulted for
personal resolution. Thus the logical transition is dual-write
(`goals` + `goal_canonicals`) while one legacy compatibility mirror remains.

### 3. Resolution is exact actor, default row, legacy column

`resolve_goal_canonical(goal_id, scope_actor)` performs:

1. Exact non-empty `scope_actor` row.
2. `scope_actor=''` default row.
3. `goals.canonical_branch_version_id`.

Missing Goal fails loudly. An unset personal row means fallback, not a stored
null. Anonymous resolution skips the personal step.

Alternative considered: project the personal result into
`goal["canonical_branch_version_id"]`. Rejected because that observable field is
the legacy Goal default and existing callers depend on that meaning.

### 4. Tighten-only action authorization

`goals action=set_canonical` uses the existing action-specific `scope` argument
as the requested actor scope and persists it as `scope_actor`.

- Empty/missing scope keeps current Goal-author or canonical capability checks.
- Non-empty `scope` requires an authenticated actor and exact equality with the
  current actor.
- Author, host, and capability holders do not gain permission to mutate another
  actor's personal row.

This preserves default semantics and prevents confused-deputy cross-user writes.

### 5. Personal canonical dispatch reuses the existing immutable runner

`resolve_canonical_for_run` checks the caller's personal row first. When found,
it returns that immutable `branch_version_id` with source
`actor_canonical`; `run_canonical` then uses the existing
`_action_run_branch_version` delegation. Default auto-leaderboard refresh runs
only when no personal binding exists, so shared policy cannot overwrite a
user's explicit route.

### 6. Gate rejection uses a typed route-back decision

The full design adds a `route_back` evaluation decision carrying `goal_id` and
typed `PatchNotes`. The run actor is the canonical scope; callers cannot name a
different actor. The handler appends route history, rejects repeated
`(goal_id, scope_actor)` hops or depth beyond three, resolves through
`goal_canonicals`, and synchronously invokes the immutable version runner.
Missing bindings, malformed notes, missing artifacts, and loops terminate with
structured errors rather than silently falling through to a live definition.

This decision is implemented by the completed route-back tasks in section 4.

### 7. Canonical handles adapt to the existing Goal dispatcher

`write_graph target=goal operation=set_canonical` forwards `goal_id`,
`branch_version_id`, and `scope` to the existing tighten-only Goal action.
`run_graph goal_id=...` forwards run inputs and limits to `run_canonical`, which
derives the current actor and dispatches the resolved immutable version. A call
that supplies both `branch_def_id` and `goal_id` is rejected as ambiguous. This
keeps authorization, attribution, and canonical resolution in their existing
owners while preserving the advertised handle set.

## Risks / Trade-offs

- [Two transition tables exist temporarily] → Keep `goal_canonicals` as the only
  personal-resolution source and document `canonical_bindings` as compatibility
  residue; remove it only in a separately approved migration.
- [Dual-write divergence] → Perform all SQLite writes in one connection
  transaction and test overwrite/unset/fallback cases.
- [Personal binding exposes another actor's private choice] → No list surface is
  added; exact-scope reads are derived from current authenticated identity.
- [A stored version is rolled back after binding] → Binding rejects inactive
  versions, but canonical resolution and the existing runner do not re-check
  status after a later rollback, so the stored immutable snapshot can still be
  queued. This behavior is inherited from the existing default-canonical path;
  route-back implementation must classify inactive artifacts explicitly, and a
  separate follow-up is required if all canonical runs must reject them.
- [Migration 011 is present before parallel migration 010] → Do not renumber or
  add a placeholder. Record that the strict PostgreSQL chain cannot apply 011
  until 010 lands.

## Migration Plan

1. Add SQLite `goal_canonicals` DDL and idempotently backfill default rows from
   non-null legacy Goal canonicals.
2. Add PostgreSQL `011_goal_canonicals.sql`, dependent on migration 010's Goal
   and Branch-version storage.
3. Start dual-writing default canonical mutations; leave legacy reads valid.
4. Enable personal set/get storage and actor-aware `run_canonical`.
5. Observe and later migrate remaining default readers.
6. Implement typed gate route-back in a follow-up slice, then remove transition
   residue only after verified zero use.

Rollback is behavioral: disable personal action usage and return to the legacy
Goal column, which remains current because of dual-write. Do not drop data as
part of rollback.

## Open Questions

- What final migration retires the earlier `canonical_bindings` experiment?
- Which contribution event should a completed route-back emit?

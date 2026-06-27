# Canonical-Branch-for-Goal Primitive Audit

**Date:** 2026-04-25
**Author:** dev-2
**Scope:** read-only audit. Answers questions A-F about the canonical-branch primitive's data model, authz, action surface, lookup, variant support, and Mark gate-series user-story gap. NO redesign. Lead routes redesign as a follow-up.
**Surfaces read:** `tinyassets/daemon_server.py` (lines 285-424 schema; 2240-2429 canonical helpers; 2525-2553 `branches_for_goal`); `tinyassets/universe_server.py` (lines 9996-10702 `_action_goal_*` handlers + `_GOAL_ACTIONS` registry); `tests/test_canonical_branch.py`, `tests/test_canonical_branch_mcp.py`, `tests/test_goals_*.py`.

---

## Summary

The canonical-branch primitive is **strictly per-goal-one-canonical**. There is no per-(goal, user) variant slot, no per-(goal, scope) slot, and no notion of "my canonical" vs "the goal's canonical." A Goal has at most one `canonical_branch_version_id` at any time; setting a new one overwrites the previous (with full history retained for audit).

Authorization on `set_canonical` is **single-author + host fallback**: only the Goal's `author` field or the host actor (`UNIVERSE_SERVER_HOST_USER`, default "host") may call it. No governance / DAO / co-author / delegate model.

There is **no `goals action=resolve_canonical(goal_id)` lookup verb.** The canonical lookup primitive is the `canonical_branch_version_id` field on the Goal row, retrievable via `goals action=get goal_id=...`. Code that needs to "send back to canonical for goal X" must `get_goal` and read the field — no first-class router.

For Mark's gate-series user-story ("for MY goal G, MY canonical is branch B"), the data model **does not support per-user canonicals**. Mark cannot have his own canonical for a Goal he didn't author without one of: (a) authoring his own Goal that wraps the same intent, (b) governance change letting non-authors set the Goal's single canonical, or (c) a new schema column for variant canonicals.

---

## A. Data model

### Storage table: `goals` (`tinyassets/daemon_server.py:301-310`)

```sql
CREATE TABLE goals (
    goal_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT 'anonymous',
    tags_json   TEXT NOT NULL DEFAULT '[]',
    visibility  TEXT NOT NULL DEFAULT 'public',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
```

### Canonical-binding columns (added by migration, `daemon_server.py:413-423`)

| Column | Type | Default | Purpose |
|---|---|---|---|
| `canonical_branch_version_id` | TEXT | NULL | The single published `branch_version_id` designated as canonical for this Goal. NULL = no canonical set. |
| `canonical_branch_history_json` | TEXT | `'[]'` | History of previous canonicals: list of `{branch_version_id, unset_at, replaced_by}` entries appended whenever a new canonical replaces an old one. Audit-only; not used for routing. |

**Cardinality:** strictly one `canonical_branch_version_id` per goal_id. A Goal row can have at most one current canonical.

**Persistence:** the canonical is a column on the `goals` table itself, not a separate `canonical_bindings` table. This means there is no schema headroom for a per-(goal, user) canonical without either a new column (one-of-some-fixed-set) or a new table (general N-to-N).

**Reference semantics:** `canonical_branch_version_id` points to a row in `branch_versions`, NOT to a `branch_def_id`. Validation enforces this in `set_canonical_branch` (`daemon_server.py:2381-2388`) — only published branch versions can be canonical. This is a deliberate immutability primitive: the canonical points at a specific version snapshot, so editing the live `branch_definitions` row doesn't silently shift the canonical's behavior.

---

## B. Authorization on `set_canonical`

### Server-side authority (`tinyassets/universe_server.py:10648-10658`)

```python
actor = _current_actor()
host_actor = os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")
if actor != goal["author"] and actor != host_actor:
    return json.dumps({"status": "rejected", "error": ...})
```

**Two paths:**
1. Goal author (`goal["author"]` field) may set canonical.
2. Host actor (`UNIVERSE_SERVER_HOST_USER`, default `"host"`) may set canonical regardless of authorship.

**Storage-layer note (`daemon_server.py:2362-2364`):**
> "Only the Goal author or a host-level actor may set canonical. **Caller must validate authority before calling this function.**"

The storage layer is permissive — `set_canonical_branch()` does not re-check authority. The MCP action layer is the only gate. Direct `daemon_server.set_canonical_branch()` calls bypass the check entirely. This is acceptable for the current single-process daemon but flags as a defense-in-depth gap.

**No governance / co-author / delegate model.** No DAO vote, no community-flag, no per-team admin. Mark cannot set canonical on someone else's Goal even if 100 users want him to.

---

## C. Action surface inventory

### `_GOAL_ACTIONS` registry (`tinyassets/universe_server.py:10688-10698`)

| Action | Handler | Args | Returns | Write? |
|---|---|---|---|---|
| `propose` | `_action_goal_propose` | `name`, `description`, `tags`, `visibility` (public/private), `force` | `{status: "proposed", goal: {...}}` | Yes |
| `update` | `_action_goal_update` | `goal_id`, optional fields | updated goal | Yes |
| `bind` | `_action_goal_bind` | `branch_def_id`, `goal_id` (empty = unbind), `force` | `{status: "bound" \| "unbound"}` | Yes |
| `list` | `_action_goal_list` | `author`, `tags`, `limit` | `{goals: [...], count}` | No |
| `get` | `_action_goal_get` | `goal_id` | `{goal: {...}, branches: [...], gate_summary: ...}` | No |
| `search` | `_action_goal_search` | `query`, `limit` | `{goals: [...]}` | No |
| `leaderboard` | `_action_goal_leaderboard` | TBD | gate-claim ranking | No |
| `common_nodes` | `_action_goal_common_nodes` | TBD | shared-node analysis | No |
| `set_canonical` | `_action_goal_set_canonical` | `goal_id`, `branch_version_id` (empty = unset) | `{status: "ok", canonical_branch_version_id}` | Yes |

**Write actions** (gated through ledger commit): `propose`, `update`, `bind`, `set_canonical` (`_GOAL_WRITE_ACTIONS` at `universe_server.py:10700-10702`).

**Soft-delete:** there is no `delete` action in `_GOAL_ACTIONS`. The propose handler (`universe_server.py:10013`) hints at a future `delete_goal` action, but it isn't wired in `_GOAL_ACTIONS`. Goals soft-delete via `visibility='deleted'` set through `update`, judging by handler patterns.

**No actions for:**
- Resolving the canonical branch (no `resolve_canonical`, `get_canonical`, or similar).
- Listing goals by their current canonical's status.
- Querying the canonical history.
- Setting per-user canonical variants.
- Gate-routing decisions (no "where do rejected patches go" verb).

### Storage-layer surface (`daemon_server.py`)

| Function | Lines | Purpose |
|---|---|---|
| `save_goal` | 2272-2301 | Insert/replace goal row. Does NOT touch canonical fields. |
| `get_goal` | 2304-2318 | Read goal incl. canonical_branch_version_id + canonical_branch_history. |
| `set_canonical_branch` | 2354-2411 | Set/unset canonical. Validates branch_version_id exists. Appends prev to history. |
| `get_canonical_branch_history` | 2414-2428 | Read-only history fetch. Returns `[]` for missing goals (silent). |
| `branches_for_goal` | 2525-2553 | List branches bound to goal. NO canonical-awareness — returns all bound, no "which is canonical" sort. |

**Gap:** no convenience function `get_canonical_branch(goal_id) -> branch_version_id | None` at the storage layer. Callers must `get_goal()` and read the field.

---

## D. Lookup primitive

**There is no first-class "resolve canonical" lookup primitive.**

The only path to find "the canonical branch for goal X" is:

```python
goal = get_goal(base_path, goal_id="...")
canonical_bvid = goal["canonical_branch_version_id"]  # may be None
```

Or via MCP:

```
goals action=get goal_id=...
# parse response.goal.canonical_branch_version_id
```

**Implications for "send back to canonical for goal X" routing:**
- Any code that needs to route to canonical (gate node, dispatcher, scheduler) must do a goals lookup as a separate step.
- No subscription / event surface fires when canonical changes — code that has cached a canonical must re-lookup or stale.
- No `branch_version_id → canonical_for_goals[]` reverse index. If branch B is canonical for goal G, you can find G only by enumerating goals and inspecting each.
- The `branches` payload in `goals action=get` lists ALL bound branches but does NOT mark which one is canonical. Chatbot has to read `goal.canonical_branch_version_id` separately and cross-reference manually.

This is fine for the current low-volume cases. It becomes load-bearing when:
- A gate node needs to route hundreds of rejected patches per day.
- A scheduler needs to enumerate "all canonicals for filing" without a separate goal query per branch.
- A chatbot needs to render "this is THE canonical" badges in branch-list output.

---

## E. Variant-canonical support

**The schema does not permit per-(goal, user) or per-(goal, scope) canonicals.**

`canonical_branch_version_id` is a single TEXT column on `goals` with at most one value per goal. To support variants would require one of:

1. **New table** (cleanest): `goal_canonicals(goal_id, scope_actor, branch_version_id, set_at, set_by)` with composite primary key. Lookup becomes "give me canonical for (goal, actor) with fallback to (goal, NULL)."
2. **JSON column extension**: stuff a `{actor: branch_version_id}` map into a new `canonical_variants_json` column. Cheaper but not queryable via SQL — every read deserializes.
3. **Branch-side flag**: add `is_canonical_for_user TEXT` on `branch_definitions` or `branch_versions`. Rotates the schema axis; gets messy if a branch is canonical for multiple users.

None of these exist today. Mark's "MY canonical for goal G" intent has no schema slot to land in.

**Migration path for option 1** (no design here, scoping only): introduce `goal_canonicals` table, write into it ALSO when set_canonical fires (mirror to existing column for backward compat during transition), then deprecate the column on `goals` once readers all migrated. ~2-week window.

---

## F. Mark gate-series user-story walkthrough

### Mark's intent (per task brief)

> "for MY goal G, MY canonical is branch B; if any gate rejects, route patch_notes back to B."

Walk through the calls Mark would make today:

| Step | Mark's intent | Call | Today's result |
|---|---|---|---|
| 1 | Find or create Goal G | `goals action=propose name=G` (if new) or `goals action=search query=G` | ✓ works. Mark gets goal_id. |
| 2 | Bind his branch B to G | `goals action=bind branch_def_id=B goal_id=G` | ✓ works. Branch is now in `branches_for_goal(G)`. |
| 3 | Set B as MY canonical for G | `goals action=set_canonical goal_id=G branch_version_id=v(B)` | ✗ **FAILS UNLESS Mark IS the goal's author.** If someone else proposed G (e.g. host or another user), Mark gets `"Only the Goal author or a host-level actor may set the canonical branch."` |
| 4 | Tell gate node "if reject, route back to canonical for G" | (no MCP action exists) | ✗ **NO ROUTING PRIMITIVE EXISTS.** Gate nodes have no way to declare "on reject, send patch_notes back to canonical_for(goal_id)." Gate-rejection routing today is hard-coded in node graph definitions, not goal-aware. |
| 5 | At runtime, gate node looks up canonical for G | `goals action=get goal_id=G`, parse `canonical_branch_version_id` | ✓ works (lookup is read-only and unauthenticated). |
| 6 | Gate node spawns a run on the canonical with patch_notes payload | (no `run_branch_version_with_payload` primitive) | ✗ **NO RUN-FROM-VERSION PRIMITIVE.** Today branches run via `run_branch_def_id` (live editable definition). The canonical is a published `branch_version_id` (immutable snapshot). The runner doesn't accept `branch_version_id` as input AFAICS. |

### Gap list (priority-ranked)

| # | Gap | Severity for Mark's story | Severity for platform |
|---|---|---|---|
| **1** | No per-user canonical. Authorship gates set_canonical to one actor. | **Blocking** | High — variant canonicals are a load-bearing piece of the convergence story. |
| **2** | No `goals action=resolve_canonical(goal_id)` first-class lookup. Today must use `get` and parse. | Medium | Medium — works today; will not scale to high-frequency gate routing. |
| **3** | Gate-rejection routing has no goal-aware "send to canonical" verb. | **Blocking** | High — without this, gate output has nowhere typed to land for Mark's story. |
| **4** | Runner does not accept `branch_version_id` (immutable snapshot) as a run target. Only `branch_def_id` (live editable). | **Blocking** | Medium-high — canonical immutability is a feature; runner needs to honor it. |
| **5** | No reverse index from `branch_version_id → goals_where_canonical[]`. | Low for Mark | Low for now; matters if any "where am I canonical" UX is built. |
| **6** | `branches_for_goal()` does not surface which branch IS canonical in its return shape. | Low | Low — chatbot can compute by reading `goal.canonical_branch_version_id` separately. |
| **7** | Storage-layer `set_canonical_branch()` does not re-check authority. | Low (defense in depth) | Low — defense-in-depth gap, not exploitable in current single-process daemon. |
| **8** | No event/subscription on canonical change. Cached lookups go stale silently. | Low for now | Low — relevant when scheduler / gate nodes cache canonicals across runs. |

### What unblocks Mark's story

The minimal viable path is **gaps #1, #3, #4** — the three "Blocking" rows. Without #1, Mark cannot register his variant. Without #3, the gate cannot route. Without #4, the gate cannot actually invoke a canonical version.

#2 and #5–#8 are nice-to-haves; the story works without them via current `goals action=get` + manual cross-reference, just slower / clunkier.

---

## What this audit does NOT cover

- **No design proposal** for resolving any gap. Lead routes redesign as a follow-up dispatch.
- **No live MCP probes** — paper audit only against the source. To certify any specific call's behavior, run `scripts/mcp_probe.py` against the production endpoint with real test data.
- **No Mark-session cross-reference.** Mark's wins/grievances files were skimmed; no MARK-W or MARK-F entry today specifically requests canonical variants — the user-story is forward-looking from the host, not retro from a Mark session.
- **No exec-plan check.** Whether `set_canonical` migration has fully landed in production (cloud daemon redeploy is currently STATUS-blocked per Task #32 row) is not verified here — the audit reads code state, not runtime state.

---

## References

- Schema: `tinyassets/daemon_server.py` lines 301-310 (goals table) + 413-423 (canonical migration).
- Storage helpers: `tinyassets/daemon_server.py` lines 2240-2429.
- MCP handler: `tinyassets/universe_server.py` lines 10634-10685 (`_action_goal_set_canonical`).
- MCP registry: `tinyassets/universe_server.py` lines 10688-10702 (`_GOAL_ACTIONS`, `_GOAL_WRITE_ACTIONS`).
- Tests: `tests/test_canonical_branch.py`, `tests/test_canonical_branch_mcp.py`.
- Storage-split scoping: `docs/design-notes/2026-04-25-arch-audit-5-r7-split-scoping.md` line 81 (acknowledges current goal-CRUD scope).
- Mark persona: `.claude/agent-memory/user/personas/mark/` (no canonical-variants grievance on file as of 2026-04-25).

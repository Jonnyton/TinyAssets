---
status: active
---

# Variant Canonicals — Schema Proposal

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Lead/navigator/host ratifies for v2 self-evolving-platform vision.
**Builds on:** `docs/audits/2026-04-25-canonical-primitive-audit.md` (G1 audit) — surveyed 3 paths, declined to design. This proposal picks ONE.
**Scope:** schema design only. Not a code dispatch. Code follows after ratification.

---

## 1. Recommended schema — new `canonical_bindings` table

Pick **Path 1** from G1 audit: separate composite-key table, NOT a JSON column on `goals` and NOT a branch-side flag.

### Schema

```sql
CREATE TABLE canonical_bindings (
    goal_id            TEXT NOT NULL,
    scope_token        TEXT NOT NULL DEFAULT '',  -- '' = unscoped/default canonical
    branch_version_id  TEXT NOT NULL,
    bound_by_actor_id  TEXT NOT NULL,
    bound_at           REAL NOT NULL,
    visibility         TEXT NOT NULL DEFAULT 'public',  -- 'public' | 'private'
    PRIMARY KEY (goal_id, scope_token),
    FOREIGN KEY (goal_id)           REFERENCES goals(goal_id),
    FOREIGN KEY (branch_version_id) REFERENCES branch_versions(branch_version_id)
);

CREATE INDEX idx_canonical_bindings_goal       ON canonical_bindings(goal_id);
CREATE INDEX idx_canonical_bindings_actor      ON canonical_bindings(bound_by_actor_id);
CREATE INDEX idx_canonical_bindings_branch_ver ON canonical_bindings(branch_version_id);
```

### Why this shape

- **Per-(goal, scope) uniqueness via composite primary key.** Schema enforces "one canonical per goal+scope" — no ambiguity, no race for who-wins.
- **`scope_token` is opaque.** Conventions are app-level: `''` = default/unscoped, `user:<actor_id>` = per-user variant, `tier:<tier_name>` = community-tier variant, `team:<team_id>` = future. The schema treats these as opaque strings; resolution rules below are pure-app-layer policy and can evolve without schema changes.
- **`bound_by_actor_id` separate from `scope_token`.** A user can bind a `tier:expert` canonical they qualify for; the binder isn't always the scope. Authority checks read `bound_by_actor_id` against scope-policy rules (§4).
- **`visibility` per-binding, not per-goal.** Symmetric privacy is filterable in a single SQL `WHERE` clause, not a post-fetch loop.
- **Indexes for the three real queries.** Forward (`goal → canonical`), reverse (`actor → canonicals_i_bound`), and "where is this branch canonical" (`branch_version_id → goals`).

The retained column on `goals` (`canonical_branch_version_id`) becomes a derived/materialized view of `canonical_bindings WHERE goal_id = ? AND scope_token = ''` — see migration §5.

---

## 2. Tradeoff table

| Axis | Path 1: New table (recommended) | Path 2: JSON column on goals | Path 3: Branch-side flag |
|---|---|---|---|
| **Schema complexity** | New table + 3 indexes. Moderate. | Single `canonical_bindings_json` column added. Lowest. | New `is_canonical_for(goal,scope)` field on `branch_versions` or `branch_definitions`. Moderate but rotates wrong axis. |
| **Query performance — forward (goal → canonical)** | O(log n) index lookup per scope. Excellent. | O(1) deserialize-then-dict-lookup. Good for small variant counts; degrades when 1000s of variants per goal. | Full scan of branches table where `is_canonical_for=goal_id` matches. Poor without index. |
| **Reverse (actor → my canonicals)** | Trivial — `WHERE bound_by_actor_id = ?`. | **Awful** — full goals table scan + JSON deserialize per row. | Easy if branch carries actor; messy if branch is canonical for someone else's goal. |
| **Lookup-by-scope ergonomics** | `SELECT * FROM canonical_bindings WHERE goal_id=? AND scope_token IN (?, '')`. Clean. | App-side dict access after deserialize. Clean for flat scopes; messy with fallback chain. | Branch-side filtering requires cross-table join. Awkward. |
| **Authority model fit** | Per-row visibility + bound_by_actor lets §4 authority rules express cleanly. | Requires JSON-internal authority checks (per-key visibility encoded inside the JSON). Brittle. | Authority lives on the branch row, not the binding — confuses "who owns the binding" with "who owns the branch." |
| **Migration cost** | New table + dual-write shim during transition. Highest cost. | Add column + json-encode current single canonical. Lowest cost. | Add fields to branch tables, backfill canonical bindings to those fields. Painful. |
| **Symmetric-privacy filterability** | `WHERE visibility='public' OR bound_by_actor_id = ?` — single SQL clause. Best. | Per-row JSON filter post-fetch. Bad. | Visibility lives on branch, but binding may have different visibility — misfit. |
| **Reverse index "branch is canonical for which goals"** | `WHERE branch_version_id = ?`. Single indexed lookup. | Full scan + deserialize. | Trivial — read the branch row. |
| **Resolution-rule expressibility (§3)** | Multi-row + composite PK lets fallback chain (`scope_token IN (?, '')` ordered by scope priority) be a single SQL select. | Possible via app code; not enforced. | Hard — need cross-row coordination. |

**Net:** Path 1 wins on every read pattern that matters at scale. Path 2 wins only on initial migration cost. Path 3 wins only on "branch knows its own canonical scope," which is the wrong invariant — the binding is goal-centric, not branch-centric.

---

## 3. Resolution rule

When code asks "what's the canonical branch for goal G, from actor A's perspective?" the resolver runs this fallback chain:

```sql
SELECT branch_version_id FROM canonical_bindings
 WHERE goal_id = :goal_id
   AND (visibility = 'public' OR bound_by_actor_id = :viewer_actor_id)
   AND scope_token IN ('user:' || :viewer_actor_id, :community_tier, '')
 ORDER BY
   CASE scope_token
     WHEN 'user:' || :viewer_actor_id THEN 1
     WHEN :community_tier THEN 2
     ELSE 3
   END
 LIMIT 1;
```

**Default rule (most → least specific):**
1. **My personal canonical** (`scope_token = 'user:<my_actor_id>'`) — if I've bound one, it wins.
2. **My community-tier canonical** (`scope_token = 'tier:expert'` etc.) — if my tier has a binding.
3. **Goal default canonical** (`scope_token = ''`) — set only by Goal author or host.

**Override mechanism:** the MCP action accepts an optional `canonical_scope` arg that pins the resolver to one tier. `goals action=resolve_canonical goal_id=G canonical_scope=user:alice` returns alice's binding directly without falling through. Used by gate nodes that want "MY canonical" specifically.

**Why this default order:** matches G1 blocker #1 (Mark needs HIS canonical to win for HIM) AND matches the ratified principle from `project_user_builds_we_enable` ("if users can make it, the user does"). Personal scope beats tier beats global default — users own their own routing decisions.

**Edge case — viewer with no actor (anonymous):** falls through immediately to the goal default canonical. Anonymous users get the Goal author's binding. Documented in resolver docstring.

**Edge case — multiple tiers per actor:** scope_token is single-valued; the resolver takes whichever tier appears first in a config-provided priority list. Tier ranking is policy, not schema. Punt to §6 open question.

---

## 4. Authority model

Matches `project_user_builds_we_enable`: any user binds their own scope; only Goal author touches the unscoped default.

| Action | Who can perform |
|---|---|
| Bind `scope_token = 'user:<my_actor_id>'` | The actor whose id matches the suffix. Anyone can bind THEIR own variant on any public Goal. |
| Bind `scope_token = ''` (default) | Goal author OR `UNIVERSE_SERVER_HOST_USER`. Same as today. |
| Bind `scope_token = 'tier:<tier>'` | Members of that tier (tier-policy lookup). Punt to §6. |
| Bind `scope_token = 'team:<team_id>'` | Team admin (team-policy lookup). Punt to §6. |
| Unset (delete row) | Same actor who bound it, OR Goal author for default scope. |

**Server-side check** in `_action_goal_set_canonical`:

```python
scope_token = (kwargs.get("scope_token") or "").strip()
actor = _current_actor()

if scope_token == "":
    # Default canonical — author/host only (current behavior preserved)
    if actor != goal["author"] and actor != host_actor:
        return rejected("Only Goal author or host may set default canonical.")
elif scope_token == f"user:{actor}":
    # Personal canonical — anyone can bind their own
    pass
elif scope_token.startswith("user:"):
    # Trying to bind someone else's personal canonical
    return rejected("Cannot bind a canonical for another user's scope.")
elif scope_token.startswith("tier:"):
    # Tier-policy lookup — punt; reject for now
    return rejected("Tier-scoped canonicals not yet supported. Open question §6.")
# ... etc
```

**Storage-layer note:** the storage helper (`set_canonical_binding`) still does NOT re-check authority — same defense-in-depth gap as today. MCP action layer is the only gate. Acceptable for current single-process daemon; flag for future hardening.

**Symmetric privacy:** when a user binds `scope_token = 'user:<actor>'` with `visibility = 'private'`, only that actor can see it via `goals action=get`. Other viewers see only public bindings + their own private ones (single SQL clause as in §3 query).

---

## 5. Migration plan — additive, no breaking changes

### Step 0 — schema add (no behavior change)

Add `canonical_bindings` table + indexes. Run migration on next daemon start. Existing reads of `goals.canonical_branch_version_id` continue working (column unchanged).

### Step 1 — backfill from existing column

For every Goal where `canonical_branch_version_id IS NOT NULL`:

```sql
INSERT INTO canonical_bindings (goal_id, scope_token, branch_version_id, bound_by_actor_id, bound_at, visibility)
SELECT goal_id, '', canonical_branch_version_id, author, updated_at, 'public'
FROM goals
WHERE canonical_branch_version_id IS NOT NULL;
```

`bound_by_actor_id = author` (best-guess — original row didn't track who set it). `bound_at = updated_at` (closest available timestamp). All backfilled rows are `scope_token = ''` (default canonical) and `visibility = 'public'`.

### Step 2 — dual-write shim

In `set_canonical_branch` (storage helper): every write updates BOTH `canonical_bindings` AND `goals.canonical_branch_version_id`. The legacy column becomes a denormalized cache of the default-scope binding. Existing readers of `goal["canonical_branch_version_id"]` keep working.

### Step 3 — new readers prefer the table

New action `goals action=resolve_canonical(goal_id, canonical_scope?)` reads from `canonical_bindings` directly per §3. Old `goals action=get` keeps returning `canonical_branch_version_id` (default scope only) for back-compat.

### Step 4 — eventual deprecation (out of scope here)

Once all readers migrated, the `goals.canonical_branch_version_id` column gets marked deprecated. Final removal is a future migration window. Not in this proposal's scope.

**Mark's in-flight bindings preserved.** Any canonical Mark already set (via author-of-Goal path) remains a `scope_token = ''` row in `canonical_bindings` after Step 1. No data loss. Mark can subsequently bind `user:mark` rows for any goal he wants without touching the default.

**Rollback path:** if the new table breaks something post-deploy, drop the table — readers fall back to `goals.canonical_branch_version_id` cleanly because the dual-write shim kept it current. Step 2's dual-write is the rollback insurance.

---

## 6. Open questions

Bounded list for navigator/host to ratify in v2:

1. **Tier-scope policy.** How does an actor prove tier membership? Punted in §4. Is tier membership stored per-actor in some `actor_tiers` table, or computed from gate-claim history (e.g. "you're 'expert' tier if you have 3+ accepted gate claims")? This blocks `scope_token = 'tier:*'` enablement.

2. **Team-scope policy.** Same shape as tier — who's a team admin, where's that recorded? Blocks `scope_token = 'team:*'`.

3. **Multi-tier resolution priority.** If actor A is in both `tier:expert` and `tier:reviewer`, and goal G has bindings for both, which wins? Config-driven priority list? Most-specific (whichever tier has fewest members)? Most-recent binding? §3 punted on this.

4. **Sybil resistance for `user:*` bindings.** Path 1 lets anyone bind `user:<their_id>` on any goal. Without sybil protection, a user with N spam accounts can set up N variant canonicals to game gate-routing or visibility heuristics. Is this a real concern given the cooperative trust model in `project_paid_market_trust_model`? If yes, do we need a rate-limit, claim-cost, or proof-of-work? If no, document the assumption explicitly.

5. **Cascade on Goal soft-delete.** When `goals.visibility = 'deleted'`, what happens to `canonical_bindings` rows? Hard-delete (data loss), soft-delete-on-binding (replicate the visibility), or leave-as-orphan (harmless until Goal undeleted)? G1 audit didn't surface this; needs a call.

---

## 7. What this proposal does NOT cover

- **No code changes.** Design only.
- **No `goals action=resolve_canonical` MCP action wiring.** That's the dev-task brief that follows ratification.
- **No `canonical_bindings_json` reverse-compat shim** (an alternate idea: keep both formats during transition). Rejected because it doubles the dual-write surface area for marginal benefit.
- **No leaderboard / discovery integration.** "Show me the most-canonical branches across goals" is a downstream feature. Independent.
- **No event/subscription on canonical change.** G1 gap #8. Independent feature; this proposal's schema doesn't preclude it but doesn't add it.
- **Persona-specific policy decisions** beyond Mark's gate-series story. The proposal is general-purpose; specific persona walkthroughs (Priya, Devin, Maya) are out of scope.

---

## 8. References

- Audit this builds on: `docs/audits/2026-04-25-canonical-primitive-audit.md` (G1).
- Authority principle: project memory `project_user_builds_we_enable.md`.
- Trust-model context: project memory `project_paid_market_trust_model.md` (informs §6 question 4).
- Current code being extended: `tinyassets/daemon_server.py:2354-2429` (set_canonical_branch + history); `tinyassets/universe_server.py:10634-10685` (MCP handler).
- Schema migration pattern reference: `tinyassets/daemon_server.py:413-423` (canonical_branch_history_json migration is the precedent for additive ALTER on `goals`).

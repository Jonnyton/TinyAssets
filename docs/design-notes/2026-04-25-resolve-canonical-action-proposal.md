---
status: active
---

# `goals action=resolve_canonical` — MCP Read Action

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Final design doc in the canonical-resolution chain (#47 → #53 → #54 → #56 → #59).
**Builds on:** Task #47 variant canonicals §3 (fallback chain semantics); Task #53 route-back verdict (engine consumer); Task #56 sub-branch invocation (future consumer).
**Scope:** MCP action signature + behavior. No code changes.

---

## 1. Recommendation

Add `goals action=resolve_canonical` — read-only MCP action that resolves a `(goal_id, canonical_scope)` tuple to a `branch_version_id` per Task #47 §3 fallback chain. **This is the read primitive #47 §3 named.**

Closes the #47 → #59 design loop. Chatbots authoring gate-series can preview "what would route-back resolve to?" before authoring the gate; chatbots executing route-back (Task #53) call this primitive internally.

---

## 2. Action signature

```
goals action=resolve_canonical
  goal_id=<required>
  canonical_scope=<optional, default "" — falls through to caller's user scope or default>
```

### Returns

```json
{
  "goal_id": "<input_goal_id>",
  "requested_scope": "<the canonical_scope arg as supplied, '' if absent>",
  "resolved_branch_version_id": "<def_id>@<sha8>" | null,
  "resolved_via_scope": "user:alice" | "tier:expert" | "" | null,
  "fallback_chain_attempted": ["user:alice", "tier:expert", ""],
  "error": "<message>" // present only on failure cases (§4)
}
```

- `requested_scope` echoes input so chatbot UI can show "you asked for X."
- `resolved_branch_version_id` = `null` when nothing in the fallback chain matches; NOT an error.
- `resolved_via_scope` = the scope token that actually matched (might differ from requested due to fallback). `null` when no match.
- `fallback_chain_attempted` = the ordered list of scopes the resolver checked. Useful for chatbot rendering: "your personal canonical was checked first, fell through to default."

---

## 3. Fallback chain semantics (per Task #47 §3)

This is the read implementation of #47's resolution chain. The order:

1. **Requested scope** — if `canonical_scope` arg is non-empty, check that scope first.
2. **Caller's user scope** — `user:<caller_actor_id>` if `canonical_scope` was unset OR didn't resolve.
3. **Goal default** — `''` (unscoped) — last fallback.

Tier scopes (`tier:expert`, etc.) are checked between user and default IF the caller's tier membership is known (per #47 §6 Q1, tier policy is currently punted; resolver returns no tier matches until tier-membership lookup ships).

### SQL

```sql
SELECT branch_version_id, scope_token FROM canonical_bindings
 WHERE goal_id = :goal_id
   AND (visibility = 'public' OR bound_by_actor_id = :caller_actor_id)
   AND scope_token IN (:fallback_chain)
 ORDER BY
   CASE scope_token
     WHEN :requested_scope THEN 1
     WHEN 'user:' || :caller_actor_id THEN 2
     WHEN '' THEN 3
     ELSE 99
   END
 LIMIT 1;
```

The `:fallback_chain` is the ordered set of scopes; ORDER BY's CASE picks the highest-priority match. Symmetric privacy filter (`visibility = 'public' OR bound_by_actor_id = :caller_actor_id`) per #47 §1.

---

## 4. Error shapes

| Condition | Response shape | Authority |
|---|---|---|
| Missing `goal_id` arg | `{"error": "goal_id is required"}` | Read-only — no authority required to use the action, but malformed args still 400-equivalent. |
| Goal not found | `{"error": "Goal '<id>' not found"}` | — |
| Goal exists, no canonical bound at any scope | `{"goal_id": ..., "resolved_branch_version_id": null, "fallback_chain_attempted": [...]}` | NOT an error. Routine query response. Chatbot interprets `null` as "no canonical bound." |
| Goal exists, canonical exists but caller can't see it (private + caller != owner) | Treated as "no canonical bound" — `null`. Privacy filter is silent at SQL level. | Symmetric privacy honored. |
| Resolved `branch_version_id` orphaned (canonical points to deleted version) | `{"resolved_branch_version_id": "<orphan_id>", ..., "warning": "branch_version_id <id> not found in branch_versions"}` | NOT an error per se; chatbot can choose to act on the warning. |

The orphan case is rare but possible if a published version is hard-deleted; the `canonical_bindings` row becomes a dangling pointer. Resolver still returns the id so navigator can triage; the warning surfaces it.

---

## 5. Authority and symmetric privacy

**Read-only. No authority required.** `_GOAL_ACTIONS` registry adds this as a non-write action (mirrors `goals action=get` / `goals action=list` / `goals action=search`).

Symmetric privacy from #47 §1 is enforced at SQL level: `visibility = 'public' OR bound_by_actor_id = :caller_actor_id` clause. Caller B querying for goal G never sees caller A's private user-scope canonical. If A's binding is the ONLY binding for G, B's resolver returns `null`.

---

## 6. No contribution event emitted (per #48 ledger discipline)

The `contribution_events` ledger from Task #48 is for value-creating events (execute_step, design_used, code_committed, feedback_provided, caused_regression). Read operations don't create value; recording them inflates the ledger without analytical benefit.

`resolve_canonical` calls do NOT emit any contribution event. If a downstream caller (e.g., Task #53 route-back execution) USES the resolved branch_version_id to actually invoke a run, that downstream invocation emits its own `execute_step` / `design_used` events. Resolution itself is observable via run_event traces, not the contribution ledger.

---

## 7. No caching for v1

Resolution is one indexed SQLite query (composite-PK index from #47 §1 plus the scope-priority `idx_canonical_bindings_scope_goal` from Task #61's implementation). Sub-millisecond on small tables, ~milliseconds at scale.

Cache invalidation on `set_canonical` writes is its own complexity. Defer to v2 if profiling shows the resolver as a hot path; v1 plain query is sufficient.

---

## 8. Tests footprint

```python
# tests/test_resolve_canonical.py — ~5 tests

def test_resolves_to_user_scope_when_caller_has_personal_binding(goal_with_user_canonical):
    """Caller A queries goal G; A's user:A binding wins over goal default."""

def test_falls_through_to_tier_when_no_user_binding(goal_with_tier_canonical):
    """Caller A's no user:A binding → tier:expert binding wins (when tier membership known)."""

def test_falls_through_to_default_when_nothing_else_matches(goal_with_only_default_canonical):
    """Caller A's no user/tier bindings → goal's '' default canonical wins."""

def test_returns_null_when_goal_has_no_canonicals_at_all(goal_with_no_canonicals):
    """Goal exists but no canonical_bindings rows → resolved_branch_version_id == None, no error."""

def test_symmetric_privacy_caller_b_cannot_see_caller_a_private_binding(goal_with_a_private_canonical):
    """Caller B's resolve returns null even though A has a private user:A binding."""
```

Auxiliary: error shapes (missing goal_id, goal not found) follow existing `goals action=get` validation patterns; existing test infrastructure covers these.

---

## 9. Open questions

1. **`canonical_scope` arg accepts raw scope token OR shorthand?** RECOMMENDED: raw (`user:alice`, `tier:expert`). Shorthand creates ambiguity — `user` alone could mean self or another. Closed per lead pre-draft note.

2. **Read-event in #48 contribution ledger?** RECOMMENDED: NO. Ledger is for value-creating events; reads don't add value. Closed per lead pre-draft note.

3. **Cache resolved value?** RECOMMENDED: NO for v1. Indexed query is sub-millisecond; cache invalidation is its own complexity. Closed per lead pre-draft note.

---

## 10. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No tier-membership lookup primitive.** Tier scopes are punted in #47 §6 Q1; resolver returns no tier matches until tier policy ships.
- **No reverse-resolution.** "Show me all goals where I have a canonical bound" is a separate read primitive — out of scope here. The `canonical_bindings.bound_by_actor_id` index from Task #47 §1 makes that future query cheap.
- **No write operations.** Just resolution. `set_canonical` (existing) is the write primitive and is unchanged.
- **No bulk resolution.** "Resolve canonical for goals X, Y, Z" needs a separate batch action; v1 is per-goal.

---

## 11. References

- Read primitive named in: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Task #47) §3 — this proposal is its implementation.
- Engine consumer: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (Task #53) §3 — route-back execution calls this.
- Future consumer: `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (Task #56) §6 Q5 — goal-aware sub-branch invocation will use this.
- Schema: `canonical_bindings` table per Task #47 §1, implemented in Task #61 Step 0+1.
- Privacy filter: Task #47 §1 (visibility column on canonical_bindings) + §3 (SQL clause).
- Ledger discipline: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) §1 — reads don't emit events.
- Existing read-only goal actions (pattern reference): `tinyassets/universe_server.py:10247-10328` (`_action_goal_get`) + `:10218-10245` (`_action_goal_list`).

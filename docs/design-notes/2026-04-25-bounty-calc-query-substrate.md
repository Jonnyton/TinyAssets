---
status: active
---

# Bounty-Calc Query Template Substrate

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Bridges Task #48 IN-direction (events) + Task #77 OUT-direction (outcomes) via a reusable query template.
**Builds on:** Task #48 §4 bounty-calc sketch (this proposal formalizes); Task #77 §3 aggregation (composition); attribution-layer-specs §3 (decay) + §6.1 (weight calibration).
**Scope:** schema/contract design only. No code changes. Currency translation deferred (§10 Q5).

---

## 1. Recommendation summary

Two artifacts:

1. **`tinyassets/attribution/bounty_calc.py`** module — `bounty_calc_query_template(...)` returns a parameterized SQL string + helper functions (`decay_coeff`, `compose_filters`).
2. **`extensions action=query_bounty_pool`** MCP read action — thin wrapper exposing the calc to chatbots.

The substrate (#1) is engine-side, reusable across chatbot dispatch + scheduled bounty cycles + ad-hoc analyses. The MCP action (#2) is user-facing surface using "bounty pool" vocabulary. **Two-name pattern:** `attribution` is the engine concept; `bounty_pool` is the user-facing concept.

**Top tradeoff axis:** **substrate reusability vs single-call ergonomics.** Going substrate-first; single-call action couples chatbot UX to one calc pattern.

---

## 2. Module location — `tinyassets/attribution/bounty_calc.py`

Under existing `tinyassets/attribution/` (sibling to attribution-layer-specs impl). NOT a new `tinyassets/economics/` package — that overstates scope. Engine concept is attribution; user-facing concept is bounty pool. Two-name pattern.

Module exports:

```python
# tinyassets/attribution/bounty_calc.py
"""Reusable bounty-calc query substrate.

Composes Task #48 contribution_events ledger (IN-direction) with
Task #77 outcome_attribution events (OUT-direction). Returns
(actor_id, share) tuples for downstream bookkeeping.
"""

LINEAGE_MAX_DEPTH_DEFAULT = 5
DECAY_ALPHA_DEFAULT = 0.6


def decay_coeff(depth: int, alpha: float = DECAY_ALPHA_DEFAULT) -> float:
    """Geometric decay: alpha=0.6 → depth=0:1.0, depth=1:0.6, depth=2:0.36."""
    return alpha ** depth


def bounty_calc_query_template(
    *,
    target_artifact_id: str,
    window_start_ts: float,
    window_end_ts: float,
    max_lineage_depth: int = LINEAGE_MAX_DEPTH_DEFAULT,
    alpha: float = DECAY_ALPHA_DEFAULT,
    actor_id_filter: str | None = None,
    scope_filter_kind: str | None = None,
) -> tuple[str, dict]:
    """Return (sql_template, bind_params) for execution.

    Substrate is reusable; downstream callers execute via their own
    sqlite3 cursor. Returns parameterized SQL — no string concatenation
    of user input."""
    # ... see §3 for the SQL ...
```

Configurable via `TINYASSETS_LINEAGE_MAX_DEPTH` env var (introducing this — checked existing repo, not yet defined).

---

## 3. Recursive-CTE walk + filter layer + aggregation

```sql
WITH RECURSIVE lineage(artifact_id, depth) AS (
    SELECT :target_artifact_id, 0
    UNION ALL
    SELECT bd.fork_from, lineage.depth + 1
    FROM lineage
    JOIN branch_definitions bd ON bd.branch_def_id = lineage.artifact_id
    WHERE bd.fork_from IS NOT NULL AND lineage.depth < :max_lineage_depth
),
-- Apply geometric decay per depth via inline POWER
lineage_with_decay AS (
    SELECT artifact_id, depth, POWER(:alpha, depth) AS decay
    FROM lineage
)
SELECT
    ce.actor_id,
    ce.actor_handle,
    SUM(ce.weight * lwd.decay) AS share
FROM contribution_events ce
JOIN lineage_with_decay lwd ON lwd.artifact_id = ce.source_artifact_id
WHERE
    -- ROLLBACK-EXCLUSION FILTER (load-bearing, per #77 §3): rolled-back
    -- work doesn't earn.
    NOT EXISTS (
        SELECT 1 FROM contribution_events ce2
        WHERE ce2.source_artifact_id = ce.source_artifact_id
          AND ce2.event_type = 'caused_regression'
    )
    -- ANONYMOUS FILTER (per verifier pair-read): execute_step rows from
    -- anonymous daemons are excluded to reduce share-table bloat.
    AND NOT (ce.event_type = 'execute_step' AND ce.actor_id = 'anonymous')
    -- WINDOW SCOPING: events within [start, end].
    AND ce.occurred_at BETWEEN :window_start_ts AND :window_end_ts
    -- Optional: scope_filter_kind narrows to a specific source_artifact_kind
    AND (:scope_filter_kind IS NULL OR ce.source_artifact_kind = :scope_filter_kind)
    -- Optional: single-actor lookup for "show me Bob's share"
    AND (:actor_id_filter IS NULL OR ce.actor_id = :actor_id_filter)
GROUP BY ce.actor_id, ce.actor_handle
ORDER BY share DESC;
```

**Outcome events flow through the SAME aggregation.** No separate query. `outcome_stable` (+3) and `outcome_rolled_back` (-10) are just rows with their `event_type` and `weight` — the SUM picks them up alongside `execute_step`/`design_used` rows. ADD semantics — see §4.

**Decay shape:** geometric `α=0.6` per project-consistency (matches attribution-layer-specs §3 + #57 + #77 sibling decays). Canonical fixture (carol=1.0, bob=0.6, alice=0.36) at 3-deep lineage — see §6 smoke.

---

## 4. Outcome-event composability — ADD with floor at zero

**ADD, NOT MULTIPLY.** Three reasons:

1. **Commutative + associative.** Order of events doesn't matter; partial sums compose cleanly across windows.
2. **Doesn't amplify base contributions.** Multiply would scale outcome-bonus by the base contribution magnitude — a tiny-base × bonus = tiny; a huge-base × same bonus = huge. Outcomes credit/debit work, not scale it.
3. **Single SUM aggregation primitive** serves both event-type families. No code branch on event_type at the query level; handled implicitly via signed weights.

### Floor at zero (v1) — see §10 Q2

For v1, per-actor share is floored at zero in post-query result handling: `share = max(0, raw_share)`. Reasoning:

- **Clean payout semantics:** a bounty pool dispatching X currency knows every share is non-negative; total disbursed ≤ X.
- **Debt-tracking is a separate concern.** Negative-share carry-forward across pools is v2 work — different bookkeeping primitive (debt ledger? credit cap?). v1 substrate is share-only, no debt.

Surface as Q2 truly-open: **negative shares allowed (debt-tracking) vs floored at zero (clean payout)** — recommended floor for v1.

---

## 5. Time-window scoping

Both bounds explicit. Lifetime query passes `:window_start_ts = 0` (epoch beginning) + `:window_end_ts = now()`.

NULL handling deferred to v2 — v1 callers MUST pass concrete bounds. Avoids "did the caller mean lifetime or did they forget to pass an arg" ambiguity.

---

## 6. MCP action `extensions action=query_bounty_pool`

```
extensions action=query_bounty_pool
  pool_id <required, str>            # identifies the pool (future: bounty pools as separate table)
  target_artifact_id <required, str> # the artifact whose lineage we query
  window_seconds <int> = 86400       # 24h default; 0 = lifetime (start_ts = 0)
  actor_id <optional, str>           # if set, returns single-actor share lookup
  scope_filter_kind <optional, str>  # filter source_artifact_kind, e.g. "branch_version"
  → returns {
      pool_id: <input>,
      window: {start_ts, end_ts},
      results: [{actor_id, actor_handle, share}, ...],
      total_share: <sum>,
      query_metadata: {alpha, max_depth, target_artifact_id}
    }
```

Read-only action per #59 / #74 ledger-discipline pattern. No contribution_events emitted for query operations. **No storage-auth check** (read-only; same orthogonality as #74 author_patch_notes per §4 there).

The handler at `tinyassets/universe_server.py` `_action_extensions_query_bounty_pool` calls `bounty_calc_query_template` from the `tinyassets/attribution/bounty_calc.py` module, executes via the existing sqlite3 connection helper, and returns the result shape above.

---

## 7. Composition test cases (independent of smoke fixture)

Documents canonical end-to-end scenarios the implementation MUST handle correctly. No fixture code; just descriptions:

| # | Scenario | Setup | Expected result |
|---|----------|-------|-----------------|
| **CT-1** | Pure-design-credit run | 3-deep lineage alice (depth 2) → bob (depth 1) → carol (depth 0). Each contributes 1 `design_used` event with weight=1.0. | shares: carol=1.0, bob=0.6, alice=0.36 |
| **CT-2** | Mixed credit (design + outcome) | CT-1 setup + carol's artifact attains `outcome_stable` (+3). | shares: carol=4.0 (=1.0 + 3.0 ADD), bob=0.6, alice=0.36 |
| **CT-3** | Rollback exclusion | CT-1 setup + bob's artifact has `caused_regression` event. | shares: carol=1.0, alice=0.36, bob excluded by NOT EXISTS clause |
| **CT-4** | Anonymous filter | 1 anonymous daemon-host run with `execute_step` (weight=1.0) + 1 named actor's `design_used` (weight=1.0). | share: only named actor with 1.0; anonymous excluded |
| **CT-5** | Window scoping | CT-1 events distributed across two 24h windows. | querying first-window → carol=1.0, bob/alice excluded if their events were in second window |
| **CT-6** | Outcome-rolled-back negative | CT-1 setup + carol's artifact attains `outcome_rolled_back` (-10). | shares: carol=max(0, 1.0-10) = 0 (floor at zero, Q2 v1), bob=0.6, alice=0.36 |
| **CT-7** | Lifetime query | CT-1 events; query with window_seconds=0 → start_ts=0. | same as CT-1 — all events included |
| **CT-8** | Single-actor lookup | CT-1 events; query with actor_id="bob". | single row: bob=0.6 |

These compose cases verify both the SQL template and the post-query share-floor handling. Implementation tests should use these as ground-truth expected outcomes; no SQL gymnastics-by-developer-creativity permitted (test against the table).

---

## 8. Smoke test fixture

Schema-only smoke that runs the recursive CTE against a 3-actor lineage:

```python
# Fixture sketch — not actual implementation
def test_bounty_calc_canonical_lineage_smoke(tmp_path):
    """Verify (1.0, 0.6, 0.36) shares for 3-deep design_used lineage at α=0.6."""
    # Setup: branch_definitions with fork_from chain
    #   carol_branch (fork_from=bob_branch)
    #   bob_branch   (fork_from=alice_branch)
    #   alice_branch (fork_from=NULL)
    # Setup: contribution_events
    #   ('design_used', actor='carol', source_artifact_id='carol_branch', weight=1.0)
    #   ('design_used', actor='bob',   source_artifact_id='bob_branch',   weight=1.0)
    #   ('design_used', actor='alice', source_artifact_id='alice_branch', weight=1.0)
    # Run: bounty_calc_query_template(target='carol_branch', window_start=0, window_end=now)
    # Assert: shares match {carol: 1.0, bob: 0.6, alice: 0.36} (within float tolerance)
```

Going α=0.6 per project-consistency (NOT 0.5 which would give (1.0, 0.5, 0.25)). Smoke verifies the canonical (1.0, 0.6, 0.36) result.

---

## 9. Performance characteristic

**Expected cost:** O(events_in_window × max_lineage_depth).

At expected scale (10k events / 24h × depth=5 = 50k row-touches), SQLite handles in <100ms with the `(occurred_at)` index from #48 §1.

**At 1M events / lifetime query:** the bounded depth cap keeps it tractable but query time grows linearly. Likely needs:

- Index hint on `(source_artifact_id, occurred_at)` composite for the window+lineage join.
- Pagination via `LIMIT/OFFSET` or cursor-based paging on share-rank.
- Possibly materialized view of (actor_id, lifetime_share) for hot lifetime queries.

Defer optimization to v2; v1 substrate is correct + handles expected scale (10k events/day).

**Concurrency:** SQLite WAL mode (project default per `branch_versions.py:_connect`) gives concurrent reads with one writer. Bounty calc is read-only; concurrent queries don't block each other.

---

## 10. Composition with sibling proposals

### Task #48 §4 bounty-calc sketch — formalized

#48 §4 was the v1 sketch. This proposal is the v2 substrate:
- Formalizes #48's SQL into a callable template module.
- Adds outcome-event composability (per #77).
- Adds anonymous-actor filter (per verifier pair-read).
- Adds parameterized window scoping (was hardcoded in #48).
- Cite + supersede.

### Task #77 §3 aggregation — shared lineage walk

Outcome-attribution aggregation (#77 §3) uses the SAME recursive CTE shape. Both queries share the lineage walk; outcome events filter to `outcome_*` event_types vs bounty-calc filters to all events. Could share `_recursive_lineage_walk_cte()` helper in this module — recommend YES at v2 refactor.

### Task #57 surgical rollback — caused_regression source

#57 emits `caused_regression` events when bisect-on-canary identifies a regression. This proposal's filter `NOT EXISTS (caused_regression for same source_artifact)` excludes those artifacts from earning. Hard dependency — needs #57's emit path live.

### Task #66 / #74 — orthogonal (read-only)

PatchNotes and author_patch_notes don't interact with bounty-calc. Bounty calc reads contribution_events; PatchNotes data lives in `metadata_json` of those events but the calc doesn't deserialize it.

### Task #69 storage-auth — orthogonal (read-only)

Read-only action; no storage-auth check needed. Same orthogonality as #74 author_patch_notes per §4 there.

### attribution-layer-specs §3 + §6.1 — decay + weight calibration

α=0.6 decay matches §3. Outcome weights from #77 §2 calibrated by analogy to §6.1 P0/P1/P2.

---

## 11. Open questions

1. **Window vs lifetime.** RECOMMENDED: support both via `window_seconds=0` → lifetime (start_ts=0, end_ts=now()). Closed.

2. **Negative shares allowed (debt-tracking) vs floored at zero (clean payout).** RECOMMENDED: floor at zero for v1. Subordinate Q from lead's note. Two paths:
   - **Allow negative shares (debt-tracking):** bounty pool dispatch must handle non-payout AND maybe debt accumulation across pools. v2 needs a debt-ledger primitive.
   - **Floor at zero (clean payout):** every share is non-negative; total disbursed ≤ pool. Debt is a separate concern (potentially never).
   Recommend floor v1. Truly open for v2 host call: do we ever want debt-tracking? Depends on platform-economy maturity.

3. **Sybil-resistance inline vs post-query layer.** RECOMMENDED: post-query layer. Inline couples sybil logic to SQL template; layer keeps query pure + sybil-detection a separate composable filter applied to results. Easier to test sybil rules in isolation. Truly open.

4. **Carve-outs (corporate-host opt-out / credit routing).** RECOMMENDED: NOT in v1. v2 feature: `actor_credit_routing` table mapping actor_id → list of `(target_actor_id, weight)` tuples for credit-routing. A corporate-host running daemons-for-hire could route its credit downstream to specific clients. Truly open with v2-defer.

5. **Currency translation.** RECOMMENDED: separate concern from query substrate. Query produces shares; downstream bookkeeper applies pool_total_currency to disburse. Could pass `pool_total_currency` arg on the MCP action that just multiplies through; substrate stays currency-agnostic. Truly open.

---

## 12. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No bounty-pool storage.** "Bounty pool" is a v2 table (out of scope here); v1 `pool_id` arg is opaque metadata, not a foreign key.
- **No currency disbursement / bookkeeping.** §11 Q5; substrate produces shares only.
- **No sybil-detection logic.** Substrate is sybil-neutral; §11 Q3 surfaces composability.
- **No credit-routing primitives.** §11 Q4 v2 feature.
- **No dispatcher / scheduler integration.** "When does the bounty calc fire?" is bounty-pool-dispatch concern, not substrate concern.
- **No real-time recalc on every event.** Calc runs on-demand at query time; no caching invariant beyond SQLite's own.

---

## 13. References

- v1 sketch this formalizes: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) §4.
- Outcome composability: `docs/design-notes/2026-04-25-outcome-attribution-primitive.md` (Task #77) §3.
- Caused_regression source: `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (Task #57) §3+§4.
- Weight calibration analogy: `docs/design-notes/2026-04-25-attribution-layer-specs.md` §3 (decay) + §6.1 (P0/P1/P2 weights).
- Read-only orthogonality precedent (no storage-auth, no ledger event): `docs/design-notes/2026-04-25-author-patch-notes-mcp-wrapper.md` (Task #74) §4.
- Convention adherence: `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` — 5-move pattern.
- Companion principle: `project_designer_royalties_and_bounties.md` — remix-economy lineage credit (Carol→Bob via decay).
- Existing schema reuse:
  - `contribution_events` (per #48 §1) + 4 indexes (`occurred_at`, `actor_id+occurred_at`, `source_artifact_id+kind`, `source_run_id`).
  - `branch_definitions.fork_from` (`tinyassets/daemon_server.py` — fork_from migration block; grep `fork_from` for current location).
- Existing dispatch pattern reference: `tinyassets/universe_server.py` `_action_extensions_*` registry.
- Convention for grep-anchored references (per #77 line-drift fix): file references that depend on line numbers should describe the region semantically rather than pin exact lines.

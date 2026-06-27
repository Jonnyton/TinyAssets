---
status: active
---

# Surgical Rollback — Atomic Set + Bisect-on-Canary

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Closes self-evolving-platform-vision §4 row "Surgical rollback (bisect-on-canary + atomic-rollback-set)". Resolves E11 (auto-rollback safety / cascading reverts) from v1 vision.
**Builds on:** Task #48 contribution ledger (`caused_regression` events); navigator's attribution-layer-specs (`docs/design-notes/2026-04-25-attribution-layer-specs.md`) §1.5 + §6.1; Task #54 runner version-id bridge (committed `dc7d2cb`).
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation summary

Four sub-decisions:

1. **Rollback unit: atomic-rollback-set** — the entire dependency closure rolls back together or not at all. Closure walk uses `branch_versions.parent_version_id` (forward chain) + `branch_definitions.fork_from` (fork-children).
2. **Detection: watch-window-after-merge** — 24h default per-merge, tunable via frontmatter. High-risk paths get 7d; trivial fixes 1h. RED canary during window emits a `caused_regression` candidate event.
3. **Bisect-on-canary as attribution primitive** — when multiple merges happened in the watch-window and a canary fires RED, binary-search the merge boundary by replaying the canary against each `branch_versions` snapshot. log2(N) probes; reuses existing canary scripts.
4. **MCP action `runs action=rollback_merge` engine-internal + host-emergency-override** — auto-fires for P1+ regressions; P2 emits `caused_regression` event but does NOT auto-rollback (false-positive cost). Host can manually trigger or inspect via `runs action=get_rollback_history`.

**Top tradeoff axis:** dependency-closure correctness vs. rollback latency. Single-merge rollback is fast but creates broken-references. Atomic set is correct but takes longer (compute closure + lock + execute). Going correct.

---

## 2. Atomic-rollback-set

### Closure computation

When merge X is identified for rollback, compute the closure walking two relations:

```python
def compute_rollback_set(rolled_back_version_id: str) -> list[str]:
    """Return all branch_version_ids that depend on the rolled-back version."""
    closure = {rolled_back_version_id}
    queue = [rolled_back_version_id]
    while queue:
        bvid = queue.pop()
        # Forward chain: any version where parent_version_id == bvid
        children = query("SELECT branch_version_id FROM branch_versions "
                         "WHERE parent_version_id = ?", bvid)
        # Fork-children: any branch_def that forked from this version
        forks = query("SELECT branch_def_id FROM branch_definitions "
                      "WHERE fork_from = ?", bvid)
        # Each fork's published versions also belong to the closure
        for fork_def_id in forks:
            fork_versions = query("SELECT branch_version_id FROM branch_versions "
                                  "WHERE branch_def_id = ?", fork_def_id)
            for fv in fork_versions:
                if fv not in closure:
                    closure.add(fv); queue.append(fv)
        for child in children:
            if child not in closure:
                closure.add(child); queue.append(child)
    return list(closure)
```

Closure is artifact-level only. Active runs that referenced the rolled-back artifact are handled separately (see §6 Q6).

### Atomic execution

The rollback engine:

1. Computes the closure.
2. Acquires a rollback-lock against every `branch_version_id` in the closure (single transaction; SQLite's BEGIN IMMEDIATE).
3. Marks each version with `status = "rolled_back"` + `rolled_back_at` timestamp + `rolled_back_by` actor + `rolled_back_reason`. The version row stays in `branch_versions` (immutable invariant); only the status flag changes.
4. Re-points any goal's `canonical_branch_version_id` from a rolled-back version to its `parent_version_id` (cascading: if the parent is also in the closure, walk up until you find a non-rolled-back ancestor, or NULL if none).
5. Emits one `caused_regression` event per rolled-back version per attribution-layer-specs §1.5.
6. Commits the transaction.

If any step in (1-5) fails (lock contention, missing parent, etc.), the entire transaction aborts — atomic invariant preserved. Per Q4 lead pre-draft: abort-all, no partial commits.

### Schema additions

```sql
-- tinyassets/branch_versions.py — extend BRANCH_VERSIONS_SCHEMA
ALTER TABLE branch_versions ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE branch_versions ADD COLUMN rolled_back_at REAL;
ALTER TABLE branch_versions ADD COLUMN rolled_back_by TEXT;
ALTER TABLE branch_versions ADD COLUMN rolled_back_reason TEXT;
ALTER TABLE branch_versions ADD COLUMN watch_window_seconds INTEGER NOT NULL DEFAULT 86400;

CREATE INDEX IF NOT EXISTS idx_bv_status ON branch_versions(status);
CREATE INDEX IF NOT EXISTS idx_bv_published_at ON branch_versions(published_at);
```

`status ∈ {"active", "rolled_back", "superseded"}`. `superseded` is reserved for a future "this version was replaced by a newer one" pattern; not used in this proposal.

`watch_window_seconds` is per-version, defaulting 86400 (24h). Set at publish time via a new `watch_window_seconds` arg on `publish_branch_version`. Frontmatter override: `_publish_metadata: {watch_window_seconds: 604800}` for high-risk paths.

---

## 3. Watch-window detection

When a `branch_version_id` is published, the engine schedules a watch-window timer:

```
publish_at = T0
watch_window_until = T0 + watch_window_seconds
```

During `[publish_at, watch_window_until]`:
- All canaries (PROBE-001 / PROBE-002 / PROBE-003 / PROBE-004 + revert_loop_canary) running RED emit a `caused_regression` candidate event.
- The candidate event references this `branch_version_id` IF the bisect (§4) attributes the regression to it.
- Otherwise the candidate is discarded.

After `watch_window_until`:
- The version's lock is released.
- Future canary RED events do NOT emit `caused_regression` for this version (fault attribution requires bisect to find a more recent suspect within its own watch-window).
- The version transitions from "actively watched" to "stable" (still `status = "active"`, just no rollback eligibility).

### Per-version watch-window calibration

Operator sets `watch_window_seconds` at publish time based on perceived risk:

| Risk path | Recommended `watch_window_seconds` |
|---|---|
| Trivial doc fix, no code touched | 3600 (1h) |
| Standard feature/bugfix | 86400 (24h, default) |
| Auth/identity-related changes | 604800 (7d) |
| Storage-layer / schema-migration | 1209600 (14d) |
| Critical path (paid market, gates) | 2592000 (30d) |

Operator discretion per branch_version, no rigid policy. Frontmatter is per-snapshot immutable per Q1.

---

## 4. Bisect-on-canary

### Trigger

Canary X fires RED. Engine queries: "which `branch_version_id` rows are within their watch-window AND were published since the last green canary X run?" That's the suspect set S.

If `|S| == 1`: regression attributed to that single version. Skip to §5 rollback execution.

If `|S| > 1`: bisect.

If `|S| > 32`: escalate to host (per Q2). The merge-velocity is too high to bisect cheaply; suggest merge throttling. Open `runs action=get_rollback_history` shows the queue.

### Bisect algorithm

```python
def bisect_canary(suspect_versions: list[str], canary_script: Path) -> str | None:
    """Binary-search the suspect set for the offending version. Returns version_id or None."""
    # suspect_versions is sorted ascending by published_at
    lo, hi = 0, len(suspect_versions) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        # Snapshot the runtime against the suspect at mid, run canary
        result = replay_canary_at_version(suspect_versions[mid], canary_script)
        if result == "GREEN":
            # Fault is in [mid+1, hi]
            lo = mid + 1
        else:  # RED
            # Fault was introduced at or before mid
            hi = mid
    # Verify lo is actually the culprit (not a flaky canary)
    confirm = replay_canary_at_version(suspect_versions[lo], canary_script)
    return suspect_versions[lo] if confirm == "RED" else None
```

`replay_canary_at_version` reconstructs the runtime state at the version's published-at timestamp — for canaries that probe MCP endpoints, this means running the canary against the still-live system but parameterized to the version's known artifact state. For LangGraph-replay canaries (future), it means re-running with the snapshot's BranchDefinition.

**log2(N) probes for N candidates.** With cap=32 → max 5 probe rounds. Each probe round is one canary execution (≤30s typical).

### Confirmation step

After bisect identifies a culprit, the engine **runs the canary one more time at that version** to confirm the regression is reproducible (not a flaky one-shot). If confirmation is GREEN, the bisect is invalidated — likely a transient failure that happened to land during the merge window. Engine logs "bisect inconclusive, transient regression suspected" and emits no `caused_regression` event.

### Reuse of existing canary infrastructure

No new probe types. The bisect operates on the existing canary scripts:
- `scripts/mcp_public_canary.py` (PROBE-001)
- `scripts/uptime_canary_layer2.py` (PROBE-002)
- `scripts/wiki_canary.py` (PROBE-003)
- `scripts/mcp_tool_canary.py` (PROBE-004)
- `scripts/revert_loop_canary.py`

Each canary's existing exit-code ladder maps directly to a `caused_regression` weight via attribution-layer-specs §6.1: P0=-10, P1=-3, P2=-1.

---

## 5. MCP action surface

### Engine-internal trigger (default)

When bisect identifies a culprit AND the regression weight ≥ -3 (P1 severity or worse), the engine:

1. Computes the rollback set per §2.
2. Executes the atomic rollback transaction.
3. Emits `caused_regression` events.
4. Logs the rollback to `.agents/rollback.log` (NEW log file, format mirrors `uptime.log`).
5. Pages host via Pushover if ` priority severity` was P0.

For weight = -1 (P2): emit `caused_regression` event but do NOT auto-rollback. Host or chatbot reviews via `runs action=get_rollback_history` and decides whether to manually trigger.

### `runs action=rollback_merge` (host-only)

```
runs action=rollback_merge
  branch_version_id="<def_id>@<sha8>"     # required
  reason="<free text>"                    # required
  → returns { status, rollback_set, error? }
```

Authority: only `UNIVERSE_SERVER_HOST_USER` (default `"host"`) per Hard Rule emergency-override pattern. Other actors get `{"error": "host-only authority"}`.

The action runs §2's atomic execution against the supplied `branch_version_id`. Useful for host-initiated rollback when bisect failed (e.g., regression detected via user report, not canary).

### `runs action=get_rollback_history` (read-only)

```
runs action=get_rollback_history
  since_days=<N>                          # optional, default 7
  → returns { rollbacks: [...], count }
```

Each entry: `{branch_version_id, rolled_back_at, rolled_back_by, rolled_back_reason, rollback_set, caused_regression_weights}`. Filterable by date range. No authority restriction (read-only).

---

## 6. Open questions

1. **Watch-window storage — frontmatter (per-snapshot immutable) APPROVED.** Closed.

2. **Bisect performance bound — cap 32 candidates / 5 probe rounds APPROVED.** Above 32 → escalate to host without auto-bisect; suggest merge throttling. Note: high-velocity windows hitting this cap are a separate operational concern (merge throttling spec needed downstream). Closed.

3. **Dependency-closure granularity — artifact-level only for v1 APPROVED.** Runtime-level (active runs that referenced the artifact) is too dynamic. v2 work. Closed.

4. **Rollback transaction atomicity — abort-all APPROVED.** Atomic invariant > partial-rollback complexity. Closed.

5. **`caused_regression` weight calibration — reuse attribution-layer-specs §6.1 verbatim APPROVED.** P0=-10, P1=-3, P2=-1. Closed.

6. **(Truly open) Rollback during in-flight runs.** If a rollback executes while a run is active and that run was using the rolled-back artifact, what happens? Recommend: **cancel the run with structured `failure_class="rolled_back_during_execution"`**. Run's terminal status flips to `cancelled`; emit run-cancellation contribution event to ledger; client receives structured error. Detailed recovery (e.g., "save partial output and resume on rolled-forward version") is v2 work.

7. **(Truly open) Bisect against in-flight publish.** What if a new version is published WHILE bisect is running against an older window? Recommend: **bisect's suspect set is snapshot-at-trigger-time**. New publishes don't enter the in-flight bisect; if they trigger their own canary RED, that's a separate bisect run.

---

## 7. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No merge-throttling spec.** Q2 escalation path mentions it but doesn't design it. Separate dispatch when high-velocity windows become a real operational pain.
- **No runtime-level dependency tracking.** Q3 punted.
- **No cross-tenant rollback isolation.** When multiple tenants share artifact lineage, a rollback affecting one tenant's chain may visibly affect another's runs. Out of scope; host can use the `runs action=rollback_merge` override to reason case-by-case.
- **No `superseded` status flow.** Reserved for future use; this proposal only writes `active` → `rolled_back`.
- **No detailed in-flight-run recovery.** Q6 cancellation is the v1 contract; richer "save partial output and resume on rolled-forward version" is v2.
- **No alternative-canary-replay execution model.** This proposal assumes existing canary scripts run idempotently against the live system; some canaries (e.g., write-roundtrip) might leave state behind. Out-of-scope cleanup.

---

## 8. References

- Closes self-evolving-platform-vision §4 row "Surgical rollback": `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` line 123.
- Resolves E11 (auto-rollback safety / cascading reverts): `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §5 line 147.
- Attribution-layer-specs (`caused_regression` event shape + weight calibration): `docs/design-notes/2026-04-25-attribution-layer-specs.md` §1.5 (event semantics) + §6.1 (weight table).
- Contribution ledger emit point: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) — `caused_regression` is one of the 5 fixed event types.
- Variant canonicals (rollback re-points goal canonical): `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Task #47).
- Runner version-id bridge (immutable version snapshots): `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (Task #54, committed `dc7d2cb`).
- Probe catalog (canary inventory used by bisect): `docs/ops/acceptance-probe-catalog.md`.
- Existing schema:
  - `branch_versions` table: `tinyassets/branch_versions.py:25-67` — current shape, this proposal adds `status` / `rolled_back_*` / `watch_window_seconds` columns.
  - `branch_definitions.fork_from` column: `tinyassets/daemon_server.py:404-411` (closure walk).
  - `branch_versions.parent_version_id` column: `tinyassets/branch_versions.py:34` (closure walk).
- Existing canary scripts (reused by bisect):
  - `scripts/mcp_public_canary.py`
  - `scripts/uptime_canary_layer2.py`
  - `scripts/wiki_canary.py`
  - `scripts/mcp_tool_canary.py`
  - `scripts/revert_loop_canary.py`

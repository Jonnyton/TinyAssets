---
status: active
---

# Outcome Attribution — Event-Aggregation Primitive

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Phase B/D primitive — bridges "engine emitted events" to "real-world outcome reshapes future routing."
**Builds on:** Task #48 contribution_events ledger (event-type extension); Task #57 surgical rollback (`caused_regression` source + `watch_window_seconds`); attribution-layer-specs §3 + §6.1 (decay shape + weight calibration).
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation summary

Extend Task #48's `contribution_events` table with new `event_type` enum values (`outcome_stable`, `outcome_unstable`, `outcome_rolled_back`, `outcome_cancelled`, `outcome_superseded`). NO new table. Aggregation via recursive-CTE same shape as #48 §4 bounty calc, with rollback-exclusion filter. New `extensions action=report_outcome` write-side MCP action with evidence-refs-required + storage-auth check. Time-window auto-emission reuses #57's `watch_window_seconds` field.

**Top tradeoff axis:** **schema extensibility vs read-pattern coherence.** Extending #48 wins because every attribution-layer query (bounty calc, reputation aggregation, outcome roll-up) reads from the same table with the same indexes. A separate `outcome_events` table would split read patterns and force UNION ALL across two surfaces.

---

## 2. Schema extension

`contribution_events` schema from Task #48 §1 already supports outcome events. Verbatim:

```sql
CREATE TABLE contribution_events (
    event_id              TEXT PRIMARY KEY,
    event_type            TEXT NOT NULL,              -- open enum, extended below
    actor_id              TEXT NOT NULL,
    actor_handle          TEXT NOT NULL DEFAULT '',
    source_run_id         TEXT,
    source_artifact_id    TEXT,
    source_artifact_kind  TEXT NOT NULL DEFAULT '',
    weight                REAL NOT NULL DEFAULT 1.0,
    occurred_at           REAL NOT NULL,
    metadata_json         TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (source_run_id) REFERENCES runs(run_id)
);
```

### Five new event_type values

| event_type | Emitted by | Weight (default) | Trigger |
|---|---|---|---|
| `outcome_stable` | time-window detector OR external report | +3 (P1-positive) | watch_window_seconds expires with no caused_regression event in the window |
| `outcome_unstable` | external report (chatbot/host) | -3 (P1-negative) | user/host reports the work is unstable but not rolled back |
| `outcome_rolled_back` | rollback execution path (per #57) | -10 (P0) | atomic-rollback-set executes; the rollback IS the outcome |
| `outcome_cancelled` | manual host emission | -1 (light) | host explicitly withdraws work; no production damage |
| `outcome_superseded` | manual host emission | 0 (neutral) | work was replaced by a newer version; not a failure |

**`metadata_json` for outcome events:**

```json
{
  "outcome_label": "stable" | "unstable" | "rolled_back" | "cancelled" | "superseded",
  "evidence_refs": [{"kind": "wiki_page", "id": "...", "cited_by": "..."}, ...],
  "window_seconds": 86400,
  "detector": "time_window" | "manual" | "external" | "rollback_executor",
  "reported_by_actor_id": "<actor>",   // distinct from actor_id (= the work's actor)
  "reason": "<free text>"               // optional, present for manual emissions
}
```

The `actor_id` field on the row is the actor whose work attained the outcome (read from the originating run/artifact). The `reported_by_actor_id` in metadata is who emitted the event (host for time-window; chatbot user for `report_outcome`; rollback executor for `outcome_rolled_back`). Two separate identities for two semantics.

---

## 3. Aggregation algorithm — recursive CTE

When a downstream consumer (bounty calc, reputation aggregation) wants per-actor outcome share for a target artifact:

```sql
WITH RECURSIVE outcome_chain(artifact_id, depth) AS (
    SELECT :outcome_artifact_id, 0
    UNION ALL
    SELECT bd.fork_from, oc.depth + 1
    FROM outcome_chain oc
    JOIN branch_definitions bd ON bd.branch_def_id = oc.artifact_id
    WHERE bd.fork_from IS NOT NULL AND oc.depth < :max_lineage_depth
)
SELECT
    ce.actor_id,
    ce.actor_handle,
    SUM(ce.weight * decay_coeff(oc.depth, alpha=0.6)) AS outcome_share,
    GROUP_CONCAT(oc.artifact_id || '@depth' || oc.depth) AS contribution_path
FROM contribution_events ce
JOIN outcome_chain oc ON oc.artifact_id = ce.source_artifact_id
WHERE
    ce.event_type IN ('execute_step', 'design_used', 'code_committed', 'feedback_provided')
    AND ce.weight > 0  -- positive contributions only
    AND NOT EXISTS (
        -- ROLLBACK-EXCLUSION FILTER (load-bearing): rolled-back work
        -- does not earn outcome attribution.
        SELECT 1 FROM contribution_events ce2
        WHERE ce2.source_artifact_id = ce.source_artifact_id
          AND ce2.event_type = 'caused_regression'
    )
GROUP BY ce.actor_id, ce.actor_handle
ORDER BY outcome_share DESC;
```

**Decay shape:** geometric `α=0.6` per attribution-layer-specs §3, matching #48 §4 bounty calc + #57 bisect convention. Half-life and linear were considered; geometric won on consistency with sibling decays.

**Cross-actor coupling (Carol→Bob via lineage decay):** YES — when Carol's fork attains `outcome_stable`, Bob (Carol's parent in `fork_from` chain) earns a share via the lineage walk. Geometric decay reduces Bob's share vs Carol's (depth=1 → 0.6×; depth=2 → 0.36×); credit flows but diminishes. This IS the remix-economy primitive from `project_designer_royalties_and_bounties`.

**Sybil-resistance composability:** outcome events flow into the same per-actor `SUM(weight)` input that attribution-layer-specs §5 sybil-detection consumes. An actor stockpiling `outcome_stable` events on cheap forks would surface as anomalous in the same detection surface. Outcome events deepen the signal, don't change sybil shape.

---

## 4. Trigger surfaces (3)

### 4.1 Time-window auto-emission

Scheduled detector job scans `branch_versions` rows with `published_at + watch_window_seconds < now()` AND no terminal outcome event yet:

- If NO `caused_regression` event in the window for that artifact → emit `outcome_stable` (+3 weight).
- If `caused_regression` event present (i.e., regression was detected; rollback may or may not have executed) → emit `outcome_unstable` (-3 weight). If rollback DID execute, the rollback execution path emits `outcome_rolled_back` (-10) directly per §4.3.

**Race-handling per lead's ask A:** "outcome window expires at T+86400, regression detected at T+86399." The detector's pre-emit gate query:

```sql
-- Before emitting outcome_stable, check for any caused_regression
-- since the watch window started.
SELECT COUNT(*) FROM contribution_events
WHERE source_artifact_id = :artifact_id
  AND event_type = 'caused_regression'
  AND occurred_at >= :artifact_published_at;
```

If count > 0, the detector emits `outcome_unstable` (or skips if rollback already emitted `outcome_rolled_back`). This pre-empt check makes the regression-detection-near-window-expiry race deterministic: regression always wins. Without the pre-empt, T+86399 regression vs T+86400 outcome_stable is a coin flip.

The detector itself runs hourly; the pre-empt check fires once per artifact per detection cycle. Cost: one indexed query per artifact in the scan window. Sub-millisecond.

### 4.2 External / manual report (chatbot + user)

New MCP action `extensions action=report_outcome` (see §5). Chatbot users explicitly report outcome states they observe — e.g., "this branch's MVP shipped to production successfully" → `outcome_stable`; "the deploy failed in staging" → `outcome_unstable`.

### 4.3 Rollback execution path

Per #57 surgical rollback, when `runs action=rollback_merge` executes the atomic-rollback-set, the rollback executor emits `outcome_rolled_back` (-10 weight) for each artifact in the closure. This composes the rollback decision with the outcome ledger in one place — the rollback IS the outcome.

---

## 5. `extensions action=report_outcome` MCP action

Write-side action; gates on storage-auth per #69.

### Signature

```
extensions action=report_outcome
  target_artifact_id <required, str>      # branch_version_id or branch_def_id
  outcome <required, str>                 # one of: stable | unstable | rolled_back | cancelled | superseded
  evidence_refs_json <required, list[dict]>  # NON-EMPTY per §5.2 spam prevention
  reason <optional, str>                  # free-text rationale
  weight_override <optional, float>       # rare; defaults to outcome_label's table weight
  → returns {event_id, outcome_event: <serialized>, validation_status}
```

### 5.1 Authority — write-side, requires storage-auth

Per #69 storage-auth pattern, this is a WRITE action (persists row to contribution_events). Gates on new `check_outcome_report_authority(actor_id, target_artifact_id)` in `tinyassets/storage/authority.py`:

```python
def check_outcome_report_authority(
    base_path: str | Path,
    actor_id: str,
    *,
    target_artifact_id: str,
) -> None:
    """Raise AuthorizationError if actor cannot report outcome for this artifact.

    Authority rules:
    - Artifact author may report (read goal.author or branch_def.author).
    - Host may always report.
    - Any actor with prior contribution_events row on this artifact's run-chain
      may report (they participated; their voice counts).
    - Otherwise: reject. Prevents anonymous spam reports.
    """
```

The "actors with prior contribution_events on this artifact's run-chain" rule is broader than just artifact-author — it captures the daemon hosts who executed steps + designers who contributed nodes used in the runs. They have skin in the game; they can report outcomes meaningfully.

### 5.2 Evidence-refs required (non-empty)

Per lead's ask B + spam-vector analysis: `evidence_refs_json` MUST be non-empty. No "this branch is unstable" report without typed evidence (per #66 EvidenceRef shape).

Validation rule: if `len(evidence_refs) == 0`, reject with `{"validation_status": "rejected", "field_errors": {"evidence_refs_json": "must contain at least one EvidenceRef — outcome reports require typed evidence"}}`.

This composes with the authority check: an authorized actor still cannot emit a credit-impacting outcome without showing receipts. Closes the spam vector at two layers.

### 5.3 Server-set fields

- `actor_id` (the work's actor) is read from the artifact's author (goal.author for goal-level; branch_def.author for branch-level).
- `reported_by_actor_id` in metadata is `_current_actor()` — server-set per #74 author_patch_notes precedent. Chatbot can't impersonate.
- `event_id` is uuid hex.
- `occurred_at` is server-set unix-now.

---

## 6. Composition with sibling proposals

### Task #48 contribution_events — same table

Outcome events emit INTO the existing table. The 4 indexes from #48 §1 (window, actor, artifact, run) all serve outcome-event queries directly. Bounty calc (#48 §5) extends its `event_type IN (...)` filter to include outcome types. No new indexes needed.

### Task #57 surgical rollback — pre-empt + integration

- Race handling per §4.1: the detector's pre-empt check ensures `caused_regression` events ALWAYS win against `outcome_stable` near window-expiry. Regression wins, deterministic.
- Rollback execution emits `outcome_rolled_back` directly per §4.3 — the rollback IS the outcome.
- `watch_window_seconds` field on `branch_versions` is reused (NOT a new `outcome_window_seconds` field) — closes a near-redundancy.

### Task #58 attribution-layer-specs — reputation flows

Reputation aggregation in attribution-layer-specs §7 reads `(actor_id, weight, event_type)`. Outcome events flow naturally — event_type filter expands to `outcome_*` types. Reputation deweights actors who repeatedly attain `outcome_unstable` / `outcome_rolled_back`; rewards actors with `outcome_stable` chains.

### Task #66 TypedPatchNotes — evidence_refs alignment

`evidence_refs_json` accepts `EvidenceRef` typed shape per #66 §2 — same kind enum (`wiki_page`, `node_def`, `branch_version`, `github_pr`, `run_artifact`). Outcome reports cite the same kinds of artifacts gate-evaluators cite. Cross-doc shape consistency.

### Task #69 storage-auth — write-side gating

`check_outcome_report_authority` lives in the policy module per #69 §2. Following the established pattern: every write-side surface (set_canonical, rollback, report_outcome, etc.) gates on a `check_*_authority` function in the centralized module.

---

## 7. Open questions

1. **Recursive CTE depth bound.** Recommended: `:max_lineage_depth = 5`, configurable via `TINYASSETS_LINEAGE_MAX_DEPTH` env var (introduce if not yet defined; reuse if it is). Closed.

2. **Multiple outcomes per artifact?** Recommended: YES. A branch_version can have `outcome_stable` then later `outcome_superseded` (replaced by newer version). Outcomes are append-only events; latest weighted-aggregate wins for reputation. UI can render history. Closed.

3. **Outcome weights configurability per-universe.** TRULY OPEN. Weights are calibrated by analogy to attribution-layer-specs §6.1 P0/P1/P2 — but some universes may treat `outcome_rolled_back` differently. A "we caught a P0 regression early" universe might treat rollback as +1 (early-detection win), while a "we shipped P0 to prod" universe treats it as -10. Recommend: NOT pre-decide. Surface as v2 question. Default v1 = global weights from §2 table.

4. **Detector implementation surface.** TRULY OPEN. Where does the time-window scheduled job live? Recommend NEW `scripts/outcome_window_detector.py` — own script, scheduled hourly, mirrors the canary-script pattern. Out of this proposal's scope; named as Step 1 implementation dispatch.

5. **(Truly open) Outcome-event idempotency.** Can the same artifact get TWO `outcome_stable` events emitted (e.g., detector races itself)? Recommend NO — detector queries existing terminal outcome events before emitting. Manual report MCP also rejects duplicate-emit attempts. But: there's a race window where two detectors running in parallel (rare) could both emit. Defer hard-uniqueness-via-DB-constraint to v2; v1 relies on advisory check. If observed in production, add unique constraint `(source_artifact_id, event_type) WHERE event_type LIKE 'outcome_%'`.

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No detector script implementation.** §7 Q4 — separate dispatch.
- **No new table.** Schema extension via event_type values per §2.
- **No bounty calc changes.** Existing #48 §5 bounty calc reads outcome events automatically once event_type filter expands.
- **No reputation calculation logic.** That's attribution-layer-specs §7 territory; this proposal supplies the input event types.
- **No gate-evaluator weight feedback.** Lead's brief explicitly excluded this — that's gate-side, separate spec.
- **No outcome event UI.** Surfacing outcomes to chatbots is downstream UX work.
- **No upstream signal-detection for canaries.** That's #57 + canary spec territory.

---

## 9. References

- Builds on: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) — schema extension; bounty calc reuses indexes.
- Builds on: `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (Task #57) — `caused_regression` source events + `watch_window_seconds` reuse + rollback-execution path emits `outcome_rolled_back`.
- Builds on: `docs/design-notes/2026-04-25-attribution-layer-specs.md` §3 (decay α=0.6) + §6.1 (P0/P1/P2 weight calibration analogy) + §7 (reputation aggregation consumes outcome events).
- Composes with: `docs/design-notes/2026-04-25-typed-patch-notes-spec.md` (Task #66) — `EvidenceRef` shape for evidence_refs_json validation.
- Composes with: `docs/design-notes/2026-04-25-storage-auth-refactor-proposal.md` (Task #69) — `check_outcome_report_authority` lives in policy module per §2 pattern.
- Companion principle: `project_designer_royalties_and_bounties.md` — remix-economy lineage credit (Carol→Bob via decay).
- Convention adherence: `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` — 5-move pattern.
- Existing schema reuse:
  - `branch_versions.watch_window_seconds` (added per #57 §3) — NOT introducing a new field.
  - `branch_definitions.fork_from` (`tinyassets/daemon_server.py` — fork_from migration block; line numbers drift as new migrations land, grep `fork_from` for current location) — lineage walk source.
  - `contribution_events` (per #48 §1) + 4 existing indexes.
- Existing dispatch + MCP patterns:
  - `_action_extensions_*` registry for `report_outcome` registration alongside `build_branch`/`patch_branch`/`author_patch_notes`.
  - `_current_actor()` for `reported_by_actor_id` server-set per #74 precedent.

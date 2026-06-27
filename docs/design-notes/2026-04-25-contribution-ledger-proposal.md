---
status: active
---

# Contribution Ledger — Schema Proposal (A1 / E15)

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Lead/navigator/host ratifies for v2 self-evolving-platform vision.
**Builds on:** navigator v1 vision §3 (`docs/design-notes/2026-04-25-self-evolving-platform-vision.md`); memory `project_designer_royalties_and_bounties`; G1 audit `docs/audits/2026-04-25-canonical-primitive-audit.md` (sibling design).
**Scope:** schema design only. No code changes. Picks one model + tradeoffs alternatives + emit-site audit.

---

## 1. Recommended schema — single `contribution_events` ledger

Pick the **one-table** model. Single append-only events ledger; all five contribution surfaces emit into it.

### DDL

```sql
CREATE TABLE contribution_events (
    event_id              TEXT PRIMARY KEY,           -- uuid hex
    event_type            TEXT NOT NULL,              -- enum below
    actor_id              TEXT NOT NULL,              -- internal Workflow user id
    actor_handle          TEXT NOT NULL DEFAULT '',   -- optional GitHub handle / display
    source_run_id         TEXT,                       -- runs.run_id, NULL for non-run events
    source_artifact_id    TEXT,                       -- branch_version_id, node_def_id, BUG-id, PR url
    source_artifact_kind  TEXT NOT NULL DEFAULT '',   -- 'branch_version' | 'node_def' | 'wiki_page' | 'github_pr' | ''
    weight                REAL NOT NULL DEFAULT 1.0,  -- contribution share (negative = regression)
    occurred_at           REAL NOT NULL,              -- unix ts seconds
    metadata_json         TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (source_run_id) REFERENCES runs(run_id)
);

CREATE INDEX idx_contribution_events_window
    ON contribution_events(occurred_at);
CREATE INDEX idx_contribution_events_actor
    ON contribution_events(actor_id, occurred_at);
CREATE INDEX idx_contribution_events_artifact
    ON contribution_events(source_artifact_id, source_artifact_kind);
CREATE INDEX idx_contribution_events_run
    ON contribution_events(source_run_id);
```

### Initial `event_type` enum (fixed initial set, open via registry)

| event_type | Emitted when | Surface |
|---|---|---|
| `execute_step` | Daemon-host runs a single node step | 1 (daemon-host) |
| `design_used` | A step references a published artifact (branch_version, node_def) | 2 (designer) |
| `code_committed` | A repo PR carrying the `patch-request` label is merged | 3 (PR) |
| `feedback_provided` | A gate-series evaluator cites a wiki page or chatbot artifact as decision input | 5 (chatbot-action) |
| `caused_regression` | A canary or rollback chain attributes a regression to a specific artifact (negative weight) | (E19, all surfaces) |

Lineage credit (surface 4) is **derived** at distribution-time from the leaf `design_used` events plus the artifact's `fork_from` chain — no dedicated event type. This is a deliberate optimization (see §1.3 below).

### Why this shape

- **Append-only.** No updates, no deletes — events are facts. Reputation/regression corrections come via new `caused_regression` events with negative weight, not by mutating prior rows. Survives audit.
- **Run-anchored AND run-free.** Surface 1 + 2 always carry `source_run_id` (every step is in a run). Surface 3 (PR) and surface 5 (gate cite of wiki page that pre-existed) may have no run. Schema accommodates both.
- **Three indexes, three real queries.** Window scans (bounty calc within `[t1, t2]`), per-actor reverse query (my dashboard / "show my contributions"), per-artifact reverse query ("who contributed to this branch_version"). All indexed.
- **`weight` is REAL, signed.** Positive = credit; negative = regression. E19 stays in this table without a separate negative-events table — see §6 Q2.

### Lineage credit derivation (surface 4)

The naïve approach is to emit one event per ancestor every time a `design_used` fires — but then a 5-generation lineage chain produces 5x the events. With heavy run volume that table grows fast and the bounty calc has to deduplicate.

**Better:** emit one `design_used` event per leaf artifact reference. At distribution-time, the bounty calculator walks `branch_definitions.fork_from` (or per-node lineage) and applies the platform's decay coefficient to derive ancestor shares from the same single event. Lineage walk happens once per merge (bounty calc), not once per execution.

**Why this works:** `fork_from` chain is content-addressed and immutable per `daemon_server.py:404-411`. The lineage of `branch_version_id = X` is a deterministic walk; deriving credit from it at calc-time is equivalent to (and cheaper than) writing N events at emit-time.

---

## 2. Tradeoff table — one-table vs two-table

| Axis | One-table (recommended) | Two-table (`step_executions` + `artifact_usages`) |
|---|---|---|
| **Schema complexity** | One table + 4 indexes. Moderate. | Two tables + ≥4 indexes + cross-table joins for unified queries. Higher. |
| **Emit-site clarity per surface** | **Decisive — one INSERT per step boundary, atomic.** Daemon-host and designer events fire on the SAME step-finalize transaction. | Two INSERTs at every step (one per table), needing same-transaction guarantees. Risk: cross-table partial writes if one fails mid-transaction. |
| **Lineage walk efficiency** | Walk `fork_from` once at calc-time; one `design_used` per leaf. | Same fork_from walk, but the walk's results join across `artifact_usages` rows, doubling the join surface. |
| **Bounty calc query performance** | `SELECT actor_id, SUM(weight) FROM contribution_events WHERE occurred_at BETWEEN ? AND ? AND ...`. Single indexed scan + GROUP BY. | UNION ALL (or two queries client-merged) of step_executions + artifact_usages; same index hit but more rows scanned in the union. |
| **Schema-extensibility (future event types)** | Add a new `event_type` enum value + handler. No migration. | Adding a new surface requires choosing which table it lives in (or a third table). Migration friction grows. |
| **Anti-spam fit (surface 5)** | `feedback_provided` events only emitted when gate cites — handler decides at emit-time, no schema constraint. | Same; both models satisfy. Tied. |
| **Migration cost** | Two tables added (`contribution_events` + `event_type_registry`); zero changes to existing tables. | Same — one or two tables; minor edge to two-table because each table is smaller and schema-evolves independently. Tied. |
| **Sybil-neutrality** | Schema doesn't bake assumptions; `actor_id` is opaque. Vetted-actor or pseudonymous models both work. | Same. Tied. |
| **Reverse query "show my contributions"** | `WHERE actor_id = ?` indexed, single table scan. | `UNION ALL` across both tables — slower, more code at the query site. |
| **Query for "all contributions to artifact X"** | `WHERE source_artifact_id = ? AND source_artifact_kind = ?` indexed. | Same join across two tables; slower. |

**Net:** one-table wins decisively on emit-site clarity (the deal-breaker) and on every read-side query that matters at scale. Two-table only ties on anti-spam fit and migration cost. There is no axis on which two-table strictly wins.

**Why "emit-site clarity" is the decisive axis:** surfaces 1 (daemon-host) and 2 (designer) BOTH fire on the same step boundary in the executor. Two-table would require either a SQLite multi-table transaction (fine on single-process daemon, harder under future contention) or two separate INSERTs with no atomicity guarantee. One-table = one INSERT, one transaction, no race.

---

## 3. Emit sites — concrete code references

| Surface | Emit site | Code path | What's added |
|---|---|---|---|
| 1. Daemon-host step | `update_run_status()` step-finalize path | `tinyassets/runs.py:331-377` | New sibling `record_contribution_event(event_type='execute_step', actor_id=daemon_actor_id, source_run_id=run_id, weight=1.0, ...)` call. Daemon's actor_id is captured at run claim time (today's `runs.actor` field). |
| 2. Designer (branch / node) | Same step-finalize as #1 + `record_event()` | `tinyassets/runs.py:434-450` | At each step, after running a node referencing branch_version_id V, emit `design_used` with actor_id=branch author, source_artifact_id=V, source_artifact_kind='branch_version'. Per-node references emit per-node events with kind='node_def'. |
| 3. Repo PR | NEW path — GitHub webhook handler | NEW file (does not exist yet). Lives alongside `tinyassets/api/` if HTTP, else `tinyassets/integrations/github_webhook.py`. | On `pull_request.closed` with `merged=true` AND label = `patch-request`, insert `code_committed` event with actor_id=PR author Workflow id, source_artifact_id=PR url, source_artifact_kind='github_pr'. |
| 4. Lineage (N-gen) | Derived at distribution-time, not emit-time | Bounty calculator (NEW). Reads `branch_definitions.fork_from` (`daemon_server.py:404-411`) + ancestor walk. | NO emit-site. Derived from the leaf `design_used` event by walking `fork_from` and applying decay coefficient. |
| 5. Helpful chatbot-action | Gate-series evaluator citing wiki content | `tinyassets/universe_server.py:13102` (`_wiki_file_bug` write) is the upstream emit; the evaluator's cite-decision is the actual emit trigger. | When a gate's evaluator returns a decision payload that names a wiki page or chatbot artifact (BUG-NNN, drafts/foo) as evidence, evaluator emits `feedback_provided` with actor_id=wiki page author, source_artifact_id=page slug, kind='wiki_page'. Anti-spam: NO emit unless a gate explicitly cites. |

**Note on surface 1 vs 2 atomicity:** both fire on the same step-finalize transaction. The handler emits BOTH events (daemon-host = 1 event, designer = 1+ events per artifact referenced) inside the same `_connect()` block alongside the existing `update_run_status()` + `record_event()` calls. SQLite `BEGIN/COMMIT` covers all writes atomically. One-table model means one shared table for both, no cross-table coordination.

---

## 4. Bounty calc query shape

Sketch (NOT implementation — design only):

```sql
-- Step 1: compute leaf ancestor set for the merge (recursive walk via fork_from)
WITH RECURSIVE lineage(artifact_id, depth) AS (
    SELECT :merge_artifact_id, 0
    UNION ALL
    SELECT bd.fork_from, lineage.depth + 1
    FROM lineage
    JOIN branch_definitions bd ON bd.branch_def_id = lineage.artifact_id
    WHERE bd.fork_from IS NOT NULL AND lineage.depth < :max_lineage_depth
)
-- Step 2: aggregate contribution weight by actor, applying decay per depth
SELECT
    ce.actor_id,
    ce.actor_handle,
    SUM(ce.weight * decay_coeff(lineage.depth)) AS share
FROM contribution_events ce
JOIN lineage ON lineage.artifact_id = ce.source_artifact_id
WHERE
    ce.occurred_at BETWEEN :window_start AND :window_end
    AND ce.weight > 0  -- positive contributions only at this stage
GROUP BY ce.actor_id, ce.actor_handle
ORDER BY share DESC;
```

A second pass subtracts `caused_regression` events (`weight < 0`) by actor for net reputation. Final routing layer uses the (actor_id, share) pairs to emit Co-Authored-By trailers + bounty payouts.

**Index hit confirmation:** `(occurred_at)` for window filter, `(source_artifact_id, source_artifact_kind)` for lineage join, `(actor_id, occurred_at)` covers per-actor totals. All three queried paths hit indexes; no full-table scan at expected event volumes.

`decay_coeff(depth)` is config-as-code per `project_designer_royalties_and_bounties` ("Specific weights are a platform parameter, not a per-user choice").

---

## 5. Migration plan — additive

### Step 0 — schema add

Add `contribution_events` table + 4 indexes. Add `event_type_registry` reference table for community-added event_type values (see §6 Q1). Run on next daemon start. Zero changes to `runs`, `branch_definitions`, `branch_versions`, `goals`, or any existing table.

### Step 1 — emitters opt in surface-by-surface

Surfaces are independent; each one's emit site can land separately:
- Surface 1 (daemon-host execute_step) lands when the executor's step-finalize path is wired. Lowest-risk first because runs already track daemon actor.
- Surface 2 (designer design_used) lands next; depends on the executor knowing the artifact references at step time (already true).
- Surface 3 (PR webhook) lands independently — new HTTP path.
- Surface 5 (feedback_provided) requires gate evaluator updates; lands when the gate-series typed-output contract from navigator's v1 vision §2 ships.
- Surface 4 (lineage credit) is bounty-calc-side; lands with the bounty calculator, not with the emitters.

### Step 2 — bounty calc reads

The bounty calculator (separate dispatch) reads from `contribution_events` for fair-distribution math. It does NOT modify the table — append-only invariant preserved.

### Step 3 — observability

Add `goals action=list_my_contributions` MCP action that reads from this table for chatbot-side dashboards. Independent of bounty calc; unblocks user-visible "what have I contributed" without monetization.

**Rollback:** drop the table; no other table depends on it. All current runs/branch flows continue working — events table is purely additive.

**No data loss:** existing `runs` row data (`provider_used`, `token_count`, `model` from Tasks #20/#24) stays where it is. `contribution_events` references runs by foreign key; runs row never moves.

---

## 6. Open questions

1. **`event_type` enum — fixed list, or open registry?** Recommend **fixed initial enum (the 5 surface types) + an `event_type_registry(event_type, description, registered_at, registered_by)` reference table for community-added types.** Survives community evolution without re-migrating the events table; new types must be registered (governance hook) but adding them doesn't touch `contribution_events`. Host can override toward a strictly-fixed enum if community-added types are out of scope.

2. **Negative events (E19 `caused_regression`) — same table or separate?** Recommend **same table with negative weight.** Reasons: (a) bounty calc and reputation calc both need to read positive AND negative in one query — separating doubles the read code; (b) the canary attribution flow naturally produces a row with negative weight when a rollback identifies the offending artifact; (c) the schema's `weight REAL` already supports it. Host can override toward a separate `regression_events` table for clearer audit.

3. **Lineage-decay coefficient location — config-as-code, or per-event metadata?** Recommend **config-as-code in `tinyassets/economics/decay.py` or similar** (matches project memory `project_designer_royalties_and_bounties`'s "platform parameter, not per-user choice"). Per-event metadata storage would make decay tuning a data migration. Host can override toward escrow-setter-customizable per-event decay if escrow customization wins precedence.

4. **Run cancellation / failed step — emit zero-weight events, or no event?** Recommend **emit no event for cancelled/failed steps.** Reasons: (a) the daemon didn't complete useful work (claimer payment is a separate question handled by the runs row's `status` field, not by contributions); (b) adding zero-weight events bloats the table without adding bounty signal; (c) regression attribution is a separate explicit `caused_regression` event with its own decision path. Host can override.

5. **(Punt) E18 sybil resistance** — schema is sybil-neutral as designed. `actor_id` is opaque; the schema doesn't care if it's a vetted-actor or a pseudonymous-with-vouching id. The vouching-decay-tier model from navigator's v1 vision §3 attaches at the actor identity layer, NOT at the events table. Where it interacts: bounty calc layer applies sybil-aware scaling to per-actor totals before payout, but `contribution_events` itself remains untouched. Host go/no-go on E18 is required before bounty calc ships, but does NOT block this schema.

---

## 7. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No bounty calc implementation.** Query shape sketched (§4); actual calculator + decay function + payout routing are downstream.
- **No GitHub webhook implementation** (surface 3). Only the schema slot. Mechanics are Task #55 (external PR bridge) per current queue.
- **No gate-series typed-output contract.** Surface 5 emit-site assumes the contract exists; that's a separate v2 deliverable.
- **No identity / sybil resolution.** Punted to E18. Schema is neutral.
- **No reputation system.** Net positive/negative weight is computable from this table, but reputation thresholds, decay, and surfacing are separate decisions.
- **No microtransaction vs pool-share decision** (E16). Bounty calc may aggregate or per-event-payout based on host call; schema supports both.

---

## 8. References

- Navigator v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §3 (five contribution surfaces) + §4 (priority HIGH for daemon contribution ledger + usage-event ledger).
- Project memory: `project_designer_royalties_and_bounties.md` (royalty distribution; navigator's fair-weighting role).
- Sibling design: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (G1 follow-on; matching audit-style discipline).
- Underlying audit: `docs/audits/2026-04-25-canonical-primitive-audit.md` (G1).
- Existing schema:
  - `runs` table — `tinyassets/runs.py:95-111` (per-run row; `provider_used`/`model`/`token_count` from Tasks #20/#24).
  - `run_events` table — `tinyassets/runs.py:116-127` (per-step event log; emit-site precedent).
  - `branch_definitions.fork_from` — `tinyassets/daemon_server.py:404-411` (lineage substrate).
  - `branch_versions` (publish path) — `tinyassets/branch_versions.py:109` (immutable artifact id).
- Emit-site files audited: `tinyassets/runs.py`, `tinyassets/branch_versions.py`, `tinyassets/daemon_server.py`, `tinyassets/universe_server.py`.

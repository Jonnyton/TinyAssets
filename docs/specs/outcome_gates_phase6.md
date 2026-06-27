---
status: active
---

# Phase 6 — Outcome Gates

**Status:** spec-first draft — planner-authored, awaiting dev claim.
**Depends on:** Phase 5 Goals cluster shipped (`4127fdb`); Phase 7.x storage cutover in-flight but not blocking. `goals` tool already stubs `leaderboard` with `metric="outcome"` — this spec lights that stub up.
**PLAN.md anchor:** Multi-User Evolutionary Design — "Outcome gates — real-world impact is the truth signal."
**Task row:** STATUS.md #56.

---

## Thesis

Through Phase 5 the Goal is a first-class object and Branches bind to it. What Goals still lack is a **truth signal**: an answer to "did this Branch's output actually matter?" Word count, run count, and fork count are proxies. The Project Thesis calls for real-world outcomes — DOIs, court filings, published books, awards, citations, conviction rates.

Phase 6 introduces **outcome gates** as ordered rungs on a Goal-specific ladder. Each Branch can self-report progress up its Goal's ladder; `goals leaderboard metric=outcome` ranks Branches by highest rung reached. Automation (DOI crawl, court-docket scrape, sales API) is explicitly deferred — the point of self-report v1 is to prove the data shape and the social dynamics before investing in integrations that will lag years behind.

**What this spec is NOT:**
- Not a review/judge mechanism (that's Phase 4's `run_judgments`).
- Not a scoring system — gates are binary achievements (reached / not reached), not numeric.
- Not a leaderboard rewrite — `goals leaderboard metric=outcome` already exists as a stub; this ships the data.
- Not automation. Every gate is self-reported with an evidence URL. Adversarial validation is Phase 6.5+.

---

## Non-goals (explicitly deferred)

- **No automated gate detection.** No DOI crawlers, no court-docket scrapers, no Amazon-rank pollers. Self-report + evidence URL only.
- **No per-rung scoring.** Rungs are ordered and discrete; "rung 3 reached" is the signal, no sub-rung fractions.
- **No moderation / fraud detection.** Gate claims go in as-is with evidence URL. Social accountability (public attribution, see PLAN.md "Private chats, public actions") handles the first wave; adversarial validation is Phase 6.5.
- **No retroactive backfill.** Existing Branches start with no gates. Users claim their own.
- **No cross-Goal outcome comparison.** Different Goals have different ladders; leaderboards are per-Goal only.
- **No ladder versioning in v1.** Editing a Goal's ladder re-scores existing claims by matching `rung_key` strings. Formal versioning is Phase 6.5 if users bikeshed the ladder.

---

## Data model

Two new tables + one column on `goals`.

```sql
-- Phase 5 goals table extended with ladder column
ALTER TABLE goals ADD COLUMN gate_ladder_json TEXT NOT NULL DEFAULT '[]';

-- A rung is proposed by the Goal author and applies to every Branch
-- bound to the Goal. Stored inline as JSON on the goals row to keep
-- the Phase 7 YAML-round-trip simple (ladder serializes as a list
-- under goals/<slug>.yaml#/gate_ladder).
--
-- Ladder shape:
-- [
--   {"rung_key": "draft_complete", "name": "Draft complete",
--    "description": "Workflow produced a full draft." },
--   {"rung_key": "peer_reviewed", "name": "Peer-reviewed",
--    "description": "At least 2 external reviewers commented." },
--   {"rung_key": "submitted", "name": "Submitted to venue",
--    "description": "Submission ID or tracking URL." },
--   ...
-- ]
-- Order in the list defines rung order. First rung is the easiest
-- to reach; last is the real-world impact gate.

-- Gate claims — one row per (branch, rung) achievement.
CREATE TABLE gate_claims (
  claim_id          TEXT PRIMARY KEY,            -- ulid
  branch_def_id     TEXT NOT NULL,               -- which Branch claims this
  goal_id           TEXT NOT NULL,               -- denormalized for query speed
  rung_key          TEXT NOT NULL,               -- matches a ladder entry
  evidence_url      TEXT NOT NULL,               -- required, validated as URL
  evidence_note     TEXT NOT NULL DEFAULT '',    -- optional human summary
  claimed_by        TEXT NOT NULL,               -- actor identity
  claimed_at        TEXT NOT NULL,               -- ISO8601
  retracted_at      TEXT,                        -- non-null = retracted
  retracted_reason  TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (branch_def_id) REFERENCES branch_definitions(branch_def_id),
  FOREIGN KEY (goal_id)       REFERENCES goals(goal_id),
  UNIQUE (branch_def_id, rung_key)               -- one active claim per rung per branch
);

CREATE INDEX idx_gate_claims_goal   ON gate_claims(goal_id);
CREATE INDEX idx_gate_claims_branch ON gate_claims(branch_def_id);
```

**Why inline ladder on `goals`, separate table for claims:**
- Ladder is a small, low-churn attribute of the Goal itself — edited by the Goal author, rarely. Inline = simpler YAML, fewer joins, no extra file in Phase 7 layout.
- Claims are high-churn, per-Branch, and need their own query patterns (leaderboard aggregation, retraction, evidence URL lookup). Separate table scales.

**Phase 7 YAML layout:**
- Ladder lands inside `goals/<slug>.yaml` under `gate_ladder:`.
- Claims land as `gates/<goal_slug>/<branch_slug>__<rung_key>.yaml` — one file per claim. Retractions rewrite the file with `retracted_at` populated rather than deleting, so git history preserves the retraction reason.

---

## Tool surface

New composite tool `gates` — mirrors the `goals` tool pattern (single dispatch, many actions). NOT folded into `goals` because the action count is large enough to bloat that docstring, and `gates` has a distinct mental model ("did outcomes happen?" vs. "what's the intent?"). Keep them separable per PLAN.md "Prefer a smaller number of reliable composable tools over many overlapping ones" — two tools each with clean scope, not one mega-tool.

### Actions

| Action | Params | Purpose |
|---|---|---|
| `define_ladder` | `goal_id`, `ladder` (JSON list) | Set or replace the ladder on a Goal. Owner-only. |
| `get_ladder` | `goal_id` | Read the ladder for a Goal. |
| `claim` | `branch_def_id`, `rung_key`, `evidence_url`, `evidence_note?` | Self-report a rung reached. Idempotent on `(branch, rung)` — re-claim updates evidence. |
| `retract` | `branch_def_id`, `rung_key`, `reason` | Owner-retract a claim. Record survives with `retracted_at`. |
| `list_claims` | `branch_def_id?` OR `goal_id?`, `include_retracted?` | Browse claims. One filter required. |
| `leaderboard` | `goal_id`, `limit?` | Rank Branches by highest-rung-reached, tiebreak by earliest claim. (Populates `goals leaderboard metric=outcome`.) |

### Dispatch pattern

```python
@mcp.tool(
    title="Outcome Gates",
    tags={"gates", "outcomes", "impact", "leaderboard", "community"},
    annotations=ToolAnnotations(
        title="Outcome Gates",
        readOnlyHint=False,
        destructiveHint=False,   # retract is soft-delete
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def gates(
    action: str,
    goal_id: str = "",
    branch_def_id: str = "",
    rung_key: str = "",
    ladder: str = "",           # JSON string; parsed in handler
    evidence_url: str = "",
    evidence_note: str = "",
    reason: str = "",
    include_retracted: bool = False,
    limit: int = 50,
    force: bool = False,
) -> str:
    """Outcome Gates — real-world impact claims per Branch.

    Each Goal declares a ladder of rungs (draft → peer-reviewed → published
    → cited → breakthrough). Branches self-report which rungs they've
    reached, with an evidence URL. `goals leaderboard metric=outcome`
    ranks Branches by highest rung.

    Actions:
      define_ladder Owner sets the rung list on a Goal.
      get_ladder    Read a Goal's ladder.
      claim         Report a rung reached. Needs branch_def_id,
                    rung_key, evidence_url.
      retract       Owner-retract a claim. Needs branch_def_id,
                    rung_key, reason.
      list_claims   Browse claims by branch_def_id OR goal_id.
      leaderboard   Rank Branches bound to a Goal by highest rung.

    This is self-report. Evidence URL is required but not validated
    beyond URL shape — social accountability handles fraud in v1.
    """
```

Kept intentionally small: 11 params, tight dispatch.

---

## Behavior contracts

### `claim`
- Validates `rung_key` exists in the Goal's ladder. If not, return `{"error": "unknown_rung", "available_rungs": [...]}`.
- Validates `evidence_url` matches basic URL shape (protocol + host). No HEAD request — local-first, no network dependency.
- Idempotent: if `(branch_def_id, rung_key)` already has a non-retracted claim, the call updates `evidence_url` / `evidence_note` / `claimed_at` and returns `{"updated": true}`. No duplicate rows.
- If the claim exists but is retracted, new `claim` call clears `retracted_at`/`retracted_reason` and re-activates. Claims are reversible.
- Attribution: `claimed_by` = MCP actor identity (same identity used for `goals propose`). Claims are publicly attributable per PLAN.md "Private chats, public actions."

### `retract`
- Owner-only — `claimed_by` must match actor OR actor is Goal owner. This lets Goal authors retract claims that misrepresent the ladder (e.g. someone claimed "published" with a 404 URL).
- `reason` required, non-empty. Retraction is a public act — the reason lives in git history.
- Retracted claims stay in the table with `retracted_at` populated so the lineage is legible. `list_claims include_retracted=false` hides them from default listing; leaderboard ignores them.

### `define_ladder`
- Owner-only — same ownership model as `goals update`.
- Replace-in-full, not patch. Ladder is small (3–10 rungs typical); editing is rare; round-trip is simpler if the whole list is the unit.
- When existing claims reference rungs no longer in the ladder, they are kept as-is but tagged `orphaned=true` in list_claims responses and excluded from leaderboard. Stop-gap until Phase 6.5 ladder versioning.

### `leaderboard`
- Group claims by `branch_def_id`, take max rung-index reached (non-retracted, non-orphaned).
- Sort: descending rung-index, then ascending `claimed_at` (earliest reacher wins ties).
- Output: list of `{branch_def_id, branch_name, highest_rung_key, highest_rung_index, claimed_at, evidence_url}`.
- Populates `goals leaderboard metric=outcome` — that action becomes a thin forwarder to `gates leaderboard`.

---

## Integration with existing systems

### `goals` tool
`goals leaderboard metric=outcome` currently returns a stub in `_action_goal_leaderboard` at `tinyassets/universe_server.py:6229-6264`. The stub emits:

```json
{
  "text": "**Leaderboard metric `outcome`** is reserved for Phase 6...",
  "status": "not_available_until_phase_6",
  "goal_id": "...",
  "metric": "outcome",
  "entries": []
}
```

After Phase 6, the handler delegates:

```python
if metric == "outcome":
    return _gates_leaderboard(gid=gid, limit=kwargs.get("limit", 50))
```

**Caller contract change — flag for dev.** The `entries` list shape is preserved (still a ranked list of Branch dicts), but:
- `status` shifts from `"not_available_until_phase_6"` to a real-success value (recommend `"ok"` to match the v1 metric handlers).
- The placeholder `text` message goes away — consumers displaying `text` when `status != "ok"` must already handle empty-entries gracefully; verify before the flag flip.
- Same change: drop `"outcome"` from `_STUB_LEADERBOARD_METRICS`, add to `_V1_LEADERBOARD_METRICS`.

Any UI special-casing `status="not_available_until_phase_6"` should remove that branch.

### `goals get`
`goals get goal_id=X` response gains a new field `gate_summary`:

```json
{
  "gate_summary": {
    "ladder_length": 5,
    "claims_total": 17,
    "branches_with_claims": 9,
    "highest_rung_reached": "submitted"
  }
}
```

One extra query (aggregate over `gate_claims`). Cheap.

### `branch` tool
Branch detail responses gain `gate_claims` array listing non-retracted claims for that branch. Enables the UI "this Branch has reached peer-review" badge.

### Phase 7 YAML
- Ladder embeds in `goals/<slug>.yaml#/gate_ladder` — trivially round-trippable.
- Each claim is `gates/<goal_slug>/<branch_slug>__<rung_key>.yaml`. On-disk format:

```yaml
claim_id: 01HY...
branch_def_id: loral-v3
goal_id: fantasy-novel
rung_key: draft_complete
evidence_url: https://example.com/drafts/loral
evidence_note: Full draft at 82k words
claimed_by: jonathan
claimed_at: '2026-05-01T14:22:03Z'
retracted_at: null
retracted_reason: ''
```

One commit per `claim` / `retract` / `define_ladder` action, per PLAN.md "GitHub as canonical shared state" invariant.

### Commit message templates

Commit namespace follows the file the action writes, not the tool that emitted it. `define_ladder` and `get_ladder` write under `goals/<slug>.yaml`, so they are `goals.*` commits. `claim`/`retract`/`list_claims` write under `gates/<goal_slug>/`, so they are `gates.*` commits. Pattern:

| Action | Target | Commit message |
|---|---|---|
| `gates claim` | `gates/<goal_slug>/<branch_slug>__<rung_key>.yaml` | `gates.claim: <goal_slug>/<branch_slug>@<rung_key>` |
| `gates retract` | same path (soft-delete) | `gates.retract: <goal_slug>/<branch_slug>@<rung_key>` |
| `gates leaderboard` | read-only, no commit | n/a |
| `gates list_claims` | read-only, no commit | n/a |
| `goals define_ladder` | `goals/<slug>.yaml` | `goals.define_ladder: <slug>` |
| `goals get_ladder` | read-only, no commit | n/a |

Read-only actions do NOT produce commits — per Phase 7 invariant, only public mutations land as git commits.

### `force` + `local_edit_conflict` pattern (copy from Phase 7.3)

All three mutation actions (`claim`, `retract`, `define_ladder`) MUST accept `force: bool = False` and surface `local_edit_conflict` when the target YAML has uncommitted local edits. Dev should copy the pattern verbatim from `_dispatch_goal_action` (`tinyassets/universe_server.py:6445`) and `_dispatch_branch_action` (`tinyassets/universe_server.py:2637`).

Response shape on conflict — built by `_format_dirty_file_conflict` at `tinyassets/universe_server.py:345-363`. Do NOT hand-author this payload; call the formatter with the `DirtyFileError`:

```json
{
  "status": "local_edit_conflict",
  "conflicting_path": "gates/<goal_slug>/<branch_slug>__<rung_key>.yaml",
  "all_conflicts": ["gates/<goal_slug>/<branch_slug>__<rung_key>.yaml"],
  "options": [
    "pass force=True to overwrite",
    "commit or stash local edits first"
  ]
}
```

H3 test `test_add_node_dirty_returns_local_edit_conflict` asserts on `result["conflicting_path"]` — mirror that assertion in gates tests. `all_conflicts` lists every path the action tried to write; it's a list of one for the simple claim/retract/define_ladder cases but matters if a future composite gates action touches multiple claim files per commit.

Dirty-check target for each action:
- `gates claim` / `gates retract` — the claim YAML path.
- `goals define_ladder` — the goal YAML path (ladder lives inline on `goals/<slug>.yaml`).

`force=true` bypasses the check and overwrites. Same ergonomics users already have for `goals propose/update/bind` and `branch` mutations; no new behavior to learn.

---

## Migration plan

1. **Schema migration** — `ALTER TABLE goals ADD COLUMN gate_ladder_json` + `CREATE TABLE gate_claims`. Pattern matches Phase 5's #50 `PRAGMA table_info` / `ADD COLUMN IF NOT EXISTS` idiom. No data backfill.
2. **Ship `gates` tool** — define_ladder + get_ladder + claim + retract + list_claims + leaderboard.
3. **Rewire `goals leaderboard metric=outcome`** from stub to real aggregation.
4. **Extend `goals get`** with `gate_summary`.
5. **YAML emitters** — `goals` YAML gains `gate_ladder`; new `gates/` directory under repo root with claim YAMLs. **No backend protocol change for ladder** — `save_goal_and_commit` at `tinyassets/storage/backend.py:95-103` already takes `goal: dict`, so `gate_ladder` rides through as a dict key. Dev should NOT touch the three backend implementations (SqliteOnly, SqliteCached, FilesystemOnly) for ladder support — the serializer picks up the new key automatically once the YAML schema lists it. Only new code required is `save_gate_claim_and_commit`, a fresh composite for the `gate_claims` table (new surface, no precedent to extend).
6. **Tests** — table-driven: propose Goal → define_ladder → bind Branch → claim rung → retract → re-claim → leaderboard. Plus YAML round-trip property tests (SQLite → YAML → SQLite identity) matching Phase 7 precedent.

Each migration step is an independent PR. Ladder column + claim table is safe to ship before the tool handler exists — column stays empty.

---

## Testing

New test file `tests/test_outcome_gates.py`:
- `test_define_ladder_owner_only` — non-owner `define_ladder` returns error.
- `test_claim_unknown_rung_returns_available_rungs` — good error shape for humans.
- `test_claim_is_idempotent_on_branch_rung` — second claim updates, doesn't duplicate.
- `test_retract_requires_reason` — empty reason rejected.
- `test_retract_is_reversible_via_reclaim` — claim → retract → claim flow restores.
- `test_leaderboard_orders_by_highest_rung_then_earliest_claim` — tiebreak logic.
- `test_leaderboard_ignores_retracted` — retracted claims don't count.
- `test_leaderboard_ignores_orphaned_rungs` — ladder-edited-out rungs don't count.
- `test_goals_leaderboard_outcome_delegates` — `goals` tool forwards correctly.
- `test_goals_get_includes_gate_summary` — summary field present.
- `test_yaml_round_trip_ladder` — `goals/<slug>.yaml` → SQLite → YAML identity.
- `test_yaml_round_trip_claim` — `gates/<goal>/<branch>__<rung>.yaml` round-trip identity.

Existing tests that need extension:
- `tests/test_goals_surface.py` — add `gate_ladder_json` to the `goals` fixture shape. Existing assertions should pass unchanged because ladder defaults to `'[]'`.
- `tests/test_phase7_h2_goals_cutover.py` — add ladder to round-trip fixture.

---

## Rollout

- **6.1** Schema migration + `gates claim` / `get_ladder` / `define_ladder` actions. Write-through SQLite only; no git commits yet.
- **6.2** `list_claims` + `retract` + `leaderboard` actions. Rewire `goals leaderboard metric=outcome`.
- **6.3** YAML emitters + git-commit integration (matches Phase 7.3 cutover pattern). Composite `save_gate_claim_and_commit`.
- **6.4** `goals get` gate_summary extension + `branch` tool gate_claims field.

Ships behind a feature flag `GATES_ENABLED=false` by default through 6.1–6.2 so schema exists without exposing half-wired tool. Flag flips in 6.3.

### 6.2 implementation notes (planner, 2026-04-14)

Phase 6.2 adds three read/write-less actions to the existing `gates` tool and rewires one leaderboard stub. No schema change, no git-commit path (that's 6.3). The intent is: finish the tool-surface contract 6.1 half-shipped, fix two reviewer-flagged 6.1 debts, and land the outcome-metric integration `goals leaderboard metric=outcome` has been promising since Phase 5.

#### Scope (one-paragraph)

Three handlers (`_action_gates_retract`, `_action_gates_list_claims`, `_action_gates_leaderboard`) registered in `_GATES_ACTIONS` at `tinyassets/universe_server.py`. One helper in `tinyassets/author_server.py` per new action (`retract_gate_claim`, `list_gate_claims`, `gate_leaderboard`). `_action_goal_leaderboard` at ~line 6245 becomes a thin forwarder to `_action_gates_leaderboard` for `metric=outcome`. Two 6.1 debts fixed inline. Flag remains `GATES_ENABLED=0` default through 6.2 per existing rollout.

#### Action signatures

All three return JSON strings (tool-surface convention). `status` on the envelope tracks outcomes (`retracted`, `reactivated`, `ok`, `rejected`, `not_available`). Claims are returned as plain dicts matching what `claim_gate` already returns; no new row shape is invented.

- **`retract`** — `branch_def_id`, `rung_key`, `reason` (required, non-empty). Authorization: `claimed_by == actor` OR `goal.author == actor` OR `actor == "host"`. Evidence URL and note are retained; only `retracted_at` + `retracted_reason` are set. Returns `{"status": "retracted", "claim": {...}}`. Double-retract returns `{"status": "already_retracted", ...}` — idempotent so repeated owner calls don't churn. If the claim doesn't exist, `{"status": "rejected", "error": "claim_not_found"}`.
- **`list_claims`** — `branch_def_id?` XOR `goal_id?`, `include_retracted=false`, `limit=50` (capped at e.g. 500 to keep responses bounded). Exactly one filter required; both-or-neither returns rejected. Returns `{"status": "ok", "claims": [...], "count": N, "filter": {...}}`. Sort: `claimed_at` descending. Each claim includes `orphaned: bool` computed by comparing `rung_key` against the current ladder on the Goal (see behavior-contracts `define_ladder`).
- **`leaderboard`** — `goal_id` (required), `limit=50`. Returns `{"status": "ok", "goal_id": str, "goal_name": str, "entries": [...], "count": N}`. Entry shape per spec §Behavior: `branch_def_id`, `branch_name`, `highest_rung_key`, `highest_rung_index`, `claimed_at` (earliest claim at that rung), `evidence_url`. Sort: `highest_rung_index` desc, `claimed_at` asc (earliest reacher wins ties). Orphaned claims excluded; retracted claims excluded. Respects Branch visibility — see §Integration.

#### Validation & error modes

- Goal-existence and branch-existence checks mirror 6.1 handlers: `KeyError` from `get_goal` / `get_branch_definition` maps to `{"status": "rejected", "error": "Goal '...' not found."}`. Don't leak internal exception text.
- `retract.reason` must be non-empty after strip. The spec text says retraction reasons live in git history; they still land on the SQLite row in 6.2, git wiring in 6.3 will pick them up.
- `list_claims` dual-filter rule: reject with a clear message if both `branch_def_id` and `goal_id` are set, or if neither is. Keep the envelope consistent (`available_filters: ["branch_def_id", "goal_id"]`).
- `leaderboard` with an empty ladder returns `{"status": "ok", "entries": [], "count": 0, "note": "Goal has no ladder defined."}` — no error; empty is a real answer.
- Unknown branch in `list_claims branch_def_id=...`: treat as empty result set, not an error. Consistent with how `branch list` handles unknown filters. Unknown goal in `list_claims goal_id=...` OR `leaderboard goal_id=...` is a hard reject (the caller asked about a specific ID).
- URL validation stays in claim path (6.1); retract does not re-validate evidence URL.

#### Authorization model

Four authority patterns across the three actions. Keep them explicit in handler code, not buried in helper-level checks:

| Action | Authorized if … |
|---|---|
| `retract` | `actor == claim.claimed_by` OR `actor == goal.author` OR `actor == "host"` |
| `list_claims` | Anyone (read). Private-Branch filtering handled at row level (see Integration). |
| `leaderboard` | Anyone (read). Private entries filtered at row level. |

Pattern matches `goals update` at line 5936-5967 for the host fallback. Use `_current_actor_or_anon()` consistently (already used in 6.1).

#### 6.1 debts folded in

**Debt 1: host-override missing on `define_ladder`.** Current code at `tinyassets/universe_server.py:6694-6702` only checks `goal["author"] != actor` and rejects. Fix: mirror `goals update` at 5958-5959 — allow if `actor == "host"`. One-line change, no new tests needed beyond a host-actor case added to the 6.2 `retract` auth tests (same pattern).

**Debt 2: rebind-between-claims edge.** `claim_gate` at `tinyassets/author_server.py:2685-2697` UPDATE overwrites the denormalized `goal_id` with whatever the Branch is currently bound to. If a Branch rebinds from Goal A to Goal B between two claims on the same rung_key, the first claim is silently relocated to Goal B when the second `claim` call fires. Leaderboard math for Goal A quietly changes.

Fix options, rank-ordered:
1. **Preferred: reject re-claim if existing claim's `goal_id` != current branch `goal_id`.** Add a guard in `claim_gate` (or earlier in `_action_gates_claim`) that detects the mismatch and returns `{"status": "rejected", "error": "branch_rebound", "original_goal_id": "...", "current_goal_id": "...", "hint": "Retract the existing claim first, then re-claim under the new Goal."}`. Makes the rebind visible to the user and preserves Goal A's leaderboard integrity.
2. Not preferred: auto-retract under the old Goal + new claim under new Goal. Two state transitions inside one tool call hides data movement; leaderboard shifts silently.
3. Not preferred: lock Branch re-bind when any active claim exists. Pushes the tension into `goals bind`, wrong surface.

Option 1 is the smallest, clearest fix and composes with 6.3 (rebind shows up as an explicit retract+claim pair in git history). Test: create Goal A, Goal B, Branch, claim rung under A, rebind Branch to B, re-claim — assert rejected with `branch_rebound`.

#### Integration with existing systems

- **`_action_goal_leaderboard`** at `tinyassets/universe_server.py:6245` currently stubs `metric=outcome`. Replace the stub branch (lines 6267-6280) with: call `_action_gates_leaderboard` with `goal_id` + `limit` from kwargs, then massage the response shape back into the `goals leaderboard` envelope (it uses `lines` + `text` formatting; entries still land in `entries`). Keep `_V1_LEADERBOARD_METRICS` and move `"outcome"` out of `_STUB_LEADERBOARD_METRICS` into `_V1_LEADERBOARD_METRICS`. `_ALL_LEADERBOARD_METRICS` stays the union.
- **Branch visibility.** `list_claims` and `leaderboard` must filter entries whose Branch has `visibility="private"` unless the caller is the Branch owner or host. Equivalent logic already exists for `branch list`; reuse or parallel-implement minimally.
- **`GATES_ENABLED` gating stays in place.** Same flag guard as 6.1. Rewired `goals leaderboard metric=outcome` must *also* respect the flag — if the flag is off, fall back to the existing "not_available" stub response but with message "outcome metric is gated by GATES_ENABLED (Phase 6.2)." This is important: we don't want the outcome-metric rewire to make `goals leaderboard` fail when gates are disabled.

#### Test strategy

Existing 6.1 tests live in `tests/test_universe_server_gates.py` (or nearest match). Extend the same file; don't spawn a new one. Aim for ~15-20 new tests, all in one file. Structure by action, then by concern:

- **`retract` (6 tests)**: success path, `reason` empty rejected, auth — owner of claim, auth — Goal author, auth — host override, auth — unrelated user rejected, already-retracted is idempotent, claim-not-found rejected.
- **`list_claims` (5 tests)**: by `branch_def_id`, by `goal_id`, both filters rejected, neither filter rejected, `include_retracted=true` surfaces retracted rows, orphaned claims get `orphaned=true` when ladder dropped the rung, private-Branch filtering hides rows from non-owner/non-host.
- **`leaderboard` (5 tests)**: ranking correct by rung index, tiebreak by `claimed_at` asc, retracted claims excluded, orphaned claims excluded, private branches filtered.
- **6.1 debts (3 tests)**: `define_ladder` host-override succeeds for non-author host, `claim` rejects with `branch_rebound` when Branch's `goal_id` changed since first claim, `goals leaderboard metric=outcome` forwards correctly (returns real entries not stub message).
- **`GATES_ENABLED=0` behavior (2 tests)**: `gates retract` returns `not_available`, `goals leaderboard metric=outcome` falls back to gate-disabled message not stale stub.

Every test uses the existing 6.1 fixtures (base_path tmp, `initialize_author_server`, actor-identity monkeypatch). No new fixture scaffolding should be needed. If dev finds they need one, that's a signal something has drifted and worth raising.

#### Deliverables & file list

- `tinyassets/universe_server.py` — three handlers + registration + leaderboard rewire + `define_ladder` auth fix.
- `tinyassets/author_server.py` — `retract_gate_claim`, `list_gate_claims`, `gate_leaderboard`; optional helper `_get_current_goal_id_for_branch` if the rebind guard lives at that layer.
- `tests/test_universe_server_gates.py` (or nearest) — ~20 new tests.
- `docs/specs/outcome_gates_phase6.md` — mark 6.2 done in §Rollout when landed.

No PLAN.md changes. No STATUS.md changes beyond the row-delete on land.

#### Explicit non-goals in 6.2

- Git commit path. That's 6.3. Don't touch `tinyassets/storage/backend.py`.
- YAML emitters. 6.3.
- `goals get` gate_summary field. 6.4.
- `branch` tool gate_claims field. 6.4.
- Ladder versioning / rung reuse / evidence archival / adversarial validation. 6.5+.

If dev notices the 6.3 YAML layout could be shape-changed by 6.2 decisions (e.g. how orphaned claims serialize), raise it — I'd rather adjust now than cement a shape that forces 6.3 migrations.

#### Success criteria (for reviewer)

- All six 6.2 action/debt items landed with test coverage.
- `goals leaderboard metric=outcome` returns real ranked entries when gates are enabled, falls back gracefully when disabled.
- No regressions in 6.1 tests; all new tests green.
- Authorization matrix matches the table above; no silent broadening of write paths.
- Rebind guard visible in the failing-test output as an explicit `branch_rebound` error, not a silent data move.

---

## Open questions (escalate)

1. **Ladder author authority.** Current spec: only Goal owner defines the ladder. Alternative: any user can propose rung additions that the owner approves (lighter-weight, more multiplayer). Recommend: v1 = owner-only; revisit if users bikeshed ladders.
   **Resolved:** accepted default — owner-only landed in Phase 6.2; no user complaints surfaced.
2. **Evidence URL hosting.** Self-reported URLs will rot. Should Phase 6 archive a snapshot (web.archive.org submit) at claim time? Recommend: NO in v1 — keep the data model clean, revisit after abuse emerges.
   **Resolved:** accepted default — no archival snapshot shipped; abuse hasn't surfaced.
3. **Private claims.** Should Branches with `visibility=private` support private gate claims? Recommend: YES, inherit Branch visibility. Leaderboard respects visibility. Zero new UI surface for v1.
   **Resolved:** accepted default — blocked only by absence of `visibility` column on `branch_definitions` (tracked as task #56 Phase 6.2.2, separate from this question).
4. **Cross-Goal rung reuse.** A "peer-reviewed" rung means the same thing for 100 different Goals. Should rungs be shared primitives? Recommend: NO in v1 — let string-matching happen organically first, formalize if patterns emerge.
   **Resolved:** accepted default — rungs stayed per-Goal strings through 6.2/6.3/6.4; no cross-Goal sharing demand yet.

These were the four questions surfaced to host before dev coding began. All four accepted the recommended default; the spec is self-closing on §Open questions as of Phase 6.2-6.4 landing.

---

## Out of scope (future phases)

- **6.5 Adversarial validation.** Community challenges on suspicious claims. Voting, dispute resolution.
- **6.6 Automated gate detection.** DOI crawl, court-docket scrape, Amazon rank polling — per-Goal plugins.
- **6.7 Ladder versioning.** Formal `ladder_version` on claims so Goal-ladder edits don't orphan history.
- **6.8 Cross-Goal rung library.** Shared rung definitions with stable IDs.
- **6.9 Outcome-weighted leaderboard.** Currently rung-ordered; future version could weight higher rungs more heavily for aggregate scores.

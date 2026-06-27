---
status: shipped
shipped_date: 2026-04-14
shipped_in: 5fa8eda  # Phase 6.2.2: Path A — Branch visibility column + filters
---

# #56 Private-Branch Visibility Filter — 3-Path Comparison

**Status:** Decided + landed. Path A shipped in `5fa8eda` ("Phase 6.2.2: Path A — Branch visibility column + filters") with follow-up `96a73ae` closing 2 leak sites. Tests in `tests/test_branch_visibility.py`. Retain for decision archaeology.
**Related:** STATUS.md Work row #56 "Phase 6.2.2 — private-Branch visibility filter". Surfaced in `docs/specs/outcome_gates_phase6.md` §Open Questions (Q3, resolved default) and §Rollout (Phase 6.2 test gap). Referenced in `docs/specs/phase_h_preflight.md` §4.9 Q8 as "surface only; no design resolution."
**Target files:** `tinyassets/author_server.py` (schema + branch CRUD), `tinyassets/universe_server.py` (action handlers that need the filter).

## Problem

Phase 6.2 needs `list_claims` and `leaderboard` to hide gate claims whose Branch is private — unless the caller is the Branch owner or host. The `goals` table has a `visibility` column (`author_server.py:347`). The `branch_definitions` table does **not** (schema at `author_server.py:310-327` — zero visibility field). Every other flavor of "private Branch" work is downstream of resolving this one gap.

## Paths

### Path A — Add `visibility` column to `branch_definitions`

**Summary:** Mirror the Goals pattern directly. Add `visibility TEXT NOT NULL DEFAULT 'public'` to `branch_definitions`, index it, thread through Branch CRUD and the two Phase 6.2 filter sites.

**LOC estimate:** ~150–250 lines.
- Schema + migration: ~30 lines (ALTER TABLE, idempotent check, index).
- Branch CRUD handlers: ~40 lines (update `create_branch_definition`, `update_branch_definition`, `list_branch_definitions`, response shapers).
- Filter helper: ~30 lines (`_filter_private_branches(rows, actor)` reused in `list_claims` + `leaderboard`).
- Tests: ~50–100 lines (5–10 new tests: create-with-visibility, update-visibility, list-public-hides-private, owner-sees-own-private, host-sees-all, gate-filter-leaderboard, gate-filter-list-claims).

**What breaks if chosen:**
- Schema migration on live DBs. Idempotent ALTER TABLE makes this safe; precedent is Phase 5 `branch_definitions.goal_id` migration at `author_server.py:376-390`. Low risk.
- Two places to set visibility now: the Goal and the Branch. Users get to bikeshed "why do I set it in two places?"
- Any tool that queries `branch_definitions` without going through the filter helper becomes a visibility bypass. Defense: make the helper a mandatory pass-through in `list_branch_definitions`, not an opt-in.

**What accelerates:**
- Direct ownership model: Branch owner controls Branch privacy. Matches user mental model (I wrote this code, I decide who sees it).
- Decouples Branch privacy from Goal privacy. A private experimental Branch attached to a public community Goal is a real case — multiple Phase 5 discussions assume this works.
- Unblocks the Phase 6.2 tests that were written assuming this (`outcome_gates_phase6.md:402-404` — "private-Branch filtering hides rows from non-owner/non-host").
- Zero cross-table joins in the hot path — `list_claims` already joins `branch_definitions`; add one WHERE clause.

---

### Path B — Goal-gated inheritance (Branch visibility = Goal visibility)

**Summary:** No schema change. A Branch is private if-and-only-if its bound Goal is private. The filter at `list_claims` / `leaderboard` joins through `goals.visibility`.

**LOC estimate:** ~60–120 lines.
- No schema migration.
- Filter helper: ~30 lines (SQL JOIN `branch_definitions` → `goals`, WHERE `goals.visibility != 'private'` OR owner match).
- Update handlers to join: ~20–40 lines.
- Tests: ~30–50 lines (fewer test paths — one dimension to test, not two).

**What breaks if chosen:**
- **Hard semantic collision.** A community-run Goal ("publish a literary novel") is public by default. Branches attached to it cannot be made private without making the Goal private — which breaks the leaderboard/discovery for every OTHER Branch on that Goal.
- Solo private work becomes awkward. A user who wants a private scratch Branch on a public Goal has to either clone the Goal private (breaks cross-Branch comparison) or accept that their scratch work is public.
- Branches without a bound Goal (`branch_definitions.goal_id IS NULL` — permitted by schema at `author_server.py:382-386`) have undefined visibility. Treating unbound-Branch as public is wrong; treating it as private is also wrong. Requires a third rule on top.
- Hosts Q8 in phase_h_preflight (`phase_h_preflight.md:332`) explicitly names this option and defers it *because* the resolution re-introduces a PLAN.md tension.

**What accelerates:**
- Shortest path to green tests. If the host's only goal is unblocking Phase 6.2's test suite, this ships in an afternoon.
- No new column, no migration, no rollback risk.
- If the long-term answer is "everything is public by default, private is the exceptional case and always at Goal granularity," this is correct and cheaper.

---

### Path C — Separate `branch_privacy` table (visibility as a relation, not a column)

**Summary:** A new `branch_privacy(branch_def_id, visibility, authorized_actors_json, set_by, set_at)` table. Absence = public; presence = private with an ACL. No change to `branch_definitions`.

**LOC estimate:** ~200–350 lines.
- New table + schema: ~25 lines.
- CRUD handlers (`set_branch_privacy`, `get_branch_privacy`, `remove_branch_privacy`): ~80 lines.
- Filter helper with LEFT JOIN + JSON authorization check: ~50 lines.
- Tests: ~80–150 lines (covers ACL granularity, which Paths A+B don't).

**What breaks if chosen:**
- **Scope creep.** This solves #56 by building the ACL layer #56 doesn't need yet. Paid-market Phase G already has enough new concepts in flight.
- Two sources of truth on Branch metadata (`branch_definitions` + `branch_privacy`). Every tool that lists Branches must remember to join.
- Test matrix explodes: public / private-owner-only / private-with-ACL / private-owner-revoked-but-host-still-sees / etc.

**What accelerates:**
- **Only path with ACL granularity.** If the future brings "share with 3 collaborators" as a v1 requirement (not just "private to me"), this is the table you'd build anyway. Paths A and B both need a Path C migration later.
- Keeps `branch_definitions` schema stable as ownership semantics evolve.
- Natural home for future privacy metadata (set_by audit trail, expiry dates, time-limited shares).

---

## Side-by-side

| Dimension | Path A (column) | Path B (inherit) | Path C (ACL table) |
|---|---|---|---|
| LOC | ~200 | ~90 | ~275 |
| Schema change | ALTER TABLE | None | New table |
| Unblocks Phase 6.2 tests | Yes | Yes | Yes |
| Solo-private-on-public-Goal supported | Yes | **No** | Yes |
| Branch without Goal handled | Yes | Ambiguous | Yes |
| ACL (share with N users) supported | No | No | Yes |
| Rollback complexity | Low (drop column) | None | Medium (drop table) |
| Cognitive load for users | Medium (two visibility knobs) | Low (one knob) | High (ACL UI needed) |
| Future-proof if multi-user sharing arrives | Requires rewrite | Requires rewrite | Ready |
| Matches Goals-side precedent | **Yes — direct mirror** | No (new pattern) | No (new pattern) |

## What data the host needs to decide

1. **Is "private Branch on public Goal" a supported product state?** If YES → rule out Path B. If NO → Path B is viable (and cheapest).
2. **Is Branch sharing (to N named users) on the roadmap?** If YES within 6 months → Path C earns its keep. If NO → Path A or B is enough.
3. **How much of the "two visibility knobs" UX complaint (from users, not from us) would cost more than the "can't have private Branch on shared Goal" complaint?** This is user-sim territory — a mission where a daemon tries to do private experimental work on a community Goal would answer it.
4. **Phase 7 GitHub-as-canonical shift.** Once Branches migrate to repo files (per planner project memory), does "private" mean "in a private repo" rather than a DB flag? If yes, all three paths become transitional — Path B is least wasted work, Path A is second-least.

## Recommendation

**Path A, with Path C as the known-future migration if ACL arrives.** Confidence: medium-high (70%).

Reasoning:
- Path B's "private Branch on public Goal" collision is not theoretical — it's the default shape for anyone doing solo work on a community Goal. Shipping Path B and then fielding that complaint is worse than shipping Path A.
- Path A is a direct mirror of the Goals visibility pattern — the codebase already knows this shape; new code reads like old code. Minimum cognitive novelty.
- Path C is right if ACLs are coming. They're not on any roadmap I can see. Building the ACL table speculatively is exactly the "scaffolding a smarter model doesn't need" antipattern PLAN.md warns against.
- The Phase 7 GitHub-as-canonical transition (planner memory: "Final framing 2026-04-13") changes storage substrate but not the semantic need for a visibility bit per Branch. Path A's single column translates cleanly to a single YAML field per Branch file.

**If the host's real question is "can we defer this another cycle,"** Path B done surgically (JOIN in the two Phase 6.2 handlers, no Branch CRUD changes) is the cheapest "just enough" — ~60 LOC, unblocks Phase 6.2 tests, documented as provisional. The "private Branch on public Goal" complaint becomes a known defect the team ships knowing about, resolved when Path A or C lands.

## Non-recommendations (explicitly considered, rejected)

- **Path D: dashboard-only visibility.** Mentioned in phase_h_preflight §4.9 Q8 — "dashboard shows 'Private branches: N (see host settings)' without resolving the design question." This is a UI stub, not a design path. Not a candidate for #56 resolution.
- **Path E: reuse Goal `visibility='deleted'` pattern.** Soft-delete-style visibility states on Branch would work but conflates access control with lifecycle. The Goals table already has this conflation (`visibility` holds both `public/private` AND `deleted`); replicating the conflation on Branch doubles down on a suspect shape. If Path A is chosen, I'd recommend splitting `visibility` and `lifecycle_state` on Goals at the same time — out of scope for #56.

## Followups if Path A lands

- Audit every call site of `list_branch_definitions` to confirm the filter helper is mandatory (can't bypass).
- Update `branch` tool response shape in `universe_server.py` to surface `visibility` — currently omitted.
- Add a phase_h_preflight §4.9 Q8 resolution note pointing at Path A when shipped.
- Delete STATUS.md Work row #56.

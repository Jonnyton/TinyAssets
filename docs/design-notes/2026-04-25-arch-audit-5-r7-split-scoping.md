---
status: superseded
superseded_by:
  - docs/exec-plans/active/2026-04-26-decomp-arc-b-prep.md
  - docs/exec-plans/active/2026-04-19-rename-end-state.md
status_detail: Items 1-5 covered by Arc B/C; 6+7 OBVIATED 2026-04-28 (audit doc); 8 by Task #25 STATUS format
---

# Arch Audit Finding #5 — R7 Split Scoping

**Date:** 2026-04-25
**Author:** navigator
**Parent:** `docs/design-notes/2026-04-24-architecture-audit.md` §Finding #5
**Status:** dev-dispatchable (unblocked after finding #3 gate is frozen, not necessarily merged)

---

## What R7 is

R7 = extract `tinyassets/daemon_server.py`'s bounded storage contexts into `tinyassets/storage/` submodules.

**Current state:** 3,289 lines, 95 functions, 23 `CREATE TABLE` statements in one file.
**Done (37%):** `storage/accounts.py` (307L), `storage/rotation.py` (193L), `storage/caps.py` (156L), `storage/__init__.py` (569L) = 1,225 lines migrated.
**Remaining (63%):** ~2,064 lines across 4 target modules.

---

## Is this worth doing? (ROI read)

The 3-layer lens: does splitting `daemon_server.py` make the chatbot better at serving the user? Indirectly, yes — but the real ROI is operational:

1. **The file is growing, not shrinking.** +30%/5-weeks on `universe_server.py` is the headline, but `daemon_server.py` at 3,289L is also stalled while `storage/` is the PLAN.md-committed target. Every new feature that needs a table adds to the monolith.
2. **`catalog/backend.py` (#6) is blocked on this.** The inverted dependency (storage calling service) cannot be resolved cleanly until the storage layer has its own modules to call instead of going through the `author_server` shim. Fixing the inversion requires knowing *where* the storage primitives will live.
3. **`author_server` rename (#3) is also blocked.** The bulk rename in `universe_server.py` and `catalog/backend.py` is cleaner once the migration targets are stable — you don't want to rename 70+ call sites only to discover you're pointing at a file that's about to be split.

**Sequencing verdict:** R7 extractions (#6/#7/#8 in the audit's dispatch table) should wait until the `author_server` pre-commit gate (#2 in audit table) is in place. That gate stops new `author_server` imports from appearing in freshly extracted modules, which would re-entrench the debt. The extractions themselves don't require the bulk rename (#3/audit) to be complete — they just import from `daemon_server` directly (bypassing the shim), which is already how the three shipped `storage/` modules work.

---

## Extraction map

### Task A — `storage/universes_branches.py`

**What moves:**

| Line range | Functions |
|---|---|
| 615–807 | `create_branch`, `list_universe_forks`, `get_branch`, `mark_branch_status`, `create_snapshot`, `set_branch_head`, `get_snapshot`, `list_snapshots` |
| 808–977 | `register_author`, `list_authors`, `get_author`, `spawn_runtime_instance`, `retire_runtime_instance`, `get_runtime_instance`, `list_runtime_instances` |
| 1841–1866 | `_branch_from_row`, `_author_from_row`, `_runtime_from_row` (row helpers) |
| 1904–2202 | `save_branch_definition`, `get_branch_definition`, `list_branch_definitions`, `update_branch_definition`, `delete_branch_definition`, `fork_branch_definition` |

**Tables it owns:** `branches`, `branch_heads`, `universe_snapshots`, `author_definitions`, `author_forks`, `author_runtime_instances`, `branch_definitions`.

**Approx size:** ~700–800 lines moved out.
**Files:** `tinyassets/storage/universes_branches.py` (new), `tinyassets/daemon_server.py` (reduce), `tinyassets/storage/__init__.py` (re-export stubs).
**Deps:** Pre-commit gate for `author_server` imports (#2 in audit). No code dependency on Tasks B or C.
**Effort:** 2–3 days.

---

### Task B — `storage/requests_votes.py`

**What moves:**

| Line range | Functions |
|---|---|
| 979–1063 | `create_user_request`, `get_user_request`, `list_user_requests`, `list_active_user_ids` |
| 1065–1337 | `create_vote_window`, `propose_author_fork`, `cast_vote`, `resolve_vote_if_due`, `get_vote`, `record_action`, `list_actions` |
| 1860 | `_request_from_row` (row helper) |

**Tables it owns:** `user_requests`, `vote_windows`, `vote_ballots`, `action_records`.

**Note:** `propose_author_fork` (line 1105) calls `register_author` and `create_branch` — two functions that will move to Task A's module. Task B must import from `storage.universes_branches` after Task A lands, or accept a temporary `daemon_server` import that gets cleaned up in the rename pass. Recommend: dispatch Task B *after* Task A is merged so the cross-module import is correct from the start.

**Approx size:** ~400–450 lines moved out.
**Files:** `tinyassets/storage/requests_votes.py` (new), `tinyassets/daemon_server.py` (reduce), `tinyassets/storage/__init__.py` (re-export stubs).
**Deps:** Task A merged.
**Effort:** 2–3 days.

---

### Task C — `storage/goals_gates.py`

**What moves:**

| Line range | Functions |
|---|---|
| 2204–2812 | All goal CRUD: `save_goal`, `get_goal`, `update_goal`, `list_goals`, `search_goals`, `delete_goal`, `branches_for_goal`, `set_goal_ladder`, `get_goal_ladder` |
| 2425–2769 | All gate functions: `_gate_claim_from_row`, `claim_gate`, `get_gate_claim`, `retract_gate_claim`, `list_gate_claims`, `gates_leaderboard`, `goal_gate_summary` |
| 2816–3023 | Leaderboards + analytics: `goal_leaderboard`, `goal_common_nodes`, `goal_common_nodes_all` |
| 2208 | `_goal_from_row`, `_gate_claim_from_row` (row helpers) |

**Tables it owns:** `goals`, `gate_claims`.

**Note:** `claim_gate` (line 2491) is the most complex function in this group (~79 lines) — it calls `get_branch_definition` (Task A territory) and has a `BranchRebindError` class (line 2473) that lives nearby. Move `BranchRebindError` into this module alongside `claim_gate`.

**Approx size:** ~800–900 lines moved out.
**Files:** `tinyassets/storage/goals_gates.py` (new), `tinyassets/daemon_server.py` (reduce), `tinyassets/storage/__init__.py` (re-export stubs).
**Deps:** Task A merged (for `get_branch_definition` import). Task B independent — can run in parallel with B if A is done.
**Effort:** 2–3 days.

---

### Task D — `storage/search.py` (optional fourth extraction)

**What moves:** `search_nodes` (line 3025–3122), `_preview` helper (3123+).

This is a full-text search over branch definitions + goals. It's only ~100 lines but it reaches across multiple tables (`branch_definitions`, `goals`). It could live in `goals_gates.py` temporarily, or get its own module if search is expected to grow.

**Recommendation:** fold into `goals_gates.py` as a co-located search surface for now. Promote to `storage/search.py` when a second search surface exists.

---

## Remaining in `daemon_server.py` after A+B+C+D

After all four extractions, `daemon_server.py` retains:

- `initialize_author_server()` (lines 66–406) — schema CREATE TABLE block + migration logic. This stays until a schema-migration framework (Alembic or equivalent) is adopted, at which point the DDL moves there.
- `ensure_default_author`, `ensure_universe_registered`, `sync_universes_from_filesystem` — universe lifecycle bootstrapping (lines 421–498). These belong in `storage/universes_branches.py` but they call `ensure_default_branch` which calls `create_branch`, creating a circular scoping risk if not moved atomically. Move them in Task A.
- `get_universe`, `ensure_universe_rules`, `get_universe_rules`, `update_universe_rules` (lines 500–613) — universe rules. These belong in Task A's module.
- `_utc_iso_now` (line 2570) — shared utility, move to `storage/_utils.py` or keep in `__init__.py`.
- `grant_universe_access`, `revoke_universe_access`, `list_universe_acl` (3146–3238) — ACL surface. ~90 lines. Belongs in a future `storage/access_control.py` or folds into `universes_branches.py`. Defer until Task A is done.

**Projected end-state of `daemon_server.py`:** DDL block + schema migration only (~350–400 lines). At that point it becomes a candidate for renaming to `daemon_server_schema.py` or folding into `storage/__init__.py`'s migration bootstrap.

---

## Pre-conditions before any extraction dispatches

1. **Pre-commit gate for `author_server` imports** (audit finding #3, Priority 2 in dispatch table) must be in place. Without it, freshly extracted modules will re-acquire the deprecated import within weeks via copy-paste.
2. **`tinyassets/storage/__init__.py` re-export pattern** must be confirmed: existing modules (`accounts`, `rotation`, `caps`) export via `__init__` re-export stubs so callers using `from workflow.daemon_server import X` can be redirected without touching every call site atomically. Task A/B/C dev should follow the same pattern.

---

## Verification signal for each task

Each extraction is done when:
- `pytest tests/` full suite passes (no regressions in anything importing from `daemon_server`)
- `ruff check tinyassets/storage/` clean on the new module
- `tinyassets/daemon_server.py` line count reduced by the expected amount (±10%)
- No new `from workflow.author_server import` lines in the new module

---

## Summary dispatch table

| Task | New file | Blocks | Depends | Effort |
|---|---|---|---|---|
| A | `storage/universes_branches.py` | B, C | Pre-commit gate (#2) | 2–3 days |
| B | `storage/requests_votes.py` | — | A | 2–3 days |
| C | `storage/goals_gates.py` | — | A (B optional) | 2–3 days |
| (D) | fold into C | — | A | in C |

Total: ~6–9 days dev time, independently dispatchable after A merges. No task exceeds 3 days — each is a unit of "move functions + row helpers + table ownership, add re-export stubs, verify suite."

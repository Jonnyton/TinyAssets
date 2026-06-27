# `daemon_server.py` → `tinyassets/storage/` Package Split — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged dev-executable plan. Sequenced as **R7** in `docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md`. Heavier than R2 (bid cluster); establishes the second canonical Module Layout subpackage precedent (`tinyassets/storage/`).
**Depends on R7a (`docs/exec-plans/active/2026-04-19-r7a-phase7-to-catalog.md`)** — frees `tinyassets/storage/` from Phase 7 catalog backend before R7 splits daemon_server into storage/ context modules. Discovered via dev-flagged collision 2026-04-19; resolved with verdict **Option C** (Phase 7 → `tinyassets/catalog/`).
**Scope:** Split `tinyassets/daemon_server.py` (3,575 LOC, ~113 functions/classes, 25 CREATE TABLE statements, 5+ bounded contexts) into `tinyassets/storage/` package modules organized by storage context.
**Effort:** ~2 dev-days. Single contributor. Sequenced after R2 + (post-Q4) so storage-package commit lands as the second canonical Module Layout commit.

---

## 1. Why this is R7, not R5

`daemon_server.py` is the second-largest god-module in the engine (after `universe_server.py` at 9,895 LOC) and the second-most concerning. R5 (universe_server split) is the absolute critical path; R7 is the next natural cleanup target *after* R5 — same contributor headspace, same FastMCP-mount/subpackage discipline, but a smaller blast radius (3 fan-in vs universe_server's 23).

**Why split this one when R2 (bid) was first:** R2 was the smallest possible canonical Module Layout commit, anchoring precedent. R7 is the second commit — bigger, but still scoped to one bounded responsibility (storage layer). After R7 lands, the precedent for "subpackage per bounded context" is fully demonstrated, and R5 (universe_server split) has a proven pattern to lift from.

---

## 2. The five bounded contexts

Reading the 25 CREATE TABLE statements (`daemon_server.py:106-440`) + the function definitions reveals five clean bounded contexts. Each becomes a submodule under `tinyassets/storage/`.

### 2.1 `tinyassets/storage/accounts.py` — accounts + auth + sessions + capabilities

**Schema:**
- `user_accounts` (line 128)
- `user_sessions` (line 139)
- `capability_grants` (line 149)

**Functions:**
- `_account_id_for_username` (line 448)
- `ensure_host_account` (line 481)
- `create_or_update_account` (line 492)
- `get_account` (line 544)
- `list_accounts` (line 574)
- `list_capabilities` (line 594)
- `grant_capabilities` (line 618)
- `create_session` (line 641)
- `resolve_bearer_token` (line 676)
- `actor_has_capability` (line 717)

### 2.2 `tinyassets/storage/universes_branches.py` — universes + branches + snapshots

**Schema:**
- `universes` (line 109)
- `universe_rules` (line 117)
- `branches` (line 195)
- `branch_heads` (line 209)
- `universe_snapshots` (line 216)
- `branch_definitions` (line 310)
- `universe_acl` (line 392)

**Functions:**
- `ensure_universe_registered` (line 723)
- `sync_universes_from_filesystem` (line 762)
- `get_universe` (line 786)
- `ensure_universe_rules` (line 801)
- `get_universe_rules` (line 821)
- `update_universe_rules` (line 841)
- `ensure_default_branch` (line 871)
- `create_branch` (line 901)
- `list_universe_forks` (line 942)
- `get_branch` (line 968)
- `mark_branch_status` (line 984)
- `create_snapshot` (line 998)
- `set_branch_head` (line 1041)
- `get_snapshot` (line 1061)
- `list_snapshots` (line 1074)

### 2.3 `tinyassets/storage/daemons.py` — daemon (author) definitions + forks + runtime instances

**Schema:**
- `author_definitions` (line 159) — note: per author-daemon rename §3, this table renames to `daemon_definitions` in Phase 3 (B1). Until then, keeps current name; the *module* uses `daemons.py` to reflect the target taxonomy.
- `author_forks` (line 170) — same Phase-3 rename pending.
- `author_runtime_instances` (line 181) — same Phase-3 rename pending.

**Functions:**
- `_author_id_for` (line 452)
- `_branch_id_for` (line 458)
- `ensure_default_author` (line 465)
- `register_author` (line 1094)
- `list_authors` (line 1153)
- `get_author` (line 1161)
- `spawn_runtime_instance` (line 1185)
- `retire_runtime_instance` (line 1221)
- `get_runtime_instance` (line 1238)
- `list_runtime_instances` (line 1249)

### 2.4 `tinyassets/storage/requests_votes.py` — user requests + vote windows + ballots + action records

**Schema:**
- `user_requests` (line 227)
- `vote_windows` (line 241)
- `vote_ballots` (line 255)
- `action_records` (line 264)

**Functions:**
- `create_user_request` (line 1265)
- `get_user_request` (line 1301)
- `list_user_requests` (line 1317)
- `list_active_user_ids` (line 1332)
- `create_vote_window` (line 1351)
- `propose_author_fork` (line 1391)
- `cast_vote` (line 1422)
- `resolve_vote_if_due` (line 1456)
- `get_vote` (line 1507)
- `record_action` (line 1554)
- `list_actions` (line 1604)

### 2.5 `tinyassets/storage/notes_work_targets.py` — universe notes + work-targets + hard priorities + unreconciled writes

**Schema:**
- `universe_notes` (line 278)
- `universe_work_targets` (line 294)
- `universe_hard_priorities` (line 302)
- `unreconciled_writes` (line 374)

**Functions:**
- `_notes_json_path` (line 1625)
- `list_note_dicts` (line 1629)
- (… other notes + work-target functions starting around line 1625, full list to enumerate during implementation)

### 2.6 `tinyassets/storage/goals_gates.py` — goals + gate claims + leaderboard reads

**Schema:**
- `goals` (line 341)
- `gate_claims` (line 355)

**Functions:**
- `goal_leaderboard` (line 3102)
- `search_nodes` (line 3311) — *if* this is goal-scoped; otherwise routes to its own module.
- (other goals/gates functions starting around line 1700+; full list during implementation)

---

## 3. Shared concerns kept in `tinyassets/storage/__init__.py`

Three things stay shared across all five context modules:

1. **`_connect()`** (line 95) — single SQLite connection helper with `PRAGMA` setup. Imported by every context module.
2. **`initialize_author_server()`** (line 106) — creates all 25 tables. Stays in `__init__.py` so DB initialization is one entry point per the existing API.
3. **`author_server_db_path()`** (line 83), **`base_path_from_universe()`** (line 87), **`universe_id_from_path()`** (line 91) — small path-resolution helpers used by every context module.

`__init__.py` also re-exports the most-used names from each context module so existing `from workflow.daemon_server import register_author` keeps working through a top-level shim.

---

## 4. Top-level back-compat shim

Mirrors the R2 (bid) pattern + Author→Daemon Phase 1 Part 2.5 pattern.

`tinyassets/daemon_server.py` (NEW shim, replaces the existing god-module):
```python
"""Back-compat shim: workflow.daemon_server re-exports workflow.storage.

The 3,575-LOC god-module split into tinyassets/storage/{accounts,
universes_branches, daemons, requests_votes, notes_work_targets,
goals_gates}.py during R7 of the refactor dispatch sequence (see
docs/exec-plans/active/2026-04-19-storage-package-split.md).

This shim re-exports the public API for one deprecation cycle so
external callers keep working. New code should import from
workflow.storage.<context> directly.
"""

from __future__ import annotations

import warnings

from workflow.storage import (
    # accounts
    actor_has_capability,
    create_or_update_account,
    create_session,
    ensure_host_account,
    get_account,
    grant_capabilities,
    list_accounts,
    list_capabilities,
    resolve_bearer_token,
    # universes_branches
    create_branch,
    create_snapshot,
    ensure_default_branch,
    ensure_universe_registered,
    ensure_universe_rules,
    get_branch,
    get_snapshot,
    get_universe,
    get_universe_rules,
    list_snapshots,
    list_universe_forks,
    mark_branch_status,
    set_branch_head,
    sync_universes_from_filesystem,
    update_universe_rules,
    # daemons
    ensure_default_author,
    get_author,
    get_runtime_instance,
    list_authors,
    list_runtime_instances,
    register_author,
    retire_runtime_instance,
    spawn_runtime_instance,
    # requests_votes
    cast_vote,
    create_user_request,
    create_vote_window,
    get_user_request,
    get_vote,
    list_active_user_ids,
    list_actions,
    list_user_requests,
    propose_author_fork,
    record_action,
    resolve_vote_if_due,
    # notes_work_targets
    list_note_dicts,
    # goals_gates
    goal_leaderboard,
    search_nodes,
    # shared
    author_server_db_path,
    base_path_from_universe,
    initialize_author_server,
    universe_id_from_path,
)

# Surfacing the deprecation warning is gated behind TINYASSETS_DEPRECATIONS
# so noisy CI runs don't trigger every consumer; explicit opt-in for now,
# default-on warning in v0.3.0 release after one cycle.
import os
if os.environ.get("TINYASSETS_DEPRECATIONS", "").lower() in {"1", "true", "yes"}:
    warnings.warn(
        "workflow.daemon_server is a back-compat shim; migrate imports to "
        "workflow.storage.<context>",
        DeprecationWarning,
        stacklevel=2,
    )
```

After one release cycle, this shim deletes (D2-style finalization).

---

## 5. Call-site sweep — 3 import sites in canonical tree (low fan-in)

Per spaghetti-audit hotspot #2 evidence, `daemon_server.py` has only 3 import-fan-in (vs `universe_server.py`'s 23). That's because most callers go through the `workflow.author_server` shim. Three direct sites:

| File | Current import | New import |
|---|---|---|
| `tinyassets/universe_server.py` | (search for `from workflow.daemon_server import …` and `from workflow import daemon_server`) | Migrate each to `from workflow.storage.<context> import …` |
| `tests/test_author_server_api.py` | (similar search) | Same. |
| `fantasy_daemon/__main__.py` | (similar search) | Same. |

**Discipline:** all sweeps go through *new* paths (`workflow.storage.accounts`, etc.). Top-level shim catches *external* callers only — internal callers should never depend on the shim.

**Migration script:** `git grep -l 'from workflow.daemon_server\|tinyassets\.daemon_server' --` + a sed script per call-site. ~30 minutes including manual review of which context to route each call to.

---

## 6. Commit sequence — 6 atomic commits (one per context module + finalize)

### Commit 1 — package scaffolding + shared helpers + initialize_author_server

**Files:** `tinyassets/storage/__init__.py` + mirror. Move `_connect()`, path helpers, `initialize_author_server()`. Top-level shim NOT yet in place.

**Suggested message:**
```
storage: scaffold tinyassets/storage/ package with shared helpers + DB init

R7 commit 1/6 — first scaffolding commit. All schema CREATE TABLE
statements remain in __init__.py for now; context modules added in
follow-up commits.

No behavior change; no call-site updates yet.
```

### Commits 2-6 — one per context module

Each commit moves the functions for one bounded context into `tinyassets/storage/<context>.py`, removes them from `daemon_server.py`, updates `__init__.py` re-exports.

**Commit 2:** `tinyassets/storage/accounts.py` (R7.2)
**Commit 3:** `tinyassets/storage/universes_branches.py` (R7.3)
**Commit 4:** `tinyassets/storage/daemons.py` (R7.4)
**Commit 5:** `tinyassets/storage/requests_votes.py` (R7.5)
**Commit 6:** `tinyassets/storage/notes_work_targets.py` + `tinyassets/storage/goals_gates.py` (R7.6 — bundled because both are smaller)

**After commit 6:** `daemon_server.py` becomes the back-compat shim (per §4). Update the 3 internal call sites (§5) to use new paths.

**Suggested final commit message:**
```
storage: complete tinyassets/storage/ split — daemon_server.py becomes shim

R7 commit 6/6 — final finalization. tinyassets/daemon_server.py is now
a back-compat shim re-exporting workflow.storage.<context> public API
for one deprecation cycle. All 3 internal call sites migrated to new
paths.

Closes spaghetti audit hotspot #2.
Sets tinyassets/storage/ as the second canonical Module Layout
subpackage (after tinyassets/bid/ from R2).
```

**Verification per commit:**
- Full pytest. Touches large surface; expect zero behavior change since splits are pure namespace moves.
- `ruff check` on touched files.
- Mirror byte-equal: each commit touches both canonical + mirror.

---

## 7. Behavior-change check

**Zero behavior change.** All splits are pure namespace moves:
- Function bodies unchanged.
- SQL schema unchanged (`CREATE TABLE`s still in `__init__.py`).
- Module-level state (none — the existing module is stateless function exports).
- `_connect()` continues to be the single sqlite handle factory.

**Exception worth flagging:** if any test does `monkeypatch.setattr("workflow.daemon_server.X", …)` at the *attribute* level (not via the `_rename_compat.py` deep-submodule alias loader), it sets the attribute on the shim, NOT on the canonical `workflow.storage.<context>` module. Same risk as R2 §7 — grep for `monkeypatch.setattr("workflow.daemon_server` and retarget. Likely a small list given how few internal call sites exist.

---

## 8. Sequencing relative to other refactor blocks

| Block | R7 relationship |
|---|---|
| R2 (bid package) | Independent. R7 can ship before, parallel to, or after R2. Recommend R2 first (already pre-staged) for the smallest-cost canonical commit. |
| R4 (layer-3 rename) | Independent. Different files. |
| R5 (universe_server split) | **R5 depends on R7's pattern** but not on R7's specific commit. Recommend R7 lands before R5 starts so R5 has a battle-tested split-pattern to lift from. |
| R6 (engine/domain phase 2) | Depends on R5. Indirectly depends on R7 via R5. |
| R8 (Phase 5) | Independent. Different concern. |
| R9 (NodeScope dedup) | Independent. Calendar-gated. |
| R10 (entry-point discovery) | Independent. |
| R11 (runtime cluster) | Independent file set. |
| R12 (servers package) | **R12 depends on R7** because servers/daemon.py target lives where R7's split lands. Sequencing: R7 → R12. |

**Critical path implication:** R7 is on the critical path to R12 and indirectly to R6. Ship after R2, before R5.

---

## 9. Risk register

- **Risk:** Test suite has ~10-20 imports from `workflow.daemon_server` to update across each commit. **Mitigation:** sweep tests in the same commit that moves the corresponding context module. Verifier full-pytest after each commit catches any miss.
- **Risk:** Author→Daemon rename Phase 3 (B1 in §5 of `docs/exec-plans/active/2026-04-19-author-to-daemon-rename-status.md`) renames `author_definitions` → `daemon_definitions`. R7 commit 4 (`storage/daemons.py`) ships the *module* with the daemon name but the underlying tables retain `author_*` names until Phase 3. **Mitigation:** keep table names as-is in R7; Phase 3 (B1) handles the table rename. The module name `daemons.py` is forward-looking; the SQL inside still references `author_definitions` etc. until B1. Comment this in `daemons.py` so the asymmetry is visible.
- **Risk:** R7's 6-commit sequence creates merge windows where parallel work could collide. **Mitigation:** Run R7 as a single dev-dispatch with all 6 commits back-to-back; treat as one coordinated PR even if technically 6 separate commits.

---

## 10. Summary for dispatcher

- **6 atomic commits, ~2 dev-days total.** One contributor; do not parallelize across devs (single coherent split).
- **Pure namespace moves**, zero semantic change, zero schema change.
- **Sequenced post-R2, pre-R5.** R12 also depends on R7.
- **Establishes `tinyassets/storage/` as the second canonical Module Layout subpackage** (R2 was the first). After R7 lands, refactor pattern is fully demonstrated and R5 (the universe_server giant) has proven precedent.
- **One naming asymmetry to comment** (R7 module = `daemons.py`, SQL tables = `author_definitions` until rename Phase 3 B1).

When host approves Q4 (PLAN.md.draft), R7 dispatches second (after R2 lands) as the second canonical Module Layout commit. Pre-staged here so dispatch is zero-latency.

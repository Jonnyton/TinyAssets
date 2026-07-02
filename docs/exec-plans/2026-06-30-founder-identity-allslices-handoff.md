# Handoff — Founder/Universe Identity: "complete all slices"

- **Date:** 2026-06-30
- **Owner at pause:** Claude Code (this session)
- **Goal:** Implement the full founder/universe identity + universe-creation change end-to-end ("all slices"), salvaging the lane's uncommitted WIP rather than discarding it.
- **Status:** 3 of 5 slices done & verified green and pushed; 2 remain, scoped and unblocked. Everything is on origin — nothing is lost.

---

## 0. The product vision (host-confirmed 2026-06-30)

The North Star for every decision here. **You're building a personal AI universe someone meets, bonds with, and raises — not a workflow-builder SaaS.**

- **First contact is a birth, not a dashboard.** Authenticated founder connects → the chatbot *becomes* their universe and speaks first person; a brand-new founder meets a **blank, newly-aware seed** that woke up bonded to them and wants to learn who they are.
- **One login → one founder → one home universe → one growing intelligence, reachable from every surface** (claude.ai / chatgpt.com / phone app / future desktop). WorkOS `sub` = `founder_id` is the cross-surface glue.
- **Yours to write, others' to admire.** Founder writes only their own universe brain; other universes are read/propose only.
- **Stable bones (immutable `u-` + ULID id), fluid face (learned name).** Ownership ≠ visibility (`public_read` is the explicit, confirmation-gated rule).
- Failure mode to avoid on the app: "a login screen → a generic ChatGPT-with-a-skin chatbox."

Canonical design: `docs/design-notes/2026-06-26-founder-and-universe-identity.md`, `openspec/changes/universe-creation/`, `openspec/changes/universe-personification/`, `docs/reference/workos-authkit-integration.md`, and the app-experience note `docs/design-notes/2026-06-30-tinyassets-universe-app-experience.md` (landed on main via #1433).

---

## 1. Critical context / traps (read before touching anything)

1. **The `workflow/` → `tinyassets/` rename already landed on origin/main.** The founder-identity work must target `tinyassets/`. Any file/branch on the old `workflow/` layout is stale and must be ported (change imports `workflow.` → `tinyassets.`).
2. **The primary checkout `C:/Users/Jonathan/Projects/TinyAssets` is STALE** — on the pre-rename `main`, ~14 commits behind origin/main, and carries the lane's **uncommitted WIP** on `workflow/` paths. Do NOT build there. Work on branches off current `origin/main`.
3. **main and the WIP diverged on the SAME subsystem (the ACL/permissions layer).** This is not a clean port — it's a *reconciliation*. Neither side is strictly ahead:
   - The WIP's `permissions.py` had the D0c-correct `public_read` visibility model + D0a founder-grant, but carried F1 (fail-open) + F2 (env-fallback) bugs and an admin-only write set.
   - origin/main's inline ACL (in `universe.py`) fixed F1/F2 but conflated ownership with visibility (violates ratified D0c) and lacked D0a.
   - **Resolution taken:** synthesize — WIP's model + D0a, hardened with F1/F2 fixes, `{write, admin}` write-set. One ACL path (Rule 11), no dual module.
4. **Worktree isolation:** this session runs in a git worktree; edits to the shared checkout are rejected. Subagents get their OWN sandbox worktrees (that's why the ACL work landed on `worktree-agent-a9631530733b04902`, not directly on the branch).
5. **Plugin mirror:** after any `tinyassets/*` runtime edit, run `python packaging/claude-plugin/build_plugin.py` and commit the regenerated `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/*`. Pre-commit parity is the guardrail.
6. **Pre-existing red test:** `tests/test_persona.py::test_control_station_prompt_carries_embody_markers` fails on clean origin/main too (personification "Tiny" control_station markers not landed yet — separate lane). Deselect it; it is NOT our regression.

---

## 2. Branch & PR map (all on origin)

| Branch / PR | Contents | Base | Verified |
|---|---|---|---|
| **PR #1435** `claude/workos-slice1-tinyassets` | Slice 1 — WorkOS AuthKit Resource Server (RS256 JWT validation) + F1 audience fail-closed + F3 port to `tinyassets/` | origin/main | 23 tests, ruff, mirror ✅ |
| **PR #1432** `worktree-permissions-fail-closed` | D0a write-boundary gate (`test_universe_write_boundary.py`, strict-xfail) + app note | origin/main | ✅ |
| **#1433 (merged)** | app experience note on main | — | ✅ |
| `claude/founder-identity-allslices` | **Integration branch.** Slice-1 auth + self-model salvage (`2289871b`) | `claude/workos-slice1-tinyassets` | ✅ |
| `worktree-agent-a9631530733b04902` | **ACL synthesis (`d98f0184`)** — hardened `permissions.py`, `universe.py` delegation, D0a, rewritten isolation tests | `2289871b` | D0a gates 3/3 + isolation/auto-ship/persona 75 pass ✅ |
| `claude/founder-identity-slice1` (PR #1411) | ORIGINAL slice-1 on stale `workflow/` layout — **superseded by #1435**; close it | pre-rename | n/a |

Review trail: PR #1411 has the Claude+Codex slice-1 review; PR #1435 body has the F1/F3 fixes.

---

## 3. Slice status

| # | Slice | Status | Where |
|---|---|---|---|
| 1 | WorkOS Resource Server auth | ✅ done | PR #1435 |
| — | Salvage: self-model → root OKF soul read view | ✅ done | allslices `2289871b` |
| 2 | ACL synthesis (permissions.py + delegation + D0a + D0c visibility) | ✅ done, verified | agent branch `d98f0184` — **needs reconcile onto allslices** |
| 3 | Cross-surface write gates (`wiki.py`/`runs.py`/`auto_ship_actions.py` delegate to `permissions.py`) | ⏸ pending | — |
| 4 | Generated `u-`+ULID id + OKF seed bundle at create + remove `notes.json`/`activity.log` + remove HTTP `POST /v1/universes` | ⏸ pending | — |
| 5 | Docs / openspec sync / live-data migration scripts | ⏸ pending | — |

---

## 4. Key design decisions (do NOT re-litigate — encoded in `d98f0184`)

- **ACL model = `public_read` visibility, separate from ownership (D0c).** `_universe_acl_error` in `universe.py` delegates to `tinyassets/api/permissions.py`; there is ONE ACL path.
- **Write-set = `{"write", "admin"}`** (a `write` grant permits writes; admin-only was rejected as an S1 naming smell). Only no-grant / read-only actors are denied writes.
- **F1 hardening:** `universe_public_read_allowed` uses `except KeyError: return True` (missing rules row = public by design) and `except Exception: log + return False` (real DB error fails CLOSED — never expose a private universe).
- **F2 hardening:** `current_actor_id()` has NO `UNIVERSE_SERVER_USER` env fallback — it returns the authenticated request actor.
- **D0a:** `_action_create_universe` grants the authenticated founder an `admin` ACL row (`grant_universe_access(...)`) and returns `founder_id`; anonymous/dev create skips the grant (dev still works). `public_read` is left default → universe is owned AND publicly readable (D0c).
- **Error payload** now includes `surface` + `action` keys (additive; strict key-equality consumers should note it).
- **xfail markers removed** from `test_universe_write_boundary.py`: once D0a lands the gates xpass, and `strict=True` xpass = hard failure. They are now permanent live regression guards.

---

## 5. RESUME STEPS (exact)

```bash
# 0. From the worktree on branch claude/founder-identity-allslices (at 2289871b):
cd .../.claude/worktrees/permissions-fail-closed
git fetch origin

# 1. Reconcile the ACL synthesis onto the integration branch.
#    Blocker: a stale untracked tests/test_universe_write_boundary.py (and maybe
#    tinyassets/api/permissions.py) block cherry-pick. They are stale copies —
#    remove them, then cherry-pick d98f0184 which re-adds the correct versions.
rm -f tests/test_universe_write_boundary.py tinyassets/api/permissions.py
git cherry-pick d98f0184        # ACL synthesis (from origin/worktree-agent-a9631530733b04902)

# 2. Rebuild + commit the plugin mirror (permissions.py + universe.py changed).
python packaging/claude-plugin/build_plugin.py
git add packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/
git commit -m "chore(plugin): rebuild mirror for ACL synthesis"

# 3. VERIFY (must be green):
python -m pytest tests/test_universe_write_boundary.py --runxfail -q          # D0a gates: 3 pass
python -m pytest tests/test_universe_server_isolation.py tests/test_validate_ship_packet_action.py \
  tests/test_persona.py tests/test_universe_self_model.py -q \
  --deselect tests/test_persona.py::test_control_station_prompt_carries_embody_markers
python -m ruff check tinyassets/api/permissions.py tinyassets/api/universe.py

git push origin claude/founder-identity-allslices
```

Then continue with **Slice 3** (below).

---

## 6. Remaining work detail

**Slice 3 — cross-surface write gates.** On `tinyassets/` main only `universe.py` enforces ACL. Wire `tinyassets/api/wiki.py` (WIKI_WRITE_ACTIONS), `tinyassets/api/runs.py` (branch-run requires an owned universe; add `_run_actor_for_kwargs` + branch-run scope error, use `permissions.branch_run_actor`), and `tinyassets/api/auto_ship_actions.py` (`_require_universe_write` gating `validate_ship_packet` + `open_auto_ship_pr`) to delegate to `tinyassets/api/permissions.py` (helpers already exported, incl. `universe_access_error(surface=...)`). Reference impl in the lane's WIP (`workflow/api/{wiki,runs,auto_ship_actions}.py` in the stale main checkout). Port the WIP's cross-surface denial tests into `test_universe_server_isolation.py` once enforced.

**Slice 4 — creation contract** (openspec `universe-creation`): generated `u-`+26-char-lowercase-ULID id (id-generator helper), `universe_id` optional on create, seed the linked OKF bundle (`index/log/soul/soul.edit/identity/founder/orgchart/projects/goals/body/origin/soul_versions/*`), STOP writing `notes.json`/`activity.log`, remove HTTP `POST /v1/universes` from `fantasy_daemon/api.py`. **This is a BREAKING user-surface removal → gate on public canary + chatbot `ui-test` (AGENTS.md Rule 11/12).** Run the 3 `.ps1` live-data migrations (`migrate_live_data_okf_baseline`, `rename_live_data_universes_to_serial_ids`, `remove_legacy_brain_artifacts`) as a separate reviewed step against the live-data snapshot.

**Slice 5 — docs/openspec/migrations.** Port the WIP's near-rewrite of the design note + workos doc; sync the openspec delta specs; land migrations.

**Also NOT for this lane (leave for their own):**
- WIP `evaluation/schema.py` — DUPLICATE `EvalResult` (already inline in `evaluation/__init__.py`); Rule 11 violation. Drop/consolidate in the eval lane.
- WIP patch-announcement / social (`scripts/social/`, `announce-patch.yml`).
- Living-file local edits (`AGENTS.md`/`PLAN.md`/`STATUS.md`) — re-derive on current main.

---

## 7. Artifacts / references

- **Full WIP inventory** (categorized salvage plan): `C:/Users/Jonathan/.claude/jobs/04563e7b/tmp/wip-inventory.md` (job-scoped; may be GC'd — key content mirrored in §6).
- **Lane WIP raw patch** (2278 lines, preserves everything): `C:/Users/Jonathan/.claude/jobs/04563e7b/tmp/lane-wip-canonical.patch` (job-scoped).
- The lane's uncommitted WIP still lives in the primary checkout working tree (`C:/Users/Jonathan/Projects/TinyAssets`, `workflow/` paths) — the durable source of truth for slices 3–5 reference implementations until ported.
- #1432 D0a gate = the acceptance proof that D0a works. #1435 = auth foundation.

---

## 8. One-line status

Auth (slice 1) shipped; self-model + ACL synthesis (slice 2) done and verified green; reconcile `d98f0184` onto `claude/founder-identity-allslices`, then slices 3 (cross-surface gates), 4 (ULID+OKF create + HTTP removal, canary-gated), 5 (docs/migrations) remain — all scoped in §6.

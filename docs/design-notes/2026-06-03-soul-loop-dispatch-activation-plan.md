# Soul activation + autonomous-loop dispatch: the last gap to a live user-built loop

**Author:** claude-code (claude-opus-4-8) · **Date:** 2026-06-03
**Status:** build-ready plan — one core-daemon slice + a safe activation runbook.
**Depends on / coordinates with:** PR-139 soul substrate (landed on `main`),
`docs/design-notes/2026-05-28-souled-universe-effect-authority.md`, the in-node
enqueue verb (live as of 2026-06-03, `TINYASSETS_NODE_ENQUEUE_ENABLED=on`).

## Why this exists

The in-node enqueue verb is live and a user-built driver branch
(`backlog-driver-v0`, `cca3c93b632e`) is approved, but a dispatched run of it in
prod does **not** execute — the daemon ignores the submitted branch and runs the
legacy `fantasy_author:universe_cycle_wrapper`. This note records the exact,
design-grounded reason and the minimal path to close it, so the work is
coordinated with the active PR-139 effort rather than hacked in solo.

## What is already DONE (PR-139, landed on `main`)

- **Soul substrate** — `tinyassets/universe_soul.py`: `soul.md` per universe,
  `UniverseSoul` dataclass with `loop_branch_def_id` + `effect_authority` +
  `edit_authority`, versioned via `soul_versions/`. `has_soul` == file presence.
  Writable today: `create_universe(branch_def_id=…)` →
  `ensure_universe_soul(...)`; `set_premise` → `write_universe_soul(...)`.
- **MCP/submit-path soul routing (slice 9)** —
  `tinyassets/api/universe.py::_universe_loop_dispatch`: souled + loop declared →
  runs that branch; souled + no loop → refuses (`universe_loop_not_declared`);
  no soul → legacy fantasy fallback.
- **Effect authority "Gate 0"** — `tinyassets/effectors/authority.py` +
  `github_pr.py`: PR effects resolve against the soul's `effect_authority`;
  DENIED → dry-run, UNDECLARED → legacy env-cap/consent fall-through.

## The ONE remaining gap (critical path)

`fantasy_daemon/__main__.py::_build_unified_graph_builder` hardwires
`branches/universe_cycle.yaml` (the fantasy cycle) and never consults the
universe soul's `loop_branch_def_id`. So the **autonomous daemon loop** (what
the cloud droplet runs) keeps running the fantasy cycle even for a souled
universe. The MCP/submit path honors the soul loop; the autonomous loop does
not. Closing this — have the autonomous loop resolve its branch via
`_universe_loop_dispatch` (the already-landed slice-9 resolver) instead of the
hardwired YAML — is the single code change on the critical path.

Interacting gates to reconcile in the same slice (do not change blindly):
- `_try_dispatcher_pick` (claims an arbitrary `BranchTask` and runs it via
  `execute_branch`, which threads the enqueue context) is gated behind
  `TINYASSETS_DISPATCHER_ENABLED` + `TINYASSETS_UNIFIED_EXECUTION` (the latter is a
  **superseded Phase-D migration flag**, default off — `docs/specs/phase_d_preflight.md`).
- The slice-9 de-default only reaches the MCP path; the autonomous loop builder
  is a separate code path.

## Safety landmines (verified)

1. **Never retrofit a soul onto the live universe.** `set_premise` writes a soul
   with an *empty* `loop_branch_def_id` → `_universe_loop_dispatch` then returns
   `universe_loop_not_declared` and the universe **refuses to run** (it stops
   falling back to the legacy loop the moment a soul exists). Activating without
   atomically declaring the loop breaks that universe.
2. **First proof must keep effects dry-run** — leave `effect_authority` empty so
   the loop runs end-to-end with no real external writes until proven.

## Activation runbook (after the gap-closer lands + is reviewed)

1. Close the autonomous-loop gap (above) as a reviewed slice; keep
   `TINYASSETS_UNIFIED_EXECUTION` handling explicit.
2. `create_universe` a fresh dedicated universe with
   `loop_branch_def_id=cca3c93b632e` and `effect_authority=()` (dry-run).
   Fresh universe avoids landmine #1 (atomic soul+loop) and isolates the legacy
   fantasy universe.
3. Submit/schedule a run → soul-guided dispatch executes the driver → the driver
   enqueues canonical patch-loop runs through the live enqueue verb.
4. Verify end-to-end (driver succeeded, child canonical tasks enqueued at the
   right universe/lineage, effects dry-run). Only then consider granting real
   `effect_authority`.

## Open items to reconcile with the team

- Whether to finish the Phase-D `TINYASSETS_UNIFIED_EXECUTION` flip or leapfrog it
  via soul-declared dispatch (this note assumes the latter is the destination).
- The Tiny / soul-scoped authority model is in
  `2026-05-28-souled-universe-effect-authority.md` + auto-memory but not yet in
  `PLAN.md`; reconcile with the typed authority hierarchy in
  `2026-05-19-external-write-authority-and-rewards.md`.
- Goal `4ff5862cc26d` has many runs, quality 0, no canonical — the loop has
  never produced a real outcome; not a blocker for activation but blocks a
  *useful* loop.

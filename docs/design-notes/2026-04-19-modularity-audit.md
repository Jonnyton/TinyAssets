---
status: research
---

# Modularity Audit

**Date:** 2026-04-19
**Author:** codex
**Status:** Audit note for lead/navigator review. No design truth changes yet.

## 1. Scope and verification

This audit reoriented against:

- `STATUS.md` live state.
- `PLAN.md` sections `Cross-Cutting Principles`, `API And MCP Interface`,
  `Engine And Domains`, and `Distribution And Discoverability`.
- `docs/design-notes/2026-04-18-full-platform-architecture.md`.
- `docs/design-notes/2026-04-17-engine-domain-api-separation.md`.

Verification on 2026-04-19, Windows, repo `.venv`:

- `python -m pytest -q --maxfail=10` → `3099 passed, 1 skipped`
- `python -m ruff check` → clean

## 2. Bugs fixed during this audit

The active regressions were rename-compat bugs, not product logic bugs:

- Old-path deep imports under `domains.fantasy_author.*` were not sharing
  live module state with `domains.fantasy_daemon.*`, so old-path test patches
  missed the real code and commit/extraction calls fell through to live
  providers.
- Old-path package behavior around `fantasy_author` / `domains.fantasy_author`
  was incomplete at the CLI, discovery, and `__main__` surfaces.

The compat layer now:

- forwards old-path module writes back to the canonical target modules;
- supports `python -m fantasy_author`;
- keeps discovery returning the compat alias while the flag is enabled;
- restores old-path phase-module callability at the package surface.

## 3. Spaghetti hotspots

### 3.1 `tinyassets/universe_server.py` is still a mega-surface

Code evidence:

- `tinyassets/universe_server.py:1076` defines `universe()` with a 26-action
  dispatch table at `:1154`.
- `tinyassets/universe_server.py:3644` defines `extensions()` and then routes
  branch actions, run actions, and judgment actions through multiple dispatch
  tables (`:3917-3952`, `_BRANCH_ACTIONS` at `:5883`, `_RUN_ACTIONS` at
  `:6598`, `_JUDGMENT_ACTIONS` at `:7367`).
- The file is currently ~8.6k lines and mixes engine operations, domain-facing
  world queries/canon flows, branch authoring, run control, judging,
  rollback/versioning, goals, gates, and wiki behavior.

Why this is architectural debt:

- It violates the project's own principle that tool shape is architecture.
- The current split is mostly "one file + many action strings" rather than
  "small number of composable surfaces with bounded ownership."
- It makes engine/domain separation harder because domain-specific behavior
  (`query_world`, canon/premise flows) still sits inside the engine mega-file.

Research backing:

- FastMCP officially supports composing servers with `mount()` and describes it
  as a way to organize large applications into modular components:
  [FastMCP server composition](https://gofastmcp.com/v2/servers/server).
- FastAPI documents the same pattern on the HTTP side with `APIRouter` and
  `app.include_router()`, noting router inclusion behaves like one app and the
  cost happens only at startup:
  [FastAPI bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

Recommendation:

- Keep shared wrappers in one engine layer: auth, ledgering, error shaping,
  common serialization.
- Split capability surfaces into mounted/attached modules:
  - engine universe surface
  - extensions/branch authoring surface
  - runs surface
  - judgments surface
  - goals/gates/wiki surfaces
  - domain-mounted servers for fantasy-specific actions
- Treat `tinyassets/universe_server.py` as an integration shell, not the place
  where action logic lives.

### 3.2 `tinyassets/discovery.py` is not a real plugin boundary

Code evidence:

- `tinyassets/discovery.py:29-66` discovers domains by scanning the source tree
  for `domains/*/skill.py`.
- `tinyassets/discovery.py:66` now injects the rename compat alias
  `fantasy_author` directly into discovery results.
- `tinyassets/discovery.py:101+` constructs import paths from directory names and
  relies on naming conventions to find domain classes.

Why this is architectural debt:

- It couples discovery to the checked-out repo layout instead of the installed
  runtime surface.
- It leaks rename-compat policy into plugin discovery.
- It makes packaging/distribution less modular because installed extensions
  outside the source tree are second-class.

Research backing:

- Python's standard library exposes installed plugin discovery through
  `importlib.metadata.entry_points()` and selectable groups:
  [importlib.metadata docs](https://docs.python.org/3/library/importlib.metadata.html).
- PyPA defines entry points as the interoperable mechanism for installed
  distributions to advertise components for discovery and use by other code:
  [PyPA entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/).

Recommendation:

- Move domain discovery to an entry-point group such as `workflow.domains`.
- Keep the current filesystem scan only as a dev-mode fallback for local
  editable worktrees.
- Keep compat aliases out of discovery; compat belongs in import shims, not in
  the domain registry contract.

### 3.3 `tinyassets/daemon_server.py` mixes too many bounded contexts

Code evidence:

- `tinyassets/daemon_server.py:106-392` builds the host database schema inline.
- The same file also implements author/account/session rules, requests/votes,
  notes/work-targets, branch definitions, goals/gate claims, and search/read
  models such as `goal_leaderboard()` (`:3102`) and `search_nodes()` (`:3311`).
- The file is currently ~3.2k lines and acts as schema, repository, service,
  and query layer simultaneously.

Why this is architectural debt:

- Any change in one bounded context forces edits in the same monolith.
- It invites cross-context helper reuse through direct function calls instead of
  explicit service seams.
- It is the storage equivalent of the MCP mega-surface problem.

Recommendation:

- Split by storage context, not by generic CRUD verbs:
  - accounts/auth
  - universes/branches/snapshots
  - requests/votes/runtime capacity
  - notes/work targets/priorities
  - goals/gates/leaderboards
- Keep `_connect()` and migration bootstrap shared, but move context logic into
  separate modules with narrow exported surfaces.

## 4. Suggested next moves for navigator

1. Turn §3.1 into the concrete follow-on to the existing engine/domain note:
   first extract mounted capability servers, then move fantasy-only actions out
   of the engine shell.
2. Write an exec-plan for entry-point-based domain discovery so packaging and
   plugin distribution stop depending on repo layout.
3. Defer the `daemon_server.py` split until the current uptime/rename blockers
   are quieter, but treat it as real debt, not cosmetic cleanup.

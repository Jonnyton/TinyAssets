# Rename Phase 1 Part 2 — Tree Consistency Audit

**Date:** 2026-04-18
**Author:** dev (task dispatched by lead, pre-verifier)
**Status:** Read-only. No code changed. Audit only.
**Baseline HEAD:** `f64e9d0` (after #12 design-note landing). Rename-dirty tree = 115 files as of Phase 1 Part 2 handoff.

## 1. Straggler imports (§1 of lead's ask)

**Goal:** every `.py` in the 64-file `fantasy_daemon/` + `domains/fantasy_daemon/` dirty set has `fantasy_author.*` imports rewritten to `fantasy_daemon.*` and `workflow.author_server` rewritten to `workflow.daemon_server`.

- `grep -rn -E "^\s*(from|import)\s+fantasy_author(\.|$|\s)" fantasy_daemon/ domains/fantasy_daemon/` → **0 hits in tracked code.**
- `grep -rn "tinyassets\.author_server\|from workflow import author_server" fantasy_daemon/ domains/fantasy_daemon/` → **0 hits.**

**Only anomaly:** `fantasy_daemon/work_targets.py.truncated` (untracked, 26 KB, mtime 2026-04-05) contains two stale `from fantasy_author ...` lines. Not in git (`git status` ignores it as untracked), not imported by Python, but a leftover from an aborted edit. **Recommendation:** lead or next session delete it once rename lands — out of scope for dev in the current commit window.

Verdict: **PASS** for tracked files. Untracked leftover flagged but harmless.

## 2. Shim-pattern consistency (§2)

All 4 untracked shim files share the same `TINYASSETS_AUTHOR_RENAME_COMPAT`-gated `sys.modules[__name__] = <target>` rebind pattern:

| Shim | Gate | Rebind target |
|---|---|---|
| `fantasy_author/__init__.py` | `rename_compat_enabled()` | `fantasy_daemon` |
| `domains/fantasy_author/__init__.py` | `rename_compat_enabled()` | `domains.fantasy_daemon` |
| `tinyassets/author_server.py` | `rename_compat_enabled()` | `workflow.daemon_server` |
| `packaging/.../tinyassets/author_server.py` | `rename_compat_enabled()` | `workflow.daemon_server` |

All four emit `DeprecationWarning` with the same migrate-to message. All import `workflow._rename_compat.rename_compat_enabled`.

`packaging/.../tinyassets/_rename_compat.py` **exists** in the mirror and is **byte-identical** to `tinyassets/_rename_compat.py` — the plugin shim will load correctly on a fresh install.

Verdict: **PASS.**

## 3. `fantasy_daemon/author_server.py` position (§3)

Current content (2 lines):

```python
"""Shim: use workflow.daemon_server instead."""
from workflow.daemon_server import *  # noqa: F401,F403
```

This is a **star-import snapshot re-export**, not a sys.modules rebind. Module-level state (globals, caches, registered callbacks) written via `fantasy_daemon.author_server.X = ...` will NOT be visible at `workflow.daemon_server.X`, and vice versa. The other 4 shims all use the rebind pattern, which DOES share state.

**Position:** switch to `sys.modules[__name__] = workflow.daemon_server` for consistency. The snapshot pattern was safe pre-rename when `fantasy_daemon/author_server.py` was the authoritative module and `workflow.author_server` was the alias; post-rename the authority inverted, and the snapshot is now the divergent surface.

**Risk of keeping snapshot:** cross-alias test (e.g., `fantasy_daemon.author_server.record_action` vs `workflow.daemon_server.record_action` called in the same test) would see different ledger state. No such test surfaced in smoke per prior dev's handoff, but the full suite hasn't been run end-to-end yet (that's verifier's task #1).

**Not changed this audit** — lead explicitly asked for position-only.

## 4. Packaging-mirror spot-check (§4)

Byte-equality via `diff -q` between `tinyassets/<path>` and `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/<path>`:

| File | Result |
|---|---|
| `daemon_server.py` | identical |
| `desktop/launcher.py` | identical |
| `ingestion/core.py` | identical |
| `ingestion/extractors.py` | identical |
| `knowledge/models.py` | identical |
| `retrieval/router.py` | identical |
| `_rename_compat.py` | identical |

All 7 spot-checked files byte-equal. Auto-build pipeline (`packaging/claude-plugin/build_plugin.py`) is doing its job.

**Brand-residue flag (per lead's ask for future work beyond #8):** the plugin directory is still `tinyassets-universe-server/` — legacy brand. Rename to `workflow-server/` or similar belongs in a future task that touches the claude-plugin manifest + `build_plugin.py`'s `PLUGIN_ROOT` constant. Not task #8 (which is only the tray + bat renames at repo root).

## 5. Summary + recommendations

- **PASS:** tracked tree has zero straggler imports; shim pattern consistent; packaging mirror byte-equal where sampled.
- **POSITION (no change):** `fantasy_daemon/author_server.py` snapshot re-export is inconsistent with the other 4 shims. Recommend switching to sys.modules rebind — trivial diff, same flag gate.
- **CLEANUP (out of scope):** untracked `fantasy_daemon/work_targets.py.truncated` should be deleted post-rename.
- **FUTURE BRAND SWEEP:** `packaging/claude-plugin/plugins/tinyassets-universe-server/` directory name still carries the legacy brand. Not blocking task #2.

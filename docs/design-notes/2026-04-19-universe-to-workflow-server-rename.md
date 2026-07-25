---
status: superseded
superseded_by: docs/exec-plans/completed/2026-04-19-author-to-daemon-rename-status.md
status_detail: Layer-3 rename obsoleted by universe_server.py decomposition arc 2026-04-26+
---

# Universe Server → Workflow Server: Layer-3 Rename Scoping

**Date:** 2026-04-19
**Author:** navigator
**Successor to:** STATUS.md task #24 (layer-2, display-string rebrand, in-flight) and STATUS.md task #25 (file rename `universe_*` → `workflow_*` for tray + bat).
**Status:** Design proposal — not implementation. Awaiting host approval before dispatch.
**Related notes:** `docs/audits/2026-04-18-rename-tree-consistency-audit.md` (flagged this dir name as future brand sweep), `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` (precedent: `_rename_compat.py` aliasing pattern).

---

## 1. Is this worth doing?

**Yes, but it is the *third* layer of a single brand sweep — not a fresh project.** Layers 1 and 2 already shipped or are in-flight:

- Layer 1 (already landed) — desktop shortcut + `start-workflow-server.bat` + tray rebrand strings.
- Layer 2 (task #24, in_progress) — display strings: manifest `display_name`, MCP `serverInfo`, OAuth consent copy, packaging README/docstrings.
- **Layer 3 (this note)** — the *machine* surfaces: the Python module path (`workflow/universe_server.py`), the env-var prefix (`UNIVERSE_SERVER_*`), and the plugin directory (`packaging/claude-plugin/plugins/workflow-universe-server/`).

Layer 3 is the only layer that user-visibly carries the "Universe Server" brand once Layer 2 lands — specifically through the env-var prefix that hosts type when configuring the plugin and the plugin directory name they see in their `~/.claude/plugins/` tree. Leaving Layer 3 undone means the rebrand is half-done in exactly the surfaces an OSS contributor or daemon-host would see when they unpack the plugin or read the env block.

**Cost.** Smaller than the Author→Daemon rename (one module, one env-var family, one plugin dir vs ~2366 file footprint). Moderate test-suite churn (~48 test files import `workflow.universe_server`). Compat shim pattern is already proven by `workflow/_rename_compat.py`.

**Verdict.** Worth doing, but should be sequenced *after* Layer 2 lands and *after* the Author→Daemon rename Phase 1 lands (STATUS #3) — to avoid two large rename windows colliding in test suite + packaging mirror.

---

## 2. Three sub-renames, three different blast radiuses

### 2a. Env-var prefix: `UNIVERSE_SERVER_*` → `WORKFLOW_SERVER_*`

**Surface.** Eight distinct variables in active use:

| Variable | Purpose | Read sites |
|---|---|---|
| `UNIVERSE_SERVER_BASE` | Root output directory | `workflow/universe_server.py:112,525`, `workflow/auth/provider.py:192`, `workflow/node_eval.py:160`, `fantasy_daemon/__main__.py:2137`, `packaging/.../runtime/server.py:16-33`, `packaging/.../plugin.json:38` |
| `UNIVERSE_SERVER_DEFAULT_UNIVERSE` | Default universe ID | `workflow/universe_server.py:127`, `plugin.json:39` |
| `UNIVERSE_SERVER_USER` | Actor identity slug | `workflow/identity.py:44`, `workflow/universe_server.py:258,1696,2319,2555,2680,3956`, `workflow/git_bridge.py:242` |
| `UNIVERSE_SERVER_HOST_USER` | Host identity for tier-routing | `workflow/auth/provider.py:287`, `workflow/universe_server.py:1697,2320,2556,9759` |
| `UNIVERSE_SERVER_AUTH` | Auth mode selector | `workflow/auth/provider.py:467`, `workflow/auth/__init__.py:15` |
| `UNIVERSE_SERVER_URL` | Wellknown base URL override | `workflow/auth/wellknown.py:31` |
| `UNIVERSE_SERVER_PORT` | HTTP port | `workflow/auth/wellknown.py:32` |
| `UNIVERSE_SERVER_BASE` (also referenced by tests under tmp_path) | — | many tests |

**Compat shim pattern (recommended).** A small helper that reads new prefix first, falls back to old prefix, emits a `DeprecationWarning` (once per variable per process) when only the old is set. Centralized in `workflow/config.py` or a tiny new module `workflow/env_compat.py`:

```python
def get_workflow_env(name: str, default: str = "") -> str:
    """Read WORKFLOW_SERVER_<name>; fall back to UNIVERSE_SERVER_<name>."""
    new_key = f"WORKFLOW_SERVER_{name}"
    old_key = f"UNIVERSE_SERVER_{name}"
    if new_key in os.environ:
        return os.environ[new_key]
    if old_key in os.environ:
        _warn_once(f"{old_key} is deprecated; use {new_key}")
        return os.environ[old_key]
    return default
```

All current `os.environ.get("UNIVERSE_SERVER_X", default)` call sites migrate to `get_workflow_env("X", default)`. This is a mechanical sweep — not behavior change. Compat helper stays live for one release cycle, then deletes.

**Why a helper, not raw `os.environ.setdefault`.** `setdefault` doesn't surface a deprecation signal; users keep the old name forever. The helper makes the deprecation visible in stderr/logs without breaking workflows.

**Plugin manifest.** `plugin.json` env block updates to the new prefix. We do NOT keep both — the manifest is the spec the user configures via the plugin UI; old field names should disappear from configuration surface.

**Tests.** Tests that monkeypatch the env vars must update — preferred approach is to monkeypatch the *new* name and rely on the compat helper for one-cycle safety. Audit: ~10–15 test files monkeypatch these.

### 2b. Module rename: `workflow/universe_server.py` → `workflow/workflow_server.py`

**Surface.** ~48 test files import `workflow.universe_server`. Plus the alias shim at `fantasy_daemon/universe_server.py`. Plus `tests/test_packaging_build.py` which inspects the staged bundle for `workflow/universe_server.py` paths.

**Avoiding a name collision.** "workflow.workflow_server" is a slight but acceptable nesting. Alternatives considered:
- `workflow/server.py` — clean, but collides semantically with the existing `packaging/.../runtime/server.py` (the bootstrap stub). Recommend not.
- `workflow/mcp_server.py` — there is **already** a `workflow/mcp_server.py` in the runtime mirror tree. Confirm in canonical tree before choosing this path; if it exists, this name is taken.
- `workflow/workflow_server.py` — slightly redundant but unambiguous and matches the user-facing brand "Workflow Server" exactly. **Recommended.**

The host should pick from these three; navigator's recommendation is `workflow/workflow_server.py` for matching the user-facing brand 1:1.

**Compat shim pattern.** Use the existing `workflow/_rename_compat.py` infrastructure. It already supports deep-submodule alias preservation (built for Author→Daemon). Add one line to register `workflow.universe_server → workflow.workflow_server`. Test suite can import either path during the transition cycle.

**Migration path:**
1. Copy/rename file to new path.
2. Add compat alias in `_rename_compat.py` initialization (gated by the same `WORKFLOW_AUTHOR_RENAME_COMPAT`-style flag, OR a parallel `WORKFLOW_SERVER_RENAME_COMPAT` flag if we want independent flip cadence).
3. Update *internal* call sites that import (currently 0 in `workflow/`, all live in `tests/` and `fantasy_daemon/`).
4. Update test files in a single sweep.
5. Deprecate alias one cycle later.

**Independent flag recommended.** Author→Daemon rename has its own flip clock (Phase 5 not yet); the universe→workflow rename should not be tied to that timeline. Two flags, two clocks.

### 2c. Plugin directory: `packaging/claude-plugin/plugins/workflow-universe-server/` → `packaging/claude-plugin/plugins/workflow-server/`

**Surface.**
- The directory itself.
- `packaging/claude-plugin/build_plugin.py` `PLUGIN_ROOT` constant (per the audit note flag).
- `plugin.json` `"name"` field (`"workflow-universe-server"` → `"workflow-server"`).
- `plugin.json` `mcpServers` key name (`"workflow-universe-server"` → `"workflow-server"`).
- Any docs that reference the path (`docs/mcpb_packaging.md`, `IMPORT_COMPATIBILITY.md`).
- `pyproject.toml` entry point `workflow-universe-server` (per `IMPORT_COMPATIBILITY.md:126`).

**Migration path (one-release compat):**

For installed users, the plugin name is what Claude.ai stores in their plugin registry. Renaming the directory is fine for fresh installs but **breaks existing installs** because the plugin appears uninstalled and reinstalls under the new name. Two options:

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| **A. Hard cutover** | Just rename. Existing users see "plugin uninstalled," reinstall under new name. | Cleanest end state. | One-time UX hiccup for current installs. |
| **B. Symlink/copy bridge** | Ship both directories for one release; old one is a thin pointer (or a duplicate manifest with `"deprecated": true`). | Zero-friction for existing installs. | Plugin registry may not deduplicate; users could see two plugins listed. |

**Recommendation: Option A (hard cutover) with a release-note callout.** Current install base is small (host + minimal early daemon-hosts per memory `project_distribution_horizon.md`). One-time reinstall friction is cheaper than maintaining a parallel-name bridge that may itself surface as a duplicate-plugin bug in the Claude.ai UI. Document in release notes that v0.2.0 reinstall is required.

If install base grows beyond ~10 hosts before this lands, revisit Option B.

The MCP server *key name* inside `mcpServers` is the connection name Claude.ai uses; renaming changes the connection identifier. Same hard-cutover logic applies.

**Entry point.** `pyproject.toml`'s `workflow-universe-server` console script gets renamed to `workflow-server`. Old entry point can stay as a deprecated alias for one cycle (similar pattern to env-vars) by registering both in `pyproject.toml`.

---

## 3. Test, build, and packaging-mirror considerations

- **Test sweep.** Plan a single batch update of all 48 test imports — one PR, mechanical change. Don't trickle.
- **Packaging mirror byte-equality.** The audit at `docs/audits/2026-04-18-rename-tree-consistency-audit.md` documents that the canonical `workflow/` tree and the plugin-runtime mirror must be byte-identical. Module rename in canonical tree must immediately propagate via `scripts/sync-skills.ps1` (or its build-plugin equivalent) to the mirror tree. Verifier should run the rename-tree-consistency check after.
- **`packaging/dist/workflow-universe-server-src/`.** Stale — last built before rename. Will be regenerated under the new name on next packaging pass; no manual action.

---

## 4. Sequencing and dependencies

```
Layer 2 lands (task #24)              ← in_progress today
    ↓
Author→Daemon Phase 1 lands (task #3) ← merge first; settle test churn
    ↓
Layer 3a (env-var compat helper + sweep)
    ↓
Layer 3b (module rename + alias) — parallel-safe with 3a
    ↓
Layer 3c (plugin dir rename)         ← last; ships with v0.2.0 release notes
    ↓
(one release cycle of compat warnings)
    ↓
Compat helpers + aliases deleted
```

**Why this order.** 3a + 3b can land in either order or in parallel (different files). 3c is the most user-visible change — it lands *last* so it ships in a single coordinated release alongside the v0.2.0 brand cutover, with release notes calling out the reinstall.

---

## 5. Open questions for the host

1. **Module name pick.** Confirm `workflow/workflow_server.py` vs `workflow/server.py` vs other. Navigator recommends `workflow_server.py`.
2. **Env-var compat helper home.** Add to existing `workflow/config.py`, or new `workflow/env_compat.py`? Navigator leans `config.py` (one less file).
3. **Compat flag scheme.** Single shared `WORKFLOW_RENAME_COMPAT` flag controlling both Author→Daemon and Universe→Workflow shims, OR two independent flags? Navigator recommends two — independent flip cadence.
4. **Plugin dir migration option (A vs B).** Hard cutover OR parallel-name bridge? Navigator recommends A.
5. **Sequencing relative to STATUS #3 Author→Daemon Phase 1.** Strict serial (recommended), or accept the merge churn risk and parallelize?

---

## 6. Task decomposition (proposed STATUS.md additions, succeeding #25)

For host approval. Each task is independently claimable once its `Depends` are `done`.

| Task | Files (collision boundary) | Depends | Status | Notes |
|------|----------------------------|---------|--------|-------|
| **#26 Layer-3a env-var compat** | `workflow/config.py` (or new `workflow/env_compat.py`); migrate all `os.environ.get("UNIVERSE_SERVER_*", ...)` call sites in `workflow/**/*.py` to the helper | #24 | pending | Compat helper + mechanical call-site sweep. Tests still pass with old env names; deprecation warning surfaces. |
| **#27 Layer-3a env-var manifest cutover** | `packaging/claude-plugin/plugins/workflow-universe-server/.claude-plugin/plugin.json` env block; affected docs | #26 | pending | Switch the *configuration surface* to the new prefix. Old prefix still works for one cycle via #26's helper. |
| **#28 Layer-3b module rename + alias** | `workflow/universe_server.py` → `workflow/workflow_server.py`; `workflow/_rename_compat.py` (register alias); `fantasy_daemon/universe_server.py` shim retarget; `tests/test_packaging_build.py` path constants | #3 (Author→Daemon Phase 1) | pending | Add alias entry to `_rename_compat.py`. Both import paths resolve to the same module object. |
| **#29 Layer-3b test import sweep** | `tests/test_*.py` (all ~48 files importing `workflow.universe_server`) | #28 | pending | Mechanical sweep. Single PR. |
| **#30 Layer-3c plugin dir rename** | `packaging/claude-plugin/plugins/workflow-universe-server/` → `.../workflow-server/`; `packaging/claude-plugin/build_plugin.py` `PLUGIN_ROOT`; `plugin.json` `name` + `mcpServers` key; `pyproject.toml` entry point; `docs/mcpb_packaging.md`, `IMPORT_COMPATIBILITY.md` | #27, #28 | pending | Hard cutover. Ships with v0.2.0 release notes calling out reinstall. |
| **#31 Compat retirement** | Delete `WORKFLOW_SERVER_RENAME_COMPAT` shim entries; remove env-var fallback; remove module alias entry | #30 + one release cycle | pending | Clock starts when #30 lands. |

---

## 7. Risk register

- **Risk:** Test suite breakage during #29 sweep if alias isn't actually working. **Mitigation:** add explicit pytest at `tests/test_rename_compat.py` (extend existing if present) that asserts both `import workflow.universe_server` and `import workflow.workflow_server` resolve to the same module object before the sweep starts.
- **Risk:** Existing daemon hosts wake up after #30 and find their plugin "uninstalled." **Mitigation:** release-note callout + a one-line migration script `scripts/migrate_to_workflow_server_plugin.py` that copies their `~/.claude/plugins/workflow-universe-server/config.json` → `~/.claude/plugins/workflow-server/config.json`.
- **Risk:** Two rename clocks (Author→Daemon + Universe→Workflow) confuse a future reader. **Mitigation:** distinct env-var flags + clear comments in `_rename_compat.py` documenting which alias belongs to which sweep.
- **Risk:** `UNIVERSE_SERVER_BASE` is referenced in user-written `output/` configs. **Mitigation:** the compat helper handles silently. Document the deprecation in user-facing docs but no breaking change.

---

## 8. What this note does NOT decide

- Whether to ship 3a/3b/3c as one bundled v0.2.0 or three patch releases. (Recommend bundled v0.2.0.)
- Final names of compat env-var flag(s).
- Whether the migration script in §7 is in-scope for #30 or a follow-up.

These come back after host §5 answers.

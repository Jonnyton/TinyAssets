# Domain Discovery via `importlib.metadata` Entry Points — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged plan — not implementation. Sequenced as R10 in `docs/exec-plans/completed/2026-04-19-refactor-dispatch-sequence.md`. Closes the residual exec-plan ask from codex's `docs/design-notes/2026-04-19-modularity-audit.md` §4 #2 and the navigator's spaghetti-audit hotspot #6.
**Gating:** Depends on R8 (Author→Daemon Phase 5 — shim deletion + flag flip), so the alias-injection branch in `discovery.py:65-66` can disappear simultaneously.
**Effort:** ~1 dev-day (single contributor; no parallelism opportunity).

---

## 1. Why this is needed

`tinyassets/discovery.py` currently scans the source tree at runtime: walks `domains/*/skill.py`, builds import paths from directory names, and rebinds rename-compat aliases inline. Three concrete problems flow from this shape:

1. **Couples discovery to checked-out repo layout.** Installed extensions outside the source tree are second-class — there is no path for `pip install workflow-research-domain` to register itself with the engine without dropping files into the source `domains/` directory.
2. **Leaks rename-compat policy into plugin discovery.** Lines 65-66 inject `fantasy_author` into discovery results when `TINYASSETS_AUTHOR_RENAME_COMPAT` is on. This entangles two unrelated concerns: import-path back-compat and domain-registry contract.
3. **Encodes a heuristic class-name lookup.** `auto_register()` at `discovery.py:99-130` tries `FantasyAuthorDomain`, `ResearchProbeDomain`, then iterates `dir(module)` looking for a class ending in `"Domain"`. This works today (2 domains, hand-coded names) but doesn't scale to third-party domains that pick their own class names.

Per PyPA's entry-points specification ([packaging.python.org](https://packaging.python.org/en/latest/specifications/entry-points/)) and Python's standard library [`importlib.metadata.entry_points()`](https://docs.python.org/3/library/importlib.metadata.html), the canonical mechanism for installed distributions to advertise components is an entry-point group. Each domain declares itself in its own `pyproject.toml`; the engine reads the group at startup. No filesystem scan, no class-name heuristic, no compat injection.

---

## 2. Target shape

### 2.1 Entry-point group declaration

Define one entry-point group: `workflow.domains`. Each domain's `pyproject.toml` declares a single entry point whose key is the domain slug and whose value is a fully-qualified path to the domain class.

For the in-tree fantasy domain, this lives in the engine's `pyproject.toml` at `[project.entry-points."workflow.domains"]`:

```toml
[project.entry-points."workflow.domains"]
fantasy_daemon = "domains.fantasy_daemon.skill:FantasyDaemonDomain"
research_probe = "domains.research_probe.skill:ResearchProbeDomain"
```

Future external domains declare the same group in their own pyprojects:

```toml
# In a hypothetical workflow-research-domain package:
[project.entry-points."workflow.domains"]
research_paper = "research_domain.skill:ResearchPaperDomain"
```

Once the package is installed (`pip install workflow-research-domain`), the entry point is discoverable via `importlib.metadata.entry_points(group="workflow.domains")` — no source-tree presence required.

### 2.2 New `discovery.py` shape (target)

```python
from __future__ import annotations

import logging
import os
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DOMAINS_GROUP = "workflow.domains"
_DEV_FALLBACK_FLAG = "TINYASSETS_DISCOVERY_DEV_FALLBACK"


def discover_domains() -> list[str]:
    """Discover installed domain slugs via entry-point group ``workflow.domains``.

    Falls back to a filesystem scan only when TINYASSETS_DISCOVERY_DEV_FALLBACK
    is set (default off in production; on in editable-install dev workflows
    where pyproject re-discovery is cumbersome).
    """
    eps = entry_points(group=_DOMAINS_GROUP)
    discovered = sorted({ep.name for ep in eps})

    if discovered:
        return discovered

    # Dev fallback only when explicitly requested.
    if os.environ.get(_DEV_FALLBACK_FLAG, "").lower() in {"1", "true", "yes"}:
        return _filesystem_scan_fallback()

    return []


def auto_register(registry: Any) -> None:
    """Load and register every domain advertised in ``workflow.domains``."""
    eps = entry_points(group=_DOMAINS_GROUP)
    for ep in eps:
        try:
            domain_class = ep.load()
            registry.register(domain_class())
            logger.info("Registered domain %s from entry point %s", ep.name, ep.value)
        except Exception:
            logger.warning("Failed to register domain entry point %s", ep.name, exc_info=True)


def _filesystem_scan_fallback() -> list[str]:
    """Legacy filesystem scan — ONLY used when dev fallback flag is set.

    Kept for editable installs where re-running `pip install -e .` after every
    domain rename is cumbersome. Production discovery uses entry points only.
    """
    workflow_dir = Path(__file__).parent.parent
    domains_dir = workflow_dir / "domains"
    if not domains_dir.exists():
        return []
    return sorted(
        p.name
        for p in domains_dir.iterdir()
        if p.is_dir() and (p / "skill.py").exists()
    )


__all__ = ["discover_domains", "auto_register"]
```

**Key shape changes from current:**
- Entry-point group is the canonical source.
- Filesystem scan is a fallback gated by an explicit env var (off by default).
- No class-name heuristic — the entry-point value is a fully-qualified `module:Class` path.
- No rename-compat alias injection — rename-compat lives in import shims (`tinyassets/_rename_compat.py`), not in discovery contract.

### 2.3 Migration of in-tree domains

Each in-tree domain (`domains/fantasy_daemon/`, `domains/research_probe/`) declares its entry point in the engine's `pyproject.toml`. No per-domain `pyproject.toml` is required — they're sub-packages of the engine, not separately distributed.

When a domain becomes a separately distributed package later (e.g., `domains/research_probe/` extracted to `workflow-research-probe`), it carries its own `pyproject.toml` with its own entry-point declaration. The engine doesn't change.

---

## 3. Migration path (3 atomic commits)

### Commit 1 — Add entry-point declaration

**Files:** `pyproject.toml` (engine root).

**Change:** Add `[project.entry-points."workflow.domains"]` section with two entries (`fantasy_daemon`, `research_probe`).

**Verification:** `pip install -e .` re-installs the engine in editable mode; `python -c "from importlib.metadata import entry_points; print(list(entry_points(group='workflow.domains')))"` prints both entry points.

**Suggested commit message:**
```
packaging: declare workflow.domains entry-point group for fantasy_daemon + research_probe

Pre-stages the discovery rewrite at R10 of the refactor dispatch sequence.
discover_domains() will switch to importlib.metadata.entry_points() reads
in a follow-up commit; this commit only adds the declarations so the new
discovery code can find them.

No behavior change — discovery.py still uses filesystem scan today.
```

### Commit 2 — Switch `discovery.py` to entry-point reads + add dev-fallback gate

**Files:** `tinyassets/discovery.py`, `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/discovery.py` (mirror).

**Change:** Replace `discover_domains()` body with the §2.2 shape. `auto_register()` switches to `ep.load()`. `_filesystem_scan_fallback()` keeps the prior filesystem-scan behavior, gated on `TINYASSETS_DISCOVERY_DEV_FALLBACK`.

**Behavior change:** Production discovery now reads entry points first; falls back to filesystem only when explicitly opted in. **The `fantasy_author` rename-compat alias injection is removed.** The alias still works for *imports* (via `_rename_compat.py`'s deep-submodule meta-path finder), but no longer appears in `discover_domains()` results. Tests that assert `"fantasy_author" in discover_domains()` need update.

**Verification:** Full pytest suite. Specifically: `tests/test_discovery.py` (or equivalent — verify post-edit). Cross-alias module access (`import fantasy_author` → resolves to `fantasy_daemon`) is the import-shim's job and continues to work.

**Suggested commit message:**
```
discovery: switch to importlib.metadata entry-point group "workflow.domains"

Production reads entry points first; filesystem scan kept as opt-in dev
fallback (TINYASSETS_DISCOVERY_DEV_FALLBACK env). Removes rename-compat alias
injection from discover_domains() — alias remains active at the import-shim
layer (tinyassets/_rename_compat.py), not the discovery contract.

R10 of docs/exec-plans/completed/2026-04-19-refactor-dispatch-sequence.md.
Closes docs/design-notes/2026-04-19-modularity-audit.md §4 ask #2.
```

### Commit 3 — Test cleanup + docs

**Files:** `tests/test_discovery.py` (and any other tests that asserted on filesystem-scan or alias-injection behavior); `docs/design-notes/2026-04-19-modularity-audit.md` (mark §3.2 as resolved); `PLAN.md` (update Distribution section's "discovery via entry points" principle if PLAN.md.draft hasn't already replaced the canonical PLAN.md).

**Suggested commit message:**
```
discovery: test suite + docs reflect entry-point-based discovery

- Tests assert entry-point reads as canonical; dev-fallback covered with
  explicit env-var fixture.
- Cross-alias import shim has its own coverage (unchanged).
- modularity-audit §3.2 marked resolved.
```

---

## 4. Behavior-change check — what this breaks (deliberately)

### 4.1 Cross-alias discovery surface

**Before:** `discover_domains()` returns `["fantasy_author", "fantasy_daemon", "research_probe"]` when the rename-compat flag is on.

**After:** `discover_domains()` returns `["fantasy_daemon", "research_probe"]` (no `fantasy_author`).

**Consequence:** Code that *iterates* discovered domains and treats `fantasy_author` as a distinct domain breaks. Code that *imports* from `fantasy_author` continues to work via the import shim.

**Is this load-bearing?** Audit: grep for code that asserts or branches on `"fantasy_author"` appearing in `discover_domains()` output. Expected count: low single digits (test fixtures + maybe one or two consumer sites). Each gets a one-line update — either drop the alias-presence assertion, or migrate to assert `"fantasy_daemon"` (the canonical name).

### 4.2 Editable-install dev workflows

**Before:** Drop a new `domains/<name>/skill.py` and discovery picks it up immediately.

**After:** Drop the file *and* set `TINYASSETS_DISCOVERY_DEV_FALLBACK=1` to use filesystem scan, OR add the entry point to `pyproject.toml` and re-run `pip install -e .`.

**Consequence:** Dev-mode friction increases by one step for new-domain creation. The fallback flag mitigates this for in-progress experimentation; the proper path (entry-point declaration) is required before the domain ships.

**Mitigation:** Document the `TINYASSETS_DISCOVERY_DEV_FALLBACK` flag in CONTRIBUTING.md / domain-author docs. One-line addition.

### 4.3 No production behavior change for first-class domains

`fantasy_daemon` and `research_probe` continue to discover, register, and run identically. The change is in *how* discovery finds them, not *whether*.

---

## 5. Risk register

- **Risk:** A test asserts on the rename-compat alias appearing in discovery output. **Mitigation:** Commit 3 sweeps tests; expected impact ≤5 tests.
- **Risk:** Editable-install dev workflows break for contributors who don't see the new flag. **Mitigation:** docs update + the fallback flag itself; new contributors hit the flag in the first session and don't re-encounter.
- **Risk:** A future packaged extension declares the wrong entry-point group name. **Mitigation:** name `workflow.domains` is short + memorable; document it in domain-author docs; runtime warning if `entry_points(group="workflow.domain")` (singular) is mistakenly tried.
- **Risk:** Entry-point loading at startup is slower than a directory scan. **Mitigation:** `importlib.metadata` caches entry-point reads; for two domains this is microseconds. Will not measure pre-launch.

---

## 6. Sequencing relative to other refactor blocks

- **R8 (Author→Daemon Phase 5)** must land first. After R8, the rename-compat alias becomes an import-time concern only (no domain-registry consequences), so `discover_domains()` is free to drop the alias-injection without behavior surprise.
- **R10 is parallel-safe with R11 (runtime cluster)** and **R12 (servers package)** — no file overlap.
- **R10 depends on Q4 approval** (Module Layout commitment) for the architectural justification, but the migration code itself is small enough to ship even under a "PLAN.md unchanged" outcome — entry-point discovery is a generally-good-practice change that doesn't require a Module Layout commitment.

---

## 7. Open follow-ups (not in scope here)

- **`packaging/dist/tinyassets-universe-server-src/tinyassets/discovery.py`** is stale dist-staging output; will regenerate on next packaging build. No action needed.
- **Domain-author docs** for the entry-point pattern. Recommend a short `docs/domains/authoring.md` page after R10 lands; ~30 min to draft. Not in this exec-plan; flag for follow-up.
- **Test-domain entry point** for in-test fixture domains (the test suite spins up ad-hoc domains for plugin contract tests). Currently uses programmatic `registry.register()` calls; would benefit from a `workflow.domains.test` group convention. Defer.

---

## 8. Summary for dispatcher

- 3 atomic commits, ~1 dev-day total (Commit 2 is the heavy one — touches discovery + tests).
- One deliberate behavior change (alias drops out of `discover_domains()` output); ~5 test-fixture updates expected.
- Production runtime: zero impact for the two in-tree domains.
- Editable-install dev: documented one-flag workaround.
- Sequenced as R10 — gated on R8 (Phase 5), parallel-safe with R11/R12.

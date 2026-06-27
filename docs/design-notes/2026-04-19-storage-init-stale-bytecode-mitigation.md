---
status: shipped
shipped_date: 2026-04-19
shipped_in: 052985a (Option A — lazy __getattr__ co-shipped with R7), 0bad5b4 (Option B — import-graph smoke + pre-commit + tier-3 GHA)
status_detail: Options A + B shipped per §4 recommendation; C and D explicitly deferred in the doc and remain so.
---

# `tinyassets/storage/__init__.py` — Stale-Bytecode Mitigation Scoping

**Date:** 2026-04-19 (post-P0)
**Author:** dev
**Status:** Scoping only. No code in this commit.
**Parent:** 2026-04-19 P0 outage; root cause documented in `docs/audits/2026-04-20-public-mcp-outage-postmortem.md`.

---

## 1. The failure class

2026-04-19 P0 had two independent contributing factors. Layer 1 was the URL mismatch (Cloudflare tunnel hostname ≠ installed connector URL). Layer 2 — the one this doc addresses — was a **stale-bytecode import failure**: the running MCP server (PID 2412, started 15:12:06) had loaded `workflow.storage` from a snapshot that predated the R7a split (file mtime 16:34:46). When tools invoked paths reaching `from workflow.storage import ALL_CAPABILITIES`, Python raised `ImportError: cannot import name 'ALL_CAPABILITIES'` because the cached module didn't carry the symbol.

This is a distinct class from the tunnel-routing issue and recurs every time a refactor:
1. Moves symbols between `tinyassets/storage/__init__.py` and its submodules.
2. Changes re-export lists.
3. Lands without a server process restart.

The primary defense today is "restart the server after touching storage imports." That defense is tribal knowledge, not structural. The P0 exposed that it fails when anyone (human or tool) forgets.

---

## 2. Why the current shape is fragile

`tinyassets/storage/__init__.py` has three structural properties that amplify the failure:

**a. Body-level circular-import pattern.** Line 206 performs `from workflow.storage.accounts import ...` at the END of `__init__.py`. `accounts.py` line 25 performs `from workflow.storage import DEFAULT_USER_CAPABILITIES, SESSION_PREFIX, ...` AT MODULE TOP. This only works because Python returns the partial module from `sys.modules` during circular imports and the dependents happen to be bound before the circular re-entry — a property that holds today but is sensitive to any reordering of the `__init__.py` body.

**b. Wide re-export surface.** `__all__` on line 154 lists 36 names. Callers (`tinyassets/daemon_server.py` line 20 pulls 35 of them) depend on `workflow.storage.<flat>` access for all of them. Any missing symbol at import time is an `ImportError`, not a `None` lookup — which is correct (fail-loudly) but means the blast radius of a partial refactor is "entire process can't start" not "one function returns None."

**c. Long-running process holds the snapshot.** The tray launches `universe_server.py` as a subprocess; that subprocess loads `workflow.storage` ONCE at startup. A code change + tray unrestarted = the process permanently executes the old bytecode until manually bounced. There is no SIGHUP-style reload path and adding one is out of scope here (service reload ≠ import safety).

The mitigation goal is: **detect the stale-snapshot class of failure at the commit that introduces it, or at server start, rather than at the first MCP tool call that hits the broken path.**

---

## 3. Three mitigation options

### Option A — Lazy `__getattr__` on the package root

**Shape.** Replace the body-level re-export block (lines 206-217) with a module-level `__getattr__` that imports the bounded-context submodule on demand:

```python
# tinyassets/storage/__init__.py (end of file)

_LAZY_IMPORTS = {
    "_account_id_for_username": ("accounts", "_account_id_for_username"),
    "actor_has_capability":     ("accounts", "actor_has_capability"),
    "create_or_update_account": ("accounts", "create_or_update_account"),
    # ... rest of the 10 re-exports
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        submodule, attr = _LAZY_IMPORTS[name]
        import importlib
        mod = importlib.import_module(f"workflow.storage.{submodule}")
        value = getattr(mod, attr)
        globals()[name] = value  # cache on the package for subsequent access
        return value
    raise AttributeError(f"module 'workflow.storage' has no attribute {name!r}")
```

**What it fixes.**
- Breaks the circular import structurally: `accounts.py` imports from `workflow.storage` (constants only, bound at line ~195 before `__getattr__` runs). The re-export direction is lazy.
- Import-time blast radius drops to zero — a missing symbol during the `__init__.py` body load no longer prevents `workflow.storage` from being importable at all.
- A stale-snapshot process that hits a missing symbol still raises `AttributeError`, but the error surfaces at the specific tool-call path, not on every import of `workflow.storage`.

**What it does NOT fix.**
- Does not protect against a TRULY stale process — if the cached `__getattr__` points at a deleted submodule, the failure still happens, just in a more localized way. Server restart is still the remediation when the underlying shape changes.
- Does not catch missing symbols at commit time. Would pair well with option C.

**Cost.** ~15 LOC change + update `__all__`. Small refactor. All existing call sites keep working (Python's attribute-lookup protocol tries instance attributes first, so cached symbols stay hot after first access).

**Risk.** Python's `__getattr__` on modules is stable since 3.7 and used widely (stdlib `enum`, `typing`, `collections.abc`). Tooling-friendly: `from workflow.storage import X` still works, as does `workflow.storage.X`. Static analyzers may need a `__all__` declaration to still offer autocompletion — low-risk, already present.

**Verdict:** strong foundation. My recommendation as first step.

---

### Option B — Import-graph smoke test in CI (pre-commit + GHA)

**Shape.** A test that:
1. Spawns a fresh Python subprocess (no cached modules).
2. Runs `python -c "import workflow.storage; assert set(<expected>) <= set(dir(workflow.storage))"` for the 36 exported names.
3. Does the same for `workflow.daemon_server`, `workflow.universe_server` (the main symbol consumers).
4. Fails the commit if any expected name is missing.

Three delivery surfaces:

- **Pre-commit hook** — runs on every commit touching `tinyassets/storage/`. Fast (<2s). Catches missing-symbol regressions before landing.
- **tier-3 GHA** — already shipped in task #6. Add the import-graph smoke as a step. Catches regressions that slip past pre-commit (e.g., pre-commit disabled, merge-commit).
- **Server-startup self-check** — optionally, the MCP server's boot path asserts its own imports are clean. Rejected below (see option C contrast).

**What it fixes.**
- Catches the "missing symbol" failure mode at commit time, with full git context.
- Tier-3 GHA catches even fresh-clone install-time regressions.
- Works independently of the running process — cold import proves the package is structurally sound.

**What it does NOT fix.**
- Does not prevent the P0 mechanism itself (running process with stale bytecode). The CI check says "main is green on fresh clone"; it can't enforce "every running process has the latest bytecode."

**Cost.** ~50 LOC for the smoke test + ~5 LOC GHA step addition + ~3 LOC pre-commit hook entry. ~0.25 dev-day including pre-commit integration.

**Risk.** Low — purely additive check. False positive risk: if the expected-names list drifts from reality, the smoke flags legitimate changes. Mitigation: derive the expected set from `workflow.storage.__all__` directly, so the check is self-updating.

**Verdict:** strong complement to option A. Cheap to ship, meaningful coverage.

---

### Option C — Server-startup import-graph self-check + auto-restart hint

**Shape.** In `tinyassets/universe_server.py` startup, after FastMCP is constructed but before serving, verify the critical import graph:

```python
def _verify_import_graph():
    """Fail-loudly at startup if stale bytecode is present."""
    critical = [
        ("workflow.storage", ["ALL_CAPABILITIES", "DEFAULT_USER_CAPABILITIES",
                              "create_or_update_account", "grant_capabilities"]),
        ("workflow.daemon_server", ["initialize_author_server"]),
    ]
    import importlib
    for module_path, expected_attrs in critical:
        mod = importlib.import_module(module_path)
        missing = [a for a in expected_attrs if not hasattr(mod, a)]
        if missing:
            raise RuntimeError(
                f"Stale bytecode or partial module: {module_path} missing {missing}. "
                f"Restart the process — source has drifted from this cached snapshot."
            )
```

Called as the first step after imports. Server refuses to start if the check fails.

**What it fixes.**
- Catches the exact P0 mechanism AT SERVER START rather than at first tool call.
- Tray can observe the startup-crash, surface a tray-notification "TinyAssets MCP failed to start: stale bytecode. Restart machine or run `pip install -e .`."
- If paired with tray auto-restart (separate scope), becomes fully self-healing for this failure class.

**What it does NOT fix.**
- A server that started successfully and THEN has its source files updated still won't reload (Python import cache is process-local). The check fires at start; it doesn't re-fire.
- Does not catch missing symbols at commit time — the problem surfaces at deploy time instead. This is the trade-off: earlier signal (B) vs more-localized signal (C).

**Cost.** ~30 LOC for the check + test coverage + tray notification wiring if we want that leg. ~0.5 dev-day if we include tray auto-restart; ~0.25 dev-day for just the check + fail-loud.

**Risk.** Low at the check itself. Auto-restart has the usual blast-radius concerns (tray respawn loops if the check is broken) — mitigate by rate-limiting: max 3 auto-restarts per 10 min, then notify + stop.

**Verdict:** useful after A+B land. Not a replacement for either. Would not have caught 2026-04-19 P0 on its own because the server started BEFORE the refactor, but IS the defense for future restarts.

---

### Option D — Tray-level mtime watcher auto-restarts MCP on source change

**Shape.** Tray spawns a lightweight watcher thread that polls mtimes of canonical workflow paths every ~5s (or uses `watchdog`'s filesystem events where available). When any of `tinyassets/**/*.py`, `domains/**/*.py`, or the packaged-plugin mirror changes, tray gracefully restarts the MCP subprocess (SIGTERM + respawn).

```python
# tray/mtime_watcher.py (conceptual)
_WATCH_ROOTS = [
    "workflow", "domains",
    "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/workflow",
]

def poll_once(last_mtime: float) -> tuple[bool, float]:
    current = max(
        p.stat().st_mtime
        for root in _WATCH_ROOTS for p in Path(root).rglob("*.py")
    )
    return (current > last_mtime, current)
```

When `True`, tray calls existing restart pathway (SIGTERM PID 2412-equivalent → respawn within 2-5s per `reference_daemon_restart_procedure` memory).

**What it fixes.**
- Catches 2026-04-19 P0 directly — the file mtime (16:34:46) post-dates the server start (15:12:06); watcher fires at next 5s tick; server restarts with the new import graph.
- Works even when the developer forgets to bounce manually.
- Covers the entire class of "source updated, process stale," not just storage.

**What it does NOT fix.**
- Does not catch missing-symbol regressions at COMMIT time (B does).
- Does not prevent structural fragility (A does).
- Auto-restart has usual blast-radius concerns: file saved mid-edit triggers restart on a syntactically broken file; restart loop. Mitigation: 500ms debounce after last mtime change before triggering; rate-limit to max 3 restarts per 10 min (same as C's hint).
- Windows filesystem mtime resolution is ~1s; a rapid save-save within 1s looks like one change. Acceptable for the tray-polling cadence.
- Polling overhead: ~200-500 file stats per poll. At 5s cadence = negligible (<0.5% CPU).

**Cost.** ~80 LOC for watcher thread + debounce + rate limiter + test coverage. Plus integration with existing tray process-management. ~0.5-1 dev-day depending on how much tray refactor is needed.

**Risk.** Higher than A/B/C. Auto-restart behavior is user-visible — mid-request restart can drop in-flight tool calls. Mitigation: watch-and-defer — queue restart until current MCP sessions are idle (no active requests in past 30s) OR restart immediately if user explicitly opts in via tray setting. Recommend OPT-IN initially; move to default-on after field experience.

**Verdict:** the most aggressive + most complete fix for the stale-process class. Best paired with A (structural) + B (CI); paired alone it masks commit-time regressions by auto-rescuing the user experience, which is both a feature and a risk (easier to land broken code when the dev loop self-heals).

---

## 4. Recommendation

Ship **A + B together**; defer C and D as follow-ons.

**Rationale.**
- A fixes the structural fragility (circular import + body-level re-exports). Cheapest per unit of long-term robustness.
- B catches A's rare regressions plus ALL symbol-missing regressions at commit time — this is where the P0 class of bug should be caught, not at the already-running process.
- C is useful but only fires at server start; server start on a fresh deploy is already covered by tier-3 OSS clone GHA. Returns on C come later when we add multi-host auto-deploy.
- D is the most complete fix for the live-process leg but carries the highest risk (auto-restart UX, mid-request drops) and masks regressions that A+B would have surfaced earlier. Worth shipping after A+B, opt-in, then default-on after field experience.

**Combined cost:** ~0.5 dev-day for A+B. D adds ~0.5-1 dev-day when greenlit. C adds ~0.25 dev-day. Single commit is fine for A+B; D is its own commit because it touches tray process management.

**Why NOT D first:** D *auto-heals* the symptom without fixing the structural fragility. A developer who doesn't understand the underlying fragility (circular imports at line 206, wide re-export surface) will keep shipping symbol-addition PRs that D silently rescues. That's exactly the wrong teaching signal — the mistake should surface at commit time (B) or be structurally impossible (A), not invisibly recovered at runtime.

---

## 5. What this doc does NOT decide

- **Whether to also lazily import the constants** (`CAP_*`, `DEFAULT_USER_CAPABILITIES`, `DB_FILENAME`). Recommend NO — they're cheap + always referenced; lazy-ing them would complicate static analysis without structural benefit. Keep them as direct module-level assignments.
- **Whether to split `tinyassets/storage/__init__.py` further** (e.g., move the constants into `tinyassets/storage/_constants.py`). Recommend NO for this commit — that's a distinct refactor, not a mitigation. Current `__init__.py` placement works once option A lands.
- **Tray auto-restart policy.** Separate design question. Option C hints at it; a full policy doc belongs elsewhere.
- **Hot reload.** Out of scope. Fixing hot-reload is hard in Python and not what any P0 class benefits from right now.

---

## 6. Open questions (raise in review)

1. **Option A — does `__getattr__` break any of the existing `from workflow.storage import (...)` block imports in `tinyassets/daemon_server.py`?** Should not, because `from X import Y, Z` triggers `__getattr__` for each of `Y, Z`. Verify with a scratch test before committing: spawn `python -c "from workflow.daemon_server import ALL_CAPABILITIES; print(ALL_CAPABILITIES)"` on a lazy-`__getattr__` branch.
2. **Option B — how does the smoke test handle intentional symbol removals?** When someone drops `grant_capabilities` on purpose (R7 completion migrates it away), the smoke test fails and blocks the commit. Mitigation: derive the expected set from `__all__`, so the smoke tests "what's declared is importable" rather than "a hardcoded list is importable."
3. **Option C — tray notification pathway.** Tray currently has no cross-process notification channel from the MCP server. Adding one is out of this doc's scope but relevant for the auto-restart leg.
4. **Python-version sensitivity.** `__getattr__` on modules is 3.7+ (no concern). Pre-3.7 compat isn't a goal per Hard Rule 7.

---

## 7. Summary for dispatcher

- **Primary:** Option A (lazy `__getattr__` on `tinyassets/storage/__init__.py` re-export block). ~15 LOC. Fixes circular-import fragility.
- **Secondary:** Option B (import-graph smoke in pre-commit + tier-3 GHA). ~55 LOC. Catches missing-symbol regressions at commit/install time.
- **Deferred:** Option C (server-startup import-graph check). ~30 LOC. Useful after A+B; not load-bearing for this class.
- **Deferred (highest blast radius):** Option D (tray mtime watcher auto-restart). ~80 LOC + tray refactor. Catches the live-process leg directly but needs opt-in UX and doesn't fix the underlying fragility that A+B address.
- **Total recommended first commit:** A + B, ~0.5 dev-day, single commit. D is a separate commit after field-testing A+B.
- **Would have caught 2026-04-19 P0:**
  - A: yes (structurally — missing symbol raises `AttributeError` at narrow call site, not at import; restart still required but the process doesn't outright fail to serve unrelated tools).
  - B: yes (at commit time — smoke test would have flagged the missing export on the R7a commit).
  - C: no (server started BEFORE the refactor; check doesn't re-fire).
  - D: yes (directly — mtime watcher would have fired at 16:34:46 and restarted the process before host hit it at 17:05).

Scoping complete. Implementation waits for lead greenlight.

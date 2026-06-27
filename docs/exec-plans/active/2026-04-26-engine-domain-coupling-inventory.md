---
title: tinyassets/ → domains.fantasy_* coupling site inventory (read-only)
date: 2026-04-26
author: dev-2
status: read-only inventory — input for Task #11/#28/#29 host-review queue
companion: docs/audits/2026-04-25-engine-domain-api-separation.md (planned scope)
---

# Engine → domain coupling site inventory

Read-only audit of every `tinyassets/` import that reaches into `domains.fantasy_*`. Defines the surface area the engine-domain decoupling work has to handle when host green-lights audit doc `docs/audits/2026-04-25-engine-domain-api-separation.md`.

**Scope:** all `from domains.fantasy_(daemon|author) import …` and `import domains.fantasy_…` statements anywhere under `tinyassets/`. Does NOT include `domains/` ↔ `domains/` references (that's intra-domain) or `tests/` ↔ `domains/` (test-side, out of engine scope).

**Method:** `grep -rn "domains\.fantasy_(daemon|author)" tinyassets/`. Re-grep canonical — line numbers from navigator's earlier note (L1088, L1645, L7349, L7846, L8511, all in pre-decomp universe_server.py) have entirely drifted because `tinyassets/api/runs.py` extraction (Task #16, dev-owned, in-flight) just moved 3 of those references out. Current as of 2026-04-26 21:55 local.

**Naming caveat:** `domains.fantasy_author` is today a back-compat alias to `domains.fantasy_daemon` per `domains/fantasy_author/__init__.py` shim (gated by `TINYASSETS_AUTHOR_RENAME_COMPAT`, removed in Phase 5). Every import below uses the legacy `fantasy_author` path; the actual module loaded is `fantasy_daemon`. The decoupling work would normalize to `fantasy_daemon` in passing OR (better) replace with a domain-agnostic seam.

---

## Summary

| Category | Count | Notes |
|---|---|---|
| **Engine-only-leak** (could be eliminated by an abstraction) | 8 sites across 6 files | All are calls to `_provider_stub.call_provider` or related `_FORCE_MOCK` toggle |
| **Domain-handler** (legitimate domain entry point in engine) | 2 sites across 2 files | Compiled-graph wiring; tray hot-reload allowlist |
| **Hybrid** (engine surface that names domain-specific path) | 2 sites across 2 files | Knowledge-graph path resolution; comment-only reference |
| **TOTAL** | **12 import sites across 9 files** | Pre-decomp navigator note said "5 known sites at L1088, L1645, L7349, L7846, L8511" — that count was universe_server.py-only. Engine-wide reality is 12 sites. |

**Refactor difficulty distribution:**
- **trivial** (1-line replacement, no signature change): 6 sites — all the `_provider_stub.call_provider` lazy imports inside engine helpers; replace with a `provider_call` arg passed by caller.
- **moderate** (small abstraction needed): 4 sites — `_FORCE_MOCK` toggle reads, `resolve_kg_path`, `worldbuild._write_canon_file`.
- **large** (architectural decision required): 2 sites — `checkpointing/sqlite_saver.py` graph builders, `desktop/launcher.py` reload allowlist.

---

## Site-by-site inventory

### 1. `tinyassets/api/runs.py:387` — engine-only-leak (trivial)

```python
def _action_run_branch(kwargs):
    ...
    provider_call: Any = None
    try:
        from domains.fantasy_author.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None
```

**Context:** `_action_run_branch` MCP handler. Provider injection point for the LangGraph compile path.
**Classification:** engine-only-leak — this is the engine wiring a domain's provider stub as the default callable. The handler itself is engine; the domain reference is purely the default fallback.
**Refactor:** trivial. Replace with module-level `provider_call: Callable | None = None` resolved by a domain-router lookup at runtime, OR have the caller pass it via `kwargs`. The `try/except ImportError` graceful-degrade pattern means swapping in a registry lookup is a one-line edit.
**Recently moved:** post-Task #16 extraction — was at universe_server.py L7349 in pre-decomp. Same code, new home.

### 2. `tinyassets/api/runs.py:885` — engine-only-leak (trivial)

```python
def _action_resume_run(kwargs):
    ...
    provider_call: Any = None
    try:
        from domains.fantasy_author.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None
```

**Context:** `_action_resume_run` MCP handler. Same pattern as #1.
**Classification:** engine-only-leak.
**Refactor:** trivial — same fix as #1; share the resolution helper.
**Recently moved:** was at universe_server.py L7846 pre-decomp.

### 3. `tinyassets/api/runs.py:1232` — engine-only-leak (trivial)

```python
def _action_run_branch_version(kwargs):
    ...
    provider_call: Any = None
    try:
        from domains.fantasy_author.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None
```

**Context:** `_action_run_branch_version` MCP handler. Third copy of the provider-injection pattern in api/runs.py alone.
**Classification:** engine-only-leak.
**Refactor:** trivial — co-fix with #1, #2. Three nearly-identical blocks; consolidate into a `_resolve_provider_call() -> Callable | None` helper inside api/runs.py (or in `workflow.providers`) that the 3 handlers call.
**Recently moved:** was at universe_server.py L8511 pre-decomp.

**Cross-cut observation for sites #1-#3:** identical to the canary `_post` triplication that Task #14 consolidated. Same partial-binding pattern would fit: `_resolve_provider_call` returns the same callable object for all 3 callers, locking the contract via identity-check tests once consolidated. **NOT in scope for this inventory** — flagging as a future Task #14-style consolidation candidate.

### 4. `tinyassets/evaluation/editorial.py:119` — engine-only-leak (trivial)

```python
def get_editorial_notes(prose, ..., provider_call=None):
    ...
    if provider_call is None:
        from domains.fantasy_author.phases._provider_stub import call_provider
        provider_call = call_provider
```

**Context:** `get_editorial_notes` evaluation helper. Editorial pass over a scene draft.
**Classification:** engine-only-leak — caller can already pass `provider_call`; the domain import is just the lazy default.
**Refactor:** trivial — caller must always pass `provider_call`, OR this default lookup goes through a domain registry. Same pattern as the api/runs.py trio.

### 5. `tinyassets/knowledge/raptor.py:333` — engine-only-leak (trivial)

```python
async def _summarize(prompt: str, system: str, role: str) -> str:
    from domains.fantasy_author.phases._provider_stub import call_provider
    return call_provider(prompt, system, role=role, fallback_response="")
```

**Context:** `_summarize` async closure inside RAPTOR tree-build. Hard-coded default for cluster-summarization LLM call.
**Classification:** engine-only-leak — RAPTOR is fully domain-agnostic; the import here is purely "what callable do we use?"
**Refactor:** trivial — `build_raptor_tree` already takes `provider_call` as a parameter (see L344 of raptor.py); the wrapper closure should accept a `provider_call` from the outer scope rather than late-importing the domain stub. One refactor candidate: hoist `_summarize` to take provider_call from the enclosing function's signature.

### 6. `tinyassets/memory/reflexion.py:205` — engine-only-leak (moderate)

```python
def _llm_critique(state, feedback, template_critique):
    from domains.fantasy_author.phases._provider_stub import (
        _FORCE_MOCK,
        call_provider,
    )
    if _FORCE_MOCK:
        return ""
    ...
```

**Context:** `_llm_critique` static method on the reflexion class. Used by the per-iteration self-critique pass after a REVERT verdict.
**Classification:** engine-only-leak — but note the additional `_FORCE_MOCK` toggle reach. The toggle is a domain-internal test flag; reading it from engine code couples engine to the domain's testing model. (See memory `feedback_flag_at_import_time.md`.)
**Refactor:** moderate. The `call_provider` import is trivial; the `_FORCE_MOCK` toggle needs a different mechanism — either move to a `workflow.providers.routing._mock_mode_active()` helper, or accept the test-mode signal via env var resolved at engine boot.

### 7. `tinyassets/memory/reflexion.py:260` — engine-only-leak (moderate)

```python
def _llm_reflection(critique: str, state: dict) -> str:
    from domains.fantasy_author.phases._provider_stub import (
        _FORCE_MOCK,
        call_provider,
    )
    ...
```

**Context:** Sibling of #6 — `_llm_reflection` static method, second of the reflexion class's two LLM helpers.
**Classification:** engine-only-leak.
**Refactor:** moderate — co-fix with #6. Two near-identical blocks.

### 8. `tinyassets/ingestion/extractors.py:259-260` — hybrid (moderate)

```python
def synthesize_canon_from_source(source_text, filename, canon_dir, premise):
    from domains.fantasy_author.phases._provider_stub import call_provider, last_provider
    from domains.fantasy_author.phases.worldbuild import _write_canon_file
    ...
```

**Context:** Source ingestion pipeline — synthesizes canon docs from uploaded source text.
**Classification:** hybrid — `call_provider` is engine-only-leak (same as #1-#7), but `_write_canon_file` is genuinely domain-specific (writes to the fantasy domain's canon/ layout). Even `last_provider` is a domain-side telemetry helper.
**Refactor:** moderate. `call_provider` consolidates with #1-#7. `_write_canon_file` needs the domain to expose a public `write_canon(path, content)` API on its `Domain` protocol (see `tinyassets/registry.py` for the existing protocol surface). Then this engine helper takes a `domain_writer: Callable[[Path, str], None]` param.

### 9. `tinyassets/retrieval/agentic_search.py:140` — hybrid (moderate)

```python
def run_phase_retrieval(...):
    ...
    if kg is None:
        from domains.fantasy_author.phases._paths import resolve_kg_path
        ...
        kg_path = resolve_kg_path(state)
        if kg_path:
            kg = KnowledgeGraph(kg_path)
```

**Context:** `run_phase_retrieval` engine entry-point for retrieval. Falls back to a domain-side path resolver when the runtime singleton has no KG bound.
**Classification:** hybrid — `resolve_kg_path` IS legitimately domain-side (knows where the fantasy domain stores its KG file), but the engine retrieval router has to know it exists.
**Refactor:** moderate. Domain protocol should expose a `kg_path(state) -> Path | None` method; engine asks the registered domain rather than reaching into `domains.fantasy_author.phases._paths`. Cleaner long-term but requires a tiny protocol extension.

### 10. `tinyassets/retrieval/agentic_search.py:317` — engine-only-leak (trivial)

```python
def _build_provider_call() -> Callable[[str, str, str], Any] | None:
    from domains.fantasy_author.phases import _provider_stub
    if _provider_stub._FORCE_MOCK:
        return None
    async def _async_provider_call(prompt, system, role):
        return _provider_stub.call_provider(...)
    return _async_provider_call
```

**Context:** `_build_provider_call` helper inside the engine retrieval module. Wraps the domain stub in an async callable.
**Classification:** engine-only-leak (same `_FORCE_MOCK` smell as #6/#7).
**Refactor:** trivial for `call_provider`, moderate for the `_FORCE_MOCK` toggle.

### 11. `tinyassets/checkpointing/sqlite_saver.py:167` — domain-handler (large)

```python
def build_compiled_graphs(checkpointer):
    from domains.fantasy_author.graphs import (
        build_book_graph,
        build_chapter_graph,
        build_scene_graph,
        build_universe_graph,
    )
    return {
        "scene": build_scene_graph().compile(checkpointer=checkpointer),
        "chapter": build_chapter_graph().compile(checkpointer=checkpointer),
        "book": build_book_graph().compile(checkpointer=checkpointer),
        "universe": build_universe_graph().compile(checkpointer=checkpointer),
    }
```

**Context:** `build_compiled_graphs` — builds the LangGraph CompiledStateGraph instances for all 4 fantasy graph levels. Returned dict keys match the fantasy domain's graph hierarchy.
**Classification:** domain-handler — this function IS a domain entry point that landed in the engine package. The dict keys (`scene`/`chapter`/`book`/`universe`) are entirely fantasy-vocabulary; another domain (e.g. research_probe) would have entirely different graphs.
**Refactor:** large. This is misplaced architecturally — `build_compiled_graphs` is a fantasy-domain function masquerading as an engine helper. The right fix is to move it to `domains/fantasy_daemon/checkpointing.py` or have the domain's `Domain` protocol expose a `compile_graphs(checkpointer) -> dict[str, CompiledStateGraph]` method. Engine then asks the registered domain. Touches every caller (`workflow.checkpointing` users), so it's a real architectural commit, not a 1-liner.

### 12. `tinyassets/desktop/launcher.py:544, 553, 555` — domain-handler (large)

```python
_RELOAD_PACKAGES = (
    "domains.fantasy_author.phases",
    "workflow.providers",
    "workflow.evaluation",
    ...
    "domains.fantasy_author.graphs",
    "workflow.checkpointing",
    "domains.fantasy_author.state",
    ...
)
```

**Context:** Tray launcher's hot-reload package allowlist. When code changes are detected, these modules get re-imported so the daemon picks up the change without a full restart.
**Classification:** domain-handler — this IS legitimately the engine knowing about the domain (so it can reload it). But the hard-coded fantasy-only list won't work with multi-domain hosts.
**Refactor:** large — the right fix is to read the registered domains from `default_registry`, ask each one for its hot-reload module list, and union them. Two-domain test (e.g. fantasy_daemon + research_probe) would force this issue.

---

## Comment-only reference (NOT a coupling site)

### `tinyassets/universe_server.py:1126` — comment-only

```python
# The daemon writes `current_phase` and `last_updated` into status.json via
# `domains.fantasy_author.phases._activity.update_phase`. status.json itself
# is not a heartbeat — it only moves when a phase transitions.
```

**Classification:** documentation reference — no import, no runtime coupling. Mention-only of where the WRITE side lives. Inventory completeness; not in the surface to refactor.

## Docstring reference (NOT a coupling site)

### `tinyassets/registry.py:13` — docstring example

```python
Usage:
    from workflow.registry import default_registry
    from domains.fantasy_author.skill import FantasyAuthorDomain
    default_registry.register(FantasyAuthorDomain())
```

**Classification:** docstring example — `FantasyAuthorDomain` is the canonical reference implementation of the `Domain` protocol; using it in the docstring is appropriate. No runtime coupling. (One nit: `FantasyAuthorDomain` should be `FantasyDaemon` or whatever the canonical name is post-rename Phase 2; the docstring has drifted with the rename.)

---

## Recommended dispatch order

When host green-lights `docs/audits/2026-04-25-engine-domain-api-separation.md` work:

### Phase A — engine-only-leak consolidation (low-hanging fruit)
Sites #1, #2, #3, #4, #5 — all trivial-difficulty `provider_call` lazy imports. One Task #14-style consolidation: extract a `_resolve_default_provider_call()` helper to `tinyassets/providers/__init__.py` (or similar engine-side location); the 5 callers replace their local `try: from domains... import call_provider` blocks with a single function call. Identity-check tests lock in the contract.

**Estimate:** 60-90 min including tests + verifier handoff. Net ~20 LOC removed across 5 files; 1 new helper + tests/test_provider_resolution.py.

### Phase B — `_FORCE_MOCK` toggle abstraction
Sites #6, #7, #10 — moderate-difficulty `_FORCE_MOCK` reaches. Replace with `workflow.providers.routing.mock_mode_active() -> bool` helper resolved at call time from env var. Removes the engine→domain testing-flag dependency.

**Estimate:** 90-120 min. Reflexion + retrieval modules + 1 new helper + integration tests.

### Phase C — domain protocol extensions for the 2 hybrid sites (#8, #9)
Add to `tinyassets/protocols.py` (or wherever the `Domain` protocol lives):
```python
def write_canon(self, path: Path, content: str) -> None: ...
def kg_path(self, state: dict[str, Any]) -> Path | None: ...
```
Implement these on `FantasyDaemon`. Engine helpers (`extractors.py`, `agentic_search.py`) call through the registry rather than direct import.

**Estimate:** half-day. Touches the `Domain` protocol surface, requires care to land without breaking other domains-in-development.

### Phase D — architectural decisions for the 2 large sites (#11, #12)
Site #11 (`build_compiled_graphs`): move to domain side, expose via `Domain.compile_graphs(checkpointer)` protocol method. Touches every checkpointing user — coordinate with checkpointing tests + sqlite_saver consumers.

Site #12 (tray reload allowlist): replace hard-coded list with `default_registry.iter_reloadable_modules()` enumeration. Requires `Domain.reloadable_modules() -> tuple[str, ...]` protocol method.

**Estimate:** 1-2 dev-days, host-decision required on protocol-surface shape. Best done AFTER Phases A-C land so the engine→domain dependency surface is already shrunk.

### Phase E — fantasy_author → fantasy_daemon rename cleanup
Once Phases A-D land, the only remaining `domains.fantasy_author` refs are documentation (universe_server.py L1126 comment + registry.py L13 docstring). Rename Phase 2's `TINYASSETS_AUTHOR_RENAME_COMPAT` shim can flip default-off, then be removed in rename Phase 5.

**Estimate:** 15 min after preceding phases land. Just a docstring/comment refresh.

---

## Cross-references for host audit-review queue

This inventory becomes input for:
- **Task #11 (host queue)** — `docs/audits/2026-04-25-engine-domain-api-separation.md` review. The audit doc proposes the architectural moves; this inventory provides the concrete site count.
- **Task #28/#29 (audit-doc reviews)** — same audit suite.
- **Rename Phase 5** — removes the `domains.fantasy_author` back-compat shim. Cannot land until Phase E above.

## What this inventory does NOT do

- No code edits (read-only by brief).
- Does not propose the protocol-surface shape for sites #8, #9, #11, #12 (that's the audit doc's job).
- Does not measure test-coverage gaps for any of the 12 sites.
- Does not enumerate engine→`domains.research_probe` coupling (zero hits — research_probe is currently a stub with no engine consumers, per its directory's emptiness).
- Does not enumerate `tests/` ↔ `domains/` coupling (test-side, separate audit).
- Does not file STATUS.md concerns or open Tasks for any of the phases above (lead's call when host green-lights).

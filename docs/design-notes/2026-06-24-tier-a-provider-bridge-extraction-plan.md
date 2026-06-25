# Tier-A: provider-bridge extraction — execution plan

**Filed:** 2026-06-24 · **Branch:** `claude/defantasy-tier-a-provider-bridge`
**Parent:** `docs/audits/2026-06-24-fantasy-architecture-residue-audit.md` (Tier A).
**Status:** foundation landed; repoint pending a behavior-change decision +
opposite-provider review. NOT behavior-preserving in two places (flagged below).

## Done (this slice)

`workflow/providers/call.py` — the engine's domain-agnostic LLM-call primitive,
extracted from `domains/fantasy_daemon/phases/_provider_stub.py`. Carries
`call_provider`, the retry wrapper, the fallback-router builder, and an explicit
accessor API: `set_provider_router` / `get_provider_router` /
`set_force_mock` / `is_force_mock` / `get_last_provider`. Zero `domains.*`
imports. Unit-tested in isolation (`tests/test_providers_call.py`, 5 tests) —
pins the injection seam and the live-`last_provider` accessor.

The fantasy-specific half (`call_for_plan/draft/extraction`, `_mock_*`,
`_format_*`) STAYS in the domain and will import `call_provider` from the new
module.

## ⚠ Two latent bugs this refactor surfaces (need a decision before repoint)

These mean the repoint is NOT a pure behavior-preserving move. Both are
production-path; get sign-off (host + Codex) on fixing vs. preserving.

1. **Daemon router injection is currently a no-op.**
   `fantasy_daemon/__main__.py:1176-1178` does
   `import fantasy_daemon.nodes._provider_stub as stub; stub._real_router = self._router`.
   But `fantasy_daemon/nodes/_provider_stub.py` is `from ...phases._provider_stub import *`,
   and `import *` excludes underscore names — so `_real_router` is set on the
   *nodes* module, a different object from `phases._provider_stub` where
   `call_provider` reads `_real_router`. **The daemon's per-universe
   `_build_provider_router()` is silently ignored; production runs on the
   import-time fallback router.** Fixing it (route the daemon's router into the
   live bridge via `set_provider_router`) is correct but changes production
   provider selection — flag loudly, test, and stage.

2. **`last_provider` is an import-time snapshot.**
   `ingestion/extractors.py:260` does `from ... import call_provider, last_provider`
   then `_write_canon_file(..., model=last_provider)` at :315 — always `""`,
   so synthesized canon files record an empty model marker. The accessor
   (`get_last_provider()`) fixes it to the real provider name.

## Repoint checklist (remaining)

**Engine call sites (8) → `from workflow.providers.call import ...`:**
- `workflow/api/runs.py:542, 1110, 1520` (`call_provider`)
- `workflow/api/selector_dispatch.py:733` (`call_provider`)
- `workflow/evaluation/editorial.py:119` (`call_provider`)
- `workflow/knowledge/raptor.py:340` (`call_provider`)
- `workflow/ingestion/extractors.py:260` (`call_provider`; replace `last_provider`
  use at :315 with `get_last_provider()` — see bug #2)
- `workflow/memory/reflexion.py:205-210, 260-265` (`_FORCE_MOCK` → `is_force_mock()`)
- `workflow/retrieval/agentic_search.py:381-387` (`_provider_stub._FORCE_MOCK`
  → `call.is_force_mock()`; `_provider_stub.call_provider` → `call.call_provider`)

**Fantasy domain:** reduce `domains/fantasy_daemon/phases/_provider_stub.py` to
the fantasy functions; have them `from workflow.providers.call import call_provider`
and read force-mock via `is_force_mock()` (not the old module global).

**⚠ True consumer surface is ~35 files, not 8 (corrected after full-repo grep —
the audit + first Codex pass undercounted the fantasy-domain side).** Removing
`last_provider` / `_FORCE_MOCK` / `_real_router` / `_call_router_with_retry`
from the old module is **ATOMIC** — `from X import name` binds a snapshot, so
there is no safe partial; every consumer of a removed symbol must move in the
same commit. `call_provider` / `call_for_*` callers can keep importing from
`phases._provider_stub` (it legitimately re-imports `call_provider` for its own
use and keeps `call_for_*`), but ENGINE `call_provider` imports must still move
to `workflow.providers.call` to satisfy the de-fantasy goal + import guard.

Removed-symbol consumers that MUST move atomically:
- `last_provider` -> `get_last_provider()`:
  `domains/fantasy_daemon/phases/worldbuild.py:489,539,608,909`,
  `workflow/ingestion/extractors.py:260/315`,
  `fantasy_daemon/__main__.py:1962` (via nodes shim).
- `_FORCE_MOCK` -> `is_force_mock()` / `set_force_mock()`:
  `workflow/memory/reflexion.py:205,260`,
  `workflow/retrieval/agentic_search.py:381`, `tests/conftest.py:19`, and the
  test files below.
- Daemon injection `fantasy_daemon/__main__.py:1176-1178` ->
  `set_provider_router(self._router)` (fixes bug #1).
- Delete `fantasy_daemon/nodes/_provider_stub.py` (star-import shim);
  repoint its importers (`fantasy_daemon/__main__.py:1962,2227`).
- `scripts/rebuild_sporemarch_kg.py:92` (`call_provider`).
- Domain `call_provider` importers (`commit,consolidate,reflect,worldbuild,
  writer_tools`) — repoint to `workflow.providers.call` for cleanliness
  (optional for correctness since phases re-exports, required for the guard if
  the guard ever covers `domains/`).

**Daemon injection:** `fantasy_daemon/__main__.py:1176-1178` →
`from workflow.providers.call import set_provider_router; set_provider_router(self._router)`
(fixes bug #1). Remove/repoint `fantasy_daemon/nodes/_provider_stub.py` (the
star-import shim) — no-shims rule: delete it in this arc, not leave a re-export.

**Test infra (the load-bearing part):**
- `tests/conftest.py:17-19` — set force-mock on the new module:
  `from workflow.providers import call; call.set_force_mock(True)`. Keep the
  fantasy module's mock path honoring `is_force_mock()` so its `call_for_*`
  fallbacks still fire.
- Test files referencing `_provider_stub` / the old path — audit each; those
  mocking `call_provider` or toggling `_FORCE_MOCK` repoint to
  `workflow.providers.call`:
  `conftest, test_canonical_branch_mcp, test_commit_kg_integration,
  test_goals_set_selector, test_integration, test_nodes_real,
  test_provider_retry, test_rollback, test_stability,
  test_text_channel_id_redaction`, and (Codex review, missed in the first pass)
  `test_grok_provider_registration, test_provider_binary_probe,
  test_provider_stub_registration, test_ingestion, test_knowledge_graph,
  test_universe_nodes`.
- **Packaging mirror:** regenerate
  `packaging/claude-plugin/.../runtime/workflow/` (run
  `python packaging/claude-plugin/build_plugin.py`) so the packaged runtime
  ships the new module + repointed imports, not the old coupling.

**Prevention:** add the staged/ratcheted `workflow/** !-> domains.*` import
guard (audit Prevention). After this slice the only remaining offenders are the
Tier-C/D sites; the guard's allowlist shrinks as each tier lands.

## Gate

The real proof is the **full suite green** (7,856 tests) — this sandbox can't
run it (collection error on an unrelated module + no network for some
providers), so the repoint must be verified where the full suite runs.
Opposite-provider (Codex) review required before landing per AGENTS.md.

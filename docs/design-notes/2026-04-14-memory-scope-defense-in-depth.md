---
status: superseded
superseded_by: docs/design-notes/2026-04-15-memory-scope-tiered.md
---

# Memory-Scope Defense-in-Depth

**Status:** Design spike (planner). Promotes to dev task after host sign-off.
**Related:** STATUS.md Work row "Memory-scope defense-in-depth".
**Target files:** `tinyassets/memory/scoping.py`, `tinyassets/retrieval/agentic_search.py`, `tinyassets/retrieval/phase_context.py`.

## Context

The MCP-layer invariant (`HARD RULE — UNIVERSE ISOLATION`) and the `ScopeResolver` in `tinyassets/memory/scoping.py` both assume every fact carries a `universe_id`. Today, the physical guarantee is **path-based**: each universe has its own `knowledge.db` and its own LanceDB directory (see `tinyassets/knowledge/knowledge_graph.py:33-38`, `tinyassets/retrieval/vector_store.py:38-48` — both hard-fail on CWD-relative defaults). If the right path is passed, isolation holds. If the wrong path is passed — or if a singleton connection is reused across universe boundaries — facts from universe A leak into universe B with no row-level guard to catch it.

This spike asks: should universe_id be a row-level tag on every KG/vector row as a second line of defense, behind the per-universe DB-path boundary?

## 1. Where universe_id lives today

| Layer | Row-level universe_id? | Enforcement |
|---|---|---|
| `episodic` (SQLite: scenes, facts, promises, reflections) | **Yes** — column on every table (`tinyassets/memory/episodic.py:23,35,48,57`); all queries filter by it. | Row-tagged. |
| `ScopedMemoryRouter.store` | **Yes** — `to_filter_dict()` emits `universe_id` into `scope` dict on every write (`scoping.py:189-207,481-503`). | Row-tagged — but `store()` is currently a placeholder stub that doesn't persist. |
| `knowledge_graph.py` KG tables (entities, edges, facts, communities) | **No** — schema at `knowledge_graph.py:54-110` has zero universe column. | Path-only (one DB per universe). |
| `vector_store.py` LanceDB `prose_chunks` | **No** — schema at `vector_store.py:103-114` has zero universe column. | Path-only (one directory per universe). |
| `raptor.py` RAPTOR tree | Row-level tagging TBD — check before implementation. | Path-only (loaded from the per-universe KG). |
| `runtime.knowledge_graph` / `runtime.vector_store` singletons | N/A | Path-only, and **singleton re-use across universes is the main leak vector**. |

**Finding:** Episodic is row-tagged. Archival (KG + vectors) is path-tagged only. The hard-fail guards on empty `db_path` are the load-bearing isolation for archival — not a defense-in-depth posture but a single-layer posture.

## 2. Proposed schema change

Write-time tag, not retrofit-only. Add `universe_id TEXT NOT NULL` to:

- KG tables: `entities`, `edges`, `facts`, `communities` (and any future tables).
- LanceDB `prose_chunks`.
- RAPTOR node/summary storage (verify exact schema before landing).

Primary keys extend to include `universe_id` where identity is universe-scoped (e.g. `entities` PK becomes `(universe_id, entity_id)` — the same entity name can mean different things in different universes; forcing globally unique IDs is the bug, not the feature).

### Retrofit for existing rows

Existing DBs are already path-isolated (`<universe>/knowledge.db`, `<universe>/lancedb/`). Migration infers `universe_id` from the parent directory name of the DB file at migration time: one-shot `UPDATE ... SET universe_id = ?` per DB. Zero ambiguity because each DB belongs to exactly one universe today. Ship the migration as an idempotent `alembic`-style script that detects "universe_id column missing" and adds + backfills in one pass, invoked at daemon startup before any query runs.

## 3. Read-time filter pattern

The abstraction layer is `ScopedMemoryRouter`, and the interface is already shaped correctly — the job is to make it the *only* path into archival.

- **`agentic_search.run_phase_retrieval`** currently constructs a bare `KnowledgeGraph(kg_path)` and passes it to `RetrievalRouter` with no scope object. Change: it takes a `MemoryScope` (from `state["scope"]` or derived from `state["universe_id"]`) and passes it to the retrieval router. Router appends `WHERE universe_id = ?` to every KG query and a LanceDB `.where("universe_id = '...'")` clause to every vector search.
- **`phase_context.PhaseConfig`** stays unchanged — phase-aware retrieval is orthogonal to scope-aware retrieval. They compose.
- **Invariant:** no code path in `tinyassets/retrieval/*` issues a query without a `MemoryScope`. Enforce with a type signature, not documentation. `RetrievalRouter.query(..., scope: MemoryScope)` — no default.
- **Double-check layer:** after results return, a thin assertion in the router drops any row whose `universe_id` doesn't match `scope.universe_id` and logs a loud warning. Cheap and catches bugs that slip past the WHERE clause (e.g. someone bypasses the router).

## 4. What breaks if we skip this

Concrete failure modes, all path-based-isolation is a single point of failure:

1. **Singleton bleed.** `runtime.knowledge_graph` is a module-global (`tinyassets/memory/archival.py:120`). If the daemon switches universes mid-process without resetting the singleton, queries hit the wrong DB. No row-level tag catches this.
2. **Test-fixture contamination.** `reset_db()` exists in `vector_store.py:52` specifically because test suites hit this. Production gets no `reset_db`.
3. **Future feature: cross-universe tools.** The moment one workflow reads from two universes (a "compare-universes" node, a benchmarking tool, a moderator dashboard), path-isolation stops working by design — but we'll already have added the reads, and row-level tags are the only way to filter after.
4. **Archival shard consolidation.** If we ever move to a shared archival store (cheaper than N SQLite files, easier to back up, easier to snapshot atomically), path-isolation is gone. Row tagging now makes that migration a config flip, not a rewrite.
5. **MCP HARD RULE enforcement.** The MCP connector promises universe isolation per tool response. Today, that promise is backed by "we passed the right path" — a convention, not an invariant. Row tags let the MCP layer *verify* the promise before serving results.
6. **Debug Chrome / multi-universe sessions.** A single Claude Code session that has both `sporemarch` and `ashwater` in context is one misrouted query from canon bleed. Row tags turn this from "silently wrong" into "loudly filtered."

## 5. Migration cost + rollback

**Cost (low):**
- Schema migration: ~1-2 hrs dev, one-shot ALTER TABLE per DB, backfill from parent dir name.
- Write sites: every `KnowledgeGraph.add_*` and `VectorStore.index` takes a `universe_id` arg (threaded through from existing constructor-time `universe_id`, which all callers already hold). Touch-points are bounded — KG has ~6 writer methods, vector store has one.
- Read sites: RetrievalRouter signature change. Every caller (`agentic_search`, any direct callers) updated to pass scope. Type checker catches missing args.
- Tests: ~40 tests touch the KG/vector fixtures; most take a `universe_id` fixture already.

**Rollback:** the `universe_id` column with a NOT NULL default of `"default"` is backward-compatible with any forgotten read site — queries that don't filter still return rows. Rollback is "stop filtering"; the data stays correct.

**Risk:** PK expansion on `entities` (to `(universe_id, entity_id)`) is the one migration that can't be rolled back cleanly — the schema change is structural. Mitigation: keep `entity_id` as a secondary unique index within a universe; don't drop the old PK until a full release cycle has passed.

## 6. PLAN.md alignment

- `## Retrieval And Memory` (PLAN.md L144): "Retrieval and memory are one system with multiple backends... routing policy matters more than any individual backend." Row-tagging strengthens the routing policy without adding a backend.
- `## Multiplayer Daemon Platform` (PLAN.md L102): "Separate identity from runtime... per-universe host dashboards." Path-only isolation is a runtime coupling; row-tagging is an identity property that survives runtime consolidation.
- No principle conflict. Reinforces existing invariants.

## 7. Recommendation

**Ship it, but in two stages.**

1. **Stage 1 (low risk, high leverage):** Thread `MemoryScope` through `agentic_search` → `RetrievalRouter` and enforce a post-query `universe_id` assertion that logs+drops mismatched rows. This is pure defensive code — no schema change, no migration. It catches the singleton-bleed class of bugs immediately.
2. **Stage 2 (schema change):** Add `universe_id` column + migration + write-site threading. Ship behind a flag; verify on sporemarch and ashwater; flip default.

Stage 1 proves the interface without touching storage. Stage 2 earns its keep only if Stage 1's assertion fires in practice or if the cross-universe-tools roadmap lands. If Stage 1 never fires in 30 days of real use, Stage 2 is a judgment call: cheap insurance vs. scaffolding a smarter model doesn't need.

## Open questions for host

1. Is per-universe `knowledge.db` the long-term plan, or are we moving to a shared archival store? (Answer changes urgency of Stage 2.)
2. Should `ScopedMemoryRouter.store()` — currently a placeholder — get finished as part of this work, or remain deferred?
3. Flag name for Stage 2? `TINYASSETS_ROW_SCOPED_ARCHIVAL`?

# Memory-Scope Stage 2b — Execution Plan

**Status:** Design resolved 2026-04-16 (navigator + lead on §9.2 defaults). Promotion-ready; dev claims when task #4 is picked up.
**Design reference:** `docs/design-notes/2026-04-15-memory-scope-tiered.md` §3 (MemoryScope redesign), §4 (write/read-site behavior), §9.3 (resolution block).
**Depends:** Stage 2a (`969b9c3` — schema + universe_acl + node_scope loader) — **landed**.
**Flag:** `TINYASSETS_TIERED_SCOPE` (gates enforcement; off until Stage 2c).
**Scope boundary:** Interface reshape + write-site threading. **No enforcement flip** (that's 2c). Stage 2b must be semantically a no-op when the flag is off.

## Goal

Reshape `MemoryScope` to the 5-tier orthogonal-composition model and thread it through every archival write site so rows get tagged with the full scope at insert time. After 2b, rows carry scope metadata but reads still return at broadest scope (no new filtering). 2c flips the predicate on.

## Non-goals

- No predicate enforcement on reads (that is 2c).
- No change to Stage 1's post-query assertion beyond extending its field list.
- No node-scope manifest loader rewrite — Stage 2a already shipped `tinyassets/memory/node_scope.py`.
- No removal of the existing `author_id` / `session_id` fields until the rename (§Compatibility).

## 1. `MemoryScope` redesign (`tinyassets/memory/scoping.py`)

Per design-note §3. Target shape:

```python
@dataclass(frozen=True)
class MemoryScope:
    universe_id: str              # REQUIRED
    goal_id: str | None = None
    branch_id: str | None = None
    user_id: str | None = None
    node_scope: NodeScope | None = None

@dataclass(frozen=True)
class NodeScope:
    universe_member: bool = True
    breadth: Literal["full_canon", "narrow_slice"] = "full_canon"
    slice_spec: SliceSpec | None = None
    external_sources: list[ExternalSource] | None = None

@dataclass(frozen=True)
class SliceSpec:
    entity_ids: list[str] | None = None
    relation_types: list[str] | None = None
    document_ids: list[str] | None = None

@dataclass(frozen=True)
class ExternalSource:
    kind: Literal["universe", "external_api", "system_tool", "cross_universe_join"]
    identifier: str
```

### Compatibility

- **`author_id` and `session_id` are removed** per design §3 ("Author/session deleted. Author collapses into `user_id` …; session collapses into node execution"). Before removal: audit all callers. The Author→Daemon rename plan (`2026-04-15-author-to-daemon-rename.md`) owns the content-authorship side; memory-scope owns the agent-runtime side. `author_id` in `MemoryScope` refers to the runtime, so it goes away here.
- **Replace `contains`/`narrow`/`overlaps`/`broaden` nested-narrowing API** with orthogonal-composition helpers (design §3 "Orthogonal composition, not nested narrowing"). Dev may keep the old method names for the transition as thin shims — but the underlying semantics must be predicate-conjunction, not path-containment. Remove shims in 2c.
- **`ScopeResolver.resolve_effective_scope` / `can_write`** need rewriting to the orthogonal model. A new `compose_predicate(scope) -> dict` helper returns the per-tier filter dict (the `WHERE` fragment in design §4 "Read-site behavior").

## 2. Write-site threading

Every archival write path must accept a `MemoryScope` argument and populate the four scope columns from it. Scope columns already exist on the tables (Stage 2a shipped the schema).

### Sites to thread

| File | Function(s) | Notes |
|---|---|---|
| `tinyassets/knowledge/knowledge_graph.py` | `add_entity` (L186), `add_edge` (L263), `add_facts` (L338) | Already has `universe_id` threading from Stage 1. Extend to `goal_id`/`branch_id`/`user_id`. `INSERT INTO entities/edges/facts` statements need the new columns. |
| `tinyassets/retrieval/vector_store.py` | `index` (L128) | LanceDB `prose_chunks` seeded with scope fields in Stage 2a (defaults `""`). Populate from caller's scope at index time. |
| `tinyassets/memory/episodic.py` | `store_summary` (L112), `store_fact` (L171), `store_observation` (L264), `store_reflection` (L308) | Scope columns need adding to episodic tables (`scene_summaries`, `episodic_facts`, `style_observations`, `reflections`) — **check whether Stage 2a covered these; if not, schema-migration is in-scope for 2b**. Design §4 only names "archival tables"; episodic may or may not be "archival." Navigator call: include episodic in 2b to keep the write-site surface coherent. |
| `tinyassets/ingestion/indexer.py` | `index_text` (L23) | Upload entry point. Calls `kg.add_entity`, `kg.add_edge`, `kg.add_facts`, `vector_store.index` (L186/L194/L208/L268/L302). Must accept and forward a `MemoryScope`. |

### Call-site updates

Every caller of the above sites passes a `MemoryScope`. Primary call-sites (grep surface):

- `tinyassets/universe_server.py` — ingestion tool-call paths.
- `tinyassets/author_server.py` — writer commit path emitting fact packets.
- `tinyassets/graph_compiler.py` — node-level memory writes.
- `tinyassets/evaluation/structural.py` — eval-time writes (if any).
- `tinyassets/desktop/launcher.py` — seeding paths.

Dev enumerates the actual list via `grep -rn 'add_entity\|add_edge\|add_facts\|vector_store\.index\|episodic\.store_'` once work begins. Design note §4 says "every archival write site accepts a `MemoryScope`"; the list above is the starting set, not exhaustive.

## 3. Stage-1 assertion extension

Stage 1 shipped `assert_scope_match(row, caller_scope)` for `universe_id` only. Extend to check all four scope columns when present on the row (design §4 "Read-site behavior"). Warn-and-drop behavior stays (hard-fail comes in 2c). Zero assertion fires post-2b is an acceptance criterion for 2c flag-flip.

## 4. Flag gating

`TINYASSETS_TIERED_SCOPE`:
- **Off (default in 2b):** write sites still tag rows with scope. Reads ignore scope columns (broadest-visibility semantics, same as today). Assertion runs in warn mode.
- **On (2c):** reads filter by composed predicate. Assertion hard-fails. Private universes reject cross-universe reads at Layer 1.

In 2b, ensure the flag gates only the read-side filtering — writes always tag rows regardless of flag state, so when 2c flips the flag, rows already have correct scope.

## 5. Testing

- **Unit:** `tests/test_memory_scoping.py` rewritten to the orthogonal model; add tests for `compose_predicate`, `NodeScope.universe_member=False` with `external_sources`, `breadth=narrow_slice` with `slice_spec`.
- **Integration:** a fantasy-universe test fixture that runs a full ingestion + query cycle, asserts rows land with correct scope columns.
- **Private-universe fixture:** a test universe with `universe_acl` rows, asserts Layer 1 rejection path exists (even though flag is off — the ACL function is testable independently).
- **Regression:** full test suite pre- and post-change. 2b must not shift any existing test behavior when `TINYASSETS_TIERED_SCOPE=0`.

## 6. Shape + stages

Roughly three dev sessions, in order:

- **2b.1 — API reshape.** Rewrite `scoping.py` to the new dataclasses + helpers. All call-sites adapter-updated (old 5-tier field shape → new 5-tier field shape). Tests green.
- **2b.2 — Write-site threading.** Thread `MemoryScope` through KG + vector + episodic + ingestion write sites. New rows carry scope columns.
- **2b.3 — Assertion + flag wiring.** Extend Stage-1 assertion. Wire `TINYASSETS_TIERED_SCOPE` as a read-side gate (does nothing in 2b when off).

If 2b.1 turns out larger than one session (likely — author_id removal has reach), split it further rather than bundling.

## 7. Acceptance criteria

- [ ] `MemoryScope` has the §3 shape; old nested-narrowing API is either removed or shimmed with new semantics.
- [ ] All write sites in §2 accept and use `MemoryScope`.
- [ ] New writes populate all four scope columns (NULL allowed for tiers the caller doesn't specify).
- [ ] Stage-1 assertion checks all four columns.
- [ ] Full test suite green with `TINYASSETS_TIERED_SCOPE=0`.
- [ ] Zero behavioral change for current fantasy-author usage (checked via sporemarch + ashwater test runs).
- [ ] `docs/exec-plans/active/2026-04-16-memory-scope-stage-2b.md` moved to `landed/` after merge.

## 8. Open questions for dev

- **Episodic scope columns — migrate in 2b or defer?** Navigator recommends 2b (coherence). If dev prefers to defer, raise to lead.
- **`author_id` removal timing — coordinate with Author→Daemon rename?** The two plans touch overlapping surface. Recommend: 2b removes `author_id` from `MemoryScope` (runtime concept); the rename plan handles `author_id` on content rows (authorship concept). They are independent but should land close in time.
- **`compose_predicate` return type — dict vs SQLAlchemy-style fragment?** Dev's call. Dict is simpler; fragment composes better with existing query builders. Navigator weakly prefers dict for Stage 2b, revisit in 2c.

## 9. Out-of-scope (deferred to 2c)

- Read-side predicate enforcement.
- Private-universe ACL hard-rejection wired into read paths.
- Narrow-slice retrieval narrowing.
- Stage-1 assertion hard-fail mode.
- Flag-flip.

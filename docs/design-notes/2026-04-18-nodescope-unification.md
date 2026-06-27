---
status: active
---

# NodeScope Unification — `node_scope.py` + `scoping.py`

**Date:** 2026-04-18
**Author:** navigator
**Status:** Scoping. Implementation sequences after Stage 2c flag flip (monitoring started 2026-04-16, 30-day clean required). Read-only research.
**Relates to:** STATUS.md concern "Dual NodeScope hierarchies" (2026-04-16). Memory-scope Stage 2a/2b/2c.

---

## 1. What each file does today

**`tinyassets/memory/node_scope.py` (277 lines, Stage 2a).** Disk-side manifest loader. Parses `node_scope.yaml` sidecars into frozen tuple-based dataclasses. Types: `SliceSpec` (tuple-of-str), `ExternalSource` (plain `kind: str`), `NodeScopeEntry` (per-node config), `NodeScopeManifest` (branch-level collection with `default` + `nodes: dict[str, NodeScopeEntry]`). Ships the parser + validation errors; zero runtime integration.

**`tinyassets/memory/scoping.py` (356 lines, Stage 2b).** Runtime scope hierarchy. Types: `SliceSpec` (list-of-str, lowercase `None` default), `ExternalSource` (`Literal[...]` on `kind`), `NodeScope` (runtime dataclass — same conceptual fields as `NodeScopeEntry` minus the `for_node` dispatch), `MemoryScope` (5-tier: universe/goal/branch/user/node), `ScopedQuery`, `ScopeResolver`, `ScopedMemoryRouter`. Consumed by 14+ runtime sites — KG, retrieval router, vector store, agentic search, episodic memory, knowledge_graph, plus domain phases.

## 2. Where they overlap vs diverge

**Duplicated primitives:**

| Type | `node_scope.py` (2a) | `scoping.py` (2b) |
|---|---|---|
| `SliceSpec` | `tuple[str, ...]`, frozen, `is_empty()` helper, `None` means "not a narrow slice" | `list[str] \| None`, frozen, no helper, `None` on a field means "no constraint" |
| `ExternalSource` | `kind: str` with frozenset validator at parse time | `kind: Literal["universe","external_api","system_tool","cross_universe_join"]` enforced by type checker |
| "NodeScope"-ish | `NodeScopeEntry` — YAML-loaded, validated at parse | `NodeScope` — runtime-built, validated in `__post_init__` |

**Non-overlap:**

- 2a manifest collection (`NodeScopeManifest.for_node`) has no 2b equivalent — 2b receives a single `NodeScope` already resolved for the executing node.
- 2b `MemoryScope` / `ScopedQuery` / `ScopeResolver` / `ScopedMemoryRouter` have no 2a counterpart — they're the tier composition surface the loader never reached.

**Asymmetry that matters:** 2a's manifest loader has exactly 1 import site (`tests/test_memory_scope_stage_2a.py`). 2b's `MemoryScope` has ~14 runtime imports. The loader exists but isn't wired — the runtime synthesizes `NodeScope` inline rather than consulting the manifest. The duplication is two almost-identical models living in parallel because 2b got built before 2a got integrated.

## 3. Proposed unified shape

**Keep `scoping.py` as canonical runtime.** Its consumers are numerous and its type shapes (Literal kinds, None-sentinel semantics) match how the rest of the codebase composes.

**Re-home the loader.** `node_scope.py` becomes a thin parser that produces `scoping.NodeScope` instances directly — no parallel `NodeScopeEntry` type. Proposed module shape:

```python
# tinyassets/memory/node_scope.py (post-unification)
from workflow.memory.scoping import NodeScope, SliceSpec, ExternalSource

MANIFEST_FILENAME = "node_scope.yaml"

@dataclass(frozen=True)
class NodeScopeManifest:
    default: NodeScope = field(default_factory=NodeScope)
    nodes: dict[str, NodeScope] = field(default_factory=dict)
    def for_node(self, node_id: str) -> NodeScope: ...

def load_manifest(path) -> NodeScopeManifest: ...
def parse_manifest(text, *, where) -> NodeScopeManifest: ...
```

**Shape decision: `scoping.py`'s `list | None` wins over tuple.** The 14 runtime sites already use list-based predicate composition and None-sentinel for "no constraint." Converting runtime to tuple is a bigger blast radius than converting the 2a loader's internal storage to list. The immutability win from tuples is nice-to-have; the runtime-site count is decisive.

**Loader-side tightening stays.** Parse-time validation (frozenset check on `kind`, required `slice_spec` on narrow_slice, required `external_sources` on non-member) moves into the parser functions, producing already-validated `NodeScope` objects. The 2b `__post_init__` invariants in `scoping.py:95-105` become a second line of defense — same checks, belt-and-braces.

## 4. Migration cost + surface

**Readers:** zero runtime change. All 14 sites import from `scoping.py`; they keep doing so.

**Writers:** only the 2a loader (`node_scope.py`) changes. Internal primitives swap from `NodeScopeEntry` / local `SliceSpec` / local `ExternalSource` to `scoping.NodeScope` / `scoping.SliceSpec` / `scoping.ExternalSource`. ~40 lines of diff in the parser functions.

**Tests:** `test_memory_scope_stage_2a.py` (the 1 import site) re-targets to `scoping` types. All existing test cases should pass unchanged semantically — same validation rules, same field names, just tuple→list on `SliceSpec`.

**Docs:** Memory-scope design note §4 references need a pass. Indicates unification as the follow-through on Stage 2a's loader-then-integrate plan.

**Total: ~0.5 dev-day.** Small, self-contained, low-risk.

## 5. Sequence against Stage 2c flag flip

**Wait for 2c.** The clock started 2026-04-16 and requires 30 clean days before flip. Unifying during that window risks conflating unification bugs with predicate-enforcement bugs — if a Stage-1 assertion fires in the monitoring window, it should be trivially attributable to scope-tier misalignment, not "did the type refactor break it?"

**Land the unification 1–2 weeks AFTER flag flip stabilizes.** By that point:
- The runtime shape in `scoping.py` is battle-tested at flip-time — can confidently adopt as canonical.
- Loader integration (making `node_scope.yaml` actually feed the runtime) becomes the follow-up work, which unification unlocks.

**Do not bundle with 2c flag flip itself.** Keep 2c scope narrow: predicate enforcement on/off. Unification is a separate concern — sequence after, not during.

---

## 6. Sources

- `tinyassets/memory/node_scope.py` (277 lines, Stage 2a loader).
- `tinyassets/memory/scoping.py` (356 lines, Stage 2b runtime).
- `tests/test_memory_scope_stage_2a.py` — sole 2a import site.
- `docs/design-notes/2026-04-15-memory-scope-tiered.md` §4 (manifest design), §9.3 Q4-Q5 (SliceSpec + ExternalSource shape resolutions).
- STATUS.md work row #19 (2c flag-flip monitoring, 2026-04-16 start).
- Runtime import map: knowledge_graph.py:22, retrieval/router.py:25, retrieval/vector_store.py:18, retrieval/agentic_search.py:15, memory/episodic.py:19, ingestion/indexer.py:18, domains/fantasy_daemon/phases/{commit,worldbuild}.py, +packaging mirror (5 more).

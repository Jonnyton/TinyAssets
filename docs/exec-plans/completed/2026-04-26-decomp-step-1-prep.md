---
title: Task #8 prep — universe_helpers extraction scope
date: 2026-04-26
author: dev
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §5.1, §8 step 1
target_task: #8 — Extract tinyassets/api/universe_helpers.py
---

# Task #8 pre-flight scope

Read-only scope analysis run while #8 was blocked by Task #4 dirty `universe_server.py`. Cuts the eventual implementation to a 30-min job (no re-discovery cost when the file unblocks).

---

## 1. Audit-vs-reality verdict

**Stale on the partial-extraction state.** The audit lists 8 helpers needing extraction to a new `tinyassets/api/universe_helpers.py`. **5 of those 8 already live in `tinyassets/api/helpers.py`** (extracted in a prior Bundle 1 pass — see header comment of `helpers.py`):

| Helper | Audit says | Reality |
|---|---|---|
| `_base_path` | extract to universe_helpers.py | DONE — lives in `tinyassets/api/helpers.py` |
| `_universe_dir` | extract to universe_helpers.py | DONE — lives in `tinyassets/api/helpers.py` |
| `_default_universe` | extract to universe_helpers.py | DONE — lives in `tinyassets/api/helpers.py` |
| `_read_json` | extract to universe_helpers.py | DONE — lives in `tinyassets/api/helpers.py` |
| `_read_text` | extract to universe_helpers.py | DONE — lives in `tinyassets/api/helpers.py` |
| `_find_all_pages` | extract to universe_helpers.py | NOT extracted — inline at universe_server.py:12152 |
| `_wiki_pages_dir` | extract to universe_helpers.py | NOT extracted — inline at universe_server.py:12080 |
| `_wiki_drafts_dir` | extract to universe_helpers.py | NOT extracted — inline at universe_server.py:12084 |

**The audit is also slightly off on naming.** The prior pass used `tinyassets/api/helpers.py`, not `tinyassets/api/universe_helpers.py`. Continuation should match the existing name unless the lead wants a rename.

---

## 2. Remaining helpers — line ranges + signatures

All 3 remaining helpers cluster in the wiki preamble of `universe_server.py`:

| Helper | Line | Signature | Body |
|---|---|---|---|
| `_wiki_pages_dir` | 12080 | `() -> Path` | `return _wiki_root() / "pages"` |
| `_wiki_drafts_dir` | 12084 | `() -> Path` | `return _wiki_root() / "drafts"` |
| `_find_all_pages` | 12152 | `(directory: Path) -> list[Path]` | `if not dir.is_dir(): return []; return sorted(p for p in directory.rglob("*.md") if p.is_file())` |

**Cross-helper internal references:**
- `_wiki_pages_dir` calls `_wiki_root()`.
- `_wiki_drafts_dir` calls `_wiki_root()`.
- `_find_all_pages` is pure (no project dependencies).
- `_wiki_root` (universe_server.py:12072) calls `workflow.storage.wiki_path()` — leaf dependency, no cycle risk.

---

## 3. Call-site counts (universe_server.py only)

Symbol-by-symbol grep counts in current canonical `tinyassets/universe_server.py`:

| Symbol | call-sites |
|---|---|
| `_base_path` | 173 |
| `_universe_dir` | 30 |
| `_default_universe` | 28 |
| `_read_text` | 20 |
| `_read_json` | 19 |
| `_wiki_drafts_dir` | 16 |
| `_wiki_pages_dir` | 14 |
| `_wiki_root` | 11 |
| `_find_all_pages` | 9 |

The 5 already-extracted helpers ARE NOT removed from universe_server.py — they're imported at L184-190 from `workflow.api.helpers`. Call-sites still write `_base_path()` etc., resolved via the module-level import.

---

## 4. External importers (cross-module, before #8)

| Importer | Line | Symbol(s) imported via `from workflow.universe_server import ...` |
|---|---|---|
| `tests/test_data_dir_resolver.py` | 181 | `_base_path` (works because universe_server imports it from helpers — accessible as a module attr) |
| `tests/test_wiki_path_resolver.py` | 137 | `_wiki_root` (defined inline in universe_server.py) |
| `docs/audits/2026-04-25-engine-domain-api-separation.md` | 145 | mentions intent to import `_universe_dir, _default_universe, _read_json` |

`workflow.api.helpers` direct-importers (after Bundle 1):

| Importer | Line | Notes |
|---|---|---|
| `tinyassets/universe_server.py` | 184 | Bundle 1 import |
| `tinyassets/api/__init__.py` | 17 | re-exports from package surface |
| `tests/test_api_helpers.py` | 9 | dedicated test file (178 LOC) — covers the 5 extracted helpers |
| (packaging mirrors of the above) | — | parallel state |

---

## 5. Extraction risks the audit didn't anticipate

1. **Naming consistency.** The audit prescribes `tinyassets/api/universe_helpers.py`, but the existing partial extraction is `tinyassets/api/helpers.py`. Three options:
   - (A) Add the 3 remaining helpers to `tinyassets/api/helpers.py` (extends existing module, no rename).
   - (B) Rename `tinyassets/api/helpers.py` → `tinyassets/api/universe_helpers.py` (matches audit, 4 file edits + tests).
   - (C) Create `tinyassets/api/wiki_helpers.py` for the 3 wiki-adjacent helpers (semantic split, leaves `helpers.py` for path/IO basics).

   Recommendation: **(A)** — smallest diff, no rename churn, defers the naming question. The 3 wiki-adjacent helpers are cheap to extract again into their own module if `wiki.py` extraction (Task #9) wants it.

2. **`_wiki_root` is referenced by `tests/test_wiki_path_resolver.py:137`.** If `_wiki_root` moves out of universe_server.py too, that test breaks unless the move preserves a re-export. The audit only lists the 8 helpers, not `_wiki_root`. Recommendation: include `_wiki_root` in the same extraction since the 2 directory helpers depend on it — otherwise we'd have `_wiki_pages_dir` in `helpers.py` calling `_wiki_root` still in `universe_server.py` (cyclical-import risk).

3. **`_wiki_pages_dir` and `_wiki_drafts_dir` are also used inside `_resolve_page` and other wiki-only functions** that will themselves move out as part of Task #9 (`wiki.py` extraction). After #9 lands, the 2 directory helpers might move ENTIRELY into `wiki.py` if no other submodule consumes them. Audit §5.1 lists them as "used by branches.py + wiki.py" — branches.py uses `_find_all_pages` for `_related_wiki_pages`, but the 2 dir helpers' branches.py usage is implicit (through `_find_all_pages(_wiki_pages_dir())` patterns).

   Recommendation for #8: extract all 3 (plus `_wiki_root`) to `helpers.py` for now. Re-evaluate after #9 lands whether `_wiki_pages_dir`/`_wiki_drafts_dir` should re-collapse into `wiki.py` if branches.py doesn't actually call them directly.

4. **No domain logic in any of these 3 helpers** — they're pure path operations. Domain-extraction concerns from the companion engine/domain audit do not apply. Safe to move regardless of domain extraction sequencing.

5. **Pre-commit canonical-vs-plugin parity check.** Per memory `feedback_run_build_plugin_after_canonical_edits`, after editing `tinyassets/universe_server.py` and creating `tinyassets/api/helpers.py` extension, must run `python packaging/claude-plugin/build_plugin.py` so the plugin runtime mirror matches.

6. **If naming option (B) is chosen** — renaming `helpers.py` → `universe_helpers.py` — the 4 importers + the file itself need synchronized edits. The plugin runtime mirror also has its own `tinyassets/api/helpers.py` copy (`packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/helpers.py`) — `build_plugin.py` resyncs it.

---

## 6. Concrete Task #8 implementation plan (option A)

Smallest viable diff. Estimated wall time: 20-30 min.

1. **Read `tinyassets/api/helpers.py`** (already done — 90 LOC, listed above).
2. **Add 4 helpers to `helpers.py`:** `_wiki_root`, `_wiki_pages_dir`, `_wiki_drafts_dir`, `_find_all_pages`. Add to `__all__`. Preserve docstrings + behavior verbatim.
3. **Update universe_server.py:**
   - Extend the existing `from workflow.api.helpers import (...)` block at L184 to include the 4 new symbols.
   - Delete the inline definitions at L12072-12077, L12080-12081, L12084-12085, L12152-12156. (Net: ~16 lines removed from universe_server.)
   - Move comment at L12076-77 about the `r"C:\..."` pre-2026-04-20 fallback into `helpers.py` `_wiki_root` docstring (preserves the historical context).
4. **Update `tinyassets/api/__init__.py`:** add the 4 new symbols to the re-export list at L17 if appropriate (currently only re-exports the path/IO basics).
5. **Add tests to `tests/test_api_helpers.py`:** smoke tests for each of the 4 new helpers.
6. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
7. **Verification:** `pytest tests/test_api_helpers.py tests/test_wiki_path_resolver.py tests/test_data_dir_resolver.py` → green; ruff on touched files → clean.

**Files in the eventual #8 SHIP handoff:**
- `tinyassets/api/helpers.py` (extended)
- `tinyassets/api/__init__.py` (re-exports updated, optional)
- `tinyassets/universe_server.py` (4 inline defs → import)
- `tests/test_api_helpers.py` (new tests)
- `packaging/claude-plugin/.../tinyassets/api/helpers.py` (mirror)
- `packaging/claude-plugin/.../tinyassets/api/__init__.py` (mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

7 files, all cleanly diff-able, total est. +60 / -30 LOC.

---

## 7. What this prep does NOT cover

- Tasks #9 (wiki.py extraction) and #10 (status.py extraction) are blockedBy #8. Their pre-flight scoping is a separate exercise.
- The 23-importer fan-in analysis from audit §7 is only relevant when the residual `universe_server.py` shim shape is finalized — out of scope for #8.
- The big-picture FastMCP integration shell question (Pattern A vs B) from audit §6 is settled: Pattern A. Reaffirmed by current state of `tinyassets/api/__init__.py` which uses the single-mcp pattern.

---

## 8. Decision asks for the lead

Before #8 dispatch, the lead should pick:
- **Naming:** option (A) extend `helpers.py`, (B) rename to `universe_helpers.py`, or (C) split into `wiki_helpers.py`?
- **Include `_wiki_root` in #8?** Recommended yes (else cycles), but adds 1 helper beyond audit list.
- **Update `tinyassets/api/__init__.py` re-exports?** Tests don't currently import the 4 new helpers via the package surface — `__init__.py` re-exports may not be load-bearing yet.

## 8a. Decisions (2026-04-26 by team-lead)

1. **Naming → option (A):** extend existing `tinyassets/api/helpers.py`. Add an "ADDED 2026-04-26" comment block in the header noting the wiki-adjacent batch. Audit doc gets updated post-#8 by navigator to reflect actual file layout.
2. **Include `_wiki_root` → yes.** 4 helpers total: `_find_all_pages`, `_wiki_pages_dir`, `_wiki_drafts_dir`, `_wiki_root`.
3. **`tinyassets/api/__init__.py` re-exports → no change.** Verified post-decision: `tests/test_wiki_path_resolver.py:137` imports `_wiki_root` via `from workflow.universe_server import _wiki_root`, and `tests/test_data_dir_resolver.py:181` imports `_base_path` the same way. Both rely on the `from workflow.api.helpers import (...)` block in universe_server.py making the helpers accessible as module attributes — that pattern preserves back-compat without exposing new symbols on the `workflow.api` package surface.

**Gate:** Task #8 must NOT begin until verifier ships Tasks #4 + #6 and lead commits them — `tinyassets/universe_server.py` is currently dirty from #4. Implementation is the 20-30 min job described in §6 above.

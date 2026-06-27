---
title: Task #9 prep — tinyassets/api/wiki.py extraction scope
date: 2026-04-26
author: dev
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.2 (`wiki.py`), §8 step 2
target_task: #9 — Extract tinyassets/api/wiki.py (decomp audit step 2)
gates_on: #8 ships first; #9 inherits universe_server.py's already-modified preamble + helper imports.
---

# Task #9 pre-flight scope

Read-only scope for extracting the wiki subsystem from `tinyassets/universe_server.py` into a new `tinyassets/api/wiki.py`. Same freshness-check protocol as #8 prep — verify audit prescription against current code before trusting the spec.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§3.1):** wiki LOC ~1,312, line range 11,268–12,580, single inline dispatch.

**Reality (current code, 2026-04-26):**
- Wiki banner at L12031 (`# TOOL 4 — Wiki`).
- Constants/helpers (`_WIKI_CATEGORIES`, `_STOP_WORDS`, path helpers, scaffold, similarity) L12040–12296.
- `@mcp.tool()` decorator L12297.
- `def wiki(...)` MCP entry L12308.
- Dispatch table inside `wiki()` body — actions: read/search/list/lint/write/consolidate/promote/ingest/supersede/sync_projects/file_bug/cosign_bug.
- `_wiki_*` action implementations L12509–13561.
- `_BUGS_CATEGORY` + bug-filing constants L13164–13169.
- `_wiki_cosign_bug` L13339, `_wiki_file_bug` L13425.
- Section ends L13602 (just before `@mcp.tool` for `get_status` at L13604).

**Total lines (banner → end of section): L12031 → L13602 = 1,572 LOC.** Audit estimate (~1,312) was about 19% low — the bug-filing helpers (`_wiki_file_bug`, `_wiki_cosign_bug`, kind/severity constants) added since the audit account for the delta.

**Audit was NOT stale on the basics:** wiki section is contiguous, has not been partially extracted, all symbols still inline. The §5.2 audit recommendation "wiki helpers move with primary consumer" already implies this.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Constants + globals
| Symbol | Line | LOC |
|---|---|---|
| `_WIKI_CATEGORIES` | 12040 | 13 (tuple) |
| `_STOP_WORDS` | 12053 | 6 (frozenset) |
| `_logger_wiki` | 12061 | 1 |
| `_BUG_ID_RE` | 13164 | 1 |
| `_BUGS_CATEGORY` | 13165 | 1 |
| `_KIND_FEATURES_DIR` / `_KIND_DESIGNS_DIR` / `_KIND_PATCH_REQUESTS_DIR` | 13166–13168 | 3 |
| `_VALID_SEVERITIES` | 13169 | 1 |

### 2.2 Path helpers (4 ARE already #8 candidates; rest stay inline to wiki.py)
| Helper | Line | Notes |
|---|---|---|
| `_wiki_root` | 12064 | Moves in #8 to `tinyassets/api/helpers.py`. After #8 lands, this is an import in wiki.py, not a def. |
| `_wiki_pages_dir` | 12080 | Moves in #8. |
| `_wiki_drafts_dir` | 12084 | Moves in #8. |
| `_wiki_raw_dir` | 12088 | Stays in wiki.py — only used by `_wiki_ingest`. |
| `_wiki_index_path` | 12092 | Stays in wiki.py — only used by `_wiki_read`/`_wiki_search`/`_add_to_index`. |
| `_wiki_log_path` | 12096 | Stays in wiki.py — only used by `_append_wiki_log`/`_wiki_read`. |

### 2.3 Wiki-internal helpers (all stay in wiki.py)
| Helper | Line | Used by |
|---|---|---|
| `_ensure_wiki_scaffold` | 12100 | `wiki()` entry, also imported by 2 tests |
| `_find_all_pages` | 12152 | Moves in #8. After #8, imported by wiki.py. |
| `_parse_frontmatter` | 12159 | `_wiki_search`/`_wiki_consolidate`/`_wiki_lint`/`_wiki_promote`/`_wiki_supersede` |
| `_page_rel_path` | 12172 | `_wiki_search`/`_wiki_read`/`_wiki_list`/`_wiki_consolidate` |
| `_resolve_page` | 12180 | `_wiki_read` |
| `_extract_keywords` | 12208 | `_wiki_similarity_score` |
| `_wiki_similarity_score` | 12214 | `_wiki_consolidate` + (audit hint) `_wiki_file_bug` similarity check |
| `_add_to_index` | 12241 | `_wiki_promote` |
| `_append_wiki_log` | 12280 | most wiki actions |
| `_sanitize_slug` | 12291 | `_wiki_write`/`_wiki_promote`/`_wiki_supersede` |

### 2.4 Action handlers (all move to wiki.py)
| Handler | Line | LOC |
|---|---|---|
| `_wiki_read` | 12509 | ~30 |
| `_wiki_search` | 12538 | ~50 |
| `_wiki_list` | 12588 | ~35 |
| `_wiki_write` | 12623 | ~72 |
| `_wiki_consolidate` | 12695 | ~80 |
| `_wiki_promote` | 12776 | ~73 |
| `_wiki_ingest` | 12849 | ~25 |
| `_wiki_supersede` | 12874 | ~78 |
| `_wiki_lint` | 12952 | ~100 |
| `_wiki_sync_projects` | 13052 | ~100 |
| `_wiki_cosign_bug` | 13339 | ~85 |
| `_wiki_file_bug` | 13425 | ~140 |

### 2.5 Public MCP tool
| Symbol | Line | Notes |
|---|---|---|
| `@mcp.tool(...)` decorator | 12297 | needs `mcp` instance — see §4 below |
| `def wiki(...)` | 12308 | ~190 LOC of args + dispatch |

---

## 3. Cross-references — does #9 depend on #10 symbols (or vice versa)?

**No bidirectional dependency.** Status section (`get_status` + helpers) starts at L13604 — entirely after wiki section ends L13602.

`get_status` does NOT call any `_wiki_*` symbols. `wiki()` does NOT call `get_status` or any `_action_run_routing_evidence` / `_policy_hash` helpers. Sections are cleanly separable.

**Indirect overlap — both depend on shared #8 helpers:** `_universe_dir`, `_default_universe`, `_base_path`, `_read_json`, `_read_text`, `_find_all_pages`, `_wiki_pages_dir`, `_wiki_drafts_dir`, `_wiki_root`. After #8 lands, both wiki.py and status.py import these from `tinyassets/api/helpers.py`. No circularity.

**Internal wiki ↔ wiki cross-helper refs are dense:** the 12 action handlers call ~10 internal helpers; all stay in wiki.py.

**One subtle dependency:** `_wiki_file_bug` calls `_wiki_similarity_score` for dedup (per memory `project_file_bug_dedup_at_filing`). Both move together — no extraction risk.

---

## 4. FastMCP `mcp` instance — same Pattern A as #8 audit §6

Per audit §6 + current `tinyassets/api/__init__.py` state: Pattern A (single `mcp` instance shared via decorator imports). New `wiki.py` will need to import `mcp` from a leaf module to avoid the `workflow.api → workflow.api.wiki → workflow.api` cycle.

**Recommendation:** Audit suggests creating `workflow.mcp_setup` as a leaf module. This is a Phase 0 dependency for ALL future submodule extractions (#9, #10, and the rest of the audit's 8-step plan). May be worth landing as a separate prep step before #9 to keep #9 focused.

**Alternative:** Inside wiki.py, do `from workflow.universe_server import mcp` — works today (mcp is defined inline in universe_server.py), but locks in the back-compat shim direction. Audit's preferred pattern is the leaf-module split.

**Decision needed for #9 dispatch:** lead picks (a) extract `mcp` to `workflow.mcp_setup` as #9 prereq, or (b) accept `from workflow.universe_server import mcp` in wiki.py.

---

## 5. Test files importing wiki symbols (and how)

All via `from workflow.universe_server import ...` — none via `workflow.api.wiki`:

| Test file | Symbol(s) imported | Count |
|---|---|---|
| `tests/test_wiki_path_resolver.py:137` | `_wiki_root` | 1 (already moves in #8 — relevance to #9: nil) |
| `tests/test_wiki_file_bug_dedup.py` (10 lines) | `wiki`, `_ensure_wiki_scaffold` | 10 |
| `tests/test_wiki_file_bug.py` (3 lines) | `wiki` | 3 |
| `tests/test_wiki_cosign_flow.py` | `wiki`, `_ensure_wiki_scaffold` | 3 |
| `tests/test_wiki_scaffold.py:16` | `_WIKI_CATEGORIES`, `_ensure_wiki_scaffold` | 1 (top-level) |
| `tests/test_describe_branch_wiki_pages.py` | `_related_wiki_pages` | 11 (NOT a wiki symbol — `_related_wiki_pages` lives at L5030, in branches.py territory; NOT moving in #9) |
| `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md:84` | `_wiki_file_bug` | 1 (doc-snippet, not real import) |

**Strategy:** All 17 production test imports go through `workflow.universe_server` namespace. Audit §7 Strategy 1 (keep universe_server as aggregator shim) preserves these unchanged. After #9 lands, `tinyassets/universe_server.py` adds:
```python
from workflow.api.wiki import (  # back-compat re-export
    wiki, _ensure_wiki_scaffold, _WIKI_CATEGORIES,
    _wiki_file_bug,  # for design-note ref + future direct imports
)
```
17 test imports continue to work; no test edits required for #9.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any wiki symbols already shipped to a submodule. **None found.** The wiki section is fully contiguous in universe_server.py with no in-flight extraction. Unlike #8 (where `helpers.py` already had 5 of 8 symbols extracted), #9 starts from a clean baseline.

The only wiki-adjacent partial move is the 4 path helpers landing in #8 (`_wiki_root`/`_wiki_pages_dir`/`_wiki_drafts_dir`/`_find_all_pages`). After #8 lands, those become `from workflow.api.helpers import (...)` lines at the top of wiki.py.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Constants + globals (§2.1) | ~25 |
| Wiki-internal helpers (§2.3, after #8 removes 4) | ~250 |
| Action handlers (§2.4) | ~870 |
| MCP tool def + dispatch (§2.5) | ~205 |
| Banner comments + section divider | ~20 |
| **Total moved out of universe_server.py** | **~1,370** |
| Back-compat re-export block added to universe_server.py | ~10 |
| **Net reduction in universe_server.py** | **~1,360** |
| New `tinyassets/api/wiki.py` size | **~1,400** (with imports) |

**Audit said ~1,312.** Reality ~1,370. Within 5% — audit's LOC estimate is actually closer than its symbol count.

---

## 8. Risks the audit didn't anticipate

1. **`_related_wiki_pages` at L5030 is OUT of scope for #9** — it's branches.py territory per audit §5.2 ("Move with primary consumer: `_related_wiki_pages` → branches.py, secondary importer wiki.py potentially"). Keep #9 from accidentally pulling it in. The 11 test references in `tests/test_describe_branch_wiki_pages.py` will move when branches.py extracts.

2. **`_wiki_similarity_score` is consumed by both `_wiki_consolidate` AND `_wiki_file_bug` dedup** — both stay in wiki.py, no problem. But audit §5.2 listed `_wiki_similarity_score` as wiki.py-only; reality matches.

3. **`mcp` instance import strategy** — see §4 above. This is the only blocking design decision for #9.

4. **Bug-filing kind constants (`_KIND_FEATURES_DIR`, etc.)** are at L13166-13168, separated from `_BUGS_CATEGORY` at L13165 only by line, but logically they're a unit. Move all 6 constants together.

5. **Pre-commit canonical-vs-plugin parity check** — same as #8. After editing universe_server.py + creating wiki.py, run `python packaging/claude-plugin/build_plugin.py`.

6. **`_wiki_file_bug` recently-edited surface area** — per memory `project_file_bug_dedup_at_filing` and Task #21 (in-flight per audit §8 sequencing constraints). If #21 is still in-flight when #9 dispatches, expect merge conflicts on `_wiki_file_bug`. **Verify task #21 status before claiming #9.** As of 2026-04-26 TaskList, no task #21 is open — likely landed.

---

## 9. Concrete Task #9 implementation plan

Estimated wall time: 60-90 min (larger than #8 because of the 17-test-import surface and the `mcp` instance question).

1. **Decision-point:** confirm `mcp` instance pattern (§4). If lead picks (a) leaf-module extraction, do that as a separate sub-step first. If (b), proceed with `from workflow.universe_server import mcp` inside wiki.py.
2. **Confirm #21 has landed** (or coordinate with anyone editing `_wiki_file_bug`).
3. **Confirm #8 has landed** (4 helpers extracted to `helpers.py` are import targets in wiki.py).
4. **Create `tinyassets/api/wiki.py`:**
   - Header: module docstring referencing audit + extraction date.
   - Imports: `from workflow.api.helpers import _wiki_root, _wiki_pages_dir, _wiki_drafts_dir, _find_all_pages, _base_path, _default_universe, _universe_dir, _read_json, _read_text` + the `mcp` instance per §4 decision.
   - Move all symbols from §2.1, §2.3, §2.4, §2.5 verbatim. Preserve docstrings + behavior.
5. **Update `tinyassets/universe_server.py`:**
   - Delete L12031–13602 (the wiki section).
   - Add back-compat re-export block at end of file or in a dedicated shim section:
     ```python
     # Phase-1 wiki extraction — back-compat re-exports for tests.
     from workflow.api.wiki import (  # noqa: F401
         wiki, _ensure_wiki_scaffold, _WIKI_CATEGORIES,
         _wiki_file_bug, _wiki_cosign_bug,
     )
     ```
6. **No test edits required** — re-export shim preserves the existing import paths.
7. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
8. **Verification:**
   - `pytest tests/test_wiki_*.py tests/test_get_status_primitive.py` → green.
   - `pytest -q` → full suite green.
   - `ruff check tinyassets/api/wiki.py tinyassets/universe_server.py` → clean.

**Files in eventual #9 SHIP handoff:**
- `tinyassets/api/wiki.py` (NEW, ~1,400 LOC)
- `tinyassets/universe_server.py` (~1,360 LOC removed + ~10 re-export shim added)
- `packaging/claude-plugin/.../tinyassets/api/wiki.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)
- Possibly `tinyassets/mcp_setup.py` (NEW leaf module) if §4 decision is (a).

5–6 files, +1,420 / -1,360 LOC net.

---

## 10. Decision asks for the lead

1. **`mcp` instance import strategy** — Pattern A1 (leaf-module `workflow.mcp_setup`) or Pattern A2 (`from workflow.universe_server import mcp` shim inside wiki.py)? (Audit favors A1; A2 is the smaller diff for #9 alone.)
2. **Bundle a back-compat re-export inside universe_server.py at #9 land** — same as Strategy 1 in audit §7? (Recommended yes — preserves 17 test imports without test edits.)
3. **Defer until #8 ships** — confirmed. #9 inherits #8's helpers extraction.

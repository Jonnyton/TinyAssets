---
title: Step 7 prep — tinyassets/api/market.py extraction scope
date: 2026-04-26
author: dev
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.5 (`market.py`), §8 step 7
target_task: Decomp audit Step 7 — Extract tinyassets/api/market.py
gates_on: Steps 1-6 ✅ landed (4f98654, 32b919c, ab61da5, 80108fb, 555712e, cdbafe3). Step 7 sequenced after Step 6 — both Steps 7 and 8 must serialize because both edit `tinyassets/universe_server.py`. After Step 7 SHIP, Step 8 (branches.py) follows immediately.
---

# Step 7 (`market.py`) pre-flight scope

Read-only scope for extracting the paid-market economy primitives — goals, gates, gate events, outcomes, attribution, escrow — from `tinyassets/universe_server.py` into a new `tinyassets/api/market.py`. Same freshness-check protocol as Steps 1-6 prep (audit prescription verified against current code; line numbers re-grepped post-Step-6).

---

## 1. Audit-vs-reality verdict

**Audit estimate (§4.5):** market.py LOC ~1,813. Audit lists scope: `goals()` MCP tool + `_GOAL_ACTIONS`, `gates()` MCP tool + `_GATES_ACTIONS` + `_GATE_EVENT_ACTIONS`, `_OUTCOME_ACTIONS`, `_ATTRIBUTION_ACTIONS`, `_ESCROW_ACTIONS`. Audit framing: "Groups the paid-market economy primitives together: goal graphs, gate ladders, real-world outcomes, remix attribution, escrow. These are logically one concern even if they have separate MCP tools."

**Reality (current code, 2026-04-26 post-Step-6):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| Escrow | `# ── Escrow MCP handlers ──` L7117 | L7117–L7224 | ~108 |
| Outcomes | `# ── Outcome event MCP actions ──` L7233 | L7233–L7384 | ~152 |
| Attribution | `# ── Attribution chain ──` L7387 | L7387–L7574 | ~188 |
| Goals (TOOL 3) | `# TOOL 3 — Goals` banner L7579–7581 | L7579–L8472 | ~894 |
| Gates (TOOL 3b) | `# TOOL 3b — Outcome Gates (Phase 6.1)` L8475–8477 | L8475–L9369 | ~895 |

**Total moveable: ~2,237 LOC.** Audit said ~1,813 — about 23% under (audit pre-dated Phase 6.1 gates expansion + multiple new gate-event handlers landing 2026-04 per `_action_attest_gate_event` / `_action_verify_gate_event` / `_action_dispute_gate_event` / `_action_retract_gate_event` / `_action_get_gate_event` / `_action_list_gate_events`).

**Audit framing CONFIRMED:** All 5 blocks are paid-market economy concerns. Each handler operates on either monetary state (escrow), outcome events, attribution chains, goal graphs, or gate ladders. None is pure runtime coordination, evaluation, or branch-CRUD.

**Audit's "1 dev-day" sizing is OPTIMISTIC.** This is the largest extraction so far (2,237 LOC vs Step 4's 1,379-LOC runs.py). Two MCP tools (`goals` + `gates`) need to be wrapped in `@mcp.tool` shims in universe_server.py — first time we have multiple tool decorations to preserve.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Escrow block (contiguous L7117–L7224)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 7117 | 1 | "── Escrow MCP handlers ──" |
| `_action_escrow_lock` | 7119 | ~35 | Imports `workflow.escrow.escrow_lock` (presumed) |
| `_action_escrow_release` | 7154 | ~32 | |
| `_action_escrow_refund` | 7186 | ~20 | |
| `_action_escrow_inspect` | 7206 | ~13 | |
| `_ESCROW_ACTIONS` | 7219 | 6 | Dict literal — 4 handlers |

### 2.2 Outcomes block (contiguous L7233–L7384)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 7233 | 1 | "── Outcome event MCP actions ──" |
| `_action_record_outcome` | 7270 | ~50 | |
| `_action_list_outcomes` | 7320 | ~45 | |
| `_action_get_outcome` | 7365 | ~15 | |
| `_OUTCOME_ACTIONS` | 7380 | 5 | Dict literal — 3 handlers |

### 2.3 Attribution block (contiguous L7387–L7574)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 7387 | 1 | "── Attribution chain ──" |
| `_action_record_remix` | 7408 | ~106 | Largest attribution handler |
| `_action_get_provenance` | 7514 | ~57 | |
| `_ATTRIBUTION_ACTIONS` | 7571 | 4 | Dict literal — 2 handlers |

### 2.4 Goals block (contiguous L7579–L8472)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| TOOL 3 banner + design comment | 7579 | ~28 | Phase 5 design rationale |
| `_action_goal_propose` | 7608 | ~49 | |
| `_action_goal_update` | 7657 | ~85 | |
| `_action_goal_bind` | 7742 | ~88 | |
| `_action_goal_list` | 7830 | ~29 | |
| `_action_goal_get` | 7859 | ~84 | |
| `_action_goal_search` | 7943 | ~41 | |
| `_action_goal_leaderboard` | 7984 | ~137 | |
| `_action_goal_common_nodes` | 8121 | ~125 | |
| `_action_goal_set_canonical` | 8246 | ~54 | |
| `_GOAL_ACTIONS` | 8300 | 12 | Dict literal — 9 handlers |
| `_GOAL_WRITE_ACTIONS` | 8312 | 5 | Frozenset |
| `_dispatch_goal_action` | 8317 | ~45 | Ledger glue |
| `@mcp.tool(...)` decorator + `def goals(...)` | 8365 | ~108 | MCP tool entry — DELEGATES, MUST PRESERVE |

### 2.5 Gates block (contiguous L8475–L9369)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| TOOL 3b banner + design comment | 8475 | ~29 | Phase 6.1 design rationale |
| `_action_gates_define_ladder` | 8504 | ~90 | |
| `_action_gates_get_ladder` | 8594 | ~24 | |
| `_action_gates_claim` | 8618 | ~120 | Largest gates handler |
| `_action_gates_retract` | 8738 | ~99 | |
| `_action_gates_list_claims` | 8837 | ~55 | |
| `_action_gates_leaderboard` | 8892 | ~46 | |
| `_action_gates_stake_bonus` | 8938 | ~51 | |
| `_action_gates_unstake_bonus` | 8989 | ~26 | |
| `_action_gates_release_bonus` | 9015 | ~53 | |
| `_action_attest_gate_event` | 9068 | ~34 | |
| `_action_verify_gate_event` | 9102 | ~16 | |
| `_action_dispute_gate_event` | 9118 | ~17 | |
| `_action_retract_gate_event` | 9135 | ~17 | |
| `_action_get_gate_event` | 9152 | ~27 | |
| `_action_list_gate_events` | 9179 | ~27 | |
| `_GATE_EVENT_ACTIONS` | 9206 | 8 | Dict literal — 6 handlers |
| `_GATES_ACTIONS` | 9216 | 11 | Dict literal — 9 handlers |
| `@mcp.tool(...)` decorator + `def gates(...)` | 9229 | ~141 | MCP tool entry — DELEGATES, MUST PRESERVE |

**No `_GATES_WRITE_ACTIONS` or `_GATE_EVENT_WRITE_ACTIONS`** (verified via grep). Gates section uses inline ledger writes inside individual handlers, not a shared write-set.

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does market.py depend on Step 1-6 (helpers / wiki / status / runs / evaluation / runtime_ops) symbols?

**No direct API-submodule depends.** Verified by grep — none of the moved code references `_wiki_*`, `get_status`, `_RUN_ACTIONS`, `_action_run_*`, `_JUDGMENT_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_SCHEDULER_ACTIONS`, `_MESSAGING_ACTIONS`, or `_INSPECT_DRY_ACTIONS`.

### 3.2 Does market.py depend on shared #8 helpers?

**Yes:** Most handlers use `_base_path()`. After Steps 1-6 landed (4f98654 + others), market.py imports `_base_path` from `tinyassets/api/helpers.py`. `_default_universe`, `_universe_dir`, `_read_json`, `_read_text` likely also used by some handlers — verify at extraction time.

### 3.3 Does market.py depend on universe_server preamble helpers?

**Yes — same pattern as #11/#12/#13 lazy-imports.** Expected preamble dependencies (verify via AST scan at extraction time):
- `_current_actor` — actor-credit on writes (escrow_lock, record_outcome, record_remix, goal_propose, gates_claim, etc.). High frequency.
- `_append_global_ledger` + `_truncate` — likely used by `_dispatch_goal_action` for ledger writes (mirrors `_dispatch_run_action` / `_dispatch_judgment_action` pattern).
- `_resolve_branch_id` — probably used by some attribution / goal-bind handlers.
- `_ensure_author_server_db` — possibly used by goal_propose / goal_bind.
- `logger` — universe_server-scoped logger; market.py should define its own `logger = logging.getLogger("universe_server.market")` instead.

**Strategy:** lazy-import inside each consuming function (same pattern as #11's 7 lazy imports, #12's 4, #13's 1). Re-grep at extraction time for the exact set.

### 3.4 Does market.py share dispatch surface with `extensions()`?

**Yes — 3 dispatch reads in `extensions()` body:**
- `_ESCROW_ACTIONS.get(action)` — escrow dispatch
- `_OUTCOME_ACTIONS.get(action)` — outcomes dispatch
- `_ATTRIBUTION_ACTIONS.get(action)` — attribution dispatch

After Step 7 lands, `extensions()` body needs **one new import line** at top of universe_server.py:
```python
from workflow.api.market import (
    _ESCROW_ACTIONS, _OUTCOME_ACTIONS, _ATTRIBUTION_ACTIONS,
)
```

`_GOAL_ACTIONS` and `_GATES_ACTIONS` + `_GATE_EVENT_ACTIONS` are NOT consumed by `extensions()` body — they're consumed inside the standalone `goals()` and `gates()` MCP tools, which we preserve as @mcp.tool wrappers in universe_server.py (Pattern A2).

**Structurally identical** to Step 4 (`_RUN_ACTIONS`) and Step 6 patterns for the 3 dispatch tables consumed by `extensions()`. **Trivial; not a refactor of `extensions()` body.**

### 3.5 `goals()` and `gates()` MCP tools — Pattern A2 with TWO wrapper preservation

This is the first extraction with **multiple** `@mcp.tool` decorations to preserve. Same Pattern A2 as #9 (wiki) and #10 (status), but applied twice:

```python
# universe_server.py post-extraction
from workflow.api.market import (
    goals as _goals_impl,
    gates as _gates_impl,
    # ... + 3 dispatch tables for extensions() ...
)

@mcp.tool(title="Goals", tags={...}, annotations=ToolAnnotations(...))
def goals(action, ...) -> str:
    """<full chatbot-facing docstring>"""
    return _goals_impl(action=action, ...)

@mcp.tool(title="Outcome Gates", tags={...}, annotations=ToolAnnotations(...))
def gates(action, ...) -> str:
    """<full chatbot-facing docstring>"""
    return _gates_impl(action=action, ...)
```

market.py exposes plain `goals(...)` and `gates(...)` callables (no decorators); universe_server.py keeps both decorators wrapping delegations.

**No new design decision needed** — Pattern A2 is the established pattern. Just apply it twice.

---

## 4. FastMCP `mcp` instance — inherits #9 decision

Same Pattern A2 as Steps 1-6. **Inherited.**

market.py does NOT register any `@mcp.tool()` decorator directly — both `goals()` and `gates()` decorators stay in universe_server.py with delegation. `mcp` import is NOT required for market.py.

---

## 5. Test files importing market symbols (and how)

Searched broadly across `tests/`. Likely import patterns:

| Test file | Symbol(s) imported (estimated) | Count |
|---|---|---|
| `tests/test_goals_*.py` (multiple files) | `goals` (MCP tool surface) | many |
| `tests/test_gates_*.py` | `gates` (MCP tool surface) | many |
| `tests/test_escrow_*.py` | `_action_escrow_*`, `extensions` | varies |
| `tests/test_outcome*.py` | `_action_record_outcome`, `extensions` | varies |
| `tests/test_attribution*.py` | `_action_record_remix`, `_action_get_provenance` | varies |
| `tests/test_canonical_branch_mcp.py:115,126` | `_GOAL_ACTIONS` (back-compat re-export already needed for #11) | 2 |

**Strategy:** Audit §7 Strategy 1 (back-compat re-export shim) preserves all imports. After Step 7 lands, `tinyassets/universe_server.py` adds re-export block for ~35 symbols (the 5 dispatch dicts + 23 handlers + `goals`/`gates` impl callables + `_dispatch_goal_action`).

**Confirmation needed at extraction time:** grep `tests/` for direct imports of `_action_escrow_*`, `_action_record_outcome`, `_action_record_remix`, `_action_goal_*`, `_action_gates_*`, `_action_*_gate_event`. Pre-export each name found.

**Direct test-import surface estimated 30-50 imports** across ~10-15 test files. Larger than Step 6 (~26 imports), comparable to Step 4 (~32). Re-export shim handles all without test edits — same pattern as Steps 4, 5, 6.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any market-scope symbols already shipped to a submodule (e.g. `workflow.api.market`, `workflow.escrow`, `workflow.outcomes`, `workflow.attribution`). **None found in the API layer.**

Note: there ARE storage-layer modules (`tinyassets/escrow.py`, `tinyassets/outcomes.py`, `tinyassets/goals.py`, etc.) — these are the persistence backends that the market action handlers wrap. Different namespaces. Inside market.py, imports stay as `from workflow.goals import ...` (storage), `from workflow.escrow import ...` (storage), etc. **Verify no name collision** at extraction time — the new file is `tinyassets/api/market.py`, not `tinyassets/market.py`.

Adjacent partial moves: only the 5 helpers in #8 — most market handlers already use `_base_path` from helpers.py.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Escrow (L7117–L7224) | ~108 |
| Outcomes (L7233–L7384) | ~152 |
| Attribution (L7387–L7574) | ~188 |
| Goals (L7579–L8472) | ~894 |
| Gates (L8475–L9369) | ~895 |
| **Total moved out of universe_server.py** | **~2,237** |
| Back-compat re-export block added to universe_server.py | ~45 |
| `@mcp.tool` wrappers for `goals` + `gates` (preserved) | ~250 (decorators + signatures + docstrings + delegations) |
| **Net reduction in universe_server.py** | **~1,940** |
| New `tinyassets/api/market.py` size | **~2,300** (with imports + module docstring) |

**Audit said ~1,813.** Reality ~2,237 — about 23% over (gates Phase 6.1 expansion + new gate_event handlers since audit). The wrappers preserved in universe_server.py reduce net shrink by ~250 LOC vs the full-move ideal.

---

## 8. Risks the audit didn't anticipate

1. **Two MCP tool decorators preserved.** First extraction with multiple `@mcp.tool` wrappers. Both `goals()` and `gates()` need their decorator + signature + docstring preserved verbatim in universe_server.py for FastMCP introspection. Both delegate to `_goals_impl` / `_gates_impl` in market.py. ~250 LOC of wrapper preservation reduces net shrink.

2. **Largest extraction by LOC** (~2,237 vs runs.py ~1,379, the previous max). Higher cognitive load + more interleaved sections = higher chance of missing a back-edge. **Strict line-by-line `git diff` review against §2 enumeration before handing to verifier.** Use the same per-range boundary asserts pattern as Steps 4/5/6.

3. **Five non-contiguous source ranges** (escrow, outcomes, attribution, goals, gates) — but adjacent in the file (L7117–L9369). All 5 in one contiguous super-range with internal section banners. **Could potentially be a single L7117–L9369 deletion** + reverse-order isn't strictly needed since it's monotonic. Recommendation: still do 5 separate ranges for clarity (mirrors §2 enumeration directly) and to make any accidental skip explicit.

4. **`_dispatch_goal_action` vs no `_dispatch_*` for escrow/outcome/attribution/gates.** Goals is the only block with dispatch glue (because `goals()` MCP tool is standalone like `gates()`). Escrow/outcome/attribution dispatch is inlined in `extensions()` body. Gates handlers are dispatched inline via `gates()` MCP tool body itself (verify by reading `gates()` body — likely uses `_GATES_ACTIONS.get(action)` plus `_GATE_EVENT_ACTIONS.get(action)` directly).

5. **Storage-layer namespace overlap.** `tinyassets/goals.py`, `tinyassets/escrow.py`, etc. exist as storage backends. New `tinyassets/api/market.py` imports from those (`from workflow.goals import propose_goal, ...`). Same pattern as runs.py importing `workflow.runs` storage. Verify no naming confusion at extraction time.

6. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

7. **Lazy-import scope likely wider than Steps 4-6.** Market handlers touch attribution, escrow, ledger, gate events — many call `_current_actor`, `_resolve_branch_id`, `_append_global_ledger`. Expect lazy-import insertions in 8-15 functions (vs Step 4's 6, Step 6's 1). Plan accordingly.

8. **Verify gates-section internal layout.** The gates section (L8475–L9369) has a subtle structure: 9 main `_action_gates_*` handlers → `_GATE_EVENT_ACTIONS` (6 gate-event handlers) → `_GATES_ACTIONS` (9 main handlers, indexed AFTER the 6 gate-event handlers are also defined). Order in market.py should match — define all `_action_*_gate_event` handlers BEFORE `_GATE_EVENT_ACTIONS` dict, and define all 9 main `_action_gates_*` handlers BEFORE `_GATES_ACTIONS` dict. The current source order satisfies this, so extracting verbatim preserves correctness.

9. **Sequencing constraint.** Step 7 → Step 8 strict serialization (both edit universe_server.py shim block). Audit §8 explicitly puts Step 7 before Step 8. Confirmed.

---

## 9. Concrete Step 7 implementation plan

Estimated wall time: **90-120 min** (largest extraction; double Step 4's surface).

1. **Confirm Steps 1-6 landed.** ✅ All 6 commits in main as of writing.
2. **Re-grep external symbol set** with AST scan (same script pattern as Steps 4-6 prep verification): identify exact set of universe_server-internal symbols the moved code references. Lazy-import each in the consuming function.
3. **Create `tinyassets/api/market.py`:**
   - Module docstring referencing audit + extraction date + the 5 source ranges + dispatch table inventory + Pattern A2 explanation for the dual `goals`/`gates` MCP wrappers.
   - Imports: `from workflow.api.helpers import _base_path` + (any other helpers actually used per AST scan) + std-lib + typing + `logging.getLogger("universe_server.market")`.
   - Move 5 source-range chunks in this order (matches source order; minimizes diff confusion):
     1. Escrow handlers + `_ESCROW_ACTIONS` (L7117–L7224)
     2. Outcomes handlers + `_OUTCOME_ACTIONS` (L7233–L7384)
     3. Attribution handlers + `_ATTRIBUTION_ACTIONS` (L7387–L7574)
     4. Goals: TOOL 3 banner + 9 handlers + `_GOAL_ACTIONS` + `_GOAL_WRITE_ACTIONS` + `_dispatch_goal_action` + the `goals()` BODY (without `@mcp.tool` decorator) (L7579–L8472)
     5. Gates: TOOL 3b banner + 9 main handlers + 6 gate_event handlers + `_GATE_EVENT_ACTIONS` + `_GATES_ACTIONS` + the `gates()` BODY (without `@mcp.tool` decorator) (L8475–L9369)
4. **Update `tinyassets/universe_server.py`:**
   - Delete the 5 source ranges in REVERSE order to avoid line-shift confusion (5,4,3,2,1).
   - Add to back-compat shim block (after the existing #11/#12/#13 re-export blocks):
     ```python
     from workflow.api.market import (  # noqa: E402, F401
         _ATTRIBUTION_ACTIONS,
         _ESCROW_ACTIONS,
         _GATES_ACTIONS,
         _GATE_EVENT_ACTIONS,
         _GOAL_ACTIONS,
         _GOAL_WRITE_ACTIONS,
         _OUTCOME_ACTIONS,
         _action_escrow_lock, _action_escrow_release, _action_escrow_refund, _action_escrow_inspect,
         _action_record_outcome, _action_list_outcomes, _action_get_outcome,
         _action_record_remix, _action_get_provenance,
         _action_goal_propose, _action_goal_update, _action_goal_bind,
         _action_goal_list, _action_goal_get, _action_goal_search,
         _action_goal_leaderboard, _action_goal_common_nodes, _action_goal_set_canonical,
         _action_gates_define_ladder, _action_gates_get_ladder,
         _action_gates_claim, _action_gates_retract, _action_gates_list_claims,
         _action_gates_leaderboard,
         _action_gates_stake_bonus, _action_gates_unstake_bonus, _action_gates_release_bonus,
         _action_attest_gate_event, _action_verify_gate_event, _action_dispute_gate_event,
         _action_retract_gate_event, _action_get_gate_event, _action_list_gate_events,
         _dispatch_goal_action,
     )
     from workflow.api.market import goals as _goals_impl  # noqa: E402
     from workflow.api.market import gates as _gates_impl  # noqa: E402
     ```
   - Add `@mcp.tool(...)` decorator + thin `goals()` wrapper that delegates to `_goals_impl`. Preserve full chatbot-facing docstring + signature.
   - Add `@mcp.tool(...)` decorator + thin `gates()` wrapper that delegates to `_gates_impl`. Same pattern.
5. **No test edits required** (unless a monkeypatch-target case surfaces like #9's `mock.patch("workflow.universe_server.open", ...)` or #11's `monkeypatch.setattr(us, "_base_path", ...)`). If found, adjust per the extraction-aware pattern documented in #9 + #11.
6. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
7. **Verification:**
   - `pytest tests/test_goals_*.py tests/test_gates_*.py tests/test_escrow_*.py tests/test_outcome*.py tests/test_attribution*.py -q` → green.
   - `pytest -k "goals or gates or escrow or outcome or attribution or market" -q` → cross-cutting smoke.
   - `pytest -q` → full suite green (highly recommended given LOC volume).
   - `ruff check tinyassets/api/market.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _action_"` should equal 27 (4 escrow + 3 outcomes + 2 attribution + 9 goals + 9 gates main, but NOT the 6 gate_event handlers because those go to `_GATE_EVENT_ACTIONS` which moves with the gates section). Actually let me recount: 4+3+2+9+9+6 = **33 `_action_` defs deleted**. Anything else means an accidental pull or skip.

**Files in eventual Step 7 SHIP handoff:**
- `tinyassets/api/market.py` (NEW, ~2,300 LOC — largest extraction)
- `tinyassets/universe_server.py` (~1,940 LOC removed + ~45 re-export added + ~250 wrapper-preservation = net ~−1,650)
- `tests/test_api_market.py` (NEW, 60-80 tests recommended given the surface area)
- `packaging/claude-plugin/.../tinyassets/api/market.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

5 files, +2,400 / −1,650 LOC net.

---

## 10. Decision asks for the lead

1. **Test edits expected?** Re-grep `tests/` for direct imports of any of the 33 handler names + 5 dispatch dicts before claiming "no test edits." Likely 0-2 monkeypatch-target fixes (per Steps 4/9 patterns). Recommend: proceed with implementation; if test fixes needed, treat them as same pattern as #9 + #11 monkeypatch-target updates.
2. **Single 5-range deletion vs one big L7117–L9369 deletion?** Ranges are ADJACENT in source. Could collapse to single deletion. Recommend: keep 5 separate ranges (one per logical block) for clarity in the code review diff and to mirror the extraction enumeration. Marginal cost; high readability win.
3. **Auto-derive `extensions()` import line vs hand-craft?** `extensions()` body needs `_ESCROW_ACTIONS`, `_OUTCOME_ACTIONS`, `_ATTRIBUTION_ACTIONS` import. Recommend: hand-craft the import next to the existing `from workflow.api.runtime_ops import (...)` block — clean grouping with other Phase-1 extraction re-exports.

---

## 11. Cross-prep summary (Steps 1-7 combined)

After Step 7 lands:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 ✅ | extends `helpers.py` | ~16 | ~13,996 |
| #9 ✅ | `wiki.py` | ~1,360 | ~12,636 |
| #10 ✅ | `status.py` | ~422 | ~12,214 |
| Step 4 ✅ | `runs.py` | ~1,379 | ~10,835 |
| Step 5 ✅ | `evaluation.py` | ~822 | ~10,013 |
| Step 6 ✅ | `runtime_ops.py` | ~458 | ~9,555 |
| Step 7 (this prep) | `market.py` | ~1,940 (incl wrapper preservation) | **~7,615** |
| **Total** | 5 new + 1 extended | ~6,397 | **~7,615** |

**universe_server.py crosses below ~7,600 LOC after Step 7** (from baseline 14,012 = ~46% reduction). After Step 8 (branches.py ~3,200 LOC), the residual shim is projected at ~4,400 LOC — close to audit's "~100-LOC routing shell" projection but not yet there (residual contains `extensions()` body, `universe()` body, `_dispatch_with_ledger`, preamble helpers like `_truncate`/`_current_actor`/`_append_global_ledger`/`_resolve_branch_id`/`_ensure_author_server_db` that the audit envisioned moving to `universe_helpers.py` in a later step).

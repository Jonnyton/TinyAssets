# #15 Mitigation Scope — `tinyassets/universe_server.py` Directive Relocation

**Date:** 2026-04-18
**Author:** dev (task #18 pre-draft for blocked task #15)
**Status:** Scope plan. No code change. Executes in minutes when #15 unblocks (post-#8 file renames).
**Relates to:** `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md` §5 (mitigation proposals).

## Goal

Collapse the 3 load-bearing phrases — `NO SIMULATION`, `AFFIRMATIVE CONSENT`, `Silently simulating a run breaks user trust` — to **one canonical site each** in the `control_station` prompt. Strip behavioral directives from MCP tool `description` fields. Trim over-long tool docstrings toward I/O-contract-only.

## 1. Phrase inventory (current sites)

### 1.1 `NO SIMULATION` — 4 sites

| # | File:Line | Surface | Disposition |
|---|---|---|---|
| 1 | `universe_server.py:83` | `FastMCP(instructions=...)` server handshake | **DELETE** — handshake is always-loaded at tool-list time; maximum injection-heuristic exposure |
| 2 | `universe_server.py:809` | `_CONTROL_STATION_PROMPT` bullet 5 | **KEEP CANONICAL** (rephrase — see §3) |
| 3 | `universe_server.py:1003` | `_EXTENSION_GUIDE_PROMPT` body | **DELETE** — duplicated from control_station; extension guide users already have it |
| 4 | `universe_server.py:3704` | `extensions` tool docstring | **DELETE** — the tool description must NOT be a directive surface (design-note §5.1) |

### 1.2 `AFFIRMATIVE CONSENT` — 2 sites

| # | File:Line | Surface | Disposition |
|---|---|---|---|
| 1 | `universe_server.py:3712` | `extensions` tool docstring — "INTENT DISAMBIGUATION" block | **DELETE** — move the rule to control_station §3 (see §3) |
| 2 | `universe_server.py:3722` | `extensions` tool docstring — `register` action bullet | **DELETE** — re-mention of the same rule 10 lines later; redundant even pre-mitigation |

### 1.3 `Silently simulating a run breaks user trust` — 3 sites

| # | File:Line | Surface | Disposition |
|---|---|---|---|
| 1 | `universe_server.py:89` | `FastMCP(instructions=...)` tail of NO SIMULATION block | **DELETE** (with #1.1.1) |
| 2 | `universe_server.py:814` | `_CONTROL_STATION_PROMPT` bullet 5 tail | **REPHRASE** — drop "Silently simulating", keep the substantive point in sentence-case |
| 3 | `universe_server.py:3708` | `extensions` tool docstring | **DELETE** (with #1.1.4) |

### 1.4 Sibling directives surfaced in the audit

- `universe_server.py:92-102` — `HARD RULE — UNIVERSE ISOLATION` in server instructions. Same class of problem; same fix: **DELETE from instructions**, keep canonical in control_station (already present at line ~830).
- `universe_server.py:6048` — `SIMULATION BAN` in `_BRANCH_DESIGN_GUIDE_PROMPT`. Lower risk (prompt is invoked on demand, not at handshake). **REPHRASE** to sentence-case — drop "SIMULATION BAN" header.

## 2. Tool description rewrites

Sizes measured via `ast.get_docstring`:

| Tool | Current | Target | Shape |
|---|---|---|---|
| `universe` (L1076) | 52 lines / 2767c | ≤12 lines (I/O + action list only) | Keep action enum + Args; strip "Universe isolation" paragraph (move to control_station if not already there) |
| `extensions` (L3644) | **172 lines / 9144c** | ≤25 lines (action groups + Args summary) | Strip NO SIMULATION + INTENT DISAMBIGUATION blocks; keep action group headers + Args |
| `goals` (L8129) | 49 lines / 2460c | ≤10 lines | Likely already mostly I/O; directive scrub pass |
| `gates` (L8704) | 46 lines / 2291c | ≤10 lines | Same |
| `wiki` (L9014) | 35 lines / 1716c | ≤8 lines | Same |

## 3. Proposed canonical `control_station` block

Replace `_CONTROL_STATION_PROMPT` lines ~802-815 with a single sentence-case paragraph that consolidates the 3 phrases without all-caps clusters:

```
When a user asks to run a workflow, branch, or registered node, use
`extensions action=run_branch`. If the run action is unavailable or a
source-code node isn't approved, say so plainly and stop — don't
web-search, populate wiki pages, or narrate imagined output. Creating
state (registering a node, building a branch) requires an explicit
user ask — route "what do i have", "show me", "list my" to `list` or
`list_branches`, never to a write. When intent is ambiguous, ask.
```

Rationale:
- Sentence-case throughout; no all-caps directive clusters.
- Single occurrence of the "run or stop" rule.
- Single occurrence of the "create only on explicit ask" rule.
- Drops the phrase "Silently simulating a run breaks user trust" entirely — the positive-phrased "say so plainly and stop" carries the same contract without the distinctive lexical fingerprint the injection heuristic latches onto.

## 4. Before/after diff previews

### 4.1 `FastMCP(instructions=...)` (lines 78-103)

**Before (~26 lines):** contains 2 HARD RULE blocks with NO SIMULATION + UNIVERSE ISOLATION walls.

**After (~8 lines):** keep the workflow-builder framing + intent-disambiguation pointer ("If a user asks about their 'workflow builder'..."); delete both HARD RULE blocks; end with "Start with `universe action=inspect` to orient, and read the `control_station` prompt for operating guidelines."

### 4.2 `extensions` tool docstring (L3644-3864)

**Before (172 lines):** intro + 2 HARD-RULE-style blocks (NO SIMULATION, INTENT DISAMBIGUATION) + action groups + full Args table.

**After (~25 lines):** intro (2 lines) + action groups as short bullets (10 lines) + Args as short table (12 lines). All behavioral guidance gone — it lives in `control_station` + `extension_guide` + `branch_design_guide` prompts.

### 4.3 `universe` tool docstring (L1101-1117)

**Before (~17 lines before Args):** intro + "Universe isolation" behavioral paragraph.

**After (~5 lines):** intro only; isolation rule stays canonical in `control_station` prompt (already present at ~line 830).

### 4.4 `_EXTENSION_GUIDE_PROMPT` (L993-1007)

**Before:** repeats NO SIMULATION block verbatim from `_CONTROL_STATION_PROMPT`.

**After:** replace the 6-line NO SIMULATION paragraph with a one-line pointer: "Runtime rules live in the `control_station` prompt; this guide focuses on node/branch authoring."

### 4.5 `_BRANCH_DESIGN_GUIDE_PROMPT` (L6048)

**Before:** ends with "SIMULATION BAN: if run_branch fails, ... Do not pretend a run happened by fabricating output or writing wiki pages."

**After:** "If validation fails or a source-code node isn't approved, `run_branch` returns an error — surface it and stop." Drops the BAN header, drops "pretend", drops "fabricating" — neutral wording the injection heuristic has no hook on.

## 5. Test impact

No existing tests pin any of the 3 target phrases as literal substrings (grep across `tests/` for NO SIMULATION / AFFIRMATIVE / Silently simulat: 0 hits).

Tests that MAY touch the rewrite surface:
- `tests/test_universe_server_framing.py` — pins "workflow builder" + non-fiction domain examples in server instructions + control_station prompt. My proposed rewrites preserve both. Re-run after edits; should pass without changes.
- `tests/test_universe_server_metadata.py` — pins `control_station.description` contains "TinyAssets Server" (from #7). Unchanged by this work.

No test changes anticipated. If any assertion fails unexpectedly, fix by adjusting the pin to the new canonical phrasing rather than reinstating the directive.

## 6. Execution order when #15 unblocks

1. Edit `_CONTROL_STATION_PROMPT` (bullet 5) — land the canonical paragraph from §3.
2. Strip HARD RULE blocks from `FastMCP(instructions=...)`.
3. Strip NO SIMULATION from `_EXTENSION_GUIDE_PROMPT`; replace with 1-line pointer.
4. Rewrite `extensions` docstring (biggest diff — ~150-line delete).
5. Rewrite `universe`, `goals`, `gates`, `wiki` docstrings (scrub behavioral prose, trim to I/O contract).
6. Rephrase `SIMULATION BAN` tail in `_BRANCH_DESIGN_GUIDE_PROMPT`.
7. `ruff check tinyassets/universe_server.py`.
8. `pytest tests/test_universe_server_framing.py tests/test_universe_server_metadata.py` — smoke both framing pins hold.
9. Hand to verifier for full suite.

Estimated execution: 25–40 min.

## 7. Out-of-scope (not this plan)

- Tool `description` fields in the `ToolAnnotations` blocks (separate from docstrings) — inventory if any carry directives; scoped in §2 follow-up if present.
- `tinyassets/universe_server.py` module-level docstring (L1-50) — header prose, not transmitted as MCP metadata.
- Phrase audits on OTHER files (`tinyassets/daemon_server.py`, `fantasy_daemon/api.py`) — if directives leaked there, separate task.
- Packaging-mirror refresh — auto-handled by `build_plugin.py` on next build.

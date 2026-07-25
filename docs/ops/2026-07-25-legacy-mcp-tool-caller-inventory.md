# Legacy hidden-MCP-tool caller inventory

**Change:** `openspec/changes/retire-legacy-live-mcp-tools` — satisfies tasks 2.1, 2.2, 2.3.
**Date:** 2026-07-25. **Provider:** claude-code (Opus 5), branch `claude/o5-retire-inventory`.
**Base:** `origin/main` = `d8ef3dea`; analysis tree = `92d730bc` (1 commit behind; the delta
`d8ef3dea` is STATUS.md-only, so it does not affect any finding here).
**Method:** read-only static analysis (AST + dispatch-table extraction) over the working tree,
plus `gh` PR-state queries. No runtime code was changed.

Scope note: this is the **repository-internal** inventory. It does **not** satisfy task 1.3
(external hidden-name call telemetry) — see §7.

---

## 1. Premise verification

`tinyassets/universe_server.py` registers **13** MCP tools via `_register_structured_tool`:

- **7 canonical:** `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
  `converse`, `get_status`.
- **6 hidden legacy:** `universe`, `community_change_context`, `extensions`, `goals`, `gates`,
  `wiki` (`_DEPRECATED_TOOL_NAMES`, universe_server.py:1030).

`_DeprecatedToolVisibility` (universe_server.py:1983) drops the six from `tools/list` but
`on_call_tool` still forwards them — **hidden yet dispatchable**, as the change premise states.

Two consequences worth recording:

- **`scripts/mcp_public_canary.py` is blind to this.** Its `CANONICAL_HANDLES` check reads
  `tools/list`, which the middleware has already filtered. A green `--assert-handles` run is
  therefore *not* evidence that the six are gone. This is exactly why task 3.1 requires a
  registry test "with listing middleware bypassed."
- **Anonymous calls to the six already fail** in gating auth modes: `on_call_tool` raises
  `ToolError` when `write_gate_rejection(name)` fires (the #1441 anonymous-write gate). Only
  signed-in callers and dev mode still reach them.

---

## 2. Task 2.1 — fresh ownership and collision state

Nine PRs named in task 2.1, queried 2026-07-25:

| PR | State | Draft | Touches retirement runtime files? |
|---|---|---|---|
| #1560 | CLOSED | no | — (no longer an owner) |
| #1550 | CLOSED | no | — |
| #1549 | CLOSED | no | — |
| #1493 | **OPEN** | draft | `tinyassets/universe_server.py`, `api/extensions.py`, mirror, `tests/test_universe_server_isolation.py` |
| #1478 | CLOSED | draft | — |
| #1467 | **OPEN** | draft | `universe_server.py`, `api/extensions.py`, **`tinyassets/directory_server.py`**, mirror |
| #1466 | **OPEN** | draft | `universe_server.py`, `api/universe.py`, mirror, `tests/test_universe_server_ledger.py` |
| #1465 | **OPEN** | draft | `universe_server.py`, `api/extensions.py`, `api/extensions_consent_actions.py`, mirror |
| #1464 | CLOSED | draft | — |

**Resolution:** five of nine are CLOSED and impose no dependency. **Four remain open**
(#1493 `a4115dd3`, #1467 `5fb6d16a`, #1466 `4427d012`, #1465 `8eef71b8`) and all four edit
`tinyassets/universe_server.py` — the exact file task 4.1/4.2 must rewrite. The implementation
lane must depend on these four, not merely note them. (Head shas are pinned because open-PR
state on a saturated fleet expires quickly.)

**Collision check** (`scripts/claim_check.py --check-files`) for this artifact's write-set
(`docs/ops/2026-07-25-legacy-mcp-tool-caller-inventory.md`,
`openspec/changes/retire-legacy-live-mcp-tools/tasks.md`): **CLEAR — no overlap with any
claimed/in-flight row.** This inventory lane claims no runtime files, so the four open-PR
collisions above are recorded as a dependency for the future implementation lane rather than
resolved here.

---

## 3. Task 2.2 — stdio-server boundary

- **PR #1561 (`1a5d45af`, OPEN draft) is confirmed limited to the separate legacy stdio server.**
  Its complete file set is 3 files: `tinyassets/mcp_server.py`, its packaged mirror, and
  `tests/test_legacy_mcp_server_fence.py`. It touches neither `universe_server.py` nor the canary.
- **`tinyassets/mcp_server.py` is excluded from this change and is structurally unaffected.** It
  is a separate `FastMCP` instance whose tool surface is disjoint from the six: `get_status`,
  `add_note`, `steer`, `get_premise`, `set_premise`, `get_progress`, `get_work_targets`,
  `get_review_state`, `get_chapter`, `get_activity`, `pause`, `resume`, `add_canon`. **None of the
  six legacy names is defined or registered there**, so unregistering them from `universe_server.py`
  cannot affect it.
- **`tinyassets/directory_server.py` is already absent from `origin/main`** — deleted by
  `60f7f9f1` ("Retire /mcp-directory and converge on canonical /mcp", #1718). It must not return.

> ### ⚠ Finding 2.2-A — open PR #1467 carries a modify-delta against the deleted `directory_server.py`
>
> `gh api .../pulls/1467/files` reports `modified +30/-3` on **both**
> `tinyassets/directory_server.py` and its packaged mirror. That branch predates `60f7f9f1`, so
> merging it without a rebase either raises a modify/delete conflict or, if resolved toward the
> branch, **restores the retired directory surface** — a direct violation of tasks 2.2 and 4.4.
> #1467 must be rebased past `60f7f9f1` (and its `directory_server.py` delta dropped) before it
> merges, independently of this retirement change.

---

## 4. Task 2.3 — caller inventory by binding kind

The decisive distinction: **unregistering an MCP tool breaks only *wire* callers.** A Python
caller holding `from tinyassets.universe_server import extensions` binds the plain wrapper
function and is completely unaffected by `mcp.tool` registration. The inventory is therefore
classified by binding kind, not by file.

### 4a. Python callers (unaffected by unregistration)

| Caller class | Bindings | Files | Preserve-or-migrate |
|---|---|---|---|
| `tests/` — direct import (`from ...universe_server import <legacy>`) | 57 | 26 | **Preserve.** Unaffected. |
| `tests/` — module-attr call (`us.<legacy>(...)`) | 119 | 41 | **Preserve.** Unaffected. |
| **Production runtime (`tinyassets/` non-test)** | **0** | **0** | n/a — none exist |
| `scripts/` Python-API callers | 0 | 0 | n/a |
| `fantasy_daemon/universe_server.py` — `import *` | 1 | 1 | **Preserve.** Legacy alias shim; re-exports whatever the module defines. Unaffected as long as task 4.1 keeps the wrapper `def`s. |

**Union: 67 distinct files bind the six wrappers in Python, and every one is under `tests/`.**

> ### ✅ Finding 2.3-A — there are zero production-runtime Python callers
>
> An AST pass over `tinyassets/universe_server.py` also confirms that **no canonical handler
> delegates into any of the six legacy wrappers** (zero call edges from
> `read_graph`/`write_graph`/`run_graph`/`read_page`/`write_page`/`converse`/`get_status` into
> `universe`/`community_change_context`/`extensions`/`goals`/`gates`/`wiki`). Both surfaces
> delegate *independently* to the same `tinyassets/api/*` implementations
> (`_universe_impl`, `_extensions_impl`, `api.market.goals`/`.gates`, `api.wiki.wiki`).
>
> **Consequence:** task 4.1's default — "preserve wrapper functions unless 2.3 proves an explicit
> caller migration" — is the correct call. Removing the six `_register_structured_tool(...)`
> blocks while leaving the six `def`s in place breaks **no** Python caller and **no** test import.
> Deleting the wrapper bodies would break 67 test files for no benefit.

### 4b. Wire callers (BROKEN by unregistration)

These invoke the legacy names as MCP tool handles and are the real migration work.

| # | Site | Call | Canonical replacement | Verdict |
|---|---|---|---|---|
| 1 | `scripts/navigator_wiki_sweep.py:162` | `tools/call name="wiki" {action:"list"}` against **`https://tinyassets.io/mcp`** (default) | **none — `list` is orphaned (§5)** | **MIGRATE — BLOCKED** |
| 2 | `scripts/mcp_probe.py:139` | `tools/call "universe" {action:"list"}` | `read_graph target="graphs"` | **MIGRATE — straightforward** |
| 3 | `scripts/mcp_probe.py:146` | `tools/call "universe" {action:"inspect"}` | `read_graph target="graph"` | **MIGRATE — straightforward** |
| 4 | `scripts/mcp_probe.py:155` | `tools/call "wiki" {action:"list"}` | **none — `list` is orphaned (§5)** | **MIGRATE — BLOCKED** |
| 5 | `packaging/conway/panel-metadata.json` (×3 panels) | `data_source.tool: "universe"` + `action: inspect / get_activity / query_world` | `read_graph target="graph"` covers `inspect` only | **Fix metadata.** No programmatic loader exists; `packaging/INDEX.md` calls `conway/` "speculative". Low risk, but it is retired-tool metadata residue under task 4.5. |
| 6 | `tinyassets/api/market.py:2600, 3907, 3946` | `"tool": "goals"` / `"tool": "gates"` in error payloads and `_action_gates_list`'s self-description | — | **Fix strings.** Not dispatch calls; they are user-facing labels naming a tool that will no longer exist. Task 4.5 residue. |

> ### 🔴 Finding 2.3-B — `wiki action=list` has no canonical replacement, and two live scripts depend on it
>
> `scripts/navigator_wiki_sweep.py` implements the navigator's standing 30-minute wiki-sweep
> cadence and defaults to the **public production endpoint**. Retiring `wiki` breaks it, and it
> cannot be fixed by swapping the handle: `read_page` never emits `action="list"` (§5).
> Retirement must therefore be preceded by either (a) extending `read_page` to reach `list`, or
> (b) explicitly retiring the sweep cadence with host sign-off. This is a **prerequisite**, not
> cleanup.

> ### ✅ Finding 2.3-C — the migration pattern already has a working precedent in-repo
>
> `scripts/last_activity_canary.py` performed exactly this migration and documents it in its
> module docstring: it "originally read the `universe action=inspect` fat tool, but since the
> anonymous write gate (#1441) the deprecated fat tools refuse ALL anonymous calls — reads
> included — so an unauthenticated canary must use the canonical handle." It now calls
> `read_graph target="graph"`, which "routes to the same `_action_inspect_universe` payload …
> every shape assertion below [is] unchanged." Sites 2 and 3 above should follow this pattern
> verbatim.

### 4c. Explicitly excluded false positives

A naive grep for the six names produces these; they are **not** callers and must not be "fixed":

- `WebSite/site/src/lib/content/mcp-snapshot.json` — baked **content data** (fetched 2026-04-30).
  Its `"goals"` / `"wiki"` / `"extensions"` / `"universe"` occurrences are goal tags, wiki
  category keys, universe ids, and `tags` values — never tool handles.
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/**` — the byte-parity
  packaged mirror of `tinyassets/`. It carries the same 6 registrations by construction and is
  regenerated by `packaging/claude-plugin/build_plugin.py` (task 4.4), not edited directly.
- `logging.getLogger("universe_server.universe")` / `"universe_server.wiki"` — logger names.
- `tinyassets/api/universe.py:2540` — a hint string `"Use \`wiki action=list category=…\`"`;
  prose residue for task 4.5, not a call site.

---

## 5. Action-reachability gap (the load-bearing result)

Each legacy tool is a **passthrough**: it forwards `action=` verbatim into its api-layer dispatch
table. Each canonical handle is a **narrow target router** emitting only hand-picked literal
actions, with an `_unknown_target` fallback. So the retirement's true blast radius is
*(actions in each dispatch table)* − *(literal actions the canonical seven emit)*.

| Legacy tool | Dispatch table | Actions | Reachable via canonical 7 | **Orphaned** |
|---|---|---|---|---|
| `universe` | `UNIVERSE_ACTIONS` (api/universe.py) | 50 | 3 — `list`, `inspect`, `create_universe` | **47** |
| `community_change_context` | fixed `action="community_change_context"` | 1 | 0 | **1** |
| `extensions` | union of 12 tables (api/extensions.py) | 87 | 5 — `list_runs`, `get_run`, `get_branch`, `patch_branch`, `run_branch` | **82** |
| `goals` | `_GOAL_ACTIONS` (api/market.py) | 14 | 4 — `get`, `list`, `search`, `propose` | **10** |
| `gates` | `_GATES_ACTIONS` + `_GATE_EVENT_ACTIONS` | 20 | **0** | **20** |
| `wiki` | `WIKI_ACTIONS` (api/wiki.py) | 15 | 6 — `read`, `search`, `since`, `file_bug`, `patch`, `write` | **9** |
| **Total** | | **187** | **18** | **169** |

Orphaned sets in full for the three smallest:

- **`wiki` (9):** `consolidate`, `cosign_bug`, `delete`, `ingest`, `lint`, `list`, `promote`,
  `supersede`, `sync_projects`.
- **`goals` (10):** `archive_consultation`, `bind`, `common_nodes`, `define_protocol`,
  `get_protocol`, `leaderboard`, `run_canonical`, `set_canonical`, `set_selector`, `update`.
- **`gates` (20):** all of them — no canonical handle routes to `gates` at all.

**Interpretation.** 169 orphans does *not* mean 169 regressions: the reshape's stated intent was
to shrink the advertised surface, so many are deliberately dropped. What the number establishes is
that **retirement is a surface reduction of ~90% of dispatchable actions, not a rename**, and the
change's own evidence gates treat it as the latter. Two live STATUS.md rows already depend on
orphaned actions:

- *"Mark-branch canonical decision (Task #33 phase 0)"* — names `goals action=propose/bind/set_canonical`.
  `propose` survives; **`bind` and `set_canonical` are orphaned.**
- *"BUG-018 canonical filename trailing-hyphen"* — names `wiki action=promote`; **orphaned.**

Before task 4.1 removes the registrations, the host needs an explicit keep/drop decision on the
169 — at minimum on `wiki action=list` (§4b Finding 2.3-B) and on the two STATUS rows above.

---

## 6. Focused coverage map (task 2.3 "focused coverage for each wrapper")

Existing per-wrapper test surface, all binding the Python API (so all survive unregistration):

| Wrapper | Test files | Representative |
|---|---|---|
| `extensions` | 47 | `test_attach_existing_child_run.py`, `test_attribution_mcp.py`, `test_branch_authoring_actions.py` |
| `goals` | 9 | `test_api_market.py`, `test_canonical_branch_mcp.py`, `test_goals_run_canonical.py` |
| `wiki` | 7 | `test_wiki_cosign_flow.py`, `test_wiki_file_bug.py`, `test_universe_server_mcp_structured_results.py` |
| `universe` | 6 | `test_api_universe.py`, `test_first_contact.py`, `test_get_recent_events.py` |
| `gates` | 5 | `test_gate_bonuses_mcp.py`, `test_outcome_gate_claims.py`, `test_api_market.py` |
| `community_change_context` | 1 | `test_api_universe.py` |

**Gap:** every one of these tests the *wrapper*, not the *registration*. No existing test asserts
which names are registered with the listing middleware bypassed — which is precisely the hole
task 3.1 fills. `tests/test_universe_server_five_handles.py:127` calls
`mcp.call_tool("universe", …)` and is the one test that **will** need updating at task 4.1, since
it asserts the hidden tools remain dispatchable.

---

## 7. What this inventory does NOT establish

Stated explicitly so it is not mistaken for a cleared gate:

- **Task 1.3 (external caller telemetry) is untouched.** This is repository-internal only. It
  cannot see calls from installed connectors, external clients, or the live production server.
  Zero *internal* wire callers outside `scripts/` says nothing about *external* ones.
- **No live probe was run.** All findings are static, against tree `92d730bc`.
- **The 169 orphaned actions are surfaced, not adjudicated.** Deciding which are deliberate
  reductions versus regressions is a host/interface-review call (tasks 1.5 and 5.3).
- **Tasks 2.1–2.3 being checked off does not unblock task 4.1.** The §1 gates (1.1–1.5) and
  Finding 2.3-B remain open.

---

## 8. Recommended dependency edges for the implementation lane

1. Depend on open PRs #1493, #1467, #1466, #1465 — all four edit `universe_server.py`.
2. Rebase #1467 past `60f7f9f1` and drop its `directory_server.py` delta (Finding 2.2-A).
3. Resolve `wiki action=list` before retirement (Finding 2.3-B); migrate
   `scripts/mcp_probe.py` sites 2–3 now using the `last_activity_canary.py` pattern
   (Finding 2.3-C) — those two are safe today and shrink the retirement diff.
4. Fold the §5 orphan table into the task 1.5 host-approval packet.

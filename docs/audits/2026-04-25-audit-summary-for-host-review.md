# Audit Summary for Host Review — Engine/Domain Separation + universe_server Decomposition

**Date:** 2026-04-26
**Author:** navigator
**Source audits:**
- `docs/audits/2026-04-25-engine-domain-api-separation.md` (188 lines, Task #28)
- `docs/audits/2026-04-25-universe-server-decomposition.md` (276 lines, Task #29)

**Purpose:** Reduce host review friction. The two audits are complementary — read together they recommend a single bundled refactor with concrete sequencing. This memo abstracts the conclusions for accept/reject judgment without re-reading 464 lines of detail.

---

## TL;DR for STATUS.md

> Two audits recommend bundled refactor of `tinyassets/universe_server.py` (13,067 LOC, 490 KB). #28: extract 9 fantasy-domain actions (~720 LOC) to `domains/fantasy_daemon/api/`. #29: split remaining engine code into 8 submodules under `tinyassets/api/`. Net effort: ~5 dev-days, no behavior change, executes in 8 incrementally-mergeable commits. Sequence: gates on rename Phases 2–4 + in-flight tasks #21/#22 landing first. Three host questions outstanding (tool-shape after extraction, security-surface placement, registration pattern).

---

## 1. What problem each audit solves

| Audit | Problem |
|-------|---------|
| **#28 Engine/Domain separation** | `tinyassets/universe_server.py` mixes engine primitives (cross-domain) with fantasy-specific world state (`story.db`, premises, canon). PLAN.md test fails: a second domain (research, journalism, etc.) cannot adopt the engine without engine changes. |
| **#29 universe_server decomposition** | The file is 13,067 LOC / 490 KB — every dev touches it; merge conflicts compound; 23 importers fan in. The 2026-04-19 spaghetti audit already named it the #1 hotspot. |

Both problems live in the same file, which is why both audits exist as a pair and why a bundled execution is the proposal.

---

## 2. Key conclusions

### #28 (Domain extraction)

- **9 of 20 `universe()` actions are fantasy-specific:** `submit_request`, `give_direction`, `query_world`, `read/set_premise`, `add/list/read_canon`, `add_canon_from_path`. Total ~720 LOC, ~5.5% of file.
- **The other 4 top-level MCP tools are 100% engine** — `extensions()`, `goals()`, `gates()`, `wiki()`, `get_status()` all stay as-is.
- **Target:** `domains/fantasy_daemon/api/` with two modules — `world_state.py` (canon + premise + query_world) and `editorial.py` (submit_request + give_direction).
- **Estimate:** ~2 dev-days once rename Phases 2–4 land.

### #29 (Decomposition)

- **8 submodules under `tinyassets/api/`:** `universe_helpers.py`, `universe_ops.py`, `branches.py` (largest at ~3,282 LOC), `runs.py`, `evaluation.py`, `market.py` (goals + gates + escrow + outcomes + attribution bundled), `runtime_ops.py`, `wiki.py`, `status.py`.
- **Pattern A (Single FastMCP instance, decorators on shared `mcp`)** recommended over Pattern B (mount-based isolation) — Pattern B would change all tool names and break chatbot integrations. Defer to future breaking-change window.
- **`universe_server.py` becomes a ~100-LOC aggregator shim** that re-exports from `tinyassets/api/*` to preserve the 23 existing importers — Strategy 1 (compat shim) over Strategy 2 (migrate all 23 immediately).
- **No behavior change** — pure refactor.
- **Estimate:** ~5 dev-days across 8 sequential commits, each green on `pytest` + `ruff` between.

---

## 3. Recommendation matrix

| Aspect | Recommendation | Confidence |
|--------|----------------|------------|
| **Direction** (do this work at all) | ACCEPT — the file is the #1 hotspot per spaghetti audit, and PLAN.md's "second domain" pressure test motivates #28. | High |
| **Sequence #28 before #29 OR #29 before #28** | #29 first (extract engine submodules); #28 last (extract domain). Reason: shared helpers (`_universe_dir`, `_default_universe`, `_read_json`, etc.) need a stable home in `universe_helpers.py` before domain handlers can safely import them. | High |
| **Bundle execution OR separate** | Bundle — they're the same file; doing them in two separate efforts means touching the file twice. | Medium-high |
| **Pattern A (shared mcp)** | ACCEPT for Phase 1. Pattern B (mount + tool-prefix) is correct long-term but breaks chatbot integrations. | High |
| **Aggregator-shim strategy** | ACCEPT — preserves 23 importers, lower-risk migration. | High |

---

## 4. Risks + mitigations

| Risk | Mitigation |
|------|------------|
| **Merge conflicts during 5-day refactor.** Multiple devs touch `universe_server.py` regularly (#21 wiki cosign, #22 add_canon followups, recent task lineage shows constant activity). | Wait until current in-flight tasks land. Tag a quiet window. Each of the 8 commits is small + independently mergeable, so refactor can pause between commits if a hotfix needs the file. |
| **Domain extraction premature** if rename Phases 2–4 haven't landed (handlers would be renamed twice). | Sequencing gate explicit: rename Phases 2–4 → domain extraction. Audit #28 §6 documents this. |
| **Universe-to-Workflow-Server file rename** (per `docs/design-notes/2026-04-19-universe-to-tinyassets-server-rename.md`) is blocked on host §5 answers. If file moves to `workflow_server.py`, extraction reapplies cleanly but adds one rename round-trip. | Either rename first OR extract first — both valid. Audit #29 notes "doing extraction first is fine and slightly simplifies the rename." |
| **Pattern A circular-import risk** (`workflow.api → workflow.api.branches → workflow.api`). | Resolved by leaf module `workflow.mcp_setup` holding the FastMCP instance — explicitly called out in audit #29 §6. |

---

## 5. Sequencing gates (what must land first)

1. **Rename Phases 2–4** — clean handler identifiers before moving handlers (gates #28 only, not #29).
2. **In-flight tasks #21/#22** — anything currently touching `universe_server.py` must land before the refactor starts (gates both #28 and #29).
3. **Domain extraction (#28)** must follow `universe_helpers.py` extraction (gates #28 only). #29's first commit (`universe_helpers.py`) is the unblocker.

---

## 6. Outstanding host questions

Both audits surface decisions only the host can make:

**From #28 §8:**

1. **Tool shape after extraction.** Should domain actions remain accessible via `universe(action="query_world")` (engine delegates to domain) or surface as a separate domain-registered tool (e.g. `fantasy(action="query_world")`)? Latter is cleaner long-term; former preserves existing chatbot flows.
2. **Security-surface placement.** `add_canon_from_path` has `TINYASSETS_UPLOAD_WHITELIST` enforcement. Should the whitelist check stay engine-side (policy enforcement at the boundary) or move with the handler to the domain?
3. **Registration hook.** Import-time declarative registration vs explicit `register(mcp)` call from engine startup?

**From #29:** No new asks beyond the in-flight rename design note's §5 host questions, which already track separately.

---

## 7. Recommended host action

**Option A (full accept):** Approve direction. Lead schedules execution after rename Phases 2–4 land + in-flight tasks #21/#22 land. Answer 3 host questions in §6 above before extraction starts.

**Option B (partial accept):** Approve #29 (decomposition only) now; defer #28 (domain extraction) until rename phases land. Lower coordination cost; same 5-day estimate slips a week or two.

**Option C (defer entirely):** Mark as approved-but-unscheduled. Capture as a STATUS.md Approved-Specs row with no execution date. Spaghetti audit hotspot persists; PLAN.md "second domain" test still fails until done.

**Navigator's recommendation:** Option A. The file gets bigger every week (13,067 LOC today, was 9.9K at the original spaghetti audit) — postponing increases blast radius, not decreases it. The 5-day estimate is small relative to the structural payoff (PLAN.md commitment satisfied + #1 hotspot retired). The 3 host questions are scope-defining, not blocking — execution starts as soon as they're answered.

---

## 8. If accepted, what changes for the team

- Lead adds 8 sequential STATUS.md Work rows (one per submodule extraction commit).
- Dev claims rows in audit #29 §8 order: helpers → wiki → status → runs → evaluation → runtime_ops → market → branches.
- After all 8 land, Domain extraction (#28) becomes a separate dispatch (~2 dev-days, two more commits).
- `universe_server.py` shrinks to ~100 LOC aggregator shim. Most devs stop touching it; new code goes to the right submodule by domain.

---
title: Step 11+ retarget sweep ROI analysis (audit "100-LOC routing shell" target push)
date: 2026-04-27
author: navigator
status: read-only ROI analysis — host decision pending
companion:
  - docs/audits/2026-04-25-universe-server-decomposition.md (audit's "~100-LOC routing shell" target)
  - docs/exec-plans/completed/2026-04-26-decomp-step-{8,9,10,11}-prep.md (Steps 8-11 prep series; this doc continues from Step 11 prep §9.7)
load-bearing-question: Does the ~6-hour mechanical retarget sweep (1,400 → 150 LOC) earn its keep, or is post-Step-11 ~1,400 LOC the right steady state?
audience: lead, host (final scope decision)
---

# Step 11+ retarget sweep — ROI analysis

## TL;DR

After Steps 1-11 land, `tinyassets/universe_server.py` settles at **~1,400 LOC** — a **90% reduction** from baseline 14,012. The audit's literal "~100-LOC routing shell" target requires one additional mechanical pass: change ~317 test-import + monkeypatch sites across the codebase from `workflow.universe_server.X` to canonical `workflow.api.<module>.X` paths, then delete the back-compat re-export shims (~700 LOC of shim removal).

**Recommendation: DEFER until a concrete trigger appears.** The sweep is ~5-7 wall-hours of mechanical work for a 1,250-LOC additional reduction (~9% of baseline). At ~1,400 LOC residual the file is already legible, every MCP tool is one file, every dispatch table is co-located. The marginal benefit of dropping to ~150 LOC is real but small relative to other available work. If a concrete trigger appears later (e.g. a host-visible refactor friction, a new MCP tool that needs a clean slate), revisit.

---

## 1. Concrete count of mechanical edit surface

Surveyed via grep across `tests/` (2026-04-27, post-Step-7 code):

| Surface | Count |
|---|---|
| `from workflow.universe_server import …` lines | **261** |
| Distinct test files with such imports | **53** |
| Unique import-line bodies (after dedup) | **92** |
| Distinct symbols imported | **~86** |
| `patch("workflow.universe_server.X", …)` sites | ~50 |
| `monkeypatch.setattr(us, "X", …)` sites | ~6 |
| **Total mechanical edit sites** | **~317** |

**Average ~6 sites per file** across 53 files. Most edits are single-line: change `from workflow.universe_server import _current_actor` → `from workflow.api.engine_helpers import _current_actor`.

### Top patch targets (by frequency, from grep sample)

| Symbol | Sites | Canonical destination after Steps 8-10 |
|---|---|---|
| `_base_path` | ~15 | `workflow.api.helpers` (Step 8 — already extracted) |
| `_current_actor` | ~10 | `workflow.api.engine_helpers` (Step 10) |
| `_storage_backend` | ~5 | `workflow.api.engine_helpers` (Step 10) |
| `_universe_dir`, `_default_universe` | ~7 | `workflow.api.helpers` (Step 8) |
| `_daemon_liveness` | 1 | `workflow.api.universe` (Step 9) |
| `_action_*` (28 universe-tool actions) | ~30 | `workflow.api.universe` (Step 9) |
| `_action_*` (rest — runs/judgment/market/runtime_ops) | ~50 | `workflow.api.{runs,evaluation,market,runtime_ops}` |
| `_ext_*`, `_load_nodes`, `_save_nodes` | ~10 | `workflow.api.extensions` (Step 11) |
| `_ext_branch_*`, `_BRANCH_ACTIONS` | ~30 | `workflow.api.branches` (Step 8) |
| `_gates_enabled` | 2 | `workflow.api.market` (Step 7 — already extracted) |
| `WRITE_ACTIONS` | 5 | `workflow.api.universe` (Step 9) |
| `_CONTROL_STATION_PROMPT` | 1 | `workflow.api.prompts` (already extracted) |
| Other (rare) | ~150 | various |

**Conclusion:** The 317 sites distribute across ~10 destination submodules. No single bottleneck; mechanical sed-style replacements with destination derived from the symbol name + a small lookup table.

---

## 2. Effort estimate

### Per-edit unit cost

- **Find:** grep already produced the catalog (above); script can dump symbol → destination map.
- **Edit:** single-line sed replacement.
- **Verify:** run the affected test file individually to confirm green.

### Optimistic path (sed-script + verify-by-file)

1. Write a 50-line Python script: walks tests/, parses `from workflow.universe_server import X, Y, Z`, looks up X/Y/Z in the symbol → destination map, regenerates the import line(s) with one line per destination submodule. ~30 min.
2. Run the script. ~5 min.
3. `pytest tests/ -q` against the affected files. ~10-30 min depending on test wall-time.
4. Investigate any breakage (likely 5-10 cases where the symbol → destination map is wrong or the symbol moved more than once across the decomp). ~1-2 hours.
5. Same for monkeypatch sites — separate sed pass for `patch("workflow.universe_server.X", …)` → canonical path. ~30 min script + 30 min run.
6. Final full-suite `pytest -q`. ~30-60 min.
7. Delete the back-compat re-export shims in `tinyassets/universe_server.py` (~700 LOC of shim block deletions). ~30 min.
8. Re-run full suite. ~30-60 min.
9. Update the symbol → destination map doc, commit, ship.

**Optimistic total: ~5-6 hours** with no surprises.

### Realistic path (with surprises)

Add 1-2 hours for:
- Symbol-name collisions (a handful of `_action_*` names exist in multiple modules with intentionally different signatures — needs disambiguation).
- Tests that import a symbol via `import workflow.universe_server as us` then access `us.X` in many places (not caught by the import-line sed; need a separate `us.X` → `<canonical_module>.X` pass).
- Tests that monkeypatch a symbol that was the back-compat re-export AND a symbol that exists at the canonical path — needs both patches dropped (otherwise double-patching).
- Plugin-mirror parity check — the `packaging/claude-plugin/.../runtime/tinyassets/` mirror has the same back-compat shims; need to mirror the deletion. Plus mirror's own test harness.

**Realistic total: ~6-8 hours.** Step 11 prep §9.7 said ~6h; that estimate stands.

---

## 3. Risk profile

### Low-risk (mitigated by mechanical nature)

- **Sed-style edits don't change behavior.** Each edit is "import the same symbol from a different module path." Tests should pass identically.
- **Test failures are loud.** If the symbol → destination map is wrong, the test fails on import; we fix the map and re-run.
- **Per-file verification cadence.** Run the affected test file individually before moving on; quick feedback loop.

### Medium-risk

- **Re-export shim removal is the one-way step.** Once the shims are deleted, anything that still imports from `workflow.universe_server` breaks. Mitigation: run full suite green BEFORE deleting any shim. If green, the shims are unused and safe to delete.
- **Plugin-mirror drift.** `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/` ships a mirror of `tinyassets/`. Mirror's test harness lives separately. Risk: mirror passes locally but installed plugin breaks for a chatbot client. Mitigation: post-sweep, run `python packaging/claude-plugin/build_plugin.py` + `pytest packaging/claude-plugin/.../tests -q`.
- **External callers.** Anyone outside the repo importing `workflow.universe_server.X` would break. Mitigation: this is a private internal module; no external API contract. Document the change in CHANGELOG anyway.

### High-risk (none identified)

- No behavior change. No external API surface change. No data migration. No environment variable change. No test-fixture change.

**Net risk: LOW.** Mechanical work with loud failure modes.

---

## 4. ROI vs alternatives

### What the sweep buys

| Metric | Before (post-Step-11) | After sweep | Delta |
|---|---|---|---|
| `universe_server.py` LOC | ~1,400 | ~150 | −1,250 (−89%) |
| `universe_server.py` content | imports + 7 Pattern A2 wrappers + 2 @mcp.prompt + main + custom_route + ~700 LOC shim block + banners | imports + 7 Pattern A2 wrappers + 2 @mcp.prompt + main + custom_route + ~50 LOC banners | shim block deleted |
| Reduction from baseline (14,012 LOC) | 90% | 99% | +9 percentage points |
| Test imports paying mental cost | ~317 sites point at `workflow.universe_server` | 0 sites — all canonical | clearer reading flow |
| Future-extraction cost | adding new module requires shim row | adding new module is just an export | small ergonomics win |

### What the sweep does NOT change

- No behavior change. Public MCP surface identical. Live chatbots see no difference.
- No new feature. No new test coverage. No bug fix.
- No reduction in API submodule size — extensions.py / universe.py / etc. are unchanged.
- No improvement in chatbot leverage — all evaluator/primitive gaps remain (Priya's 5 chain-breaks, etc.).

### Alternative uses of 6 hours

| Alternative | What it buys |
|---|---|
| Methods-prose evaluator v1 (if host approves §3 of `2026-04-27-methods-prose-evaluator.md`) | Closes a real chain-break for academic users; ships a reusable Evaluator subtype |
| Recency composition example for run query + goal/branch lookup (Priya signal C — INBOX) | Preserves continuity intent without new engine verbs; retired as platform primitive 2026-05-01 |
| `run_branch resume_from=<run_id>` (Priya signal E + Devin Session 2 — INBOX) | Accepted post-#18 single-param add on existing `run_branch`; no standalone `continue_branch` |
| Cloud daemon redeploy verification (Mark MARK-F1/F2 + BUG-028 + BUG-034 + ~10 surfaces) | Lands shipped fixes in production |
| 3 architecture-audit reviews (#5, #6, #9-#11 from STATUS) | Unblocks multi-week design decisions |
| Half-day Layer-3 design session (host-scheduled per STATUS) | Multi-week strategic direction |
| Tier-1 Investigation routing-resolver (existing wiki plan) | Closes a known engine concern with cross-domain validation from Mark |

**Every alternative buys more 3-layer leverage** (system → chatbot → user) than dropping universe_server.py from 1,400 to 150 LOC.

---

## 5. Acceptance criteria (if approved later)

The sweep is "done" when:

1. `wc -l tinyassets/universe_server.py` ≤ 200.
2. The file's contents enumerate to:
   - Module imports + setup (~50 LOC).
   - `mcp = FastMCP(...)` instance creation (~20 LOC).
   - `@mcp.custom_route("/")` health-check (~20 LOC).
   - 7 `@mcp.tool()` Pattern A2 wrappers — `universe`, `extensions`, `goals`, `gates`, `wiki`, `get_status`, `branch_design_guide` (Pattern A2; `branch_design_guide` is `@mcp.prompt`) (~470 LOC).
   - 2 `@mcp.prompt()` registrations — `control_station`, `extension_guide` (~30 LOC).
   - `main()` daemon entrypoint (~50 LOC).
   - Module banners + comments (~30 LOC).
3. `grep -rE "from workflow.universe_server import" tests/` returns ≤ 20 lines (only the cross-Pattern-A2 wrapper imports — `extensions`, `universe`, `goals`, `gates`, `wiki`, `get_status` — which legitimately route through universe_server.py for the @mcp.tool decoration).
4. `pytest -q` green.
5. `python packaging/claude-plugin/build_plugin.py` clean parity check.
6. `python scripts/mcp_probe.py --tool universe --args '{"action":"list"}'` returns valid response. (Pattern A2 wrapper sanity check.)

---

## 6. Recommendation

**DEFER until a concrete trigger appears.**

### Why defer

- Step 11 already achieves the audit's stated principle ("make universe_server.py readable + composable"). At ~1,400 LOC residual + 9 well-bounded API submodules, every MCP tool is one file, every dispatch table is co-located, the `mcp` instance + Pattern A2 wrappers are unambiguously owned by universe_server.py.
- The literal "~100-LOC" target was an aspirational floor in the audit, not a load-bearing requirement.
- The 6-hour cost is real and the marginal benefit (1,400 → 150 LOC) is small relative to other available work that closes user-facing chain-breaks.
- No external pressure: no client-visible surface depends on the residual being smaller; no incoming refactor needs the slate clean.

### When to revisit

Trigger conditions that would justify dispatching the sweep:

1. **A new MCP tool extraction** (e.g., a hypothetical `gates2` / `goals2` tool) where the sweep would land naturally as setup. The marginal cost of doing it then is much lower because the slate-clearing happens en route to the new feature.
2. **Mechanical-refactor opportunity bundling.** If we ever do a `pytest`-fixtures migration or a plugin-runtime restructure, fold the retarget sweep into the same PR — incremental cost ~0.
3. **Host-visible friction.** If host or a contributor reports "the back-compat shim block is making it hard to find canonical paths" or similar concrete friction. Speculative today; concrete then.
4. **Onboarding pressure.** If a new contributor (Tier 3 OSS or human) trips on the shim re-exports during a first-PR. Concrete signal worth catching.

### What to do now

- Land Steps 8 → 9 → 10 → 11 as planned. Achieve ~1,400 LOC residual + 9 API submodules.
- Capture this analysis at `docs/exec-plans/active/2026-04-27-step-11plus-retarget-sweep-roi.md` (this file).
- After Step 11 lands: lead surfaces "Step 11+ sweep DEFERRED — see ROI analysis" as a single-line entry in STATUS Concerns or `ideas/PIPELINE.md` Active Promotions, so the deferred state is visible if a trigger condition surfaces.
- Re-evaluate when any §6 trigger fires.

---

## 7. Decision asks for the lead → host

1. **Defer the sweep?** Recommend yes. 6 hours of mechanical work for 1,250-LOC reduction (already 90% of baseline shipped); higher-leverage alternatives exist in the queue.
2. **Capture the deferred state where?** Recommend single line in `ideas/PIPELINE.md` Active Promotions table: state=design-note-landed, next-home=this file, owner=navigator-on-trigger. Alternative: STATUS Concerns row (more visible but consumes board budget).
3. **Trigger conditions worth committing to?** §6 §1-§4 are illustrative. If host wants explicit "do the sweep when X happens" criteria, list them here so a future session can recognize the trigger.
4. **Plugin-mirror parity** — confirm the sweep would include `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py` mirror update. (Yes — same shims live there; same deletion needed.)

---

## 8. Cross-references

- `docs/audits/2026-04-25-universe-server-decomposition.md` — original audit + "~100-LOC routing shell" target.
- `docs/exec-plans/completed/2026-04-26-decomp-step-11-prep.md` §9.7 — surfaced this analysis as decision-needed.
- `STATUS.md` Concerns — methods-prose evaluator row (2026-04-27) is a higher-leverage alternative.
- `ideas/INBOX.md` 2026-04-27 entries — 5 chain-break proposals from Priya/Devin sessions; each is a higher-leverage alternative.
- `feedback_status_md_host_managed` — host curates STATUS; navigator proposes only.

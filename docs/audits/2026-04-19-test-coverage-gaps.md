# Test Coverage Gaps — 2026-04-19

Audit of `tinyassets/*.py` top-level modules + `scripts/*.py` to identify zero-coverage and thin-coverage hotspots. Ranked by "uplift on confidence per unit of test effort" (high LOC + high fan-in + zero coverage = worst).

**Method:** cross-referenced every top-level module against `tests/test_*.py` import grep. Counted direct imports only (`from workflow.X` / `from workflow import X`). Shim path `workflow.author_server` aliases to `workflow.daemon_server`, so `daemon_server` coverage is reported via the shim. LOC from `wc -l`. Skipped modules flagged in navigator's top hotspots (`docs/audits/2026-04-19-project-folder-spaghetti.md` §#1, §#2, §#4, §#6) since they will receive tests during the refactor.

**No code modified during audit.**

---

## Zero-coverage modules (direct import-count = 0)

After removing the shim-backed cases, two modules have genuine zero coverage:

| # | Module | LOC | What it does | One-sentence test shape |
|---|--------|-----|--------------|-------------------------|
| 1 | `tinyassets/node_eval.py` | 526 | Per-node evaluation orchestration — runs a registered node's evaluator against an output, returns scored verdict. Load-bearing for autoresearch optimization and evaluator layers (PLAN.md §33). | Table-driven: register a fake node with a stub evaluator (returns fixed score), call the module's entry point, assert the verdict shape + score propagation. Add one adversarial case (evaluator raises) to pin the graceful-fallback contract. |
| 2 | `tinyassets/node_sandbox.py` | 382 | Sandboxed execution surface for node code — subprocess isolation + I/O boundary. Security-critical for paid-market node execution (per `project_node_software_capabilities`). | Mock-based: patch `subprocess.Popen` with a fake that captures argv + env + stdin, call each entry point, assert argv quoting, timeout enforcement, and that no host-side env vars leak into the sandbox. Negative test: sandbox must reject binaries outside the host registry's approved set. |

**These are the two most important test-coverage holes in the repo.** High LOC, load-bearing product surfaces, zero direct tests.

---

## Thin-coverage modules (direct import-count = 1, LOC ≥ 100)

One test importing a 400-LOC module is typically a single happy-path check — the bulk of branches are untested. Candidates for follow-up coverage work once #1–#2 above land.

| Rank | Module | LOC | Imports | Likely gap + test-shape hint |
|------|--------|-----|---------|------------------------------|
| 3 | `tinyassets/docview.py` | 455 | 1 | Scoped reader for large MD/JSON files — heading/section/lines/search/json-keys/json operations. One test likely pins one command shape. Missing: search-inside-section combined mode, JSON-path edge cases (missing keys, array traversal), limit-exceeded error path, binary-file rejection. |
| 4 | `tinyassets/protocols.py` | 417 | 1 | Typed protocol surfaces. Single test probably pins one protocol. Missing: protocol-conformance fixtures for each (verifying concrete implementers satisfy the contract) — table-driven across implementers. |
| 5 | `tinyassets/mcp_server.py` | 315 | 1 | MCP server integration shell. Missing: tool-registration-table pinning (assert exact set of registered tool names), tool-description fingerprint (pin a short hash of serialized descriptions to catch accidental edits), prompt-registration symmetry between serverInfo and the actual `@mcp.prompt` set. |
| 6 | `tinyassets/singleton_lock.py` | 200 | 1 | Host singleton lock file (one tray per host). Missing: concurrent-acquire simulation (two threads/processes), stale-lock cleanup, crash-during-acquire recovery. Feature-flag with `tmp_path`; no live filesystem race required. |
| 7 | `tinyassets/subscriptions.py` | 161 | 1 | Branch/universe subscription model. Missing: subscribe + unsubscribe idempotency, listeners fire on the right event shape, cross-universe isolation. |
| 8 | `tinyassets/packets.py` | 133 | 1 | Wire-format typed packets for cross-daemon messaging. Missing: serialize → deserialize roundtrip for each packet type, schema-drift detection (pin a frozen schema hash). |
| 9 | `tinyassets/bid_execution_log.py` | 139 | 2 | Paid-market bid-execution journal. Missing: write-read-roundtrip with concurrent writers, log-rotation / truncation behavior, replay on crash. Aligns with `project_paid_market_trust_model`. |
| 10 | `tinyassets/settlements.py` | 120 | 2 | Batch settlement for <$1 micropayments (per `project_q10_q11_q12_resolutions`). Missing: aggregation math (N bids → 1 settlement), fee calculation (1% floor), settlement idempotency on replay. |

---

## Scripts with zero tests

`scripts/*.py` are standalone helpers, not part of any package. `scripts/claude_chat.py` + `scripts/tab_watchdog.py` got tests this session (`d614ec9`). Remaining:

| Script | LOC | Priority | Why |
|--------|-----|----------|-----|
| `scripts/always_allow_watch.py` | ? | LOW | Session-hook utility; tested in practice via user-sim loops. |
| `scripts/build_shims.py` | ? | MEDIUM | Rename-era shim generator; will retire at Phase 5. Probably not worth testing in its end-of-life state. |
| `scripts/capture_idea.py` | ? | already covered | `tests/test_capture_idea.py` exists. |
| `scripts/docview.py` | ? | MEDIUM | Same surface as `tinyassets/docview.py`; consider a shared test module once the tinyassets/ side is covered. |
| `scripts/migrate_canon.py` | ? | LOW | One-shot migration; covered in practice via user-sim runs. |
| `scripts/migrate_imports.py` | ? | LOW | One-shot migration; end-of-rename-life. |
| `scripts/rebuild_sporemarch_kg.py` | ? | LOW | One-shot utility. |
| `scripts/user_sim_auth_hook.py` | ? | LOW | Session-hook; practical coverage via user-sim. |

---

## Skipped (in navigator's top-3 hotspots — will get tests during refactor)

Per navigator's §#1, §#2, §#4, §#6 in `docs/audits/2026-04-19-project-folder-spaghetti.md`:

- `tinyassets/universe_server.py` (9,895 LOC, 43 test imports) — heavy coverage already, but the refactor to `tinyassets/api/*` will generate new test files per extracted sub-dispatch.
- `tinyassets/daemon_server.py` (3,575 LOC, effectively 19 via `author_server` shim) — storage-split will generate `tests/test_storage_*` files per extracted context.
- `tinyassets/memory/node_scope.py` + `tinyassets/memory/scoping.py` — dedup post-2c-flip will rewrite tests.
- `tinyassets/discovery.py` — entry-points migration will rewrite.

---

## Recommended follow-up task breakdown

Each of the top-10 above is a dispatchable atomic task. Suggested ordering:

1. **node_sandbox.py tests** — HIGH priority; security-critical surface. ~1 dev-day including fake subprocess + signature verification paths.
2. **node_eval.py tests** — HIGH priority; load-bearing for autoresearch. ~0.75 dev-day.
3. **mcp_server.py tool-registration fingerprint** — guards against accidental tool-description edits that user-facing `control_station` prompt relies on. ~0.5 dev-day.
4. **singleton_lock.py race tests** — needed before #19 (tab_watchdog tray integration) since that feature depends on singleton behavior. ~0.5 dev-day.
5. **packets.py schema-drift fingerprint** — cheap insurance against wire-format regressions. ~0.25 dev-day.
6. **protocols.py conformance fixtures** — table-driven; ~0.5 dev-day.
7. **docview.py combined-mode + JSON edge cases** — ~0.5 dev-day.
8. **subscriptions.py idempotency + isolation** — ~0.5 dev-day.
9. **bid_execution_log.py concurrent-write + replay** — ~0.75 dev-day; aligns with paid-market surfacing.
10. **settlements.py batching math** — ~0.5 dev-day; aligns with §Q10 batching.

Total: ~6 dev-days of coverage work to close the top-10 gaps. Not critical-path — refactor work (#27B hotspots) will reshape some of these, so sequencing is "opportunistic unless the gap is security-critical (sandbox) or autoresearch-critical (node_eval)".

---

## Non-findings

- **No orphaned dead-code modules detected** at the top level. Every `tinyassets/*.py` has at least one call site (direct or via shim).
- **Test directory density is healthy** — 127 test files covering 35 modules + 16 subpackages = good module-to-test ratio on average. The gap is *concentration*: a few critical modules carry zero direct coverage while others have 20+.
- **No collision with navigator's #27 hotspot list.** The top-2 zero-coverage modules (`node_eval`, `node_sandbox`) are NOT in navigator's refactor hotspot list — safe to add tests without rework risk.

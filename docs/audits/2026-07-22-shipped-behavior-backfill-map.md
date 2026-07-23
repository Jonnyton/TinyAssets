# Shipped behavior OpenSpec backfill map — Wave 1

- **Freshness:** 2026-07-22 PT
- **Baseline:** `origin/main` at `2190f65d6742c7199e1d705bd92e3685f23a31b1`
- **Source:** PR #1616 full-coverage audit, reverse-direction findings
- **Scope:** four coordination-edge-free shipped contracts; requirements only, no runtime or canonical-spec edits

## Verdict

Wave 1 can close four of the seventeen reverse-direction coverage groups without choosing future architecture or writing an actively claimed file. Existing canonical requirements in these capabilities remain accurate; every delta is additive and preserves current limitations.

## Requirement-to-evidence map

| Capability / proposed requirement | Source evidence | Test or executable evidence | Limitation / coordination result |
|---|---|---|---|
| `constraint-evaluation` — incremental validation accumulates scenes in input order | `tinyassets/constraints/asp_engine.py:129-197` creates one `clingo.Control`, grounds base once, adds `step_<n>` in order, and solves after each addition. | `tests/test_asp_solver.py:227-247` proves ordered one-result-per-scene multi-shot use; direct focused assertions cover empty and cumulative shapes. | Violation strings use base/world plus current-scene text and are not an exact accumulated UNSAT core. No active write edge. |
| `desktop-host-runtime` — installed GUI command uses current platform name | `pyproject.toml:56-64` maps GUI command `tinyassets` to `tinyassets.desktop.launcher:main`; `tinyassets_tray.py:47-70` keeps the source tunnel opt-in, already owned by the canonical tray requirement. | Direct `tomllib` assertion proves current metadata. `tests/test_desktop.py:1311-1321` is stale and still expects `workflow`; it is verification debt, not source truth. | No packaged installer or cross-platform tray guarantee. `tests/` is claimed by another provider, so this lane records rather than edits the stale assertion. |
| `development-coordination-runtime` — guard/mirror checks and JSON diagnostics | `scripts/check_cross_provider_drift.py:42-58,103-107,153-251,420-441`; JSON emitters at `scripts/claim_check.py:450-519,538-565`, `scripts/worktree_status.py:576-605`, and `scripts/provider_context_feed.py:582-615`. | `check_cross_provider_drift.py --self-test`; existing `tests/test_worktree_status.py`, `tests/test_provider_context_feed.py`, and checker self-tests; direct JSON parse smoke for all four tools. | Diagnostic only; no auto-repair. Default skill scans cover every pair, targeted scans cover named pairs, and comparison is normalized readable text rather than byte integrity. Current JSON forms add no schema-version promise. No active write edge. |
| `domain-plugin-runtime` — domain Branch-slug and episodic-coordinate registries | `tinyassets/domain_registry.py:31-44,76-134`; fantasy shape registration at `domains/fantasy_daemon/memory/schemas.py:20-28`. | `tests/test_goal_pool.py:375-454` proves loaded/unloaded domain-slug consequences; direct registry assertions prove sorting, deduplication, replacement, tuple normalization, and absent resolution. | Mutable process-local registries only; no persistence, synchronization, thread-safety, or shared-table schema mutation. Registry absence is not an access-denial proof: the Goal-pool filter intentionally fails open when the entire accessible-slug set is empty. No active write edge. |

## Explicit exclusions retained for Wave 2

The following thirteen groups are not silently covered here: community patch-loop GitHub behavior, credential mapping/storage boundary, daemon identity metadata, daemon runtime lease/cancellation/GC, external-effect adapters, child-Branch execution, OKF export, live MCP metadata and status identity, provider retry semantics, Goal aliases, universe switching, uptime controllers, and wiki mutation semantics. Their active credential, distributed-execution, OKF, connector, universe, Goal, uptime, wiki, or effect dependencies remain authoritative.

## Completion evidence required

1. Strict validation of this change and the entire OpenSpec tree.
2. Focused tests/direct assertions for every source contract, with the stale GUI test reported separately.
3. Independent review that compares each SHALL/MUST clause to source and verifies no future behavior leaked into the deltas.
4. Fresh overlap/branch audit immediately before publication and again before canonical sync.

## Verification evidence

Freshness: 2026-07-22 PT, Windows, Python 3.14.3, worktree `wf-openspec-backfill-shipped-behavior`.

- `openspec validate backfill-shipped-behavior-coverage --strict`: passed.
- `openspec validate --all --strict`: 34 passed, 0 failed.
- `python -m pytest -q tests/test_asp_solver.py tests/test_goal_pool.py`: 63 passed.
- `python scripts/check_cross_provider_drift.py --self-test`: passed.
- `python -m pytest -q tests/test_worktree_status.py tests/test_provider_context_feed.py`: 38 passed, 1 failed. The failure is the already-audited Windows CRLF assertion at `tests/test_worktree_status.py:356`; actual UTF-8 output is correct and differs only by `\r\n` versus the test's `\n` expectation.
- Direct assertions passed for the exact `tinyassets` GUI entry, cumulative/empty incremental ASP results, Branch-slug sorting/deduplication, episodic-coordinate tuple normalization/replacement, and absent-domain resolution.
- JSON parse/shape smokes passed for claim checking, worktree status, provider context, and cross-provider drift. Human versus JSON selection semantics were also covered by the focused coordination tests above.
- `git diff --check`: passed; `STATUS.md` is 57 lines.
- The Windows-forbidden layer-2 uptime canary was not run. No public or runtime behavior changed, so rendered chatbot and production-use proofs do not apply to this proposal-only lane.

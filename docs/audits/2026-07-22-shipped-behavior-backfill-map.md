# Shipped behavior OpenSpec backfill map — Wave 1

- **Freshness:** 2026-07-22 PT
- **Baseline:** `origin/main` at `8cab31d8b734720f826a66045c1e962b44e54b72` (PR #1620 landed)
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

## Residual decomposition after fresh re-grounding

Freshness: 2026-07-22 PT against `origin/main` `8cab31d8`. Each disposition below is either an independent successor lane or an explicit absorption/correction in an existing owner. “Proposal-safe” permits an as-built proposal, not implementation of future behavior or canonical sync across an active owner.

| Reverse-coverage group | Exact successor disposition | Readiness and hard boundary |
|---|---|---|
| Community patch loop / GitHub behavior | Split into `backfill-community-patch-loop-run-reuse` and `backfill-community-patch-loop-github-effects`. | Run reuse is proposal-safe. GitHub effects waits for credential, distributed-execution, external-receipt, and boundary-layer authority review. |
| Credential mapping/storage boundary | `backfill-legacy-credential-materialization`, or fold into the accepted credential migration. | Blocked: current materialization is plaintext or base64, fixed-temp, non-transactional, whole-vault replacement and does not make every accepted provider mapping reachable. It cannot establish BYOC isolation. |
| Daemon identity metadata | `backfill-daemon-host-pool-contracts`. | Proposal-only after distributed-execution and universe owners settle identity and host-pool authority. |
| Daemon runtime lease/cancellation/GC | `backfill-local-daemon-lease-queue-contracts`. | Proposal-only after the host-pool contract; local receipts are not signed leases or proof of owner-daemon authority. |
| External-effect adapters | `backfill-external-effect-adapters`, layered under canonical `external-effect-receipts`. | Proposal-safe now; clean verification and canonical sync wait for repair of one stale `workflow-wiki-write-back:*` assertion and review against `build-forward-platform-capabilities`. Exclude future deterministic keys, caps/holds, reconciliation, proxy trust, and batch atomicity. |
| Child-Branch execution | `backfill-graph-child-run-contracts`. | Proposal-safe with read coordination against distributed execution; current child-run receipts are local execution evidence, not marketplace or remote-host authority. |
| OKF export | `backfill-okf-export-projection`. | Planning/proposal-safe; canonical sync waits for the brain OKF owner. Export is a path-filtered projection, not ACL enforcement or a canonical/write-through store. |
| Live MCP metadata and status identity | Split into `backfill-live-mcp-catalog-metadata` and `backfill-status-response-variants`. | Catalog waits for connector-manifest and legacy-tool retirement. Status variants wait for identity/reset because current early, configured, and full responses differ. |
| Provider retry semantics | Absorb into R2-1b as `reconcile-provider-call-retry-and-receipts`. | Same `tinyassets/providers/call.py` write edge. Current behavior retries only `AllProvidersExhaustedError`, at most three router calls; it does not prove BYOC or maintainer-quota isolation. |
| Goal aliases | `reconcile-goal-compatibility-aliases`. | Wait for `retire-legacy-live-mcp-tools`; aliases currently route through the legacy Python `goals` wrapper and must not be advertised as public canonical tools. |
| Universe switching | `backfill-universe-switch-scope`. | Planning/proposal-safe; sync waits for universe creation, identity/reset, and PR #1484. Authenticated switch is currently an acknowledgment, not session persistence. |
| Uptime controllers | `backfill-uptime-edge-canaries` for DNS + LLM binding; absorb release behavior into `release-reconcile-event-trigger`; correct disk behavior in `fix-disk-pressure-controller-sequencing` before backfill. | DNS/LLM proposal is safe and must preserve stable concurrency groups, `cancel-in-progress: false`, and bounded timeouts. The disk service currently stops before rotation/autoprune when pressure makes `disk_watch.py` exit 1; comments/tests must not be canonized as working sequencing. When promoted, the corrective Files claim must include its change directory, `deploy/tinyassets-disk-watch.service`, and focused sequencing tests, plus timer/scripts only if edited. |
| Wiki mutation semantics | `backfill-wiki-mutation-and-maintenance-contracts` for delete, consolidate, lint, project sync, and cosign. | Wait for PR #1550, then re-ground sequentially with `harden-canonical-absolute-guarantees` as a `wiki-commons` sync-order dependency. Current operations include best-effort/non-atomic I/O and heuristic validation; cosign is not CAS, locking, or reputation proof. |

Focused research evidence: provider retry/Goal aliases 46 passed; DNS/LLM/disk workflow and unit suite 103 passed; wiki 169 passed; effect adapters 89 passed with one stale rename assertion. None of these residual contracts establishes a compute exchange, price oracle, training procurement, model-host bidding, settlement/escrow, BYOC ownership, maintainer-quota isolation, organization authority, regulated-industry compliance, Zapier parity, or DEX/AMM economics.

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
- `git diff --check`: passed; `STATUS.md` is 58 lines.
- The Windows-forbidden layer-2 uptime canary was not run. No public or runtime behavior changed, so rendered chatbot and production-use proofs do not apply to this proposal-only lane.

## Context

The full-coverage audit found 17 shipped behavior groups without material canonical ownership. Eight collide with active credential, distributed-execution, Brain, connector, universe, or release work. The nine in this change have disjoint canonical destinations and can be reconciled without choosing a future design.

## Goals / Non-Goals

**Goals:**

- Make nine current behavior groups strict-valid as-built requirements.
- State exact current edge behavior, including cumulative ASP grounding, dry-run/refusal paths, and compatibility mappings.
- Introduce one canonical owner for the already-shipped external-effect adapter layer.
- Keep shared soul-authority, consent, and receipt semantics in `external-effect-receipts` while specifying how each adapter uses them.

**Non-Goals:**

- Change product-runtime, public-tool, storage, or deployment behavior. Focused test assertions and coordination-script output may be corrected to match the shipped contract and remain portable.
- Pull any of the eight dependency-bound backfills into this lane.
- Promise future effect-key determinism, batch caps, signed remote authority, or whole-batch atomicity.

## Decisions

### D1. Split the reverse-coverage backlog at active-change boundaries

This change owns only destinations with no current write collision. The remaining eight groups retain a separate STATUS successor. This avoids either blocking safe reconciliation or racing active design work.

### D2. Add requirements rather than rewrite already-grounded contracts

Each existing capability receives `ADDED` requirements. The new `external-effect-adapters` capability receives its complete initial requirement set. Existing independently reviewed requirement blocks remain byte-for-byte untouched during delta sync.

### D3. Specify observable implementation quirks as current behavior

Incremental ASP validation accumulates scene facts in one solver control, but grounds the base rules before scene predicates are introduced. Rules whose atoms exist only in later scene programs therefore do not constrain those facts; this under-validation is an explicit current limitation. The installed `tinyassets` GUI command starts the launcher without a tunnel flag, while the legacy source `tinyassets.pyw` launcher explicitly opts into a tunnel. These distinctions are part of the as-built contract.

### D4. Give completion adapters one owner without stealing shared gate authority

`effects` remains a node attribute and adapters remain local completion-path glue. This capability owns invocation order, sink-specific gate use, structured evidence, quarantine, and run-snapshot exposure. `external-effect-receipts` continues to own soul-authority, exact consent, and optional caller-hint receipt semantics. The adapter capability does not create a graph primitive or claim the active `distributed-execution` change's exactly-once accepted-result route, nor future deterministic keys, reconciliation, caps, or batch guarantees.

### D5. Ground every requirement in owning source and focused tests

| Capability | Primary source evidence | Focused test evidence |
|---|---|---|
| community patch loop | `tinyassets/auto_ship_pr.py`, `tinyassets/api/status.py`, `fantasy_daemon/__main__.py` | `test_auto_ship_pr.py`, `test_auto_ship_health_status.py`, `test_bug_investigation_dispatcher.py` |
| constraint evaluation | `tinyassets/constraints/asp_engine.py` | `test_asp_solver.py` |
| desktop host runtime | `pyproject.toml`, `tinyassets/desktop/launcher.py`, `tinyassets.pyw` | focused entrypoint assertions in `test_desktop.py` |
| development coordination | `check_cross_provider_drift.py`, `claim_check.py`, `worktree_status.py`, `provider_context_feed.py`, `tinyassets/resolution/` | focused script tests, drift self-test, `test_resolution_contract.py`, `test_resolution_runtime.py` |
| domain plugin runtime | `tinyassets/domain_registry.py`, `tinyassets/producers/goal_pool.py`, `tinyassets/packets.py`, fantasy memory/commit modules | `test_goal_pool.py`, `test_domain_registry.py`, `test_packets.py` |
| external effect adapters | `tinyassets/effectors/`, `tinyassets/runs.py`, `tinyassets/api/runs.py` | the five effector suites plus `test_external_write_effector.py` |
| provider routing | `tinyassets/providers/call.py` | `test_provider_retry.py` |
| shared Goals | `tinyassets/api/market.py` | Goal surface/discoverability tests |
| wiki commons | `tinyassets/api/wiki.py` | `test_wiki_tools.py`, `test_api_wiki.py`, `test_wiki_cosign_flow.py` |

## Risks / Trade-offs

- **Requirement breadth can hide an overclaim.** → Independent reviewers must check each requirement against the named source and tests before sync.
- **A future active change may start touching one destination.** → Re-run collision and provider-context gates immediately before foldback.
- **Specification-only tests can go stale.** → Run focused behavior suites and strict validation; preserve explicit current limitations.

## Migration Plan

1. Draft and strict-validate all nine deltas.
2. Run focused behavior verification and independent source-grounded review.
3. Intelligently sync the reviewed deltas into canonical specs, prove prior requirement blocks are preserved and the sync is idempotent, then strict-validate the complete tree.
4. Archive the already-synced change without applying it a second time.
5. Land through a GitHub PR and remove the completed STATUS row.

Rollback is a normal source revert of the OpenSpec, focused-test, and coordination-script maintenance changes; no product-runtime or data migration exists.

## Open Questions

None. Future behavior belongs to separate active changes.

## Context

The full-coverage audit found 17 shipped behavior groups without material canonical ownership. Eight collide with active credential, distributed-execution, Brain, connector, universe, or release work. The nine in this change have disjoint canonical destinations and can be reconciled without choosing a future design.

## Goals / Non-Goals

**Goals:**

- Make nine current behavior groups strict-valid as-built requirements.
- State exact current edge behavior, including cumulative ASP grounding, dry-run/refusal paths, and compatibility mappings.
- Introduce one canonical owner for the already-shipped external-effect adapter layer.

**Non-Goals:**

- Change runtime code, tests, public tools, storage, or deployment behavior.
- Pull any of the eight dependency-bound backfills into this lane.
- Promise future effect-key determinism, batch caps, signed remote authority, or whole-batch atomicity.

## Decisions

### D1. Split the reverse-coverage backlog at active-change boundaries

This change owns only destinations with no current write collision. The remaining eight groups retain a separate STATUS successor. This avoids either blocking safe reconciliation or racing active design work.

### D2. Add requirements rather than rewrite already-grounded contracts

Each existing capability receives `ADDED` requirements. The new `external-effect-adapters` capability receives its complete initial requirement set. Existing independently reviewed requirement blocks remain byte-for-byte untouched during delta sync.

### D3. Specify observable implementation quirks as current behavior

Incremental ASP validation accumulates scene facts in one solver control, but grounds the base rules before scene predicates are introduced. Rules whose atoms exist only in later scene programs therefore do not constrain those facts; this under-validation is an explicit current limitation. The installed `tinyassets` GUI command starts the launcher without a tunnel flag, while the legacy source `tinyassets.pyw` launcher explicitly opts into a tunnel. These distinctions are part of the as-built contract.

### D4. Give effect adapters one owner without promoting packet conventions into a new primitive

`effects` remains a node attribute and adapters remain completion-path glue. The capability owns sink dispatch, authority/consent/idempotency gates, structured evidence, quarantine, and run-snapshot exposure. It does not create a new graph primitive or claim future distributed-effect guarantees.

### D5. Ground every requirement in owning source and focused tests

| Capability | Primary source evidence | Focused test evidence |
|---|---|---|
| community patch loop | `tinyassets/auto_ship_pr.py`, `tinyassets/api/status.py`, `fantasy_daemon/__main__.py` | `test_auto_ship_pr.py`, `test_auto_ship_health_status.py`, `test_bug_investigation_dispatcher.py` |
| constraint evaluation | `tinyassets/constraints/asp_engine.py` | `test_asp_solver.py` |
| desktop host runtime | `pyproject.toml`, `tinyassets/desktop/launcher.py`, `tinyassets.pyw` | focused entrypoint assertions in `test_desktop.py` |
| development coordination | `check_cross_provider_drift.py`, `claim_check.py`, `worktree_status.py`, `provider_context_feed.py` | their focused script tests and drift self-test |
| domain plugin runtime | `tinyassets/domain_registry.py`, `tinyassets/producers/goal_pool.py` | `test_goal_pool.py`, domain/memory registry tests |
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
3. Archive the change so deltas sync into canonical specs, then strict-validate the complete tree and confirm unrelated requirements are preserved.
4. Land through a GitHub PR and remove the completed STATUS row.

Rollback is a normal documentation revert; no runtime or data migration exists.

## Open Questions

None. Future behavior belongs to separate active changes.

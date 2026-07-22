<!--
Provenance: carried verbatim from `output/s2-gate/vacuous-test-sweep.md` (lane report,
2026-07-21 18:33). The lane produced this report but never opened a PR, so it
existed only on disk. Body below is the report unmodified; only this
comment was added.
-->

# Vacuous-test sweep

Date: 2026-07-22  
Audit performed: 2026-07-21 PDT  
Scope: `tests/` at `origin/main` `220a1fc8c69d3ae07b7673494e30d1267a220f69`  
Mode: read-only static mutation analysis

## Executive summary

Ten candidate groups survive mutation analysis. Three are especially load-bearing:

1. The sole-writer boundary test can miss real writes for three of its four parametrized actions.
2. The recommended-parent privacy test observes only the winning public branch, not whether private branches entered the selector.
3. The supposedly end-to-end child-branch tests all pass when no child run occurs, leaving child identity and attribution unproved.

One assertion is an unconditional tautology: `mock_reload.call_count >= 0`.

The sweep covered 473 test-tree paths, 472 Python files, 8,777 test functions, and 81 parametrized functions. Searches included guarded assertions, broad exception handlers, mock-only tests, tautologies, assertion-free tests, and duplicate parameters. Each finding below includes a production mutation that should be rejected and the test’s predicted response.

Severity ranks the false confidence supplied by the named test, not necessarily total suite exposure. Sibling tests that would catch the mutation are noted.

## Findings

### 1. P1 — Brain-write relay test does not observe three actions’ storage targets

Test:

- `tests/test_universe_write_boundary.py:311`
- `test_brain_write_action_is_relayed_not_dispatched`

The test parametrizes `set_premise`, `add_canon`, `add_canon_from_path`, and `soul.edit`. It asserts the returned `relay_to_universe` envelope, then checks only `identity.md`, and only if that file exists.

Exact production mutation:

In `tinyassets/universe_server.py:1099`, dispatch the old write handler before returning the existing relay envelope:

- `set_premise` modifies the soul/premise files;
- `add_canon` modifies canon;
- `add_canon_from_path` modifies canon sources;
- then return the unchanged `relay_to_universe` JSON.

Expected result: the sole-writer boundary is broken because the chatbot route has performed a brain write.

Would the test notice? **No for three of four parameters.** The response remains correct and the test never inspects the premise or canon targets. `soul.edit` would be noticed only because its supplied mutation targets `identity.md`.

This is a parametrized-collapse defect: four materially different effects are reduced to one response assertion and one action-specific filesystem check.

### 2. P1 — Recommended-parent privacy test checks only the winner

Test:

- `tests/test_quality_leaderboard_auth_boundary.py:313`
- `test_recommended_parent_for_fork_inherits_same_visibility`

The selector fixture preserves candidate order. The seed inserts public branches before private branches. Production chooses `entries[0]` as the recommendation at `tinyassets/api/quality_leaderboard.py:436`.

Exact production mutation:

At `tinyassets/api/quality_leaderboard.py:173`, change candidate collection to include all private rows, for example by passing `include_private=True` without viewer filtering.

Expected result: Eve’s selector receives Alice’s and Bob’s private branches, violating the privacy boundary even if a public branch still ranks first.

Would the test notice? **No.** It checks only that the selected first entry is not one of two private IDs. It does not assert:

- `result["ok"] is True`;
- a recommendation exists;
- `leaderboard_size` excludes private candidates;
- private IDs did not enter the selector;
- the rationale contains no private material.

Because the passthrough selector preserves order, the first public seed remains the recommendation while private candidates are present later.

Mitigation elsewhere: the direct `quality_leaderboard` tests in the same file inspect the full entry set and should catch the shared-filter mutation. This specific recommended-parent test is not proof of its stated boundary.

### 3. P1 — “End-to-end” child invocation tests pass with no child run

Tests:

- `tests/test_sub_branch_invocation_integration.py:107`
- `test_parent_completes_and_design_used_emits`
- `tests/test_sub_branch_invocation_integration.py:119`
- `test_child_actor_flows_into_child_run`
- `tests/test_sub_branch_invocation_integration.py:141`
- `test_design_used_row_created_when_child_completes`

Exact production mutation:

Change the `invoke_branch_spec` execution path to return a terminal `failed`, `blocked`, or approval-required parent result without spawning the child.

Expected result: the advertised compile → execute → child-spawn → attribution closure is broken. No child receives `actor="bob"` and no `design_used` event is emitted.

Would the tests notice? **No.**

- The first test requires only a truthy run ID and any truthy status, including `"failed"`.
- The actor assertion runs only if a child row exists.
- The attribution assertions iterate over rows; zero rows execute zero assertions.

All three tests therefore accept the exact absence of the behavior their module docstring says they prove. This is load-bearing for identity, attribution, and nested-run integrity.

### 4. P1 — Fund invariant can execute zero oracles

Test:

- `tests/test_paid_market_core.py:1203`
- `test_mint_redeem_cycle_cannot_extract_value`

Exact production mutation:

Make `mint_at_nav` raise `FundError` for every generated non-genesis state.

Expected result: minting is completely broken and the invariant is never exercised for a valid cycle.

Would the test notice? **No.** Every one of the 5,000 iterations enters:

```python
except FundError:
    continue
```

The test exits green without executing either value-conservation assertion once.

Mitigation elsewhere: deterministic happy-path mint tests would catch an unconditional failure. The randomized “cannot extract value” test itself has no positive control proving that it exercised at least one cycle.

### 5. P1 — Retention tests can skip retention entirely

Tests:

- `tests/test_checkpointing.py:330`
- `test_retention_deletes_old`
- `tests/test_checkpointing.py:346`
- `test_named_checkpoints_protected`

Exact production mutation:

Make `get_checkpoint_history()` return `[]` for an existing thread, or break checkpoint creation so the invoked graph records no history.

Expected result: checkpoint history/recovery is broken, and the retention policy is never exercised.

Would the tests notice? **No.**

- `test_retention_deletes_old` runs its complete oracle only when `len(history) > 1`.
- `test_named_checkpoints_protected` runs its complete oracle only when `history` is truthy.

Neither test asserts its precondition. The mutation makes both green without calling `policy.apply()`.

Mitigation elsewhere: `TestDirectCheckpointPruning` manually seeds storage and gives the policy stronger unit coverage. These two integration-style retention tests still overstate their evidence.

### 6. P2 — Universe-cycle test accepts a graph that never cycles

Test:

- `tests/test_graph_topology.py:461`
- `test_universe_runs_at_least_one_cycle`

Exact production mutation:

Route the universe graph through one setup/no-op node and terminate before `universe_cycle`, producing one stream event whose output contains neither `health.cycles_completed` nor `total_chapters`.

Expected result: the daemon graph has not run a universe cycle.

Would the test notice? **No.** `last_state is not None` passes. The fallback loops over the last event looking for `total_chapters`, but has no terminal failure when the field is absent.

The swallowed `GraphRecursionError` is intentional; the missing post-loop assertion is the defect.

### 7. P2 — Three retrieval integration tests pass when retrieval is removed

Tests:

- `tests/test_integration.py:96`
- `test_orient_calls_retrieval_router`
- `tests/test_integration.py:102`
- `test_orient_populates_retrieved_context_with_kg`
- `tests/test_integration.py:144`
- `test_orient_passes_provider_call_to_router`

Exact production mutation:

Make `_run_retrieval()` return `{}` without constructing or calling `RetrievalRouter`.

Expected result: orient no longer retrieves known KG content or invokes the router.

Would the tests notice? **No.**

- The first test asserts only that the empty result is a `dict`.
- The KG-population test asserts content only under `if ctx`.
- The wiring test asserts constructor arguments only under `if mock_router_cls.called`.

The same mutation disables all three oracles.

### 8. P2 — Empty-prose hard-failure integration test guards on the protection itself

Test:

- `tests/test_integration.py:505`
- `test_hard_failure_triggers_revert`

Exact production mutation:

Change `StructuralEvaluator.evaluate()` so empty prose reports `hard_failure=False`.

Expected result: empty output can pass through without the intended structural-revert protection.

Would the test notice? **No.** Its only verdict assertion is inside:

```python
if result["commit_result"]["hard_failure"]:
```

Removing the detector makes the guard false.

Mitigation elsewhere: direct hard-failure verdict tests use explicit `StructuralResult(hard_failure=True)` and protect the verdict function. They do not make this empty-prose end-to-end test non-vacuous.

### 9. P3 — Empty-name API test accepts every failure status

Test:

- `tests/test_api_edge_cases.py:58`
- `test_empty_name_string`

Exact production mutation:

Make `POST /v1/universes` return HTTP 500 or 422 for `{"name": ""}`.

Expected result: behavior contradicts the test’s stated expectation that the request succeeds with a generated universe ID.

Would the test notice? **No.** It asserts only inside `if resp.status_code == 201`. Every non-201 response passes.

### 10. P3 — Reload assertion is mathematically tautological

Test:

- `tests/test_desktop.py:1035`
- `test_reimport_modules`

Assertion:

```python
assert mock_reload.call_count >= 0
```

Exact production mutation:

Replace `TinyAssetsApp._reimport_modules()` at `tinyassets/desktop/launcher.py:671` with `return None`.

Expected result: code reload no longer reloads any module.

Would the test notice? **No.** A mock call count cannot be negative. This test cannot go red from any production behavior that returns normally.

## Near misses rejected

The following suspicious shapes are not included as findings:

- `test_migration_never_strands_sidecars_from_canonical_primary` has guarded assertions, and all current injected failures occur before the canonical primary arrives. However, the relevant mutation—moving the primary first—makes the guard reachable and the test red. It is a valid negative-invariant test.
- `test_path_traversal_blocked` contains an unreachable conditional check for HTTP 200, but its preceding unconditional `status_code in (400, 404)` already catches a successful leak.
- `test_backup_dry_run_no_mutating_commands` now has the positive shim-reachability control added in PR #1482; absence of its call log after that control is meaningful.
- Cleanup catches for temporary files and concurrency-worker catches that append to an asserted-empty error collection are not vacuous.
- Mock interaction tests were excluded when they still invoked a real wrapper and asserted its dispatch or side effects.

## Recommended repair order

1. Add per-action before/after filesystem proofs to the brain-write relay test.
2. Assert the complete visibility-bounded candidate surface for recommended-parent selection.
3. Require a completed child row, exact child actor, and exactly one attribution row in the sub-branch integration lane.
4. Add positive-control counters to randomized loops and guarded retention tests.
5. Replace guarded integration assertions with unconditional precondition plus outcome assertions.
6. Delete or repair the reload tautology.

Every repair should be mutation-proven: apply the exact mutation listed above, observe the named test go red, restore production, and observe it return green.

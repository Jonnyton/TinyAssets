## 1. Premise and Contract

- [x] 1.1 Re-check current `set_canonical`, canonical resolution, immutable runner, and gate-rejection seams against the April audit
- [x] 1.2 Author proposal, design, and delta specs for the full three-gap bundle
- [x] 1.3 Validate `per-user-goal-canonicals` strictly before implementation

## 2. Actor-Scoped Canonical Storage

- [x] 2.1 Write failing SQLite schema, backfill, composite-key, fallback, overwrite, unset, and isolation tests
- [x] 2.2 Add `goal_canonicals` SQLite DDL and idempotent legacy-default backfill
- [x] 2.3 Add validated personal set/get-resolution helpers and default dual-write
- [x] 2.4 Add PostgreSQL migration `011_goal_canonicals.sql` without renumbering around the parallel 010 lane

## 3. Runnable Personal Canonical Slice

- [x] 3.1 Write failing action authorization tests for own-scope success and cross-actor/default rejection
- [x] 3.2 Extend `goals action=set_canonical` with tighten-only `scope_actor` behavior
- [x] 3.3 Write a failing routed test proving personal canonical resolution reaches the immutable version runner
- [x] 3.4 Make `resolve_canonical_for_run` prefer the current actor binding and preserve default leaderboard behavior
- [x] 3.5 Verify the already-landed direct `branch_version_id` runner tests remain green

## 4. Goal-Aware Gate Route-Back

- [x] 4.1 Add typed `PatchNotes` and a `route_back` evaluation decision
- [x] 4.2 Implement actor-derived canonical resolution, route-history loop bounds, and structured failure classes
- [x] 4.3 Execute routed patch notes synchronously through the immutable version runner
- [x] 4.4 Add end-to-end gate rejection tests for personal/default routing and fail-loud loop/missing-canonical cases

> **Archive guard:** Do not archive this change, including with
> `openspec archive --yes`, while any of 4.1–4.4 is incomplete. Syncing before
> `route_back` lands would write target-only requirements into as-built specs.

## 5. Canonical MCP Surface Follow-Up

- [ ] 5.1 `canonical-surface-route`: expose actor-scoped `set_canonical` and `run_canonical` through the advertised `write_graph` and `run_graph` handles, update their user-facing contracts, and add live-connector acceptance coverage

## 6. Verification and Delivery

- [x] 6.1 Run all touched test files and focused regression suites
- [x] 6.2 Run Ruff on every touched Python file
- [x] 6.3 Rebuild the plugin runtime mirror and pass its import probe
- [x] 6.4 Review the diff for correctness, authorization, migration safety, and unnecessary complexity
- [x] 6.5 Write the uncommitted lane report, commit the implementation, and push `codex/osx-goal-canonicals`

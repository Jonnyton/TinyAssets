# Tasks: two-dimension-usage-limits

Two PRs. PR 1 builds seats, storage and tiers; PR 2 deletes the old meters and
rebases onto #4107 so its emit meter is deleted rather than merged around.

## 1. PR 1 — seats, storage, tiers

- [ ] 1.1 `tiers.py`: the one table (free 3 seats / 2 GiB, paid 8 / 50 GiB,
      reserve 1), unknown-tier resolves to free loudly, and `upgrade_link()`
      returning `None` on the top tier.
- [ ] 1.2 `universe_seats.py`: the lease + waiter tables under the canonical
      data dir with the symlink refusal, one `BEGIN IMMEDIATE` acquire
      (reap → re-entry → count → ceiling → ahead → hold/enqueue), refresh,
      release, and the interactive reserve.
- [ ] 1.3 Hold a seat at each agent-call site: `converse` chat turns, agent
      nodes (`graph_compiler`), automation runs and `event`/`once` wakes
      (`automations.py`), with the blocking-nested seat inherited on the
      existing `provider_invocation` carrier. Overlap policy resolves first.
- [ ] 1.4 `universe_storage.py`: measured + pending accounting excluding
      scratch, the write gate, and the loud unmeasured path. Retire the 16 GiB
      constant in `effectors/workspace.py` for the tier quota.
- [ ] 1.5 Visible waiting state with the inline link: `converse` reply,
      `read_graph`, automation projection, `api/resource_usage.py`,
      `billing/status`, and `/mcp/app?upgrade=1` wired to `startSubscribe()`
      in `app.html` (native shell exempt).
- [ ] 1.6 Tests: acquire/release on all four terminal paths, queue order,
      no-overtake, interactive reserve, stale reaping, re-entrant nesting,
      storage refusal + reads-still-work + evasion-by-small-writes,
      free-tier 4-agent village completing by queueing, chat fairness under a
      background ping-pong, link resolves to the real route. Mutation-check
      each gate.

## 2. PR 2 — delete every other meter

- [ ] 2.1 Rebase onto #4107; delete its `ea.admit_detail` block and
      `usage_limit` return in `api/app_events.py` so an emit only stores a
      wake.
- [ ] 2.2 Delete the meters and every refusal that reads them:
      `RUN_WRITE_LIMIT`, `RUN_TOTAL_LIMIT`, `RUN_DAY_LIMIT`,
      `DISPATCHES_PER_HOUR`, `BYTES_PER_HOUR`, `BUDGET_WINDOW_S`,
      `usage_notice`, `charge_dispatch`, `dispatch_window_usage`, the cap
      parameters on `admit`, and `run_usage_limited` / `run_rate_limited` /
      `usage_limited` / `usage_limit_reached` at each caller (`api/runs.py`,
      `api/automations.py`, `api/deliveries.py`, `automations.py`,
      `automation_context.py`, `effectors/*`, `engine_mcp_server.py`,
      `universe_server.py`, `api/resource_usage.py`). Keep settlement.
- [ ] 2.3 Replace the meter tests with seat/storage tests — rewrite
      `test_usage_limits.py`, `test_usage_dark_default.py`,
      `test_run_usage_budgets.py`, `test_effect_quota_enforcement.py` and the
      `test_app_event_runaway.py` cases per the #4107 hand-off. No `xfail`.

## 3. Prove and land

- [ ] 3.1 `ruff`, targeted pytest (basetemp outside the repo), the Linux
      oracle container for the concurrency tests, and a gpt-6-astra refute
      round via `peer-agents` (read-only, from the PR worktree) on seat leaks,
      starvation, cross-user seat theft and storage accounting evasion. Max 3
      rounds.
- [ ] 3.2 Update PLAN.md's usage-limit design section quoting the directive;
      deploy and `python scripts/deployed_sha.py --assert-contains <sha>`.
- [ ] 3.3 Sync deltas into `openspec/specs/`, archive this change, and archive
      `usage-limits-replace-caps` and `consolidate-platform-resource-policy`,
      which this supersedes.

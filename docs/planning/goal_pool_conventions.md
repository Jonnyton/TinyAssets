# Goal Pool Conventions

Public-facing reference for the cross-universe goal pool introduced in Phase F.
Covers directory layout, YAML shape, inputs constraint, repo-root resolution,
git push workflow, subscription management, and race semantics.

---

## Directory Layout

```
<repo_root>/
  goal_pool/
    maintenance/
      README.md          # Explains maintenance pool (ships with Phase F)
      <task-id>.yaml     # Each file = one BranchTask post
    research-paper/
      <task-id>.yaml
    fantasy-novel/
      <task-id>.yaml
```

`<repo_root>` is the git repo the TinyAssets daemon runs inside.
Each directory under `goal_pool/` is a **Goal slug** (kebab-case). Slugs should
match the `goal_id` in the Goals table where applicable.

---

## YAML Shape

Each post file is a YAML document:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `branch_task_id` | string | yes | Must match filename stem (without `.yaml`). |
| `branch_def_id` | string | yes | Branch slug to execute, e.g. `fantasy_author/universe-cycle`. Must resolve at subscriber. |
| `goal_id` | string | recommended | Should match containing directory slug. Directory wins on mismatch. |
| `inputs` | flat dict | yes (can be `{}`) | Primitive values only — see [Inputs Constraint](#inputs-constraint). |
| `priority_weight` | float | no | Default `0.0`. Only host actors may set > 0 (non-host clamped at post time). |
| `posted_by` | string | no | Attribution. Stamped by `post_to_goal_pool` from `UNIVERSE_SERVER_USER`. |

Example:

```yaml
branch_task_id: bt_1712876543210_abc123
branch_def_id: fantasy_author/universe-cycle
goal_id: maintenance
inputs:
  active_series: my-series
  chapter_target: 5
priority_weight: 0.0
posted_by: host
```

---

## Filename Rules

- Filename = `<branch_task_id>.yaml`.
- Stems must be unique within a goal directory.
- If `branch_task_id` in the YAML differs from the filename stem, the
  **filename wins** (mismatch logged as a warning).
- Use the `post_to_goal_pool` MCP action to generate IDs automatically.
- Manual names: use `<slug>-<date>-<random>` or UUID4 to avoid collisions.

---

## Inputs Constraint

`inputs` must be a **flat dict** of primitives:

- Allowed value types: `str`, `int`, `float`, `bool`, `null`.
- Nested dicts and nested lists are **rejected** at both post time and producer-read time.
- Keys starting with `_` (e.g. `_universe_path`, `_db_path`) are rejected.
- The key `work_target_ref` is rejected.

**Rationale (R4):** Cross-universe isolation. A flat-only invariant is trivially
correct; a recursive strip is error-prone and could smuggle path-references across
the isolation boundary. Pool task `inputs` carry execution-intent scalars, not
structured data.

If a Branch needs structured inputs, serialize them into a single string field
and parse inside the Branch.

---

## Repo-Root Resolution

The pool directory lives at `<repo_root>/goal_pool/`. Resolution order:

1. **`TINYASSETS_REPO_ROOT` env var** — explicit override. Takes precedence.
2. **Git-detect upward** — walk parent directories from `<universe_path>` until
   `.git/` is found. Matches the "local-first, git-native" PLAN.md model.
3. **RuntimeError** — if neither resolves. Pool producer returns `[]` and logs
   at INFO; `post_to_goal_pool` MCP action returns:
   ```json
   {
     "status": "rejected",
     "error": "repo_root_not_resolvable",
     "hint": "Set TINYASSETS_REPO_ROOT or run the daemon from inside a git checkout."
   }
   ```

**Pytest fixtures:** pin `TINYASSETS_REPO_ROOT` to a `tmp_path`. No fake `.git`
scaffold required. See `tests/test_phase_f_goal_pool.py` for examples.

---

## Posting via MCP

```
tool: universe
action: post_to_goal_pool
goal_id: maintenance
branch_def_id: fantasy_author/universe-cycle
inputs_json: '{"active_series": "my-series", "chapter_target": 5}'
priority_weight: 0.0   # optional; non-host posters have this clamped to 0
```

Response:

```json
{
  "status": "posted",
  "goal_id": "maintenance",
  "branch_def_id": "fantasy_author/universe-cycle",
  "path": "/path/to/goal_pool/maintenance/<task-id>.yaml",
  "priority_weight": 0.0,
  "next_step": "To make this post visible to cross-host subscribers, run: git add goal_pool/maintenance/<task-id>.yaml && git commit && git push"
}
```

---

## Git Push Workflow

`post_to_goal_pool` writes the YAML locally. To make it visible to subscribers
on other hosts:

```bash
git add goal_pool/<goal>/<task-id>.yaml
git commit -m "<goal>: describe the task"
git push
```

Subscribers on other hosts run `git fetch` or `git pull` to pick up new pool
posts. The GoalPoolProducer reads local files only — no remote fetch. Hosts
manage their own pull cadence.

---

## Subscription Management

Daemons subscribe via the `universe` tool:

```
action: subscribe_goal    goal_id: maintenance
action: unsubscribe_goal  goal_id: maintenance
action: list_subscriptions
```

`list_subscriptions` returns:
- `goals` — current subscription list (sorted, deduped).
- `pool_status_per_goal` — count of pending YAMLs per subscribed goal.
- `config_vs_subscriptions_drift` — one of:
  - `"ok"` — configuration and subscriptions consistent.
  - `"pool_enabled_no_subs"` — `accept_goal_pool=true` in dispatcher config but
    zero subscriptions. Add subscriptions or disable the flag.
  - `"subs_but_pool_disabled"` — subscriptions exist but `accept_goal_pool=false`.
    Daemon won't receive pool tasks. Set `accept_goal_pool: true` to activate.

---

## Dispatcher Config

Enable pool acceptance in `<universe>/dispatcher_config.yaml`:

```yaml
accept_goal_pool: true
max_pool_tasks_per_cycle: 5      # cap pool tasks emitted per cycle (default 5)
goal_affinity_coefficient: 1.0  # bumps goal_pool tier scoring
```

Also set the environment flag: `TINYASSETS_GOAL_POOL=on`.

### Flag lifecycle — restart required

`TINYASSETS_GOAL_POOL` is a **registration-gate** flag: it is read once at module
import time by the `register_if_enabled()` side-effect at the bottom of
`tinyassets/producers/goal_pool.py`. Flipping the env var on a live Universe
Server has no effect until the process restarts — the producer was either
registered at startup or it wasn't.

Operators: after changing `TINYASSETS_GOAL_POOL`, restart the TinyAssets daemon
(tray → "Restart All" or equivalent). Verify via the MCP `list_subscriptions`
response — `config_vs_subscriptions_drift` will read `"ok"` or
`"pool_enabled_no_subs"` when the producer registered; pool MCP actions return
`{"status": "not_available"}` when it did not.

The two behavior-gate flags in the Phase F matrix
(`TINYASSETS_UNIFIED_EXECUTION`, `TINYASSETS_DISPATCHER_ENABLED`) are read on every
cycle and take effect without restart. Only `TINYASSETS_GOAL_POOL` is
restart-gated in this phase. See `docs/exec-plans/daemon_task_economy_rollout.md`
"Cross-phase notes → Flag lifecycle" for the full registration-gate vs
behavior-gate breakdown across all workflow flags.

### Troubleshooting `repo_root_not_resolvable`

If `post_to_goal_pool` returns `repo_root_not_resolvable`, or the producer logs
`repo_root_not_resolvable` at INFO and emits no tasks, the git-parent walk from
`<universe_path>` did not find a `.git/` directory — this happens when the
universe lives outside the repo checkout, or the `.git/` directory is elsewhere
(e.g. worktrees, submodules, or a detached layout). The walk may also settle on
the wrong `.git` if your universe is nested under an unrelated repo.

Fix: set `TINYASSETS_REPO_ROOT` in the TinyAssets daemon environment to the
absolute path of the repo that owns `goal_pool/`. This takes precedence over
the walk. `TINYASSETS_REPO_ROOT` is read on every resolution call, so it takes
effect on the next producer cycle without restart.

---

## Fresh-Install Default

Daemons subscribe to `maintenance` by default on first boot (when
`subscriptions.json` doesn't exist). This turns idle capacity into useful
background work automatically.

To opt out:

```
action: unsubscribe_goal
goal_id: maintenance
```

---

## Race Semantics (v1)

Multiple subscribers may pick the same pool YAML simultaneously. Phase F
accepts double-execution as an acceptable risk for low-volume pools (R13).
Pool tasks **should be idempotent**.

Phase G will introduce advisory claim semantics for pools where double-execution
is unacceptable.

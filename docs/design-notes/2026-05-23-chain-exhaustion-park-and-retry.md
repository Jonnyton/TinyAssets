---
status: proposed
date: 2026-05-23
author: claude-code (claude-opus-4-7)
relationship: Runtime-side counterpart to the already-merged CI architectural commitment (PR #728 / #733 / #752). Completes the "provider availability as first-class concept" across both halves.
---

# Chain-Exhaustion Park-and-Retry

**TL;DR.** The runtime currently fails a run hard when `AllProvidersExhausted` is raised by the provider router (`workflow/providers/router.py:433`). Under the host's committed steady-state — **two active codex-invoking containers (`daemon` + `worker`) sharing one codex subscription via `codex-flock-wrapper.sh`** — codex rate-limit contention reliably triggers this exhaustion, and the fallback chain on the droplet is structurally narrow (no API-key providers per project policy, `claude-code` not_in_registry on cloud image, `ollama-local` likely-not-running). The fix generalizes the existing `policy_parked_pending` parking pattern to cover chain exhaustion: **runs park (status=`chain_parked`) carrying `cooldown_remaining_s` metadata, dispatcher retries when chain capacity returns, hard-fail only after a bounded retry budget exhausts.** This makes the host's "two codex daemons sharing one subscription" topology a stable steady state instead of a recurring failure mode.

## §1. Why this is the right shape now

The host has committed to a specific daemon topology:

- **Exactly two host-run daemons**, both codex-backed (the existing `daemon` + `worker` containers in `deploy/compose.yml`).
- **Single codex subscription** shared between them via `/var/lib/workflow-codex:/app/.codex` bind mount + `flock` serialization on `/app/.codex/.lock`.
- **No API-key providers** (`WORKFLOW_ALLOW_API_KEY_PROVIDERS=0`). No second account. No local model fallback. All other daemons get hosted by other users on their own backends.

Per `project_daemon_default_behavior` (2026-05-01 host correction): "Host fleets size to provider capacity, NOT product caps. Many-daemon hosts are normal target scale, including multiple daemons same-provider. Warning-only rate-limit estimates."

In this topology, **codex rate-limit hits are a routine steady-state event, not a pathological condition**. The fallback chain `["claude-code", "codex", "gemini-free", "groq-free", "grok-free", "ollama-local"]` after policy filtering reduces to effectively `[codex, ollama-local]` on the cloud image, with `ollama-local` immediately cooldown on connection-refused. When codex cools down, the chain has no place to fall through to. The current behavior — `CompilerError: Provider call failed... All providers exhausted` propagated up as run failure — is wrong for this steady state.

Per `feedback_structural_over_chores`: this should be a one-time architectural fix, not a recurring operator chore (SSH droplet, verify auth, restart codex).

Per `feedback_no_shims_ever`: substrate-level treatment, no workaround.

## §2. Evidence

Live probe on `https://tinyassets.io/mcp` (2026-05-22 18:30Z, persona session 6 prep):

```
$ extensions action=list_runs branch_def_id=fd5c66b1d87d limit=5
5 runs · 100% failed-or-interrupted

$ extensions action=get_run run_id=bda3ef59ecdf43f7
status: failed
error: "CompilerError: Provider call failed in node 'child_invocation_receipt_gate':
        All providers exhausted for role=writer. Daemon should retry with backoff.
        [chain_state]: {
          \"role\":\"writer\",
          \"chain\":[\"codex\",\"ollama-local\"],
          \"attempts\":[
            {\"provider\":\"claude-code\",\"status\":\"skipped\",\"skip_class\":\"not_in_registry\",...},
            {\"provider\":\"codex\",\"status\":\"skipped\",\"skip_class\":\"quota_or_cooldown\",\"cooldown_remaining_s\":115},
            {\"provider\":\"ollama-local\",\"status\":\"skipped\",\"skip_class\":\"quota_or_cooldown\",\"cooldown_remaining_s\":115}
          ],
          \"api_key_providers_enabled\":false
        }"
failure_class: "quota_exhausted"
suggested_action: "Provider quota or rate limit hit; wait before retrying OR switch providers via the llm_type param."
actionable_by: "chatbot"
```

`fd5c66b1d87d` is the live canonical handler that the post-PR-127 cutover routes `wiki action=file_bug` investigations to. 100% failure rate over 2+ days, all the same root cause. The cooldown is short (120s — `COOLDOWN_UNAVAILABLE` in `workflow/providers/quota.py:20`); if the run could simply pause and retry, most of these would complete.

Sibling evidence on the CI side (the rationale for the `wf-codex-auth-expired-loop-health`, `wf-checker-worker-dispatch`, `wf-independent-checker-routing` worktrees) confirms the same pattern in a different surface: codex unavailability cascading into silent loop-health degradation, hidden behind `auto-fix-reviewed` labels. The runtime side has the additional severity that there's no human in the loop to notice.

## §3. The primitive — `chain_parked` task status

The dispatcher already supports a parking pattern: `policy_parked_pending` for tasks whose `trigger_source` tier is disabled (`workflow/api/status.py:341-360`). The proposal **generalizes this surface**:

| Existing | This proposal |
|---|---|
| `policy_parked_pending` — task tier is disabled | `chain_parked_pending` — task's chain currently has no available provider |
| Logged in `get_status.queue_state.policy_parked_pending` + `_max_age_s` | Logged in same place, separate counter `chain_parked_pending` |
| Cleared when operator enables the tier | Cleared automatically when chain has capacity (next dispatcher tick after cooldown) |

### Lifecycle

```
[task created] → status=pending → dispatcher picks up
                              ↓
                  [run starts, hits node needing writer]
                              ↓
                  [router.call raises AllProvidersExhausted]
                              ↓
                  [orchestrator catches; if cooldown_remaining_s on every
                   attempted provider is bounded (i.e. it's a quota/cooldown
                   condition, NOT a permanent registration failure), park]
                              ↓
                  status=chain_parked
                  chain_parked_at = now
                  chain_parked_retry_after = now + max(cooldown_remaining_s) + jitter
                  chain_parked_retry_count = 0..N
                              ↓
                  [dispatcher tick checks parked tasks ready to retry]
                              ↓
                  status=pending → re-enter run pipeline
                              ↓
                  [either: completes successfully, parks again, or
                   exceeds retry budget → status=failed]
```

### Retry budget

Bounded retries prevent infinite parking:

- Default: 5 retries with exponential backoff (1×, 2×, 4×, 8×, 16× the cooldown_remaining_s).
- Per `policy_parked_pending_max_age_s` evidence (21 days observed in production), the parking surface itself doesn't enforce a max-age. This proposal keeps that conservative for steady-state codex contention but **caps total wait at `WORKFLOW_CHAIN_PARK_MAX_AGE_S`** (default 30 min). After cap, run fails with a structured `chain_park_exhausted` error_kind naming the retry history.

### What does NOT trigger parking

Per `project_provider_chain_correctness_invariant`, structural chain misconfiguration is a different problem and should fail loudly, not park:

- All providers have `skip_class=not_in_registry` (chain is empty after registration filtering) → fail hard.
- All providers have `skip_class=provider_error` non-recoverable (e.g. permanent auth failure) → fail hard.
- API-key-only chain when `WORKFLOW_ALLOW_API_KEY_PROVIDERS=0` → fail hard (already the case).
- `WORKFLOW_PIN_WRITER` pinned writer exhausts → fail hard (already the case).

Only `skip_class=quota_or_cooldown` with a `cooldown_remaining_s` present triggers parking. Cooldown ranges (120s for UNAVAILABLE, 120s for TIMEOUT, 30s for OTHER per `workflow/providers/quota.py:20-22`) are well-bounded; the parking time is predictable.

## §4. Where the change lives

The substrate has **two parallel execution paths** that both must learn to park-and-retry; only covering one leaves the other silently broken.

### §4.1 Run-level path (synchronous `run_branch` MCP entry)

1. **`workflow/runs.py`** — `start_run` (around line 2090, the existing `RUN_STATUS_FAILED` path on `CompilerError`). When the underlying exception carries `chain_state` indicating all attempts were `quota_or_cooldown`, divert to `RUN_STATUS_CHAIN_PARKED` (new) with retry metadata instead of `RUN_STATUS_FAILED`. Resume-run path mirrors. The new status enum value lives alongside the existing `RUN_STATUS_*` constants.

2. **`workflow/api/status.py`** — surface `chain_parked_pending` + `chain_parked_pending_max_age_s` in `queue_state` alongside `policy_parked_pending`. Same shape; existing get_status consumers see new counters.

3. **Dispatcher/scheduler tick** — periodic tick checks parked runs whose `chain_parked_retry_after` is in the past; flip back to `pending` for re-pickup. Use same lock discipline as `claim_task`.

### §4.2 BranchTask path (queued execution via `fantasy_daemon`)

**Critical: the BranchTask lifecycle is separate from the run lifecycle.** Direct BranchTask execution finalizes via `fantasy_daemon/__main__.py::_finalize_claimed_task`, which translates run outcome into the queue row's terminal status. The queue row schema in `workflow/branch_tasks.py` today accepts only `pending / running / succeeded / failed / cancelled` — if the implementation only adds `RUN_STATUS_CHAIN_PARKED` and stops there, the parented run will be marked parked but the queue row will still flip to `failed`, and `select_next_task` (the dispatcher's pickup function) will not re-claim it. The retry never fires.

The implementation must therefore also:

1. **`workflow/branch_tasks.py`** — extend the accepted status enum to include `chain_parked` (or equivalent), and update `select_next_task` to pick up rows whose status is `chain_parked` AND `chain_parked_retry_after <= now()`. Migration path: existing rows with terminal `failed` are NOT retroactively reanimated; the new status is forward-only.

2. **`fantasy_daemon/__main__.py::_finalize_claimed_task`** — when the run finalizes with `RUN_STATUS_CHAIN_PARKED`, set the queue row's status to `chain_parked` + carry over the `retry_after` + retry count. Do NOT flip to `failed`. Existing chain-of-finalization logic stays unchanged for other run statuses.

3. **`workflow/branch_tasks.py` queue retry policy** — a parked queue row whose `retry_count >= max_retries` OR `total_park_age_s >= WORKFLOW_CHAIN_PARK_MAX_AGE_S` transitions to terminal `failed` with `failure_class=chain_park_exhausted`. Same budget envelope as §3 retry policy applied to the queue row, not just the run.

### §4.3 Why this is symmetric

Both paths share the same root signal (`AllProvidersExhausted` from `workflow/providers/router.py:433`) but propagate through different state machines. The implementation factors the park/retry decision into a helper (`is_chain_park_eligible(exc) -> ParkDecision | None` in `workflow/graph_compiler.py` or a new `workflow/parking.py` module) that both paths call. Tests cover both paths independently AND end-to-end (queue row → run → park → retry → completion).

### §4.4 Adjacent touches

- **`workflow/providers/router.py`** — the `AllProvidersExhaustedError` already carries `chain_state` + `attempts` (FEAT-006). The router doesn't need changes; the orchestrator interprets the existing diagnostic.
- **`workflow/graph_compiler.py`** — `_wrap_provider_failure` already attaches `chain_state` to the wrapped `CompilerError`. Add a helper `is_chain_park_eligible(exc)` so the orchestrator can branch on the right shape.
- **MCP surface** — `extensions action=get_run` should report `chain_parked` cleanly (`failure_class` not set; new `parking` block with retry metadata). `extensions action=list_runs` should include parked rows by default (currently filters by status).
- **Plugin mirror** — `packaging/claude-plugin/.../runtime/workflow/...` mirrored, per pre-commit parity guard.

## §5. Tests

Focused regression suite (target: 8–12 new tests):

- `test_chain_park_diverts_quota_exhaustion`: simulate writer call → all-cooldown → assert run lands in `chain_parked`, not `failed`.
- `test_chain_park_retries_when_cooldown_clears`: simulate park → advance clock past cooldown → dispatcher tick → run completes.
- `test_chain_park_exhausts_retry_budget`: simulate park → cooldown never clears → after N retries / max-age, run lands in `failed` with `chain_park_exhausted` error_kind.
- `test_chain_park_does_not_swallow_structural_failures`: chain filters to empty (all `not_in_registry`) → still fails hard.
- `test_chain_park_does_not_swallow_pinned_writer_exhaustion`: `WORKFLOW_PIN_WRITER` exhausts → still fails hard.
- `test_chain_park_status_surface`: `get_status.queue_state.chain_parked_pending` + `_max_age_s` populated correctly.
- `test_chain_park_visible_in_get_run`: parked run inspect surfaces structured parking block.
- `test_chain_park_concurrent_safe`: two dispatcher ticks racing on same parked task → file-lock-discipline mirrors `claim_task`.

End-to-end (manual, post-merge):

- File a smoke-test bug via chatgpt.com on the live droplet → observe the canonical handler run land in `chain_parked` when codex is in cooldown → wait 2-3 cooldown windows → observe the run complete + real PR fire.

## §6. Risk + rollback

**Risk: parking masks a real auth failure.** If codex auth is actually broken (not just rate-limited), the cooldown never clears, the run parks forever (until budget exhausts). Mitigation: (a) the budget exhaust DOES fail hard with `chain_park_exhausted`; (b) `policy_parked_pending_max_age_s` and the new `chain_parked_pending_max_age_s` are visible in `get_status`, so a sustained high max-age becomes the observable signal for operator attention; (c) the existing FEAT-006 chain_state diagnostic is preserved in the parking metadata for forensics.

**Risk: parking-and-retrying multiplies side effects.** If a parked run already wrote to external state before exhausting at a later node, re-running might double-fire effects. Mitigation: the runtime's effector dispatch fires only on RUN completion (`workflow/runs.py:2125`), not per-node; parking BEFORE that point means no effects have fired. Per-node effects don't exist today. For the future case where they do, idempotency_key carries through.

**Risk: queue depth grows.** Many parked tasks during a sustained cooldown = visible queue growth. Mitigation: `get_status` surface makes this observable; max-age cap prevents indefinite growth.

**Rollback:** revert the commit. The new `chain_parked` status becomes unreachable; existing parked tasks roll to `failed` on next dispatcher tick. No data loss; no schema migration required (status enum just gains an unused value).

## §7. Relationship to the CI-side lineage

**Correction from the original draft.** Three sibling worktrees that surfaced via the provider-context-feed touch the same root concern (provider/worker availability as a first-class concept) in the CI loop, but those PRs are **already merged** — they aren't pending work to consolidate or retire:

- `codex/codex-auth-expired-loop-health` → **PR #752** (merged) — stale Codex auth classified in auto-fix loop.
- `codex/checker-worker-dispatch` → **PR #733** (merged) — automatic independent-checker dispatch.
- `codex/independent-checker-routing` → **PR #728** (merged) — independent-checker blockers surfaced in loop watch.

Each shipped as CI-specific work and stayed CI-scoped. They reuse the FEAT-006 chain-state diagnostic (PR #189, merged) — the same diagnostic this design's runtime path will read from. So the architectural commitment ("provider availability is a first-class concept the system gracefully tolerates, surfaces, and recovers from") is already half-shipped, on the CI side. **This design completes it on the runtime side.** It is not the consolidator of pending work; it is the runtime counterpart to the already-shipped CI work.

### What's actually pending

The local `_PURPOSE.md` files for those three worktrees still exist on the host filesystem and keep surfacing via the provider-context-feed scan, even though the PRs are merged. PR #934 (merged) added a "prune _PURPOSE.md candidates from already-merged worktrees" hook but the three worktrees above weren't caught — likely because their `_PURPOSE.md` doesn't carry the PR-merged signal in a shape the hook recognized. **Out-of-band cleanup item, not blocking this design**:

- Remove `/c/Users/Jonathan/Projects/wf-codex-auth-expired-loop-health/` (PR #752 merged).
- Remove `/c/Users/Jonathan/Projects/wf-checker-worker-dispatch/` (PR #733 merged).
- Remove `/c/Users/Jonathan/Projects/wf-independent-checker-routing/` (PR #728 merged).
- Optionally strengthen PR #934's prune hook to catch this case.

Unrelated worktrees (`wf-pr576-rebase`, `wf-pr578-rebase`, `wf-pr587-repair`, `wf-pr602-rebase`, `wf-pr617-five-handle-cleanup`, `wf-pr828-skill-sync-refactor`, `wf-pr354-cowork-env`) touch different concerns and are out of scope for this design. Some may also be stale post-merge; should be audited separately by their owning sessions.

## §8. Sequencing

| Step | What | Who | Estimated |
|---|---|---|---|
| 1 | Merge this design note | host approve | ~1 turn |
| 2 | Implement substrate change in `claude/chain-exhaustion-park-and-retry` | claude-code | ~1 day |
| 3 | Cross-family review (writer:claude, checker:codex) | codex | ~3 review rounds historically |
| 4 | Merge implementation PR | host merge key | — |
| 5 | Deploy lands on droplet | deploy-prod CI | ~5 min |
| 6 | Resume the paused M6 cutover smoke test | persona via chatgpt.com | ~30 min |
| 7 | Out-of-band cleanup: remove the three stale `_PURPOSE.md` files for the already-merged CI sibling worktrees per §7 | filesystem cleanup | ~1 min |

After step 6, the user-buildable Loop 2 fires end-to-end with real PR emission on Jonnyton/Workflow. The cheat loop retires for real. The architectural commitment "provider availability is a first-class concept" lands fully across both CI (already shipped via #728/#733/#752) and runtime (this design's implementation).

## §9. References

- **Live evidence:** persona sessions.md `2026-05-22 ~17:01Z LIVE SESSION 6` (`.claude/agent-memory/user/personas/first-user-dev/sessions.md`).
- **Existing parking pattern:** `workflow/api/status.py:341-360` (`policy_parked_pending` for tier-policy gating).
- **Chain state diagnostic (FEAT-006):** `workflow/providers/router.py:425-438`, `workflow/graph_compiler.py:288-318` (`_wrap_provider_failure`).
- **Codex auth persistence:** `deploy/compose.yml:60-80`, `deploy/codex-flock-wrapper.sh`, PR #965.
- **Daemon topology commitment:** memory `project_daemon_default_behavior` (2026-05-01), `project_capacity_grant_control_intent_executor_backend` (host directive).
- **CI siblings (already-shipped CI counterpart; this design completes the architectural commitment runtime-side):** PR #728 (independent-checker-routing, merged), PR #733 (checker-worker-dispatch, merged), PR #752 (codex-auth-expired-loop-health, merged). Local `_PURPOSE.md` files for those branches still exist as stale worktree metadata.
- **Smoke test (paused, will resume post-merge):** `docs/ops/m6-cutover-operational-config.md` Step D.

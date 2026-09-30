# Remove every limit that is not storage or a seat

## Why

Founder directive, 2026-09-30: **an account has exactly two limits** — the cloud
storage bytes a universe occupies, and how many agent runs it may have going at
once. Over the seat count, work **waits**; it is never refused. Free and paid
differ only in those two numbers, and everything works on free.

An inventory at `origin/main` 8a7c8c00 found ~25 other numbers acting as account
limits, structural caps, or refusals: a free user could own one universe, chat
history older than 400 turns was **deleted**, an agent lineage stopped at 50
generations, a turn was killed at 3600s, and a busy host said no rather than
waiting. None of those is storage and none is a seat, so none of them is a limit
this platform has.

Sibling lane `two-dimension-usage-limits` (branch `claude/limits-two-dims`,
PR #4117) owns the seat ledger, tier storage, and the engine/effect/workspace run
meters. This change owns everything else, and does not touch those files.

## What Changes

**Account-shaped limits go; storage is the bound.**

- Any user may create any number of universes. `_universe_birth_refusal` keeps
  only the identity floor (a universe belongs to an authenticated person);
  `additional_universe_requires_subscription` is deleted.
- Chat history is never deleted. `RETENTION_TURNS` and its delete are removed:
  history counts toward storage. Context trimming stays on what is **sent** to a
  model, never on what is stored.
- Project memory's 1 MB cap, the daemon wiki's byte caps and its eviction, and
  the 4 MiB app-UI-library subquota all go. Bytes count toward tier storage,
  enforced once, by the seat lane's storage gate.
- `MAX_PENDING = 50`, `MAX_LINEAGE_DEPTH = 50` (with its CHECK constraint), the
  366-day one-shot scheduling horizon, and the 100-agent-binding consumer
  selection cutoff go. `MAX_SKILLS = 64` stops silently dropping skills.
- The receiver per-sender rate limit stops being a platform default. An owner
  MAY set one on their own receiver as their own policy; the default is none and
  there is no ceiling.

**Run and per-node counters go; the seat is the bound.**

- Per-run `RUN_DISPATCHES_MAX`/`RUN_RPC_CALLS_MAX`/`RUN_BYTES_MAX` and per-node
  `MAX_RPC_CALLS`/`MAX_WORKSPACE_COMMANDS` are removed. Per-single-call payload
  bounds stay.
- The recursion ceiling has no fixed value and no validated range: an author may
  ask for any positive number, and the default is effectively unbounded. The
  run's seat is the bound.
- `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` no longer overrides the author's
  `retry_budget`.
- The serving binding's 10,000-invocations-per-hour runaway window is removed,
  along with its in-flight token and cost ceilings — they are accounting fields
  the protocol never needed, and the seat supersedes them.
- Authoring's 512 KiB definition bound rises to the served payload limit
  (8 MiB); `MAX_OPERATIONS_PER_BATCH` is redundant under it and goes.

**Wall clocks that acted as turn caps go.**

- The 3600s served-turn cap and the 3-hour automation run cap are removed: a turn
  runs until it is finished. Liveness and run-owner proof catch a dead run.
  Per-single-call transport timeouts (bash 600s, workspace command 1800s,
  provider default 600s) stay and are each checked not to bound a turn.

**Host safety waits instead of refusing.**

- `provider_admission` waits for a slot instead of raising `ProviderBusy` after
  20s, and a blocked caller has a visible waiting state.
- Universe tool jails keep the host-wide slot count and drop the per-universe
  count of 2; a busy host waits.
- Inbound webhooks keep the 600/min **per-token** anti-flood on the
  unauthenticated public ingress — that one is aimed at a stranger, not the
  account holder. The per-universe 6000/min aggregate and the 20-in-flight 503
  go; an inbound-triggered run queues for a seat.
- Voice's per-user session and status-check rate windows go.
- Nested blocking invokes and the per-universe workspace job lock wait rather
  than fail.

**Dark code with no live caller is deleted** rather than migrated:
`_HTTP_ACTION_CAP`, the market `_MAX_FANOUT`, and the background served-provider
per-attempt budgets (the last only if the prune lane has not already claimed it).

**User-facing text stops describing limits that no longer exist.** The plan
table, onboarding, legal page, served handbook chapters, connector docs, and
`get_status`'s `resource_usage` describe exactly two dimensions: stored bytes and
simultaneous agent seats. There is no daily allowance, no compute guard, no rate
limit and no account-age gate (the last never existed).

**No compatibility shims.** The founder is the only user; a removed constant is
removed, not defaulted to infinity behind its old name, except where a name must
survive as a *payload* bound.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: universe creation carries no subscription gate;
  `get_status` publishes storage and seats only; the served handbook describes
  those two dimensions.
- `graph-execution-substrate`: no recursion ceiling, no per-run dispatch/RPC/byte
  budgets, no served-turn wall clock; author retry policy is honoured.
- `conversation-custody`: conversation turns are never deleted by retention.
- `user-owned-automations`: no run-duration ceiling and no scheduling horizon.
- `scratch-storage`: workspace and memory bytes are charged to tier storage, not
  to their own separate caps.
- `governed-agent-consumers`: consumer selection reads any number of bindings.

## Impact

Owner: Claude. Branch: `claude/limits-cleanup`. Three PRs, grouped by area:
account-shaped limits, run/host bounds, then text and specs.

Coordination (no shared file edits):

- `two-dimension-usage-limits` owns `usage_policy.py`, `universe_seats.py` and
  `openspec/specs/engine-run-admissions/`. Two notes for that lane: the seat
  ledger's 20s "TOLD so and retry" converse behaviour reads as a refusal and
  should wait; and once-wake attempts burned by rate refusals
  (`automations.py:_retire_once`) are that lane's to fix as the meters go.
- `owner-notify`: its cost bound no longer includes `MAX_PENDING`. Seats only.
- The prune lane owns `user_owned_cloud_automation.py` and
  `background_served_provider.py` dark-code deletion; this change skips whatever
  that lane is already deleting.

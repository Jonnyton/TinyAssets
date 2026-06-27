# Dashboard Conventions

Phase H scaffold for the host-facing dashboard. Panes are pluggable; MCP inspect surfaces are the canonical source of truth.

## Layout

One tray, many dashboards. The tray icon runs in the system notification area; "Show Dashboard" opens a per-universe window. Multiple live universes → multiple dashboards.

Panes per window (Phase H):

- **DispatcherPane** — tier status + toggle controls.
- **QueuePane** — top-N pending BranchTasks, tier-color-coded.
- **EarningsPane** — settlements count, open bids, recent completion rate. Hidden when `TINYASSETS_PAID_MARKET=off`.
- **SettlementsPane** — settlements ledger table (optional; merges into EarningsPane in the compact layout).

All panes consume the same `daemon_overview` MCP response via a refresh timer (default 2s cadence).

## Refresh cadence

- Dashboard polls `universe action=daemon_overview` every 2 seconds.
- `daemon_overview` caches internally with 1s TTL (preflight §4.3 invariant 1) — doubling up with the 2s UI poll gives a predictable max ~3s latency from "change on disk" to "visible in UI."
- Explicit refresh trigger: toggling a tier via `set_tier_config` busts the cache for that universe immediately so the next poll reflects the change.

## Tier toggle semantics

- Toggle flips `<universe>/dispatcher_config.yaml`.
- Takes effect at the next dispatcher cycle boundary (preflight §4.3 invariant 3).
- In-flight tasks complete normally — no mid-cycle abort.
- "Pause All Tiers" is an emergency stop that flips all four tier flags to `false`; each sub-flip is an independent `set_tier_config` call. Partial failure is rolled back best-effort (preflight §4.3 invariant 9).

## Pane exception isolation

Each pane's event handler is wrapped in `try / except`. A raise in one pane logs + returns without propagating; the UI thread survives; other panes survive (preflight §4.3 invariant 2). Dashboard-thread crashes surface as "Dashboard not responding" tray badge; the daemon keeps writing `status.json` + `activity.log` so MCP surfaces remain live.

## Shared-state policy

The dashboard **never mutates universe state directly**. Every write action goes through an MCP action (`set_tier_config`, `submit_request`, etc.). Read-through: the dashboard reads `daemon_overview`; MCP is the single source of truth.

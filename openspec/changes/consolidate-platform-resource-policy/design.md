## Context

PLAN.md was read completely. Its minimal-primitives, user-buildable-middle,
universe-authority and self-auditing-tool principles apply. No PLAN edit.
The production diagnosis and exact values are in
`docs/concerns/2026-09-08-workspace-hourly-cap-stalls-light-use.md`.

Independent Claude shape review returned ADAPT: a new ledger, import migration,
epochs and acquisition protocol are unnecessary for removing a duplicate hourly
counter. The first draft was over-scoped and is replaced by this bounded fix.

## Goals / Non-Goals

Goals: remove the independent ten-workspace-start cliff, preserve real resource
and authority checks, and expose honest owner-scoped usage through existing
status. Make progress without requiring a private workflow change.

Non-goals: unify every meter in one new database, choose commercial thresholds,
change provider entitlements, alter pricing, aggregate owners across universes,
change lock policy, or claim all storage/host safety gaps are solved.

## Decisions

1. Delete jobs-per-hour refusal at both `workspace_pool.admit` and
   `reserve_operation_bytes`, including the unused constant/argument. Keep job
   observations, stable operation IDs, byte reservations and all lock/outbox
   semantics. No unbounded-work claim: generic dispatch/run admission and actual
   transfer/storage guards remain. No replacement magic number.

2. Preserve the existing activity unit and exact scope in evidence: the global
   admissions ledger counts engine/automation run admissions and authored engine
   mutations. It is NOT every network call, every user gesture or proof of all
   connector entry-point coverage. Explain total and category counts under the
   actual existing limits rather than merging incompatible units or hiding
   stricter subcaps. Further policy reduction remains open.

3. Resource projections are observations, not authorities. Add a pure read-only
   reader under `tinyassets/api/`, using canonical trusted paths, SQLite
   `mode=ro` / query-only reads and no schema initialization. Refuse symlinked or
   escaped paths, bound SQLite waits, and report missing/unreadable/legacy schema
   as unavailable rather than zero. Do not reuse `ledger_usage` or
   `dispatch_window_usage` directly: the former creates schema and the latter
   reports unreadable usage as zero.

4. Attach private usage only after the existing universe authorization in the
   canonical status projection. Existing engine `get_status` already passes its
   pinned universe. Canary/platform-only and unauthorized/early-return status
   must not include the private block. No new tool, grant or caller-supplied
   limit; no identities, paths, lock-holder IDs or credential details in output.

5. Distinguish current workspace lease occupancy, rolling transfer reservations,
   observational job counts, and measured retained workspace bytes. If broader
   storage is not measured, label scope `retained_workspaces`, not total universe
   storage. If safe bounded measurement is unavailable, report unknown. A next
   charge expiration is `next_charge_expires_at`, not guaranteed availability
   for a requested transfer. A current lock has a release condition, not an hourly
   reset. Preserve existing failure classes while improving surrounding evidence.

6. Do not accept a quarantined-tree size as network transfer measurement. A
   failed checkout may transfer compressed/discarded data that is not retained.
   Unknown transfers keep their conservative reservation until actual measured
   transport evidence or the existing window resolves it.

## Risks / Trade-offs

- More starts can increase churn: preserve generic run/effect limits and every
  existing byte/storage/process safeguard. Do not claim the old ten-start limit
  was a physical CPU bound.
- Existing `SCOPE_HOST` is universe-local, not proven host-global. This change
  neither widens nor repairs that lock shape. Keep the concern open.
- Read-only evidence can be stale: stamp observation time and never use it to
  authorize allocation. Missing/unreadable is not zero.
- Full storage attribution and write-time aggregate disk containment remain
  separate known gaps; a status walk is not enforcement.
- The daemon has 4 CPUs available on an 8 GB host and a 4 GiB memory cgroup;
  2 GiB per-workspace RSS maxima cannot safely be multiplied without accounting
  for daemon/provider/cache memory. No host resizing or relaxed limits here.

## Migration Plan

No data or schema migration. Old jobs rows remain valid observations and age
out normally; bytes, locks and outbox ownership do not move. A rollback restores
the old starts policy against existing observations; it does not clear usage.
Deploy only after focused tests, Linux oracle, independent exact-head review and
required CI; verify authenticated canary and live deployed-SHA containment.
Coordinate one ordinary app acceptance conversation; no operator workflow edits.

## Acceptance Boundary

A synthetic sequence of more than ten admitted/released workspaces and more
than ten zero-byte operations succeeds when actual resource guards permit it.
Byte/pool/lease/storage/lock refusal tests stay effective. Read evidence is
owner-scoped, non-mutating and honest about missing data and limited coverage.
The app agent can continue its own work; broader Patches remains open until
remaining platform issues and owner acceptance are resolved.

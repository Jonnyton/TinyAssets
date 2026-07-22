# Truthful storage accounting

## Why

Live `get_status` on 2026-07-22 reported a 52.63 GB backing filesystem with
29.08 GB used while itemizing only 10.23 MB. A later live call at 05:47Z
itemized 2.92 GB after the active universe changed, but still left about
27.4 GB invisible. `pressure_level` remained `ok` in both cases.

The root cause is an accounting-domain mismatch. Production mounts the Docker
named volume `tinyassets-data` at `/data`; `shutil.disk_usage('/data')` reports
the entire host filesystem backing `/var/lib/docker`, while `per_subsystem`
walks only a fixed set of paths inside `/data` and only patches the requested
universe's checkpoint/log/output paths. The numerator and denominator do not
describe the same set of bytes.

## What Changes

- Add explicit used, attributed, unattributed, and attributed-fraction fields
  to `storage_utilization` so the volume equation is inspectable.
- Reconcile the fields after `get_status` applies universe-scoped byte counts,
  not before.
- Extend `pressure_level` with `unknown`. Existing volume thresholds still
  yield `warn` at 80% and `critical` at 95%; below those thresholds the level
  is `ok` only when every used byte is attributed.
- Treat a failed/invalid filesystem measurement as `unknown`, never `ok`.
- Add a regression test that proves reconciliation and a near-full synthetic
  volume cannot report `ok`, including witnessed red/green evidence.

## Impact

- Modified capability: `storage-observability` (new as-built backfill).
- Code: `tinyassets/storage/__init__.py`, `tinyassets/api/status.py`, and their
  packaged runtime mirrors.
- Tests: focused storage-status tests only.
- Public contract: additive numeric fields and one additive enum value,
  `pressure_level='unknown'`.
- Deferred: cap values, growth estimation, retention/reclamation, and host
  directory breakdown. No production data is deleted.

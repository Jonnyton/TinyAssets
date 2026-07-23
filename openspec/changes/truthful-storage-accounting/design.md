# Design: truthful storage accounting

## Evidence and root cause

1. Live connector, 2026-07-22 ~05:20Z: 52,626,063,360 total,
   23,542,018,048 free, 29,084,045,312 used, 10,228,120 itemized,
   `pressure_level='ok'`.
2. Live connector, 2026-07-22 ~05:47Z: 52,626,063,360 total,
   22,299,717,632 free, 30,326,345,728 used. With `concordance` scoped,
   2,919,564,300 bytes were itemized, including a 2,907,643,904-byte
   checkpoint DB; about 27.4 GB remained invisible.
3. Live connector universe probes found another 1,874,288,640-byte checkpoint
   DB in `default-universe`. A status call reports only the requested
   universe's checkpoint/log/output, so per-universe state is omitted whenever
   a different universe is scoped.
4. `deploy/compose.yml` mounts Docker named volume `tinyassets-data:/data`.
   Deploy run 29894031686, step "Preflight droplet disk before image pull",
   showed `/` and `/var/lib/docker` on the same `/dev/vda1` filesystem and
   `df: /data: No such file or directory` on the host. Thus container
   `disk_usage('/data')` measures the host filesystem containing Docker, not a
   dedicated TinyAssets filesystem.
5. The exact remaining host split (images/layers, journals, other host files,
   provider auth homes, community pool, and other `/data` state) requires
   read-only host `du` plus `docker system df`. The documented deploy key is not
   available in this sandbox, so assigning exact category bytes would be a
   guess. This change exposes that gap rather than guessing.

## Contract

`storage_utilization` gains:

- `volume_bytes_used = volume_bytes_total - volume_bytes_free`
- `attributed_bytes = sum(per_subsystem[*].bytes)`
- `unattributed_bytes = max(0, volume_bytes_used - attributed_bytes)`
- `attributed_fraction = attributed_bytes / volume_bytes_used`, or `null` when
  used bytes are unavailable/zero
- `accounting_complete = (attributed_bytes == volume_bytes_used)` when the
  volume measurement is valid, otherwise `false`

The normal under-attribution invariant is:

`attributed_bytes + unattributed_bytes == volume_bytes_used`.

`pressure_level` is evaluated in this order:

1. Invalid/unavailable volume measurement -> `unknown`.
2. Volume at or above 95% -> `critical`.
3. Volume at or above 80% -> `warn`.
4. Incomplete accounting -> `unknown`.
5. Otherwise -> `ok`.

This uses only the already-shipped volume thresholds. It introduces no cap,
retention, growth, or reclamation policy.

## Implementation

A single storage helper recomputes the derived accounting fields and pressure
level from the final snapshot. `inspect_storage_utilization()` calls it once,
and `get_status` calls it again after replacing root placeholders with the
requested universe's checkpoint/log/output sizes. The second call prevents the
derived fields from becoming stale after the existing BUG-032 overlay.

The packaged Claude runtime mirrors the source files to preserve the project's
runtime parity invariant.

## Risks

- Adding `unknown` may expose consumers that assumed three enum values. This is
  intentional fail-loud behavior and is additive under schema version 1.
- Files may grow between `disk_usage` and path walks. The snapshot is
  best-effort and read-only; a later call converges. An impossible overcount is
  treated as incomplete/unknown rather than green.
- Exact host attribution remains deferred until a host-level read-only
  collector exists; `unattributed_bytes` makes that limitation explicit now.

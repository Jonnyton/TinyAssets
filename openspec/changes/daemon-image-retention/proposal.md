## Why

Three new deployment images added approximately 4.8 GB of unique cache after the
September 18 recovery. At 04:21 UTC the same disk measured 81.07% unavailable
capacity but the watchdog measured 76.91% used/total. Its eventual broad prune
would remove rollback images and unrelated disposable host state.

## What Changes

- Unify disk alarm/retention pressure with existing storage telemetry:
  `100 * (1 - available_bytes / total_bytes)`, preserving explicit unknowns.
- Replace automatic broad prune with pressure-triggered, exact immutable
  TinyAssets daemon-image removal only after current recovery verification.
- Preserve all container references, the current daemon, two recent older
  rollback candidates, configured references and release-receipt rollback target.
- Reuse host mutation serialization and existing timers; stop at a low watermark.
- Default image-removal activation off independently of timer enablement; require
  an exact retention-only operator opt-in plus --apply after direct-helper proof.
- No runtime implementation until independent shape approval is relayed by lead.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: narrowly recoverable daemon-cache retention and consistent
  pressure semantics, replacing broad automatic cleanup.

## Impact

Owner: Codex. Branch: `codex/daemon-image-retention-mvp`. One PR, not yet opened.
Expected files: disk_watch.py, disk_autoprune.py, focused retention/pressure tests,
both automatic cleanup service units, host installer closure/tests and operator
documentation. No MCP handles, user data, journal vacuum, volume/container
deletion, build-cache cleanup, new database or provider work.

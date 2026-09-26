# Daemon logs are not shipped off-box, so every deploy erases the evidence

**Filed:** 2026-09-26 · **Verified:** 2026-09-26 on production · **Severity:** P2

## Finding

`tinyassets-ship-logs.timer` is enabled and active on the droplet, but every run logs
`ERROR: LOG_DEST is required (e.g. sftp:storagebox/tinyassets-logs or s3://bucket/logs)`
(journal, 2026-09-26 around 01:08Z and 01:11Z). Nothing is shipped. The daemon's own logs live
only in `docker logs`, which a container recreate discards, and every runtime merge recreates
the container.

Consequence, observed 2026-09-26: the free-account latency investigation needed the per-attempt
`latency_ms` lines and the `converse: learning ...` lines from the 18:12–18:18 PT turns. A
deploy about 6 minutes earlier had already recreated the container, so they were gone. Only the
SQLite turn journal survived, and it has round counts but no per-round timestamps.

## Fix shape

- Configure `LOG_DEST`: a destination and a credential. This is a host decision. It's the
  platform's own operational storage, not a user connection.
- Or have the ship-logs unit fail loudly (disk-watch / Pushover) instead of logging an ERROR
  forever.
- Separately, consider per-round timestamps in `agent_turn_rounds` (a storage-shape change
  that needs its own proposal), so latency evidence survives without logs.

# Design: align fresh-host backup configuration

## Context

`deploy/backup.sh` reads `BACKUP_DEST`, and its systemd unit runs as root.
Rclone therefore resolves `/root/.config/rclone/rclone.conf`. The current
template exposes three `STORAGEBOX_*` values that the runtime never consumes,
the cutover runbook describes `/etc/tinyassets/backup/rclone.conf`, the active
backup runbook claims the service injects `HOME=/app`, and the unit comments
claim the script reads `STORAGEBOX_*`.

## Decision

Make `BACKUP_DEST` the single fresh-host destination setting and document
`sudo rclone config` plus root-owned mode-0600 storage at the path rclone
actually resolves. Keep credentials out of `/etc/tinyassets/env`. Treat every
runtime-linked runbook and unit comment as part of the same contract surface.

## Alternatives

- Teach the backup script to synthesize rclone configuration from
  `STORAGEBOX_*`: rejected because it creates a second credential format and
  stores a password in the shared daemon env.
- Set `RCLONE_CONFIG` to the documented nonstandard path: rejected because no
  installer owns that file and current hosts already use root's normal rclone
  lookup.

## Risks

Existing hosts with a working root rclone configuration are unchanged. Hosts
that populated only the unused template fields were never configured for the
runtime and now receive an actionable setup path.

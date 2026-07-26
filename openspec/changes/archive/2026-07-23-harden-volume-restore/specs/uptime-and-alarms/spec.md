## MODIFIED Requirements

### Requirement: Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill
The installed backup timer SHALL run nightly at 03:00 UTC and catch up after a missed schedule. `deploy/backup.sh` SHALL create a strict brain archive using SQLite's backup API for database files and a best-effort live full-volume archive that tolerates only GNU tar's file-changed exit 1; it SHALL upload both tiers to the configured rclone `BACKUP_DEST` and apply per-tier daily/weekly/monthly retention, with optional best-effort GitHub release shipping when `GH_TOKEN` is set. The manually dispatched DR workflow SHALL provision a fresh DigitalOcean Droplet, bootstrap it, transfer a selected full archive from the primary host, restore the data volume without implicitly starting services, start the daemon separately, probe MCP through an SSH port forward, log a pass, and destroy the successful drill host. A red probe SHALL open `dr-failed` and leave the host available by default; a mid-job failure SHALL run cleanup. Before it stops volume consumers or changes the resolved live volume, full-volume restore SHALL validate that a selected gzip archive is readable and contains only regular files and directories rooted at `_data`; it SHALL reject traversal, absolute, mixed-root, non-directory root, symbolic-link, hardlink, and special-file members. It SHALL extract with the `_data` root stripped to a unique staging sibling so hidden files are restored exactly, preserve the resolved live volume root's ownership and mode on that sibling, serialize restores per resolved volume, stop every running container mounting that volume before swapping, and use a same-parent rename swap that automatically restores the prior directory if the replacement rename fails. A successful swap SHALL retain the old sibling for caller-controlled post-canary rollback. A local absolute, readable, non-symlink regular-file `BACKUP_FILE` SHALL be accepted for a previously downloaded full archive, bypass rclone, and remain caller-owned.

#### Scenario: Nightly backup preserves strict brain state and a recoverable full volume
- **WHEN** the persistent 03:00 UTC timer fires
- **THEN** the backup copies top-level SQLite databases transactionally into the brain tier, creates the full live-volume tier, uploads both to `BACKUP_DEST`, and prunes retention
- **AND** a full-tier tar exit of 1 is retained as a hot-volume warning while exit 2 or greater fails the backup

#### Scenario: Restore and start remain separate operations
- **WHEN** the DR workflow restores the selected archive into a fresh host's `tinyassets-data` volume
- **THEN** the restore script exits after extraction without starting the daemon
- **AND** the workflow starts only the daemon service in a separate step before probing it

#### Scenario: Fresh-host drill records success or preserves failure evidence
- **WHEN** the SSH-forwarded MCP probe is green
- **THEN** the workflow appends the backup/run evidence to `docs/ops/dr-drill-log.md` and destroys the drill Droplet
- **WHEN** the probe is red
- **THEN** it opens a `dr-failed` issue and leaves the Droplet running unless `destroy_on_failure` was explicitly selected

#### Scenario: Invalid archive leaves the live volume intact
- **WHEN** a selected archive is corrupt, truncated, unsafe, or cannot be extracted into staging
- **THEN** restore exits without stopping containers or changing the live volume

#### Scenario: Replacement rename fails
- **WHEN** the original volume has been renamed aside and the staged directory cannot be renamed into its place
- **THEN** restore automatically renames the retained original back to the resolved live path and exits with failure

#### Scenario: Concurrent restores use isolated volume locks
- **WHEN** restores target two different resolved volume directories at the same time
- **THEN** each uses a unique sibling stage and completes independently; a second restore of one resolved volume is refused while its lock is held

#### Scenario: Operator restores a downloaded GitHub Release archive
- **WHEN** `BACKUP_FILE` names an absolute readable non-symlink regular file containing a local full archive and no list or timestamp mode is requested
- **THEN** restore uses that archive without rclone and does not delete it

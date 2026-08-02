## MODIFIED Requirements

### Requirement: Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill
The installed backup timer SHALL run nightly at 03:00 UTC and catch up after a missed schedule. `deploy/backup.sh` SHALL create a strict brain archive using SQLite's backup API for database files and a best-effort live full-volume archive that tolerates only GNU tar's file-changed exit 1; it SHALL upload both tiers to the configured rclone `BACKUP_DEST` and apply per-tier daily/weekly/monthly retention, with optional best-effort GitHub release shipping when `GH_TOKEN` is set. Before provisioning, the manually dispatched DR workflow SHALL validate that its selected primary-host artifact is an absolute, readable, non-symlink `tinyassets-data-*.tar.gz` regular file confined to `/var/backups/tinyassets`, contains only the safe `_data` archive shape, and has at least one regular member; it SHALL record the archive SHA-256 plus one representative member path and SHA-256, and path-like GitHub outputs SHALL use protocol-safe encoding. DigitalOcean API failure SHALL remain red and SHALL NOT be reinterpreted as absent state; diagnostics SHALL name HTTP status or transport class, read at most 4096 failure-body bytes, emit at most 300 normalized/redacted characters, exclude bearer credentials and the raw body, and never enter a successful-response output. The workflow SHALL provision a fresh DigitalOcean Droplet, bootstrap it, transfer the selected archive with pipeline failure propagation, require the destination SHA-256 to match the preflight digest, restore that exact local file without implicitly starting services, verify the representative member at Docker's inspected restored-volume mountpoint, start the daemon separately, probe MCP through an SSH port forward, and attempt destruction of the successful drill host before publishing an unqualified artifact/run/restored-state PASS record. A failed destruction SHALL make the job red and create or update a `dr-failed` escalation containing the Droplet ID, run URL, and bounded diagnostic; it SHALL NOT leave only a PASS record. A red probe SHALL open `dr-failed` and leave the host available by default; a mid-job failure SHALL retain run evidence and run cleanup. Before it stops volume consumers or changes the resolved live volume, full-volume restore SHALL validate that a selected gzip archive is readable and contains only regular files and directories rooted at `_data`; it SHALL reject traversal, absolute, mixed-root, non-directory root, symbolic-link, hardlink, and special-file members. It SHALL extract with the `_data` root stripped to a unique staging sibling so hidden files are restored exactly, preserve the resolved live volume root's ownership and mode on that sibling, serialize restores per resolved volume, stop every running container mounting that volume before swapping, and use a same-parent rename swap that automatically restores the prior directory if the replacement rename fails. A successful swap SHALL retain the old sibling for caller-controlled post-canary rollback. A local absolute, readable, non-symlink regular-file `BACKUP_FILE` SHALL be accepted for a previously downloaded full archive, bypass rclone, and remain caller-owned.

#### Scenario: Nightly backup preserves strict brain state and a recoverable full volume
- **WHEN** the persistent 03:00 UTC timer fires
- **THEN** the backup copies top-level SQLite databases transactionally into the brain tier, creates the full live-volume tier, uploads both to `BACKUP_DEST`, and prunes retention
- **AND** a full-tier tar exit of 1 is retained as a hot-volume warning while exit 2 or greater fails the backup

#### Scenario: Invalid drill archive stops before provisioning
- **WHEN** the selected primary-host path is outside the canonical backup root, missing, unreadable, a symlink, not a regular `tinyassets-data-*.tar.gz`, unsafe, corrupt, or has no representative regular member
- **THEN** the workflow exits red before any DigitalOcean Droplet request

#### Scenario: DigitalOcean failure is not absent state
- **WHEN** key lookup, key creation, Droplet creation, lookup, or deletion receives a non-success HTTP response
- **THEN** the workflow reports only the bounded, normalized, credential-redacted diagnostic with its HTTP status
- **AND** a failed key lookup is not treated as permission to create a replacement key

#### Scenario: DigitalOcean response is adversarially large or secret-bearing
- **WHEN** a failed response exceeds 4096 bytes or contains the exact token, bearer-like text, control characters, or unstructured content
- **THEN** at most 300 sanitized diagnostic characters reach logs or failure evidence
- **AND** the raw body and bearer material do not reach stdout, GitHub outputs, or issues

#### Scenario: Transfer is bound to the selected archive
- **WHEN** either side of the primary-to-drill stream fails or the drill-host SHA-256 differs from preflight
- **THEN** the workflow exits red before restore
- **AND** restore receives the exact transferred absolute file through `BACKUP_FILE` only after the digests match

#### Scenario: Restore and start remain separate operations
- **WHEN** the DR workflow restores the selected archive into a fresh host's `tinyassets-data` volume
- **THEN** the restore script exits after extraction without starting the daemon
- **AND** the workflow verifies one preflight-selected member's path and SHA-256 at Docker's inspected restored-volume mountpoint
- **AND** the workflow starts only the daemon service in a separate step after that restored-state proof

#### Scenario: Representative restored state does not match
- **WHEN** the selected member is missing, is not a regular non-symlink file under the inspected volume root, or its SHA-256 differs
- **THEN** compose and the MCP probe do not run and the drill remains red

#### Scenario: Fresh-host drill records success or preserves failure evidence
- **WHEN** restored-state proof and the SSH-forwarded MCP probe are green
- **THEN** the workflow first confirms destruction of the drill Droplet
- **AND** only then appends the archive checksum, encoded representative member path, representative member checksum, cleanup confirmation, and run evidence to `docs/ops/dr-drill-log.md`
- **WHEN** the probe is red
- **THEN** it opens a `dr-failed` issue and leaves the Droplet running unless `destroy_on_failure` was explicitly selected
- **WHEN** a pre-probe step fails after a Droplet exists
- **THEN** the workflow retains run/artifact identifiers and runs mid-job cleanup

#### Scenario: Droplet destruction fails
- **WHEN** success cleanup, requested red cleanup, or mid-job cleanup cannot delete a known Droplet
- **THEN** the job is red and a `dr-failed` escalation records the Droplet ID, run URL, and bounded diagnostic
- **AND** no durable evidence represents that run as an unqualified PASS

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

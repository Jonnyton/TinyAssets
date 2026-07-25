## MODIFIED Requirements

### Requirement: Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill
The installed backup timer SHALL run nightly at 03:00 UTC and catch up after a missed schedule. `deploy/backup.sh` SHALL create a strict brain archive using SQLite's backup API for database files and a best-effort live full-volume archive that tolerates only GNU tar's file-changed exit 1; it SHALL upload both tiers to the configured rclone `BACKUP_DEST` and apply per-tier daily/weekly/monthly retention, with optional best-effort GitHub release shipping when `GH_TOKEN` is set. Before provisioning, the manually dispatched DR workflow SHALL validate that its selected primary-host artifact is an absolute, readable, non-symlink `tinyassets-data-*.tar.gz` regular file confined to `/var/backups/tinyassets`, contains only the safe `_data` archive shape, and has at least one regular member; it SHALL record the archive SHA-256 plus one representative member path and SHA-256, and path-like GitHub outputs SHALL use protocol-safe encoding. Before provisioning, it SHALL also read only the configured production `TINYASSETS_IMAGE` assignment, normalize at most one matching pair of surrounding single or double quotes, require the resulting exact canonical `ghcr.io/jonnyton/tinyassets-daemon@sha256:<64 lowercase hex>` form, publish that validated nonsecret value as one workflow output, and SHALL NOT copy the primary host's environment or secrets. Before any mutating DigitalOcean request, the workflow SHALL query current distribution-image inventory through the bounded API helper, treat absent pagination navigation as a valid terminal page, follow only valid non-repeating `links.pages.next` continuations on the exact images endpoint within a 10-page budget, aggregate all fetched pages, and select the highest numeric item satisfying `public is true`, `status == "available"`, `distribution == "Debian"`, full slug match `debian-<major>-x64`, and configured-region membership. Catalog/continuation failure, present-but-malformed or cyclic pagination, page-budget exhaustion, malformed inventory, or no eligible image SHALL remain red before resource creation and SHALL NOT fall back to a retired static slug. The resolved provider image slug and daemon runtime image SHALL appear as distinct fields in terminal PASS/failure evidence. DigitalOcean API failure SHALL remain red and SHALL NOT be reinterpreted as absent state; diagnostics SHALL name HTTP status or transport class, read at most 4096 failure-body bytes, emit at most 300 normalized/redacted characters, exclude bearer credentials and the raw body, and never enter a successful-response output. The workflow SHALL provision a fresh DigitalOcean Droplet, bootstrap it, transfer the selected archive with pipeline failure propagation, require the destination SHA-256 to match the preflight digest, restore that exact local file without implicitly starting services, verify the representative member at Docker's inspected restored-volume mountpoint, require exactly one `TINYASSETS_IMAGE=` assignment in the fresh template environment, replace only that assignment with the validated nonsecret digest, start only the daemon separately from that template, probe MCP through an SSH port forward, and attempt destruction of the successful drill host before publishing an unqualified artifact/run/restored-state PASS record. A failed destruction SHALL make the job red and create or update a `dr-failed` escalation containing the Droplet ID, run URL, and bounded diagnostic; it SHALL NOT leave only a PASS record. A red probe SHALL open `dr-failed`, leave the host available by default, and make the workflow conclusion red after evidence handling. A mid-job failure SHALL retain run evidence and run cleanup. A cleanup-only manual dispatch SHALL accept one explicit positive-decimal retained Droplet ID, skip all provisioning, backup, and SSH work, confirm through a bounded lookup that the exact ID has the `tinyassets-dr-drill` name and both `dr-drill` and `tinyassets` tags, and only then make exactly one bounded deletion request with the repository's configured DigitalOcean credential. Before it stops volume consumers or changes the resolved live volume, full-volume restore SHALL validate that a selected gzip archive is readable and contains only regular files and directories rooted at `_data`; it SHALL reject traversal, absolute, mixed-root, non-directory root, symbolic-link, hardlink, and special-file members. It SHALL extract with the `_data` root stripped to a unique staging sibling so hidden files are restored exactly, preserve the resolved live volume root's ownership and mode on that sibling, serialize restores per resolved volume, stop every running container mounting that volume before swapping, and use a same-parent rename swap that automatically restores the prior directory if the replacement rename fails. A successful swap SHALL retain the old sibling for caller-controlled post-canary rollback. A local absolute, readable, non-symlink regular-file `BACKUP_FILE` SHALL be accepted for a previously downloaded full archive, bypass rclone, and remain caller-owned.

#### Scenario: Nightly backup preserves strict brain state and a recoverable full volume
- **WHEN** the persistent 03:00 UTC timer fires
- **THEN** the backup copies top-level SQLite databases transactionally into the brain tier, creates the full live-volume tier, uploads both to `BACKUP_DEST`, and prunes retention
- **AND** a full-tier tar exit of 1 is retained as a hot-volume warning while exit 2 or greater fails the backup

#### Scenario: Invalid drill archive stops before provisioning
- **WHEN** the selected primary-host path is outside the canonical backup root, missing, unreadable, a symlink, not a regular `tinyassets-data-*.tar.gz`, unsafe, corrupt, or has no representative regular member
- **THEN** the workflow exits red before any DigitalOcean Droplet request

#### Scenario: Production runtime image is pinned without secret transfer
- **WHEN** the primary host's final `TINYASSETS_IMAGE` assignment, after removing at most one matching pair of surrounding quotes, is missing, mutable, outside the canonical repository, or not a lowercase SHA-256 digest reference
- **THEN** the workflow exits red before any DigitalOcean mutation
- **WHEN** that assignment is valid and the fresh template contains exactly one `TINYASSETS_IMAGE=` assignment
- **THEN** the drill replaces only that assignment with the validated public digest before Compose starts
- **AND** it does not copy or persist the primary environment or any secret
- **AND** terminal evidence distinguishes the runtime digest from the Debian provider image
- **WHEN** the fresh template contains zero or multiple `TINYASSETS_IMAGE=` assignments
- **THEN** the drill exits red before Compose starts

#### Scenario: Current Debian image is resolved before provisioning
- **WHEN** the bounded aggregate contains multiple image items
- **THEN** the workflow considers only items with `public is true`, `status == "available"`, `distribution == "Debian"`, a full `debian-<major>-x64` slug match, and configured-region membership
- **AND** selects the highest numeric major across all fetched pages
- **AND** it passes that exact current slug into the Droplet creation request

#### Scenario: Complete catalog omits pagination navigation
- **WHEN** a valid image response contains the complete `images` array and no `links` or `pages` navigation
- **THEN** the workflow treats that response as the terminal page and selects from its images

#### Scenario: No eligible Debian image is available
- **WHEN** catalog or continuation lookup fails, inventory/pagination is malformed or cyclic, the 10-page budget is exhausted, or no exact eligible image serves the configured region
- **THEN** the workflow exits red before SSH-key creation or any other mutating request
- **AND** it does not retry with a static retired image slug

#### Scenario: DigitalOcean failure is not absent state
- **WHEN** image catalog lookup, key lookup, key creation, Droplet creation, lookup, or deletion receives a non-success HTTP response
- **THEN** the workflow reports only the bounded, normalized, credential-redacted diagnostic with its HTTP status
- **AND** a failed lookup is not treated as permission to create a replacement resource

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
- **AND** the workflow writes only the validated public runtime digest into the fresh template
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
- **AND** the workflow conclusion is red
- **WHEN** a pre-probe step fails after a Droplet exists
- **THEN** the workflow retains run/artifact identifiers and runs mid-job cleanup

#### Scenario: Operator deletes one retained drill Droplet
- **WHEN** an operator manually dispatches cleanup-only with one positive decimal Droplet ID
- **THEN** the workflow skips backup validation, SSH setup, image selection, and provisioning
- **AND** it requires the looked-up resource to have that exact ID, the `tinyassets-dr-drill` name, and both drill tags
- **AND** it makes one bounded DELETE request for exactly that ID
- **WHEN** the cleanup ID is malformed, the identity check fails, or the deletion fails
- **THEN** the cleanup job exits red without provisioning another resource

#### Scenario: Droplet destruction fails
- **WHEN** success cleanup, requested red cleanup, cleanup-only deletion, or mid-job cleanup cannot delete a known Droplet
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

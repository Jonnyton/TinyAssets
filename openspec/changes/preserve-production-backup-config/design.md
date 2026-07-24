## Context

Production backup has two independent layers: rclone to DigitalOcean Spaces is
the required primary, and GitHub Releases is a best-effort secondary.
`deploy-prod.yml` currently classifies `BACKUP_DEST` as a stale rename-era
override and deletes it on every deploy. The current host also lost root's
rclone configuration, so the installed persistent timer is correctly red.

The repository already holds `DO_API_TOKEN`, production SSH credentials, and a
documented Spaces bucket. DigitalOcean's current `/v2/spaces/keys` API returns
new key credentials once at creation time, allowing a workflow runner to pass
them directly to the root-owned host configuration without storing them in the
daemon environment or repository.

## Goals / Non-Goals

**Goals:**

- Preserve host-owned backup configuration through every application deploy.
- Make the exact-source host-service installer converge a completely absent
  backup configuration before it enables the backup timer.
- Keep Spaces credentials confined to root's mode-`0600` rclone file.
- Make partial or invalid configuration fail visibly instead of rotating or
  overwriting credentials silently.
- Roll back a newly created key if installation fails before verification.

**Non-Goals:**

- Moving Spaces credentials into `/etc/tinyassets/env`.
- Treating GitHub Releases as a replacement for the required rclone primary.
- Automatically rotating a present but failing Spaces key.
- Reusing an existing Spaces key whose secret is no longer available.

## Decisions

### Preserve `BACKUP_DEST` in application deploys

Remove only `BACKUP_DEST` from the deploy scrub list. Retired `WORKFLOW_*`,
`BACKUP_GH_REPO`, and `LOG_DEST` overrides remain scrubbed. This keeps
application release configuration separate from host-owned backup authority.

Alternative: re-inject `BACKUP_DEST` on every deploy. Rejected because it would
move a host-owned setting into the application deployment secret surface and
would still leave root's rclone credentials unsynchronized.

### Converge only the completely absent state

Before installing/enabling timers, `install-host-services.yml` checks the host:

- destination plus a working root rclone configuration: no-op;
- neither destination nor rclone configuration: provision;
- partial configuration or a configured destination that fails its probe: red.

This is idempotent and avoids destructive surprise. A bad existing key requires
an explicit rotation lane.

### Create one bucket-scoped key and hand it directly to root

The runner creates a uniquely named Spaces key with `readwrite` permission on
the existing `tinyassets-backups-jonnyton-sfo3` bucket. It immediately masks
both returned credential fields, writes a temporary rclone config with mode
`0600`, copies it over the authenticated SSH channel, installs it as
`root:root 0600`, and sets only the nonsecret `BACKUP_DEST` through
`deploy/install-tinyassets-env.sh`.

The API token never reaches the host. The Spaces secret never reaches the
daemon environment, GitHub outputs, artifacts, or command arguments.

Alternative: create a full-access key. Rejected because the existing bucket
allows narrower object read/write/delete authority.

### Treat provisioning as a transaction

Until the remote destination probe succeeds, failure cleanup removes the
newly-installed config and destination assignment and deletes the newly created
Spaces key. Once verified, cleanup retains the key and deletes only temporary
files. API failures expose bounded status/class diagnostics, never response
bodies.

## Risks / Trade-offs

- **[DigitalOcean token lacks new Spaces-key scopes]** → The install run stays
  red with the HTTP status; no host configuration changes.
- **[Key created but runner dies before cleanup]** → A uniquely named orphan
  may remain; key-name/run-id evidence makes it discoverable without revealing
  credentials.
- **[Existing configuration is invalid]** → The workflow refuses automatic
  rotation and leaves the current state untouched for explicit operator review.
- **[Provider documentation is contradictory during API rollout]** → Structural
  tests cover our request/response contract and production execution is the
  acceptance gate.

## Migration Plan

1. Land the deploy preservation and convergent installer changes.
2. Run the installer at the exact merge SHA. On the currently absent host, it
   creates and verifies one scoped Spaces key.
3. Run the backup unit manually; verify both tiers exist in Spaces and GitHub.
4. Download a new full-tier artifact and run non-mutating archive validation.
5. Dispatch a production deploy and confirm `BACKUP_DEST`, rclone access, and
   the backup timer remain healthy.

Rollback removes the new key through the DigitalOcean API, removes root's
rclone file, deletes `BACKUP_DEST` through the atomic env helper, and reverts
the workflow change.

## Open Questions

None. The existing bucket, region, destination prefix, and primary/secondary
roles are already canonical in the uptime spec and runbook.

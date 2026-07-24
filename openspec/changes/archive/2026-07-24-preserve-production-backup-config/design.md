## Context

Production backup has two independent layers: rclone to DigitalOcean Spaces is
the required primary, and GitHub Releases is a best-effort secondary.
`deploy-prod.yml` currently classifies `BACKUP_DEST` as a stale rename-era
override and deletes it on every deploy. The current host also lost root's
rclone configuration, so the installed persistent timer is correctly red.

The repository already holds `DO_API_TOKEN`, production SSH credentials, and a
documented Spaces bucket. The bucket is an external resource that predates the
product rename: its immutable provider identity remains
`workflow-backups-jonnyton-sfo3`. A mechanical documentation rename introduced
the nonexistent `tinyassets-backups-jonnyton-sfo3` name. DigitalOcean's current
`/v2/spaces/keys` API returns new key credentials once at creation time,
allowing a workflow runner to pass them directly to the root-owned host
configuration without storing them in the daemon environment or repository.

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

### Preserve the external bucket identity

The canonical destination remains
`spaces:workflow-backups-jonnyton-sfo3/workflow-backups`. Product-facing names
move to TinyAssets, but existing provider resources are not renamed by a source
tree migration. On 2026-07-23, an unauthenticated `HeadBucket`-equivalent probe
returned HTTP 403 for the pre-rename bucket (private resource exists) and HTTP
404 for the mechanically renamed bucket (resource absent). The exact-merge
installer's HTTP 403 `bucket_or_grant` result independently confirms that the
new name cannot receive a scoped grant.

Alternative: create a new TinyAssets-named bucket. Rejected for this repair
because it would abandon continuity with the existing primary backup history
and require account-wide bucket-creation authority.

### Create one bucket-scoped key and hand it directly to root

The runner creates a uniquely named Spaces key with `readwrite` permission on
the existing `workflow-backups-jonnyton-sfo3` bucket. It immediately masks
both returned credential fields, writes a temporary rclone config with mode
`0600`, copies it over the authenticated SSH channel, installs it as
`root:root 0600`, and sets only the nonsecret `BACKUP_DEST` through
`deploy/install-tinyassets-env.sh`.

The API token never reaches the host. The Spaces secret never reaches the
daemon environment, GitHub outputs, artifacts, or command arguments.

Alternative: create a full-access key. Rejected because the existing bucket
allows narrower object read/write/delete authority. The original 2026-06-10
bootstrap used full access only because the bucket did not exist yet; the
repair must not retain that account-wide privilege after creation.

### Treat provisioning as a transaction

Until the remote destination probe succeeds, failure cleanup removes the
newly-installed config and destination assignment and deletes the newly created
Spaces key. Once verified, cleanup retains the key and deletes only temporary
files. API failures expose bounded status/class diagnostics, never response
bodies.

New Spaces credentials are eventually consistent at the S3-compatible data
plane. The installer retries only the read/list destination probe across a
bounded window: 65 seconds of inter-attempt backoff plus five probes hard-capped
at five seconds with one second of kill grace each, for a 95-second worst case.
It does not recreate the key, broaden its grant, or enable the timer until the
same credential succeeds. Exhausting the window follows the ordinary
transactional rollback path. The installer does not call `rclone mkdir` first:
S3 has no empty directories, and rclone's nominal no-op still performs an
unbounded data-plane request that would bypass the retry gate.

### Exercise backup only by explicit dispatch

Normal deploy-triggered and manual installer runs converge host services without
starting a potentially long backup. The `workflow_dispatch` surface exposes a
default-false boolean `run_backup`; only an explicit true value starts
`tinyassets-backup.service` after exact-source installation.

The exercise records the newest brain/full primary archive names before the
service, requires `Result=success`, then requires both newest names to change.
It captures the new service invocation's systemd `InvocationID` and queries
only journal entries carrying that exact `_SYSTEMD_INVOCATION_ID`; a
second-resolution time window could mix markers from a concurrent or immediately
preceding run. Within that invocation it requires both primary upload markers,
exactly two GitHub release asset upload markers, no backup error marker, and the
terminal completion marker. It prints only archive names and counts, never the
environment file, rclone configuration, or credentials.

## Risks / Trade-offs

- **[DigitalOcean token lacks new Spaces-key scopes]** → The install run stays
  red with the HTTP status plus an allowlisted identifier/category that never
  prints provider message text; no host configuration changes.
- **[Key created but runner dies before cleanup]** → A uniquely named orphan
  may remain; key-name/run-id evidence makes it discoverable without revealing
  credentials.
- **[New key is not immediately accepted by the Spaces data plane]** — Retry
  the non-mutating destination probe for at most 95 seconds, then roll back.
- **[Existing configuration is invalid]** → The workflow refuses automatic
  rotation and leaves the current state untouched for explicit operator review.
- **[Provider documentation is contradictory during API rollout]** → Structural
  tests cover our request/response contract and production execution is the
  acceptance gate.

## Migration Plan

1. Land the deploy preservation and convergent installer changes.
2. Run the installer at the exact merge SHA. On the currently absent host, it
   creates and verifies one scoped Spaces key.
3. Dispatch the exact-source installer with `run_backup=true`; verify fresh
   brain/full archives in Spaces and both GitHub release assets.
4. Download a new full-tier artifact and run non-mutating archive validation.
5. Dispatch a production deploy and confirm `BACKUP_DEST`, rclone access, and
   the backup timer remain healthy.

Rollback removes the new key through the DigitalOcean API, removes root's
rclone file, deletes `BACKUP_DEST` through the atomic env helper, and reverts
the workflow change.

## Open Questions

None. The existing bucket, region, destination prefix, and primary/secondary
roles are confirmed by repository history plus provider HTTP behavior. The
source-tree rename does not authorize creation of replacement infrastructure.

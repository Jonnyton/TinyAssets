# Daemon image retention: rollout remains pending

No production cleanup or service activation was performed while preparing this
patch. Both cleanup units change together; transcript rotation remains unchanged.
The compatibility command is dry-run by default. Only `--apply` permits removal;
`DRY_RUN=1` overrides that switch. Installed timers pass `--apply`, so **do not
install/activate these units until the coordinating release owner accepts the
dry-run and exact-head review**.

## Configuration and prerequisites

- Pressure is `100 * (1 - available / total)`. Zero available means100%; invalid
  or zero total is unknown. Defaults:85% trigger,75% stop; optional
  `DISK_AUTOPRUNE_PCT` and `DISK_AUTOPRUNE_LOW_PCT` must satisfy0<low<high<100.
- Classic overlay2 uses the inspected DockerRootDir. Containerd stores require
  `TINYASSETS_IMAGE_RETENTION_STORAGE_PATH` to name the operator-verified image
  content filesystem; absence refuses, including dry-run. Verify live Docker
  driver and actual storage mount before setting it. The path grants no deletion
  authority: only exact allowlisted Docker image refs can be removed.
- `DISK_WATCH_PATH` remains an explicit alarm-only override. Without it, the
  alarm uses the same image-store path resolution as retention. Unknown alarm
  mapping reports UNKNOWN/status1 and still permits transcript rotation; the
  retention command independently refuses any deletion.
- Current configuration is reread from `/etc/tinyassets/env` under the host
  mutation lock. No eval, shell sourcing, arbitrary target path, or secret log.
- `tinyassets-data` must be the active daemon's `/data` mount. Its root receipt
  must exist and contain an explicit rollback_target (empty is valid). Release
  path overrides, unknown protected images, any fence state, unavailable locks,
  or unverified registry recovery refuse.
- GHCR verification uses an anonymous pull-scoped token for the fixed public
  daemon repository. No Docker login, account key, registry push or paid service.
  Failure preserves local cache. Manifest/config hashes and host platform are
  checked; every required layer is probed before any deletion.

## Lead-owned acceptance

1. Exact-head independent review and required CI first. Publish the complete
   checksummed runtime closure, without enabling cleanup ahead of acceptance.
2. Inspect a dry-run of the installed command. Confirm current/all stopped and
   running container references, configured image, explicit receipt rollback,
   two newer rollback candidates and all newer-than-current images protected.
   Unknown store mapping is a blocker, not a reason to guess a path or skip it.
3. Lead authorizes one bounded effectful pass only after inspecting that proof.
   The helper takes fence then mutation lock, makes at most four non-force
   immutable daemon removals, caps the locked phase at60s/whole pass120s, and
   rechecks live inventory/configuration before each removal. Per-removal events
   remain visible even if a later check fails. Pressure residual is not success.
4. Verify data volumes/containers unchanged, rollback images available, protected
   public canary green, and actual filesystem pressure measured. Registry-verified
   cache can be pulled again by exact digest; remote permanence is not promised.
5. Only then accept normal timer operation; next healthy tick must avoid needless
   removal. Rollback disables cleanup entrypoints or uses a reviewed safe no-op,
   never reinstates broad prune. Sync/archive only after accepted live proof.

This slice does not fix browser per-job memory isolation, arbitrary user data
retention, build cache, journals, or the separate emergency-triage workflow.

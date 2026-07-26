## Context

The host has five timer-backed uptime layers: the local MCP watchdog,
container/heartbeat watchdog, nightly backup, weekly image prune, and hourly
disk-pressure remediation. Fresh-host bootstrap installs only three of those
five, while the post-deploy host-service workflow installs only the second
watchdog. Bootstrap also enables a timer only when its unit file changed, so a
current but disabled timer stays disabled forever.

The timers execute host-side source under `/opt/tinyassets`; synchronizing only
unit files can therefore advertise current behavior while running stale code.
The disk-watch service also invokes `python3 -m scripts.rotate_run_transcripts`
without a working directory or `PYTHONPATH`, so its rotation step cannot import
the installed module reliably on a fresh host.

## Goals / Non-Goals

**Goals:**

- Make one installer own the complete timer/unit/direct-runtime-asset manifest.
- Have fresh-host bootstrap and post-deploy reconciliation invoke that same
  installer.
- Synchronize files, reload systemd, always enable/start every timer, and prove
  each is enabled and active on every run.
- Bound same-target waiting so every caller subsequently verifies convergence,
  while independent target roots remain concurrent and isolated.

**Non-Goals:**

- Starting `tinyassets-daemon.service` before its environment is configured.
- Replacing the distinct watchdog algorithms or their timers.
- Treating successful systemd activation as proof that later probes, backups,
  or disk remediation are green.
- Mutating a live host before the reviewed change lands.

## Decisions

### Use one source-controlled installer from every caller surface

`deploy/install-host-uptime-services.sh` owns the manifest, file modes,
systemd reload, enable/start, and verification sequence. Bootstrap invokes it
after cloning the repo and creating the service account. The host-service
workflow and the restart workflow's optional install step obtain the exact
manifest from the installer, send a source-pinned bundle, and invoke that same
script remotely. This avoids three independently drifting installation
recipes.

Alternative considered: duplicate the missing units into each caller. Rejected
because the current outage is already a duplication drift failure.

### Install an exact runtime closure with its units

The unit manifest is exactly the five service/timer pairs. The runtime manifest
is exactly:

- `deploy/daemon-watchdog.sh`, `deploy/backup.sh`;
- `scripts/{__init__,watchdog,mcp_public_canary,disk_watch,disk_autoprune,rotate_run_transcripts,backup_ship_gh,backup_prune}.py`;
- `tinyassets/__init__.py`,
  `tinyassets/storage/{__init__,rotation}.py`.

The disk-watch unit uses the installed runtime root as `WorkingDirectory`, so
its module invocation resolves only this installed package closure. Runtime
assets are copied into a content-addressed release directory. Units reference a
stable `current` symlink, and the installer switches that symlink atomically
only after the full closure exists.

Alternative considered: update units only and rely on the historical host
checkout. Rejected because image deploys do not update that checkout.

### Converge state rather than branch on file changes

File copying may skip byte-identical destinations, but every invocation runs
`systemctl enable --now` and then checks both `is-enabled` and `is-active` for
all five timers. A disabled current timer is therefore repaired, and any failed
activation remains visible.

### Pin the automatic workflow bundle to the deployed source

For `workflow_run`, checkout is explicitly bound to
`github.event.workflow_run.head_sha`; manual dispatch and the restart workflow
use the dispatch's immutable `github.sha`. A private per-run bundle contains
that SHA, the installer's printed exact manifest, and a checksum verified on
the remote host before installer invocation.

### Lock and validate each target before mutation

The installer rejects missing/non-regular manifest sources; canonicalizes
absolute source, runtime, systemd, sudoers, and lock roots; and permits
non-production roots only in explicit test mode with a non-live systemctl
binary. A bounded-wait `flock` name derived from the resolved runtime root
prevents two reconciliation runs from interleaving one target's file and
systemd changes. Callers wait for that lock for a bounded interval rather than
losing immediately; after acquiring it, each independently runs the full
activation verification. Workflow uploads use a unique remote directory, so
pre-lock staging never shares fixed `/tmp` names.

### Quiesce timers without killing active work

After acquiring the lock, the installer stops the five timers to prevent new
ticks. It waits a bounded interval for their oneshot services to become
inactive; active, activating, reloading, and deactivating states all keep the
wait open, while DBus errors and unknown states fail closed. It never stops an
active backup or remediation service. A timeout restores timer activation and
exits before destination files change. Once quiescent, it installs the
versioned runtime and staged units, atomically switches `current`, reloads
systemd, and enables/starts/verifies all timers. Failure rolls the prior pointer
and unit files back before reactivation.

### Keep fresh-host recovery dormant until the daemon is configured

Both watchdog timers are enabled immediately so later configuration needs no
second activation step. Their services use an `ExecCondition` on the required
`TINYASSETS_IMAGE`, so timer ticks skip recovery while bootstrap's env template
is intentionally blank. Once the operator configures the image, both existing
watchdog algorithms run normally and can recover an inactive daemon.

### Validate sudoers before atomic installation

Fresh bootstrap installs `sudo` and `util-linux`, and the installer checks
`systemctl`, `flock`, `realpath`, `sha256sum`, `install`, and `visudo` before
mutation. It renders the watchdog rule privately, validates that exact candidate
with `visudo -cf`, then atomically installs it as mode `0440`.

## Risks / Trade-offs

- **[A new asset is referenced by a unit but omitted from the manifest] ->**
  Tests assert the exact manifest and invoke the installed disk rotation,
  backup dry-run, watchdog, and canary paths from their systemd-equivalent
  runtime root.
- **[A timer starts before all files are current] ->** install the complete
  manifest, then reload once, then enable/start.
- **[Activation succeeds initially but later work fails] ->** keep runtime
  canaries and alarm sinks as the health authority; installation proves only
  enabled/active systemd state.
- **[Concurrent workflow and bootstrap runs collide] ->** serialize per target
  root, bound lock waiting, and require every acquired caller to verify the
  converged end state.
- **[A long backup is active during reconciliation] ->** pause only timers,
  wait without killing the service, then restore timers and fail before file
  mutation if the bounded wait expires.

## Migration Plan

Land the installer, callers, tests, and spec together. The next successful
production deploy runs host-service reconciliation and repairs missing or
disabled timers. The installer retains the prior runtime pointer and unit
backups until the new timers verify, so an in-run failure restores them before
reactivation. Repository rollback then uses the prior reviewed installer.

## Open Questions

None.

## Context

Read-only September 18 04:21 evidence: root and container data filesystem agree,
52,626,063,360 total bytes, about 9,961,717,760 available. Storage telemetry is
81.07%, df rounds 80.249% upward to 81%, current watchdog is 76.91%. Docker has
23 images, three referenced by containers; three new daemon releases added about
4.8 GB unique bytes since reclaim. Data volume remains 4.547 GB. Four explicitly
inventoried old daemon digests were proved remotely recoverable: index/amd64
manifest hashes matched and all 68 distinct required config/layer blobs answered
HEAD 200. No production changes were made.

Existing seams inspected:
- `scripts/disk_watch.py::_disk_usage_pct` and `disk_autoprune.py` use used/total.
- `disk_autoprune.py::_host_disk_reclaim` currently system-prunes, builder-prunes
  and vacuums journals; none belongs in this narrow automatic path.
- `deploy/tinyassets-disk-watch.service`: ordered alert, rotation, cleanup;
  180-second total timeout; hourly/minute-27 timer. Preserve rotation behavior.
- `deploy/tinyassets-prune.service`: weekly broad image/builder prune. This second
  automatic entrypoint must use the same bounded retention path, not bypass it.
- `deploy/deploy_fail_safe.sh`: `/var/lock/tinyassets-host-mutation.lock`, held
  across pull, adoption and rollback. Current image is captured from live Docker;
  `TINYASSETS_IMAGE` is configured in `/etc/tinyassets/env`.
- `scripts/retire_cheat_loop_deploy_fence.py`: `guard-host-mutation` additionally
  holds `/run/lock/tinyassets-deploy-fence.lock` and checks durable deployment
  state before running a bounded child. Its order must precede host-mutation lock.
- `deploy/install-host-uptime-services.sh` already publishes both service units
  and disk scripts into an immutable checksummed host runtime; any new helper or
  guard dependency must enter this closure and its installer tests.
- `release-state.json` includes `rollback_target`; deployment receipt can hold
  an empty target. Do not infer an unknown rollback target from an arbitrary tag.

## Goals / Non-Goals

Goal: safe unattended relief from known recoverable daemon image cache, without
damaging current service, rollback capacity or user data.
Non-goals: general Docker cleanup, user storage rotation fixes, journals, volumes,
container deletion, provider payload reads, registry retention policy or billing.

## Decisions

1. **Pressure/hysteresis.** Same formula as telemetry (not df and not used/total).
   Retain default trigger 85%; add low watermark 75%, validated 0 < low < high <
   100. On each tick below trigger do nothing; above trigger remove oldest safe
   candidates one at a time until measured pressure <= low. No persistent
   hysteresis state. If exhausted, emit unmet-pressure evidence, not success.
   Missing/invalid/zero-total measurement means unknown and no deletion. Zero
   available bytes with a positive total is genuine 100% pressure, not unknown.
   Measure the image-store filesystem: classic overlay2 uses DockerRootDir;
   containerd requires an operator-verified configured storage path because
   DockerRootDir alone does not identify its image-content filesystem. Unknown
   store/path mapping refuses even in dry-run; never guess from daemon.json.
2. **Authorization boundary.** Literal repository allowlist
   `ghcr.io/jonnyton/tinyassets-daemon`; immutable sha256 refs only. Inventory all
   images and ALL containers including stopped. Preserve all container image IDs,
   current daemon ID, configured TINYASSETS_IMAGE and release rollback_target,
   plus two newest older daemon-image creation times relative to current. Keep
   images newer than current too (could be pending/failed rollout); creation time
   is conservative cache retention, not proof of successful deployment. Missing
   or malformed current identity, creation timestamps, configuration/receipt or
   ambiguous image mappings abort the pass. An explicitly empty rollback target
   is allowed; a nonempty unresolvable one is not silently ignored. Extra tagged
   or foreign-repository aliases cause candidate exclusion. Docker containerd
   may repeat the row's sole exact fixed-repository immutable RepoDigest as
   its sole RepoTag; that identical digest alias is eligible, not a mutable tag.
   Any additional, foreign or mismatched alias remains excluded, with unchanged
   reference protection, registry verification and under-lock re-inventory.
3. **Recoverability.** Fixed GHCR registry and pull-only token scope; never invoke
   docker login or expose a token. Fetch exact index/manifest with bounded size
   and timeout; hash-check every manifest against its descriptor; select exact
   host platform, verify config digest against local image identity where Docker
   exposes a classic config ID, and verify all referenced config/layer objects
   exist remotely. Docker containerd image IDs may equal index digests rather
   than config hashes: accept only validated index/child/config relationships,
   never assume `.Id == config.digest`. No pull required. Unknown platform,
   corrupt/missing manifest/blob, auth/network failure => no candidate removal.
4. **Race safety.** Acquire existing deployment-fence lock then shared
   host-mutation lock directly and nonblocking. Do not import the obsolete fence
   script or its unrelated disabled-timer residue check. Any existing fence
   state file, including restored or unreadable state, refuses cleanup.
   Unavailable/busy lock produces explicit skipped evidence. Re-inventory under lock and
   recheck ALL references/protected refs immediately before every deletion. Use
   `docker image rm repository@sha256:digest` with no force. Concurrent unguarded
   user Docker commands remain protected by non-force Docker refusal; stop on
   errors. Never remove by mutable tag or computed filesystem path.
5. **Bounds.** One process per tick, fixed maximum of four removals and 120-second
   overall work budget inside the existing 180-second unit; bounded network and
   subprocess deadlines. No removals after budget expiry; remeasure after each.
   Registry verification runs before locks; the locked phase is capped at 60
   seconds to leave headroom below deployment's 120-second lock wait. A tick
   that cannot finish safely leaves remaining pressure visible.
6. **Integration.** Existing hourly disk-watch and weekly prune units route to
   the same pressure-triggered command and same locks/state refusal. No new timer or rollout
   hook in V1; no nested lock inside deploy. Ensure installer supplies complete
   helper runtime and invokes existing CLI help checks, without activation
   here. Dry-run emits only selected digests, protection reasons and pressure,
   never commands that mutate; no env contents/paths/secrets are logged.
7. **Activation.** Installer always enables its timers, so a procedural pause
   is not a safety boundary. Removal requires BOTH `--apply` and the exact
   operator opt-in `TINYASSETS_DAEMON_IMAGE_RETENTION_APPLY=1`. Missing or `0`
   means read-only retention; every other value refuses before any work.
   Opt-in alone without `--apply` remains read-only. `DRY_RUN=1` can only reduce
   authority. The new flag is retention-specific: alarms and existing transcript
   rotation do not read it. Root runs the installed helper directly without
   `--apply` for acceptance; never claim the whole chained service is dry-run.

## Risks / Trade-offs

- Registry outage prevents recovery verification -> preserve all local images.
- Four removals may not reach low watermark -> explicit residual pressure; next
  existing tick can continue if above trigger. No unsafe fallback cleanup.
- Multiple automatic cleaners -> migrate both timer entrypoints together;
  unrelated emergency-triage workflows remain outside this automatic lane.
- Shared layers make estimates unreliable -> actual filesystem remeasurement,
  never claim Docker's reclaimable total (observed reporting exceeds 100%).
- Misconfigured rollback/read failure -> safe refusal, not best-effort guessing.

## Migration Plan

Independent shape approval first; implement/tests in isolated branch. Linux
oracle, exact-head review and required CI precede lead-owned host installer
activation. Before install, root confirms the retention opt-in is absent or0.
Installer can then resume ordinary alarm/rotation timers without authorizing
image removal. First direct-helper production run is dry-run with protected
identities verified; lead then sets only the retention opt-in to1 and records
health/free-space proof. No global DRY_RUN hold is needed or relied upon.
Rollback disables the two cleanup timer entrypoints or reinstalls a reviewed safe
no-op; do NOT restore broad-prune behavior. Removed cache can be re-pulled by
exact verified digest while registry objects remain available. User data untouched.

## Resolved shape review and remaining deployment evidence

Original Fable ADAPT recovered verbatim in `shape-review-recovered.md`. Adopt
direct dual locks and shorter locked phase, not the 5,208-line fence dependency.
The authoritative receipt is `release-state.json` directly under the mountpoint
of Docker volume `tinyassets-data`, confirmed by deploy-prod.yml's writer.
Require active daemon /data to name that volume; any release-path override,
missing/invalid receipt or mismatched mount refuses. Never traverse user folders.

Correct two review premises: zero available is full, and absent snapshotter
configuration does not prove classic storage. Docker Engine 29+ fresh installs
default to containerd, which may store image contents under /var/lib/containerd.
Source: [Docker's storage documentation](https://docs.docker.com/engine/storage/containerd/)
and [daemon storage paths](https://docs.docker.com/engine/daemon/).
No new dual-store abstraction is needed: require bounded verified descriptor
relationships and accept local ID only as immutable root digest or selected
config digest; record driver and unknown mapping honestly. Actual host mapping
and protected-reference dry-run are rollout prerequisites, not presumed here.

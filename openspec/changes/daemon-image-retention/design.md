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
   Missing/invalid/zero-total measurement means unknown and no deletion.
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
   or foreign-repository aliases cause candidate exclusion.
3. **Recoverability.** Fixed GHCR registry and pull-only token scope; never invoke
   docker login or expose a token. Fetch exact index/manifest with bounded size
   and timeout; hash-check every manifest against its descriptor; select exact
   host platform, verify config digest against local image identity where Docker
   exposes a classic config ID, and verify all referenced config/layer objects
   exist remotely. Docker containerd image IDs may equal index digests rather
   than config hashes: accept only validated index/child/config relationships,
   never assume `.Id == config.digest`. No pull required. Unknown platform,
   corrupt/missing manifest/blob, auth/network failure => no candidate removal.
4. **Race safety.** Invoke through existing deployment-fence guard, then acquire
   shared host-mutation lock nonblocking; unavailable/busy lock or active/unknown
   deploy state produces explicit skipped evidence. Re-inventory under lock and
   recheck ALL references/protected refs immediately before every deletion. Use
   `docker image rm repository@sha256:digest` with no force. Concurrent unguarded
   user Docker commands remain protected by non-force Docker refusal; stop on
   errors. Never remove by mutable tag or computed filesystem path.
5. **Bounds.** One process per tick, fixed maximum of four removals and 120-second
   overall work budget inside the existing 180-second unit; bounded network and
   subprocess deadlines. No removals after budget expiry; remeasure after each.
   A tick that cannot finish safely leaves remaining pressure visible.
6. **Integration.** Existing hourly disk-watch and weekly prune units route to
   the same pressure-triggered command and same guards. No new timer or rollout
   hook in V1; no nested lock inside deploy. Ensure installer supplies complete
   guard/helper runtime and invokes existing CLI help checks, without activation
   here. Dry-run emits only selected digests, protection reasons and pressure,
   never commands that mutate; no env contents/paths/secrets are logged.

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
activation. First production run is dry-run with protected identities verified;
lead then authorizes normal timer behavior and records health/free-space proof.
Rollback disables the two cleanup timer entrypoints or reinstalls a reviewed safe
no-op; do NOT restore broad-prune behavior. Removed cache can be re-pulled by
exact verified digest while registry objects remain available. User data untouched.

## Open Questions For Shape Review

The deployment-fence script is not currently in the host-uptime runtime manifest.
Review whether to add its complete stdlib closure (preferred existing guard), or
whether shared host-mutation lock alone is sufficient with this site's current
deploy-fence lifecycle. No implementation chooses or bypasses this gate yet.
Confirm authoritative host location for release-state via the active daemon's
mounted data volume/configuration without traversing user directories. Missing
receipt refuses cleanup rather than assuming no rollback target.

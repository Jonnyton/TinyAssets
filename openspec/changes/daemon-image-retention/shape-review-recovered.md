# Recovered independent shape review

Original Claude Fable 5.1 review of proposal head a94c4d15b170a933c71e2029411125ed681bd6e8.
Recovered September 19, 2026 from assistant text in local session
`b1ef658a-43e7-45b4-ae82-95066d10e893`. The lead's original output captured
only a Stop-hook continuation. This is the substantive earlier assistant block,
retained verbatim. Verdict is ADAPT, not an exact-head runtime release approval.
Source-code and environment premises must still be verified before adoption.

Review complete. Findings below, verdict at the end.

**AGREE**

- Replacing both prune entrypoints with one bounded, pressure-triggered exact removal is the right shape. The current `disk_autoprune.py:37-53` runs `docker system prune -af`, builder prune and journal vacuum, and `tinyassets-prune.service:21` prunes every image over 7 days. Both would delete rollback candidates.
- Pressure formula matches telemetry exactly: `tinyassets/storage/__init__.py:707-710` computes `1 - free/total`, and Python's `free` is `f_bavail`, so reserved blocks count as unavailable. Measure the filesystem holding the Docker root dir rather than `/`, since that is where reclaimed bytes land.
- Non-force removal by `repo@sha256:D` is safe against unlocked restarters. `scripts/watchdog.py` restarts the daemon with no lock at all, and `daemon-watchdog.sh:15` uses its own lock, not the mutation lock. Both recreate from the protected configured image, and Docker refuses to remove any image a container references.
- Deploy rollback re-pulls (`deploy_fail_safe.sh:1087`), so keeping two older candidates is defence in depth, not a hard dependency. Empty `rollback_target` must stay allowed: the deploy receipt hardcodes it empty (`deploy-prod.yml:389`).

**DISAGREE_EVIDENCE: do not add the fence script to the runtime closure**

- The two lock populations are disjoint. The real deploy and its rollback hold only the mutation lock (`deploy_fail_safe.sh:170,229-232`) and never consult the fence. Three workflows hold only the fence lock (`retire_cheat_loop_deploy_fence.py:5162`) while running `docker system prune -af` (`p0-outage-triage.yml:213-215`) and `docker pull` plus restart (`:240-264`). So holding both locks, fence first, is correct and matches the existing nesting.
- But `guard_host_mutation` (`:2114-2152`) checks only fence-state phase and masked-unit or `restart=no` residue. None of that bears on image removal, and today it would refuse permanently because `daemon-watchdog.timer` is deliberately disabled (`docs/concerns/2026-08-27-unsafe-fence-recovery-path-deleted.md:21-26`). The script is 5,208 lines, slated for deletion, and its tests carry 17 heavy-tests failures.
- Minimal adaptation: take both files directly with `fcntl.flock(LOCK_EX|LOCK_NB)`, creating `/run/lock/tinyassets-deploy-fence.lock` mode 0600 as `_operation_lock` does, then `/var/lock/tinyassets-host-mutation.lock`. Busy on either skips with evidence. Add one durable-state check: if the fence state file exists at all, skip. Nothing else enters the installer manifest except the retention module.

**DISAGREE_CONCERN: lock hold can fail a deploy**

`deploy_fail_safe.sh:171` waits 120 seconds for the mutation lock, then refuses and fails the run. A 120-second retention budget held under that lock can turn a routine deploy red. Adaptation: run all registry verification before acquiring any lock, then under lock only re-inventory local Docker state, recheck the protected set, and remove. Cap lock hold at 60 seconds. Registry state does not depend on local locks, so pre-lock verification stays valid.

**Receipt location (open question 2)**

Writer path is authoritative: `deploy-prod.yml:394-395` installs to `docker volume inspect tinyassets-data --format '{{ .Mountpoint }}'` plus `/release-state.json`. Read that one file at the volume root, never rglob. Refuse if the daemon container's `/data` mount is not that volume or its env sets `TINYASSETS_RELEASE_STATE_PATH` (unset anywhere in deploy today). Do not copy p0 triage's host read of `/data/release-state.json` (`:246`), which is a container path.

**Containerd ID validation (open question 3)**

`hetzner-bootstrap.sh:126-138` writes only log options into daemon.json and nothing in the repo enables the containerd snapshotter, so production is the classic store. Do not build a dual-store validator. Removal ref is the image's single allowlisted `RepoDigests` entry D, which is exact under either store. Remote check: fetch D, hash-check, pick the linux/amd64 child if an index, hash-check, HEAD config and every layer. Local cross-check is one rule: accept only if `.Id` equals D or the selected child's config digest. Record `docker info` driver in dry-run evidence.

**Required negative tests**

1. Fence lock busy, mutation lock busy, fence state file present: each yields zero removals and skip evidence, using a real flock in a subprocess.
2. Registry calls occur with no lock held; mutation lock released within the cap even with a slow fake Docker.
3. Reserved-block fixture from the test plan, plus zero total or zero free reads as unknown and refuses.
4. Receipt missing refuses; empty `rollback_target` allowed; nonempty unresolvable refuses; override env var present refuses.
5. `.Id` matching neither D nor child config excludes the candidate; index hash mismatch and wrong platform exclude.
6. Every Docker argv is read-only or exactly `docker image rm ghcr.io/jonnyton/tinyassets-daemon@sha256:<64hex>`; forbid force, prune, builder, journalctl.
7. A stopped container referencing the target at recheck time blocks removal.
8. Migrated weekly unit carries `EnvironmentFile` and `WorkingDirectory` (`tinyassets-prune.service` has neither today) and no builder prune.
9. Installer manifest includes the retention module and excludes the fence script; CLI help runs from the installed release root.

**Later hardening, separate lane**

Retire the fence at its three call sites (task 2.5a), unify the two locks, tag-pulled image reclaim (those are excluded and will show as residual pressure in dry-run), GHCR credential scoping if the package is private (`DEPLOY.md:325` assumes public), containerd store support if ever enabled.

VERDICT: ADAPT


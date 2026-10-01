---
severity: P1
title: A jailed process can fill the shared disk; the storage quota only counts its writes afterwards
filed: '2026-10-01'
summary: 'The account storage quota is enforced only on platform-mediated writes. Bytes written inside the tool jail or the provider jail are never gated, and are counted only when the owner''s next gated write re-measures. The tool jail stops at a volume-wide 1 GiB floor, and the provider jail has no disk limit at all. /data is a Docker volume on the droplet''s root ext4, so one universe can fill the disk that every user, Docker and the OS share. Fix by construction: kernel project quotas, one project per account, on a dedicated data volume. Interim in-repo gates are listed below.'
---

# A jailed process can fill the shared disk

**Filed:** 2026-10-01, from the gpt-6-astra refute of #4245.
**Verified:** 2026-10-01 against origin/main `9ff72abc` (code), plus a read-only check of production through `scripts/droplet.py ssh` (`df -T`, `/proc/mounts`, `docker inspect`).
**Severity:** P1. One user's writes take down every other user (the cross-user floor).

## What is true

**The quota is counted everywhere but gated only where the platform writes.**
`tinyassets/storage_accounting.py` keeps one pool per account. `reserve()` admits or refuses a write before it lands, and its callers are the platform write paths: wiki pages, uploads, run files, branch/version writes, workspaces, memory stores and the UI library. The tool jail (`universe_tools.py`), the engine tool server (`engine_mcp_server.py`) and the provider launch path (`providers/`) never call `storage_accounting`.

A jailed write lands in the universe directory, which is the `universe_files` store, a `_walk_bytes` of the directory. Nothing measures that store on a schedule. The only re-measure happens inside `reserve()`, for rows older than `FRESH_BEFORE_REFUSE_S`. So a universe can write without limit through bash or a provider CLI, and the overage first shows up on the owner's next platform write, which is then refused. The bytes are already on disk by then.

**The tool jail's disk limit is volume-wide, not per universe.**
`ToolLimits.min_free_disk_bytes` is 1 GiB and `min_free_inodes` is 4096. They are checked before launch and polled every 0.2 s by `_supervise`, which kills the jail with `disk_limit`. That stops the volume at 1 GiB free, but by then one universe has consumed everything above the floor. Every other universe's tool calls then refuse with "the shared disk is nearly full" until someone frees space. `RLIMIT_FSIZE` (32 MiB) limits the size of one file, not the total, so many small files pass it. The inode floor only fires at 4096 inodes left.

**The provider jail has no disk limit at all.**
`providers/provider_jail.py`:
- `default_view` binds the whole universe directory read-write.
- `jail_argv` sets no rlimits, no cgroup, no free-disk floor and no supervisor poll.

A provider CLI run is bounded only by its own turn.

**`/tmp` in both jails is an unsized tmpfs.**
`jail_argv` emits `--tmpfs /tmp` with no `--size`, so the kernel default applies (half of RAM). Those writes are memory, not disk. On the 2 GB box, a jail filling `/tmp` is memory pressure for the daemon, and the tool jail's process-tree RSS check does not see tmpfs pages.

**In production, the shared disk is the root disk.**
`/data` is the Docker volume `tinyassets-data` at `/var/lib/docker/volumes/tinyassets-data/_data`, on `/dev/vda1`: ext4, 49 GiB, 40% used on 2026-10-01, kernel 6.1. The same filesystem holds the OS, journald and Docker's images. A fill does more than refuse other users' writes: it can stop the host (no room to pull an image, write a log, or run SQLite WAL checkpoints for every user). Compare `2026-09-24-p0-disk-full-repair-uses-broad-prune.md`.

## Fix by construction (recommended)

Use **kernel project quotas, one project ID per account, on a dedicated data volume.** The account quota already exists as `usage_policy.limits_for(...).storage_bytes`. The kernel then refuses the write with `EDQUOT` for every process, jailed or not, platform or user, and enforces an inode limit too. Nothing has to poll or walk the tree.

1. Attach a DigitalOcean block volume, formatted ext4 with `-O project,quota` and mounted with `prjquota`, or XFS mounted with `prjquota`. Move `tinyassets-data` onto it.
   - This also takes user data off the root disk, so a fill can no longer stop the host.
   - Root ext4 cannot gain the `project` feature while mounted. That is why a new volume beats retrofitting `/dev/vda1`.
   - Cost: about $0.10/GiB/month, plus a single migration with a short downtime to copy `/data` and repoint the volume.
2. Give each account a project ID. When a universe directory is created, set that ID on it with inherit (`chattr -p <id> +P`, i.e. `FS_IOC_FSSETXATTR`), so every file a jail creates under it inherits the ID.
   - Setting project IDs and limits needs host `CAP_SYS_ADMIN`. The daemon runs as uid 1001, so a small root-side step does it: the container entrypoint before it drops privileges, or a host unit. It runs `setquota -P` from the ledger's per-account quota, and runs again when an account changes tier.
3. Map `EDQUOT` to the existing visible refusal (`storage_quota_exceeded`, with the inline upgrade link) in the jail result trailer.
4. Size `/tmp` in `jail_argv` with `--size` (bubblewrap 0.12 supports it), so jail scratch space is bounded RAM. A one-line change, independent of the rest.

Expected cost: about a day for steps 2–4 plus tests, and the host migration in step 1 recorded as a `docs/host-actions.md` row.

## Interim (in-repo, no host change; narrows the window, does not close it)

1. **Gate before launch.** The tool jail and the provider launch refuse to start when the owning account is at its quota, judged on a fresh measurement of its `universe_files` store (re-measure the account's stale rows the way `reserve` does with `_stale_pairs`/`_measure_many`, then compare. `usage()` alone only reads the ledger).
2. **Give the provider jail the tool jail's floor.** Check free bytes and inodes before launch, and add a supervisor poll that kills the run below the floor. Today it has neither.
3. **Kill on headroom crossed.** The tool jail already polls `statvfs` every 0.2 s, so it can kill when the volume's used bytes have grown since launch by more than the account's remaining headroom. Concurrent writers are attributed to this jail, which can over-kill; that errs toward refusing, which is the safe direction.
4. `--size` on `/tmp` (as in step 4 above).

What the interim leaves open: a single call can still overshoot by its own write rate times the poll interval. The volume-wide floor still lets one account consume the shared space down to 1 GiB before anything stops it. Only the project quota makes the per-account limit a property of the filesystem.

## Resolution

This concern is resolved when a jailed write past the owning account's quota fails with `EDQUOT`. The proof is a real-jail test that writes many small files and stops at the quota, with other universes' writes unaffected. Delete this file in the PR that lands it.

## Context

`backup.sh` creates a gzip archive with `_data/` as its only top-level root.
The prior restore path removed the live volume contents and extracted directly
into that directory. It could not prove an archive was usable before changing
production data, could lose dotfiles, and did not have a rollback point.

## Goals / Non-Goals

**Goals:**

- Prove the gzip archive is readable and contains only safe `_data` members
  before stopping mounts or changing the target volume.
- Extract into a unique sibling stage and use same-parent renames so a failed
  replacement move restores the original directory automatically.
- Serialize restores of the same resolved volume without serializing distinct
  volumes, and stop every running container using the volume before swapping it.
- Permit a caller to select a pre-downloaded GitHub Release full archive with
  `BACKUP_FILE`, without deleting that caller-owned file.

**Non-Goals:**

- Downloading from GitHub or changing its release retention policy.
- Starting or restarting any service after restore, or proving application
  health; those remain caller-owned actions.
- Deleting the pre-restore volume after a successful swap. It is retained for
  operator rollback until the caller's health verification succeeds.

## Decisions

### Validate member safety before extraction

A small embedded Python standard-library validator examines tar metadata before
`tar -tzf` and extraction. It rejects absolute or traversal names, any root
other than `_data`, a non-directory `_data` root member, all symbolic and hard
links, and device/FIFO members. Link targets are not accepted even when they
look contained in archive coordinates: stripping `_data` during extraction
changes those coordinates. This avoids brittle parsing of human-formatted
`tar -t` output and adds no dependency beyond the Python already required by
`backup.sh`.

### Stage and swap alongside the resolved volume

The script resolves the Docker mountpoint to an existing absolute `_data`
directory. `mktemp -d` creates the stage and old-volume names under that
directory's parent. The archive is extracted with `--strip-components=1` into
the stage, preserving dotfiles without creating `_data/_data`; the stage then
inherits the live volume root's ownership and mode so the directory swap does
not replace an accessible mountpoint with `mktemp`'s private `0700` directory.
The original is renamed to its retained sibling, then the staged directory is
renamed into the old pathname. If the second rename fails, the original is
renamed back immediately. All cleanup targets are checked to be generated
siblings before removal.

### Serialize only an individual volume

The script holds a non-blocking `flock` on a lock file in the resolved volume's
parent. A concurrent restore of the same volume fails without mutation, while
two volumes with distinct parents can restore concurrently.

### Keep remote and local archive ownership distinct

Normal restore retains the rclone listing/download flow but selects only
`tinyassets-data-*.tar.gz` entries and downloads into a unique temporary
directory. `BACKUP_FILE` is an absolute, readable, non-symlink regular file
containing a pre-downloaded full archive; it bypasses rclone and is never
removed. It cannot be combined with `--list` or `--timestamp`.

## Risks / Trade-offs

- **[Successful restore leaves disk space in use] -> Mitigation:** retain the
  old sibling intentionally until a separately started daemon and canary pass;
  document its exact cleanup and rollback commands.
- **[A stopped mount remains stopped] -> Mitigation:** this is intentional
  restore/start separation; the output identifies the next caller-owned start
  and verification actions.
- **[Archive validator and tar differ] -> Mitigation:** run both metadata
  validation and `tar -tzf`, then test a real `backup.sh` archive, corruption,
  unsafe members, rename failure, and concurrent isolated restores.

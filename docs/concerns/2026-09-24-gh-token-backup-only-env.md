# GH_TOKEN still reaches the daemon's container config through the shared env file

**Filed:** 2026-09-24
**Severity:** P2. The daemon *process* never holds it, because the entrypoint strips `GH_TOKEN`/`GITHUB_TOKEN`. The value still sits in the container config (`docker inspect`) and is inherited by `docker exec` children.
**Verified:** 2026-09-24 at PR #3966 head `7cd52795`. Found by the Tier 2 review, round 2.

## The finding

`GH_TOKEN` is the off-host backup upload token. `deploy/backup.sh` uses it to ship GitHub release assets. It lives in `/etc/tinyassets/env`. Two consumers read that file:
- `tinyassets-backup.service`, which runs as root on the host;
- the daemon container, through compose `env_file`.

The goal is for the backup unit alone to read it.

## Why the first attempt was withdrawn

PR #3966 at `7cd52795` moved the token into a new `/etc/tinyassets/backup.env` and pointed the backup unit at it with a drop-in. The move called `install-tinyassets-env.sh set` with `TINYASSETS_ENV_OWNER=root:root`. On a missing target file, the helper's `ensure_env_file` runs `chown <owner>` and `chmod 750` on the target's **directory** (`deploy/install-tinyassets-env.sh:341-345`), even when that directory already exists. That directory is `/etc/tinyassets`, so it would become `root:root 750`.

That locks the `tinyassets` user out of `/etc/tinyassets/env`. The next deploy's canary-bearer sync would then fail `assert_readable` with `ENV-UNREADABLE`, and the systemd unit's `ExecStartPre=test -r` would fail with it. The move was removed from #3966 under the two-round stop. #3966 keeps only the entrypoint strip.

**Test gap:** the retire-script test ran the move with `TINYASSETS_BACKUP_ENV_OWNER=""`. That skipped every `chown`/`chmod`, so the directory takeover was invisible. A fix needs a test that:
- runs the helper against a pre-existing directory with a real owner/group pair (or asserts the directory's mode and owner are unchanged);
- fails on the old code.

## Resolving this

Move `GH_TOKEN` into a backup-only file without touching `/etc/tinyassets` ownership. Either of these works:
- a file outside `/etc/tinyassets`;
- the helper made to never chown or chmod an existing directory.

Then:
1. Point `tinyassets-backup.service` at that file (`EnvironmentFile=-...`), shipped through `install-host-services`.
2. Scrub `GH_TOKEN` from `/etc/tinyassets/env` only after the backup unit reads the new file.
3. Prove the result live:
   - a backup run uploads to GitHub releases;
   - `docker inspect tinyassets-daemon` shows no `GH_TOKEN` after the next container recreate.

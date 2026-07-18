# TinyAssets — state restore runbook

Self-host migration Row J per
`docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md`.

Backups are nightly snapshots of the `tinyassets-data` named Docker
volume, uploaded to Hetzner Storage Box. This runbook restores from
a backup onto a fresh (or existing) Hetzner box.

**When to use:**
- Full data loss (box destroyed, disk corrupted, state file deleted).
- Rollback after a bad migration / upgrade.
- Restore-test drill (run quarterly per SUCCESSION.md §8 launch-readiness).

**Estimated time:** 5-15 min depending on archive size.

---

## Preconditions

- A running (or freshly provisioned per HETZNER-DEPLOY.md) Hetzner
  box with Docker + the tinyassets-daemon unit installed but STOPPED.
- `/etc/tinyassets/env` populated with `STORAGEBOX_HOST` /
  `STORAGEBOX_USER` / `STORAGEBOX_PASS` (same creds the backup job uses).
- `rclone` installed (bootstrap handles this).

## Step 1 — Stop the daemon (~10s)

```bash
sudo systemctl stop tinyassets-daemon
# Watchdog stays running — harmless (it'll see the outage + log reds,
# but won't restart because we're about to replace state).
```

## Step 2 — List available backups (~5s)

```bash
# Source the env so rclone picks up the config.
set -a; . /etc/tinyassets/env; set +a

# Write the ephemeral rclone config (same shape as backup.sh).
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf <<EOF
[storagebox]
type = sftp
host = ${STORAGEBOX_HOST}
user = ${STORAGEBOX_USER}
pass = $(rclone obscure "${STORAGEBOX_PASS}")
port = 22
EOF
chmod 600 ~/.config/rclone/rclone.conf

# List. Most recent first.
rclone lsl storagebox:tinyassets-backups/ | sort -k2,3 -r | head -20
```

Expect tarballs named `tinyassets-data-YYYY-MM-DDTHH-MM-SSZ.tar.zst`.
Pick the one you want (usually the most recent).

## Step 3 — Pull it down (~1-5 min depending on size)

```bash
BACKUP="tinyassets-data-2026-04-21T03-00-00Z.tar.zst"  # replace
rclone copy "storagebox:tinyassets-backups/${BACKUP}" /tmp/
ls -lh "/tmp/${BACKUP}"
```

## Step 4 — Wipe current volume (DESTRUCTIVE — only after step 1)

```bash
# Defensive: daemon must be stopped. Verify.
sudo systemctl is-active tinyassets-daemon
# Expected: inactive (or failed — OK, just not running).

# Remove the volume. Docker refuses if any container mounts it —
# that's why we stopped the daemon first.
sudo docker volume rm tinyassets-data

# Re-create the named volume (empty) so the restore has a target.
sudo docker volume create tinyassets-data
```

## Step 5 — Extract into the new volume (~30s-2min)

```bash
VOLUME_DIR="$(sudo docker volume inspect --format '{{ .Mountpoint }}' tinyassets-data)"
echo "restoring into ${VOLUME_DIR}"

# Tar contains `_data/...` entries (preserves the original parent
# dirname). Extract into the volume's parent so paths line up.
sudo tar --zstd -xf "/tmp/${BACKUP}" -C "$(dirname "${VOLUME_DIR}")"

# Sanity: verify some expected files exist.
sudo ls -la "${VOLUME_DIR}" | head
```

Expect to see the daemon's state files: `.auth.db`, `.node_eval.db`,
`.tinyassets.db`, per-universe subdirs, etc. Older backups may still contain
`.author_server.db`; current code renames it to `.tinyassets.db` on first boot.

## Step 6 — Start the daemon + verify (~30s)

```bash
sudo systemctl start tinyassets-daemon
sudo systemctl status tinyassets-daemon
# Watch for: daemon-1 | Starting TinyAssets Server on 0.0.0.0:8001

# Verify via canary.
python3 /opt/tinyassets/scripts/mcp_public_canary.py \
    --url https://tinyassets.io/mcp --verbose
```

Exit 0 + `[canary] OK` = restore successful.

## Step 7 — Clean up (~5s)

```bash
rm -f "/tmp/${BACKUP}"
rm -f ~/.config/rclone/rclone.conf
```

---

## Recovery-test drill (quarterly)

Per SUCCESSION.md §8 launch-readiness: verify the restore path works
before an incident forces it.

1. Provision a second Hetzner CX22 as a staging box (not the prod box).
2. Run `hetzner-bootstrap.sh` on it.
3. Copy `/etc/tinyassets/env` from prod (READ-ONLY: copy then edit;
   consider making the staging box point at a separate testnet Supabase).
4. Run steps 2-6 above.
5. Verify canary green.
6. **Destroy** the staging box when done (€5.83/mo is real money).

Log the drill date + result in SUCCESSION.md acceptance criteria.

---

## Common failure modes

- **Backup tarball corrupted.** `tar --zstd -t` to list contents before
  extracting; if `tar: Error is not recoverable`, the archive is bad.
  Try a different backup (older). If multiple backups are bad, the
  backup.sh pipeline itself is broken — investigate before relying on
  any untested backup.
- **rclone auth failure.** `rclone lsl storagebox:` hangs or returns
  `Permission denied`. Re-check `STORAGEBOX_USER` + `STORAGEBOX_PASS` in
  `/etc/tinyassets/env`. Hetzner Storage Box SSH creds can be rotated at
  the Hetzner console if compromised.
- **Volume already in use.** `docker volume rm tinyassets-data` refuses
  because a container mounts it. Run `sudo docker ps -a | grep
  tinyassets-data` to find the container, stop + remove it, retry.
- **Disk full.** `/tmp` needs ~2x archive size free. If low, extract to
  `/var/lib/docker/volumes/tinyassets-data/_data` directly and skip `/tmp`:
  `sudo tar --zstd -xf - -C "$(dirname "${VOLUME_DIR}")" < <(rclone cat storagebox:tinyassets-backups/${BACKUP})`.
- **Post-restore canary red but daemon up.** State from an incompatible
  schema version. Check daemon logs for migration errors; may need to
  restore an older backup that matches the current daemon version OR
  re-deploy a matching daemon image (`TINYASSETS_IMAGE` in `/etc/tinyassets/env`).

---

## Credential vault after a restore (intended fail-closed)

`backup-restore.sh` advances the vault's anti-rollback guard
(`scripts/vault_restore_bump.py`, run through the daemon image against the
`tinyassets-vault-guard` volume) after every restore. From that moment every
stored universe/founder credential raises `REAUTHORIZATION_REQUIRED` until an
operator runs the authenticated recovery reset below; the reset erases the
uncertain store, after which each founder reconnects. **This is the intended
contract, not a failure:**
a restored one-use refresh token may already have been redeemed at the
provider, so serving restored credential state would be dishonest. The same
applies to a failed vault mutation commit at runtime — the whole store fails
closed into re-authorization rather than guessing.

Do NOT restore or delete the `tinyassets-vault-guard` volume itself: it is
an independent recovery domain by design. If the bump step warned/failed,
rerun the root one-shot `docker run --entrypoint /opt/venv/bin/python ...
/app/scripts/vault_restore_bump.py` command from `backup-restore.sh`.

### Operator re-deposit path

1. Stop the daemon. Leave the guard advanced; do not copy pre-restore
   ciphertext, delete the guard, or retry reads until one happens to work.
2. From a root/operator shell, create a one-shot recovery token and run the
   recovery command against both persistent volumes (replace the image value if
   the daemon container is not present):

   ```bash
   DAEMON_IMAGE="$(sudo docker inspect tinyassets-daemon --format '{{.Config.Image}}')"
   export TINYASSETS_VAULT_RECOVERY_TOKEN="$(openssl rand -hex 32)"
   sudo docker run --rm \
     --entrypoint /opt/venv/bin/python \
     -e TINYASSETS_DATA_DIR=/data \
     -e TINYASSETS_VAULT_ROLLBACK_GUARD=/vault-guard \
     -e TINYASSETS_VAULT_RECOVERY_TOKEN \
     -v tinyassets-data:/data \
     -v tinyassets-vault-guard:/vault-guard \
     "${DAEMON_IMAGE}" /app/scripts/vault_restore_recover.py
   unset TINYASSETS_VAULT_RECOVERY_TOKEN
   ```

   The command is deliberately unavailable through MCP, workers, and normal
   `VaultBroker` construction. It accepts only a guard-ahead restored store,
   erases every uncertain credential and job grant, and atomically establishes
   the guard's new clean epoch; a current store or wrong token fails closed.
3. Restart the daemon. For every affected universe, have its founder repeat the
   same authenticated
   deposit flow that originally created each binding. Engine API keys are
   re-entered with `universe action=set_engine` and
   `inputs_json={"engine_source":"byo_api_key","service":"…","api_key":"…"}`.
   Connected GitHub/provider credentials are reconnected through their normal
   founder-authenticated connection or OAuth flow. Never paste credentials into
   branch bindings, run inputs, config files, logs, or the ledger.
4. Repeat per universe and per provider/destination. A deposit in universe A
   does not and must not repair universe B.
5. Verify each replacement through the normal status/connection surface, then
   run one clean universe-scoped operation. `REAUTHORIZATION_REQUIRED` should
   be replaced by `NOT_FOUND` until that binding is re-deposited; any remaining
   failure means another binding still needs its founder to reconnect.

The restored records and pre-restore grants are intentionally erased, never made
usable again. Re-deposit writes fresh provider state under new opaque bindings
while preserving the anti-rollback evidence.

**Grant GC (S3 seam):** expired `vault_job_grants` rows are inert (resolve
fails `EXPIRED`) but need `revoke_grant` on job completion for tidy storage.
The daemon-side completion hook lands with the S3 executor merge — until
then expired rows simply accumulate; there is no dual cleanup path.

## What this runbook does NOT cover

- **Partial restore** (one universe's state, not whole-volume). Extract
  the tar to a scratch dir, copy the specific subdir into the live
  volume. No tooling for this yet; add if incidents surface.
- **Point-in-time recovery** (restore to a specific timestamp within a
  day). Backup is nightly snapshots only. Sub-day recovery needs WAL
  shipping or similar; not in current scope.
- **Cross-region migration** (move the daemon from Hetzner to another
  provider). Restore works identically anywhere Docker runs; the
  Cloudflare tunnel just needs to point at the new box's cloudflared
  instance.

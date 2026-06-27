# Audit: /etc/tinyassets/env mode-flip root cause

**Date:** 2026-04-25
**Auditor:** dev (automated audit)
**Scope:** Every path that creates, writes, chmods, or reads `/etc/tinyassets/env` across `deploy/`, `.github/workflows/`, and systemd units.

---

## Background

STATUS Concern [2026-04-22]: `/etc/tinyassets/env` mode flipped to unreadable. The 2026-04-21 P0 outage was already traced to `sed -i` dropping group ownership; mitigations were added. This audit checks whether all write paths are covered and whether a new class of mode-flip is possible.

---

## Every path that touches /etc/tinyassets/env

### A. bootstrap — `deploy/hetzner-bootstrap.sh` lines 191–203

**Creates the file if absent:**

```bash
mkdir -p "${ENV_DIR}"                          # /etc/tinyassets
chown "root:${TINYASSETS_USER}" "${ENV_DIR}"     # dir: root:workflow
chmod 750 "${ENV_DIR}"                         # dir: rwxr-x---

if [[ ! -f "${ENV_DIR}/env" ]]; then
    cp "${TINYASSETS_HOME}/deploy/workflow-env.template" "${ENV_DIR}/env"
    chown "root:${TINYASSETS_USER}" "${ENV_DIR}/env"
    chmod 640 "${ENV_DIR}/env"                 # file: rw-r-----
fi
```

**Assessment:** Correct — `cp` preserves a new inode, then explicit `chown + chmod` sets the right mode. **Only fires when the file is absent** (idempotent guard). No mode-flip risk here.

---

### B. deploy pipeline — `.github/workflows/deploy-prod.yml`

Three `sudo sed -i` invocations, each followed by explicit `chown + chmod`:

| Step | sed -i target | Restore sequence |
|------|--------------|-----------------|
| Scrub legacy WIKI_PATH (line 134) | `/etc/tinyassets/env` | `chown root:workflow` + `chmod 640` + readability assert |
| Pin new image tag (lines 145–148) | `/etc/tinyassets/env` | `chown root:workflow` + `chmod 640` + readability assert |
| Rollback: restore previous tag (lines 230–233) | `/etc/tinyassets/env` | `chown root:workflow` + `chmod 640` + readability assert |

**`sed -i` behavior (root cause of the 2026-04-21 P0):** `sed -i` writes to a temp file then `rename(2)`s it over the target. The rename preserves the directory slot but creates a new inode with default ownership (root:root) and umask-derived mode (typically 0600). Any error between `sed -i` and the subsequent `chown`/`chmod` leaves the file in the broken 0600 state.

**Assessment:** Mitigations are in place (`chown + chmod + readability assert`), but they are three sequential SSH sub-commands in a heredoc. A transient SSH error or `set -e` fault between them could abort mid-sequence. The inline `sudo -u workflow test -r` check exits the step on failure, which is correct.

---

### C. p0-outage-triage — `.github/workflows/p0-outage-triage.yml` lines 155–159, 204–207

Two repair paths, both run `chown + chmod + readability assert` without `sed -i`:

```bash
# repair (line 155):
sudo chown root:workflow /etc/tinyassets/env
sudo chmod 640 /etc/tinyassets/env
sudo -u workflow test -r /etc/tinyassets/env
sudo ls -l /etc/tinyassets/env

# image fallback (line 204):
sudo sed -i 's|^TINYASSETS_IMAGE=.*|TINYASSETS_IMAGE=ghcr.io/.../latest|' /etc/tinyassets/env
sudo chown root:workflow /etc/tinyassets/env
sudo chmod 640 /etc/tinyassets/env
sudo -u workflow test -r /etc/tinyassets/env
```

**Assessment:** Same `sed -i` risk as B. The repair path (lines 155–159) is safe since it's a pure `chown + chmod` with no write. The image-fallback path has the same transient-abort risk.

---

### D. systemd unit — `deploy/tinyassets-daemon.service`

```ini
User=workflow
EnvironmentFile=/etc/tinyassets/env
ExecStartPre=/bin/sh -c 'test -r /etc/tinyassets/env || { echo "ENV-UNREADABLE..." >&2; exit 1; }'
ReadWritePaths=/var/lib/docker /run/docker.sock /etc/tinyassets
```

**Assessment:** The `ExecStartPre` readability check is correct and surfaces the problem via journald. `ReadWritePaths=/etc/tinyassets` allows the workflow user to write to the *directory*, but the individual `env` file is `root:workflow 640` so workflow can read but not write. The systemd unit itself never modifies the file's mode.

---

### E. docker-entrypoint.sh

Reads sentinel env vars but never writes or chmods `/etc/tinyassets/env`. No risk.

---

### F. compose.yml

References `/etc/tinyassets/env` via `env_file:` — read-only from compose's perspective. Docker reads it as the unprivileged container runtime user (root inside the container), which succeeds regardless of the file's mode on the host because compose reads it before exec. However, if compose is run as the `workflow` user (via the systemd unit) and the file is `0600 root:root`, compose itself will fail to open the file, silently passing an empty env to the container.

---

## Suspected root causes

### RC-1 (confirmed): `sed -i` clobbers group ownership + perms — 2026-04-21 P0

`sed -i` does a `rename(2)` of a temp file written as root. The new inode inherits `root:root` and umask (typically `0600`). Any path using `sed -i /etc/tinyassets/env` that aborts before `chown + chmod` leaves the file unreadable by `workflow`.

**Triggered when:**
- A `sudo sed -i` completes but the next command (`chown`) is interrupted by: SSH timeout, network drop, `set -e` triggered by a preceding command exit-code, or the `sed` process itself failing.

### RC-2 (hypothetical): Out-of-band `sudo sed -i` from SSH session

A host manually running `sudo sed -i ... /etc/tinyassets/env` via SSH (e.g., to update a secret) and forgetting to restore `chown + chmod`. There is no guard against this.

### RC-3 (hypothetical): compose run with wrong user context

If `docker compose` is run as `root` (e.g., during manual debugging via `sudo docker compose up`) rather than via the systemd unit, Docker's `env_file` processing runs as root and reads the file fine — but the file's mode on disk doesn't change. However, if a `sudo docker compose config` or similar command ever *writes* the env file as a side effect (unlikely with standard compose), it could produce a root:root file.

### RC-4 (hypothetical): Future `sed -i` added without chown/chmod restore

Any future script, runbook step, or GitHub Actions step that does `sudo sed -i /etc/tinyassets/env` without the restore trio is a latent RC-1. No structural prevention exists today.

---

## Proposed fixes

### Fix A (recommended): Replace `sed -i` with an atomic write-and-chmod helper

Instead of `sed -i + chown + chmod` (three steps, abort-prone), use a single atomic operation:

```bash
# Replace TINYASSETS_IMAGE in /etc/tinyassets/env atomically.
new_content=$(sudo sed "s|^TINYASSETS_IMAGE=.*|TINYASSETS_IMAGE=${NEW_IMAGE}|" /etc/tinyassets/env)
printf '%s\n' "${new_content}" | sudo install -m 640 -o root -g workflow /dev/stdin /etc/tinyassets/env
```

`install` writes a new file at the target path with the specified owner/perms atomically. No intermediate state with wrong perms. Applies to all three `sed -i` sites in `deploy-prod.yml` and the one in `p0-outage-triage.yml`.

### Fix B (defense-in-depth): Add a pre-deploy invariant check step

Add a dedicated CI step that runs BEFORE any `sed -i` that asserts and restores the file's mode:

```yaml
- name: Assert + restore /etc/tinyassets/env mode
  run: |
    ssh ... "sudo chown root:workflow /etc/tinyassets/env && sudo chmod 640 /etc/tinyassets/env"
```

Running this first means even if a subsequent `sed -i` aborts mid-sequence, a re-run of the workflow starts with a known-good state.

### Fix C (runbook): Document the restore trio for manual SSH sessions

Add to `deploy/HETZNER-DEPLOY.md` (or a new `deploy/OPS-RUNBOOK.md`): "Any manual edit to `/etc/tinyassets/env` must be followed by `sudo chown root:workflow /etc/tinyassets/env && sudo chmod 640 /etc/tinyassets/env`." This addresses RC-2.

### Fix D (optional, structural): Replace direct file with a wrapper script

Replace `EnvironmentFile=/etc/tinyassets/env` in the systemd unit with an `ExecStartPre` that reads secrets from the vault and writes to a tmpfs path owned by `workflow`. This removes the persistent on-disk file entirely and eliminates the mode-flip class. Higher lift — appropriate only if the vault integration lands.

---

## Recommended action for host

**Immediate:** Verify Fix B is in place (pre-deploy mode assert). The existing post-`sed` assert is correct but fires too late if sed itself fails.

**Short-term (next deploy):** Convert the three `sed -i` sites in `deploy-prod.yml` and one in `p0-outage-triage.yml` to use `install -m 640 -o root -g workflow` (Fix A). This closes RC-1 permanently.

**Runbook:** Add the manual-edit warning to `deploy/HETZNER-DEPLOY.md` (Fix C). Low cost, prevents RC-2.

---

## Files audited

| File | Verdict |
|------|---------|
| `deploy/hetzner-bootstrap.sh` | Safe — `cp` + explicit `chown + chmod`, only runs once |
| `deploy/tinyassets-daemon.service` | Safe — `ExecStartPre` readability check; unit never writes the file |
| `deploy/compose.yml` | Read-only reference; no write risk |
| `deploy/docker-entrypoint.sh` | Read-only; no write risk |
| `deploy/workflow-env.template` | Template only; never touches `/etc/tinyassets/env` directly |
| `.github/workflows/deploy-prod.yml` | **RC-1 present** at 3 `sed -i` sites; mitigated but not eliminated |
| `.github/workflows/p0-outage-triage.yml` | **RC-1 present** at 1 `sed -i` site; mitigated but not eliminated |

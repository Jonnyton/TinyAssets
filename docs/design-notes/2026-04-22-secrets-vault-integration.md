---
status: shipped
shipped_date: 2026-04-22
---

# Secrets vault integration

**Status:** Tooling landed (task #7, 2026-04-22). Host migration pending.

**Problem (HD-2 in `docs/ops/host-off-resilience-audit.md`):** local
secrets live in plaintext at `$HOME/workflow-secrets.env`. A stolen or
compromised laptop walks every key we depend on: Cloudflare API tokens,
DigitalOcean management token, Hetzner fallback credentials, OpenAI
key. The plaintext file has no protection beyond the OS user's file
permissions.

**Goal:** replace the plaintext file with a password-manager-backed
vault. Constraint: must survive the host landing on a fresh laptop with
nothing but a master password.

## Vendor comparison

| Vendor | CLI | Cost | Cross-device | Fresh-laptop via master password? | Lock-in risk |
|--------|-----|------|--------------|-----------------------------------|--------------|
| **1Password** | `op` | $3/mo personal | Yes (iCloud-/Dropbox-free sync over 1Password's own infra) | Yes — master password + Secret Key | Medium — clean export, but Secret Key is vendor-specific |
| **Bitwarden** | `bw` | Free tier works | Yes (self-hostable option) | Yes — master password alone on Bitwarden-hosted; self-host needs server URL | Low — OSS, full JSON export |
| **macOS Keychain** | `security` | Free | iCloud-only | No — requires iCloud account bootstrap; weak fresh-laptop story | Low (native) but non-portable |
| **Windows Credential Manager** | native | Free | None | No — no cross-device sync at all | High for multi-machine ops |

**Recommendation: 1Password as the default.** Best UX, clean `op` CLI
interface that's scriptable, and the Secret Key + master password
combination is a real fresh-laptop bootstrap story. The $3/mo
subscription is irrelevant next to the cost of a key compromise.

**Bitwarden is the documented alternative** for operators who prefer OSS
or want the free tier. The loader + migrator support it symmetrically.

**Native keychains rejected** because the fresh-laptop constraint
requires cross-device sync, and iCloud/Microsoft-account coupling
changes the trust model in ways that defeat the stolen-laptop threat
model we're trying to close.

## Tool surface

| File | Role |
|------|------|
| `scripts/secrets_keys.txt` | Canonical list of LOCAL keys (single source of truth), including `GH_TOKEN` for local/sandbox GitHub push flows. |
| `scripts/load_secrets.sh` | Bash/POSIX loader. Pulls keys from vault into the calling shell via `source` or `--emit-exports`. |
| `scripts/load_secrets.ps1` | PowerShell mirror. Dot-source to export. |
| `scripts/migrate_secrets_to_vault.py` | One-shot migrator — reads `$HOME/workflow-secrets.env`, writes each key into the chosen vault. Idempotent. |

**Vendor selection:** `WORKFLOW_SECRETS_VENDOR=1password|bitwarden|plaintext`
(default `1password`). The `plaintext` value is the migration-period
opt-out; it reads `$HOME/workflow-secrets.env` directly. To be removed
once the host confirms cutover works.

**Vault path convention:**
- **1Password:** vault = `workflow` (override with `WORKFLOW_SECRETS_VAULT`); item name = the KEY (e.g. `CLOUDFLARE_API_TOKEN`); field = `password`.
- **Bitwarden:** item name = the KEY; login.password = the value.

## Fresh-laptop bootstrap runbook

1. Install the vendor CLI:
   - 1Password: https://developer.1password.com/docs/cli/get-started/
   - Bitwarden: https://bitwarden.com/help/cli/
2. Sign in interactively:
   - 1Password: `eval $(op signin)`
   - Bitwarden: `bw login && export BW_SESSION=$(bw unlock --raw)`
3. Clone the Workflow repo.
4. Load secrets into the current shell:
   ```bash
   set -a; source scripts/load_secrets.sh; set +a
   ```
   (or dot-source the `.ps1` on Windows)
5. Verify: `echo "$CLOUDFLARE_API_TOKEN" | head -c 8` should print the first 8 chars of the token.

No plaintext file required. No OS-keychain coupling. Nothing on the
disk but the vault CLI's encrypted local cache.

## Migration runbook (one-shot, host runs once)

1. Stand up the vault per steps 1–2 above (on any machine that has the
   plaintext file).
2. Dry-run the migration to see what would happen:
   ```bash
   python scripts/migrate_secrets_to_vault.py --vendor 1password --dry-run
   ```
3. Run for real:
   ```bash
   python scripts/migrate_secrets_to_vault.py --vendor 1password
   ```
4. Verify end-to-end by opening a fresh shell and running:
   ```bash
   unset $(grep -v '^#' scripts/secrets_keys.txt | awk '{print $1}')
   set -a; source scripts/load_secrets.sh; set +a
   # Check each key came through:
   grep -v '^#' scripts/secrets_keys.txt | awk '{print $1}' \
     | xargs -I{} sh -c 'echo {}=${!1:0:6}...' _
   ```
5. Once verified, delete the plaintext file:
   ```bash
   shred -u ~/workflow-secrets.env  # Linux
   # macOS: rm -P; Windows: del + clear recycle bin
   ```
6. Set `WORKFLOW_SECRETS_VENDOR=1password` in your shell profile
   (`~/.bashrc`, `~/.zshrc`, or PowerShell `$PROFILE`) so future
   sessions default to the vault.

## Opt-out / fallback semantics

During the migration period, `WORKFLOW_SECRETS_VENDOR=plaintext`
explicitly selects the old file-based loader. The loader warns every
invocation: "plaintext mode is migration-period only."

`WORKFLOW_SECRETS_PLAINTEXT_FALLBACK=1` allows silent fallback when a
specified vendor CLI is unavailable — **removed after cutover**. Do not
use this in production sessions once the vault works.

## Why this closes HD-2

- Laptop theft → attacker gets the vault CLI's encrypted local cache,
  which is useless without the master password (and Secret Key for
  1Password).
- Fresh-laptop bootstrap → attacker needs master password too, which
  lives only in the host's head / hardware MFA device.
- Key rotation → one vault edit propagates to every shell that re-runs
  `load_secrets`, vs. today's "edit the .env, copy to every other
  machine" drift hazard.

## Non-scope

- **GitHub Actions secrets are unchanged.** CI uses `secrets.CLOUDFLARE_API_TOKEN` etc. directly from the GH repo settings. The local `GH_TOKEN` vault item is for operator/sandbox push sessions; GitHub Actions' built-in `GITHUB_TOKEN` stays CI-side and is not listed in `scripts/secrets_keys.txt`.
- **Daemon-side `/etc/workflow/env`** on the Droplet is also unchanged.
  That's a systemd `EnvironmentFile=` mount, not a developer laptop.
- **Shared-team vault** — the current design is per-operator. If/when
  the team grows beyond the single-host model, a shared 1Password
  vault is the same tool with a `--vault` flag pointed at a team
  vault; no new tooling needed.

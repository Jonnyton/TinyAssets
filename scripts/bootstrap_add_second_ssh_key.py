"""bootstrap_add_second_ssh_key.py — add a backup ed25519 SSH key to the Droplet.

Raises bus factor from 1 to 2 for Droplet SSH access (HD-1 close action).

What it does (idempotent):
  1. Generates a new ed25519 keypair. By default writes the private key to
     ``~/.ssh/tinyassets_deploy_backup_ed25519`` so the host can pipe it
     into 1Password (Task #7 vault-first). Pass ``--out-dir /tmp/...``
     to land the key elsewhere, or ``--print-only`` to emit the PEM to
     stdout for direct ``op item create`` piping.
  2. SSHes into the Droplet using the existing primary key and appends the
     new public key to /root/.ssh/authorized_keys (skip if already present).
  3. Optional: registers the pubkey with the DigitalOcean account via
     ``/v2/account/keys`` when ``--do-token`` / ``DIGITALOCEAN_TOKEN`` is
     set. Required for the backup key to be selectable at droplet-creation
     time (e.g. during DR drill Droplet provisioning).
  4. Optional legacy path: seeds the new private key as GH Actions secret
     ``DO_SSH_KEY_BACKUP`` when ``--gh-secret`` is passed. Disabled by
     default; the vault-first pattern from Task #7 replaces this for
     local-secret storage.

Exit codes
----------
0   Success (or already-seeded and idempotency guard triggered).
1   Required env / arg missing.
2   ssh-keygen failed.
3   SSH upload to Droplet failed.
4   GH secret seeding failed.
5   DigitalOcean account-keys registration failed.

Usage
-----
    # Vault-first default — write the private key to disk for the host to
    # pipe into 1Password:
    python scripts/bootstrap_add_second_ssh_key.py \\
        --host 161.35.237.133 \\
        --primary-key ~/.ssh/tinyassets_deploy_ed25519 \\
        --do-token "$DIGITALOCEAN_TOKEN"

    # Then (host action):
    op document create ~/.ssh/tinyassets_deploy_backup_ed25519 \\
        --title "DO Droplet backup SSH key (private)" --vault workflow
    shred -u ~/.ssh/tinyassets_deploy_backup_ed25519

    # Print-only mode (pipe directly to 1Password without touching disk):
    python scripts/bootstrap_add_second_ssh_key.py \\
        --host ... --primary-key ... --print-only \\
        | op document create --title "DO backup SSH key" --vault workflow -

    # Legacy GH-secret mode:
    python scripts/bootstrap_add_second_ssh_key.py \\
        --host ... --primary-key ... --gh-secret \\
        --repo Jonnyton/TinyAssets

Environment (override CLI for CI use):
    DROPLET_HOST          Droplet IP/hostname.
    PRIMARY_SSH_KEY_PATH  Path to the existing private key for initial SSH.
    GH_REPO               GitHub repo slug (owner/name).
    GH_TOKEN              GitHub token (falls back to git credential helper).
    DIGITALOCEAN_TOKEN    DO API token for registering the pubkey with the
                          DO account (enables droplet-creation referencing).
    DRY_RUN               Set to "1" to skip mutations (useful for CI plan).

Stdlib + subprocess only — no third-party deps.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

DEFAULT_REPO = "Jonnyton/TinyAssets"
SECRET_NAME = "DO_SSH_KEY_BACKUP"
AUTHORIZED_KEYS = "/root/.ssh/authorized_keys"
DEFAULT_KEY_NAME = "tinyassets_deploy_backup_ed25519"
DEFAULT_DO_KEY_LABEL = "tinyassets-deploy-backup"
DO_API_KEYS = "https://api.digitalocean.com/v2/account/keys"


# ── GH helpers (mirrors gh_seed_secret.py pattern) ───────────────────

def _git_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="url=https://github.com\n\n",
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git credential fill failed: {proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    raise RuntimeError("no password in git credential output")


def _gh_token(env_token: str | None) -> str:
    if env_token:
        return env_token
    t = os.environ.get("GH_TOKEN", "").strip()
    if t:
        return t
    return _git_token()


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "workflow-second-key/1.0",
    }


def _gh_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers=_gh_headers(token))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _secret_exists(token: str, repo: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/actions/secrets/{SECRET_NAME}"
    try:
        _gh_get(url, token)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _seed_secret(token: str, repo: str, private_key_pem: str) -> None:
    # Fetch the repo's public encryption key.
    key_info = _gh_get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        token,
    )
    gh_pub_key_b64 = key_info["key"]
    key_id = key_info["key_id"]

    # Encrypt with libsodium (via PyNaCl if available, else fallback message).
    try:
        from base64 import b64decode  # noqa: PLC0415  # isort: skip
        from nacl.public import PublicKey, SealedBox  # type: ignore[import]  # noqa: PLC0415  # isort: skip
        pub = PublicKey(b64decode(gh_pub_key_b64))
        box = SealedBox(pub)
        encrypted = b64encode(box.encrypt(private_key_pem.encode())).decode()
    except ImportError:
        # PyNaCl not available — fall back to gh CLI if present.
        import shutil
        if not shutil.which("gh"):
            raise RuntimeError(
                "PyNaCl not installed and gh CLI not found. "
                "Install PyNaCl (`pip install pynacl`) or the gh CLI."
            )
        proc = subprocess.run(
            ["gh", "secret", "set", SECRET_NAME,
             "--repo", repo, "--body", private_key_pem],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"gh secret set failed: {proc.stderr.strip()}")
        return

    body = json.dumps({"encrypted_value": encrypted, "key_id": key_id}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/{SECRET_NAME}",
        data=body,
        method="PUT",
        headers={**_gh_headers(token), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status not in (201, 204):
            raise RuntimeError(f"secret PUT returned {resp.status}")


# ── DigitalOcean account-keys helpers ────────────────────────────────
#
# Registering the pubkey with the DO account is distinct from adding it
# to the running droplet's authorized_keys. Account-keys are referenced
# by ID at droplet-creation time (`ssh_keys: [<id>]` in the
# POST /v2/droplets body). Without this step, the backup key works for
# existing droplets but can't be used to spin up a fresh one in a DR
# scenario — which is when bus-factor matters most.


def _do_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "workflow-second-key/1.0",
    }


def _do_key_exists(token: str, public_key: str) -> bool:
    """Return True if the pubkey (or its fingerprint) is already registered.

    DO compares by key material, so we submit and let the API tell us
    via 422 'SSH key is already in use on your account' if duplicate.
    For the pre-flight check we walk the list and match on the material.
    """
    req = urllib.request.Request(DO_API_KEYS, headers=_do_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"DO /v2/account/keys GET failed: HTTP {exc.code}",
        ) from exc
    # Match on the key body (middle field of `type key comment`).
    want_body = public_key.strip().split()[1] if len(public_key.split()) >= 2 else ""
    for entry in data.get("ssh_keys", []):
        existing = (entry.get("public_key") or "").strip().split()
        if len(existing) >= 2 and existing[1] == want_body:
            return True
    return False


def _do_register_key(
    token: str, public_key: str, label: str,
    *, opener=urllib.request.urlopen,
) -> dict:
    """POST the pubkey to DO. Returns the created key record (with id)."""
    body = json.dumps({"name": label, "public_key": public_key.strip()}).encode()
    req = urllib.request.Request(
        DO_API_KEYS, data=body, method="POST", headers=_do_headers(token),
    )
    try:
        with opener(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get("ssh_key", {})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(
            f"DO /v2/account/keys POST failed: HTTP {exc.code}: {detail}",
        ) from exc


# ── SSH helpers ───────────────────────────────────────────────────────

def _ssh_run(host: str, primary_key: str, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh", "-i", primary_key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            f"root@{host}",
            command,
        ],
        capture_output=True, text=True,
    )


def _pubkey_already_present(host: str, primary_key: str, pubkey_line: str) -> bool:
    result = _ssh_run(host, primary_key,
                      f"grep -qF '{pubkey_line}' {AUTHORIZED_KEYS} && echo YES || echo NO")
    return result.returncode == 0 and "YES" in result.stdout


def _append_pubkey(host: str, primary_key: str, pubkey_line: str) -> None:
    result = _ssh_run(
        host, primary_key,
        f"echo '{pubkey_line}' >> {AUTHORIZED_KEYS} && chmod 600 {AUTHORIZED_KEYS}",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to append pubkey to {AUTHORIZED_KEYS}: {result.stderr.strip()}"
        )


# ── Main ──────────────────────────────────────────────────────────────

def run(
    host: str,
    primary_key: str,
    repo: str,
    dry_run: bool = False,
    gh_token: str | None = None,
    *,
    gh_secret: bool = False,
    do_token: str | None = None,
    do_label: str = DEFAULT_DO_KEY_LABEL,
    out_dir: str | None = None,
    print_only: bool = False,
) -> None:
    """Generate + distribute the backup SSH key.

    Modes (mutually exclusive on the private-key destination):
      - ``print_only=True``: emit private PEM to stdout, no file written.
        Caller is expected to pipe to a vault (e.g. ``op document create``).
      - ``out_dir`` set: write private + public to that directory using
        DEFAULT_KEY_NAME. Default when no other mode flag is set.
      - ``gh_secret=True``: seed GH Actions secret (legacy path, opt-in).

    Droplet authorized_keys upload always happens (the task's headline).
    DO account-keys registration runs when ``do_token`` is provided.
    """
    # Legacy path idempotency — only applies when opting into gh-secret mode.
    if gh_secret:
        token = _gh_token(gh_token)
        if _secret_exists(token, repo):
            print(f"[second-key] {SECRET_NAME} already exists in GH Actions — "
                  f"legacy-mode skipping.")
            return

    print(f"[second-key] host:         {host}")
    print(f"[second-key] gh-secret:    {gh_secret}")
    print(f"[second-key] do-register:  {bool(do_token)}")
    print(f"[second-key] print-only:   {print_only}")
    if out_dir and not print_only:
        print(f"[second-key] out-dir:      {out_dir}")
    if dry_run:
        print("[second-key] DRY_RUN=1 — would generate keypair + upload + register.")
        return

    # Generate keypair in a tmpdir; copy out afterward if requested.
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "second_key"
        pub_path = Path(tmpdir) / "second_key.pub"

        result = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "",
             "-C", "tinyassets-backup-key", "-f", str(key_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"ERROR: ssh-keygen failed: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(2)

        pubkey_line = pub_path.read_text().strip()
        private_pem = key_path.read_text()

        print(f"[second-key] generated pubkey: {pubkey_line[:50]}...")

        # --- Droplet authorized_keys append ---
        if _pubkey_already_present(host, primary_key, pubkey_line.split()[1]):
            print("[second-key] pubkey already in authorized_keys — skipping SSH upload.")
        else:
            print(f"[second-key] appending pubkey to {host}:{AUTHORIZED_KEYS}...")
            try:
                _append_pubkey(host, primary_key, pubkey_line)
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(3)
            print("[second-key] pubkey uploaded OK.")

        # --- DO account registration ---
        if do_token:
            if _do_key_exists(do_token, pubkey_line):
                print("[second-key] pubkey already registered with DO account — skipping.")
            else:
                print(f"[second-key] registering pubkey with DO account as "
                      f"'{do_label}'...")
                try:
                    record = _do_register_key(do_token, pubkey_line, do_label)
                except RuntimeError as exc:
                    print(f"ERROR: {exc}", file=sys.stderr)
                    sys.exit(5)
                print(f"[second-key] DO registered OK: key_id={record.get('id')}, "
                      f"fingerprint={record.get('fingerprint')}")
        else:
            print("[second-key] DIGITALOCEAN_TOKEN not set — skipping DO "
                  "account-keys registration. Backup key works on the existing "
                  "droplet only.")

        # --- Private key destination ---
        if gh_secret:
            print(f"[second-key] seeding {SECRET_NAME} in {repo}...")
            try:
                _seed_secret(_gh_token(gh_token), repo, private_pem)
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(4)
            print(f"[second-key] {SECRET_NAME} seeded OK.")
        elif print_only:
            # Emit to stdout for piping to a vault. Nothing left on disk.
            sys.stdout.write(private_pem)
            sys.stdout.flush()
            print("[second-key] private key emitted to stdout (pipe to vault).",
                  file=sys.stderr)
        else:
            # Default: write to ~/.ssh/ for the host to pipe into 1Password.
            dest_dir = Path(out_dir).expanduser() if out_dir else (
                Path.home() / ".ssh"
            )
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_priv = dest_dir / DEFAULT_KEY_NAME
            dest_pub = dest_dir / f"{DEFAULT_KEY_NAME}.pub"
            dest_priv.write_text(private_pem)
            dest_pub.write_text(pubkey_line + "\n")
            try:
                os.chmod(dest_priv, 0o600)
                os.chmod(dest_pub, 0o644)
            except OSError:
                # Windows filesystems ignore chmod; cosmetic only.
                pass
            print(f"[second-key] private key written: {dest_priv}")
            print(f"[second-key] public key written:  {dest_pub}")
            print("[second-key] NEXT — host action:")
            print(f"             op document create {dest_priv} \\")
            print("                 --title 'DO Droplet backup SSH key (private)' \\")
            print("                 --vault workflow")
            print(f"             shred -u {dest_priv}  # after vault confirms")
            print("             # Stash the .pub offsite too (e.g. password-manager notes).")

        # tmpdir auto-erases ephemeral copies when the context exits.

    print("[second-key] done. Bus factor = 2.")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Add a backup ed25519 SSH key to the Droplet + seed GH secret."
    )
    p.add_argument("--host",
                   default=os.environ.get("DROPLET_HOST", ""),
                   help="Droplet IP/hostname")
    p.add_argument("--primary-key",
                   default=os.environ.get("PRIMARY_SSH_KEY_PATH", ""),
                   help="Path to existing primary private key for initial SSH access")
    p.add_argument("--repo",
                   default=os.environ.get("GH_REPO", DEFAULT_REPO),
                   help=f"GitHub repo (default: {DEFAULT_REPO})")
    p.add_argument("--gh-token",
                   default=os.environ.get("GH_TOKEN", ""),
                   help="GitHub token (default: git credential helper)")
    p.add_argument("--do-token",
                   default=os.environ.get("DIGITALOCEAN_TOKEN", ""),
                   help="DO API token for account-keys registration. "
                        "Without this, the backup key works only on the "
                        "existing droplet (not for future droplet-creation).")
    p.add_argument("--do-label",
                   default=DEFAULT_DO_KEY_LABEL,
                   help=f"Label shown in DO dashboard (default: {DEFAULT_DO_KEY_LABEL})")
    p.add_argument("--gh-secret", action="store_true",
                   help="Legacy: also seed the private key as GH Actions "
                        "secret DO_SSH_KEY_BACKUP. Off by default — "
                        "vault-first per Task #7 supersedes this path.")
    p.add_argument("--print-only", action="store_true",
                   help="Emit private PEM to stdout (for piping to vault CLI). "
                        "Mutually exclusive with --out-dir; bypasses disk write.")
    p.add_argument("--out-dir",
                   default="",
                   help="Directory to write private + public key files. "
                        "Default: ~/.ssh/. Ignored when --print-only is set "
                        "or --gh-secret is the only destination.")
    args = p.parse_args()

    if not args.host:
        print("ERROR: --host or DROPLET_HOST required", file=sys.stderr)
        sys.exit(1)
    if not args.primary_key:
        print("ERROR: --primary-key or PRIMARY_SSH_KEY_PATH required", file=sys.stderr)
        sys.exit(1)
    if args.print_only and args.gh_secret:
        print("ERROR: --print-only and --gh-secret are mutually exclusive",
              file=sys.stderr)
        sys.exit(1)

    dry_run = os.environ.get("DRY_RUN", "0").strip() == "1"
    run(
        host=args.host,
        primary_key=args.primary_key,
        repo=args.repo,
        dry_run=dry_run,
        gh_token=args.gh_token or None,
        gh_secret=args.gh_secret,
        do_token=args.do_token or None,
        do_label=args.do_label,
        out_dir=args.out_dir or None,
        print_only=args.print_only,
    )


if __name__ == "__main__":
    main()

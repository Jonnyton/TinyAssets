"""Seed GitHub Actions repo secrets using the token from git credential
manager (no device flow, no host click).

Usage:
    python scripts/gh_seed_secret.py --repo Jonnyton/TinyAssets \\
        --name DO_SSH_KEY --value-file "$HOME/.ssh/tinyassets_deploy_ed25519"
    python scripts/gh_seed_secret.py --repo Jonnyton/TinyAssets \\
        --name DO_DROPLET_HOST --value "161.35.237.133"

Secret values never print to stdout; only the HTTP result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from base64 import b64encode
from pathlib import Path


def git_credential_token(host: str = "github.com") -> str:
    """Invoke `git credential fill` and pull the password line."""
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input=f"url=https://{host}\n\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git credential fill failed: {proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    raise RuntimeError("no password in git credential output")


def _gh_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "workflow-gh-seeder/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _gh_put_secret(token: str, repo: str, name: str, encrypted: str, key_id: str) -> int:
    body = json.dumps({"encrypted_value": encrypted, "key_id": key_id}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "workflow-gh-seeder/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def encrypt_secret(public_key_b64: str, plaintext: str) -> str:
    from nacl import encoding, public

    key = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    return b64encode(public.SealedBox(key).encrypt(plaintext.encode())).decode()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--name", required=True, help="secret name")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--value", help="secret value literal")
    g.add_argument("--value-file", help="path to file containing secret value")
    args = p.parse_args()

    value = Path(args.value_file).read_text() if args.value_file else args.value
    token = git_credential_token()
    pk = _gh_get(
        f"https://api.github.com/repos/{args.repo}/actions/secrets/public-key", token
    )
    encrypted = encrypt_secret(pk["key"], value)
    status = _gh_put_secret(token, args.repo, args.name, encrypted, pk["key_id"])
    verb = {201: "CREATED", 204: "UPDATED"}.get(status, f"HTTP {status}")
    print(f"{args.name} -> {verb}")
    return 0 if status in (201, 204) else 1


if __name__ == "__main__":
    sys.exit(main())

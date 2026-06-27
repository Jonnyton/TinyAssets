#!/usr/bin/env python3
"""Mint a GitHub App installation token and install it for PR effectors.

The script intentionally uses stdlib plus the system openssl binary instead of
adding Python package dependencies to the host. It writes the minted token into
/etc/tinyassets/env through deploy/install-tinyassets-env.sh as:

    TINYASSETS_GITHUB_PR_CAPABILITIES={"Jonnyton/TinyAssets":"<token>"}
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = os.environ.get("GITHUB_API_ROOT", "https://api.github.com")
APP_ID = os.environ.get("GITHUB_APP_ID", "").strip()
INSTALLATION_ID = os.environ.get("GITHUB_APP_INSTALLATION_ID", "").strip()
REPO = os.environ.get("TINYASSETS_GITHUB_PR_CAPABILITIES_REPO", "Jonnyton/TinyAssets")
ENV_HELPER = Path(os.environ.get("TINYASSETS_ENV_HELPER", "/opt/tinyassets/deploy/install-tinyassets-env.sh"))
PRIVATE_KEY_FILE = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
PRIVATE_KEY_B64 = os.environ.get("GITHUB_APP_PRIVATE_KEY_B64", "").strip()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _private_key_path() -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if PRIVATE_KEY_FILE:
        path = Path(PRIVATE_KEY_FILE)
        if not path.is_file():
            raise SystemExit(f"private key file does not exist: {path}")
        return path, None
    if not PRIVATE_KEY_B64:
        raise SystemExit("set GITHUB_APP_PRIVATE_KEY_FILE or GITHUB_APP_PRIVATE_KEY_B64")
    tmp = tempfile.TemporaryDirectory(prefix="workflow-github-app-")
    path = Path(tmp.name) / "app-private-key.pem"
    path.write_bytes(base64.b64decode(PRIVATE_KEY_B64))
    path.chmod(0o600)
    return path, tmp


def _sign_rs256(payload: bytes, private_key: Path) -> bytes:
    result = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key), "-binary"],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")[:300]
        raise SystemExit(f"openssl signing failed: {err}")
    return result.stdout


def _jwt(private_key: Path) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {"iat": now - 60, "exp": now + 540, "iss": APP_ID}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    signature = _sign_rs256(signing_input.encode("ascii"), private_key)
    return f"{signing_input}.{_b64url(signature)}"


def _request_json(url: str, *, token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if payload is None else "POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"GitHub API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"GitHub API error: {exc}") from exc


def _installation_token(app_jwt: str) -> str:
    url = f"{API_ROOT}/app/installations/{INSTALLATION_ID}/access_tokens"
    payload = {"permissions": {"contents": "write", "pull_requests": "write"}}
    result = _request_json(url, token=app_jwt, payload=payload)
    token = result.get("token", "")
    if not token:
        raise SystemExit("GitHub did not return an installation token")
    return token


def _install_capability(token: str) -> None:
    if not ENV_HELPER.is_file():
        raise SystemExit(f"env helper does not exist: {ENV_HELPER}")
    capability = json.dumps({REPO: token}, separators=(",", ":"))
    result = subprocess.run(
        ["bash", str(ENV_HELPER), "set", "TINYASSETS_GITHUB_PR_CAPABILITIES"],
        input=capability,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:500]
        raise SystemExit(f"failed to install TINYASSETS_GITHUB_PR_CAPABILITIES: {err}")


def main() -> int:
    if not APP_ID:
        raise SystemExit("set GITHUB_APP_ID")
    if not INSTALLATION_ID:
        raise SystemExit("set GITHUB_APP_INSTALLATION_ID")
    key_path, tmp = _private_key_path()
    try:
        token = _installation_token(_jwt(key_path))
        _install_capability(token)
    finally:
        if tmp is not None:
            tmp.cleanup()
    print(f"installed TINYASSETS_GITHUB_PR_CAPABILITIES for {REPO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

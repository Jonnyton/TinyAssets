"""Deposit the founder's X posting credentials — run this YOURSELF.

    python scripts/deposit_x_credentials.py

It prompts for the four values from the X Developer Portal (no echo),
VERIFIES them against X (`GET /2/users/me`) and refuses a credential that
belongs to a different account than the destination, then ships them over
ssh into the daemon's per-universe credential vault. The values never touch
argv, a file on this machine, or any transcript.

Where the four values come from: https://developer.x.com → your app →
Keys and tokens → "API Key and Secret" + "Access Token and Secret"
(regenerate to view if hidden; posting needs the access token created with
Read and Write permission, and at least the Basic tier).
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.effectors.twitter_post import (  # noqa: E402
    TwitterCredentials,
    _normalize_handle,
    _oauth_header,
)

USERS_ME = "https://api.x.com/2/users/me"
SSH_TARGET = "workflow-droplet"
RECEIVER = "/app/x_deposit_receiver.py"


def _whoami(credentials: TwitterCredentials) -> str:
    """Return the username these credentials authenticate as, or raise."""
    req = urllib.request.Request(
        USERS_ME,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": _oauth_header(
                method="GET", url=USERS_ME, credentials=credentials
            ),
            "User-Agent": "tinyassets-x-deposit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(
            f"FAIL: X rejected the credentials (HTTP {exc.code}): {body}\n"
            "Check all four values; the access token must be Read and Write."
        ) from None
    username = str((data.get("data") or {}).get("username") or "")
    if not username:
        raise SystemExit(f"FAIL: /2/users/me returned no username: {data}")
    return username


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--destination", default="@kwisatzh4derach",
        help="the @handle these credentials post as (default: %(default)s)",
    )
    args = parser.parse_args()
    destination = _normalize_handle(args.destination)

    print(f"Depositing X credentials for {destination}. Paste each value")
    print("(input is hidden; nothing is stored on this machine):")
    credentials = TwitterCredentials(
        api_key=getpass.getpass("  API Key (consumer key): ").strip(),
        api_secret=getpass.getpass("  API Secret: ").strip(),
        access_token=getpass.getpass("  Access Token: ").strip(),
        access_token_secret=getpass.getpass("  Access Token Secret: ").strip(),
        source="deposit",
    )
    if not all([credentials.api_key, credentials.api_secret,
                credentials.access_token, credentials.access_token_secret]):
        print("FAIL: all four values are required")
        return 1

    print("Verifying with X (/2/users/me)...")
    username = _whoami(credentials)
    if username.lower() != destination.lstrip("@").lower():
        print(
            f"FAIL: these credentials authenticate as @{username}, not "
            f"{destination}. Refusing — consent and authority were granted "
            f"for {destination} only."
        )
        return 1
    print(f"  verified: authenticates as @{username}")

    payload = json.dumps({
        "destination": destination,
        "api_key": credentials.api_key,
        "api_secret": credentials.api_secret,
        "access_token": credentials.access_token,
        "access_token_secret": credentials.access_token_secret,
    })
    print("Shipping to the daemon vault over ssh...")
    result = subprocess.run(
        ["ssh", SSH_TARGET, "docker", "exec", "-i", "tinyassets-daemon",
         "python", RECEIVER],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    sys.stdout.write(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode != 0:
        sys.stdout.write(result.stderr.decode("utf-8", errors="replace")[-500:])
        return 1
    print("Done. The agent can post the moment you tell it to.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

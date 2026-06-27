"""CF Access rollback — reverse of cf_access_cutover.py.

Deletes the Access Application for mcp.tinyassets.io (which also cascades
the attached policies). Optionally deletes the service token with
--rotate-token.

Required API token scopes (same token as cutover works):
    Account:Access: Service Tokens: Edit
    Account:Access: Apps and Policies: Edit

Steps:
  1. GET  /accounts/{acct}/access/apps             → find by domain
  2. DELETE /accounts/{acct}/access/apps/{uuid}    → removes app + policies
  3. (if --rotate-token) GET + DELETE service token by name
  4. Post-rollback verification. Exit 3 if post-apply verification fails.

Usage:
    python scripts/cf_access_rollback.py [--apply] [--rotate-token]

Defaults to dry-run. Reuses CloudflareClient from emergency_dns_flip.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from emergency_dns_flip import (  # noqa: E402
    CloudflareApiError,
    CloudflareClient,
    GlobalKeyClient,
    make_cloudflare_client,
)

SERVICE_TOKEN_NAME = "tinyassets-mcp-worker"
APP_DOMAIN = "mcp.tinyassets.io"
MCP_PROTOCOL_VERSION = "2024-11-05"


def _resolve_account_id(client: CloudflareClient, zone_id: str) -> str:
    resp = client.request("GET", f"/zones/{zone_id}")
    return resp["result"]["account"]["id"]


def _delete_access_app(
    client: CloudflareClient, account_id: str, *, apply: bool
) -> bool:
    """Delete the Access app for APP_DOMAIN. Returns True if deleted/would-delete."""
    existing = client.request(
        "GET", f"/accounts/{account_id}/access/apps"
    ).get("result") or []
    target = next((a for a in existing if a.get("domain") == APP_DOMAIN), None)
    if target is None:
        print(f"access-app: no app found for domain={APP_DOMAIN} (nothing to do)")
        return False
    uid = target["uid"]
    if not apply:
        print(f"access-app: would DELETE uuid={uid} domain={APP_DOMAIN} (dry-run)")
        return True
    client.request("DELETE", f"/accounts/{account_id}/access/apps/{uid}")
    print(f"access-app: DELETED uuid={uid} domain={APP_DOMAIN} (policies cascaded)")
    return True


def _delete_service_token(
    client: CloudflareClient, account_id: str, *, apply: bool
) -> bool:
    """Delete the service token named SERVICE_TOKEN_NAME. Returns True if deleted/would-delete."""
    existing = client.request(
        "GET", f"/accounts/{account_id}/access/service_tokens"
    ).get("result") or []
    target = next((t for t in existing if t.get("name") == SERVICE_TOKEN_NAME), None)
    if target is None:
        print(f"service-token: no token found named '{SERVICE_TOKEN_NAME}' (nothing to do)")
        return False
    tid = target["id"]
    if not apply:
        print(f"service-token: would DELETE id={tid} name={SERVICE_TOKEN_NAME} (dry-run)")
        return True
    client.request("DELETE", f"/accounts/{account_id}/access/service_tokens/{tid}")
    print(f"service-token: DELETED id={tid} name={SERVICE_TOKEN_NAME}")
    return True


def rollback_check(canonical: str, internal: str) -> bool:
    """Post-rollback probe — inverse of the cutover three-check.

    Canonical should still be green (200 + serverInfo).
    Internal should now be reachable (200), proving the Access gate was removed.
    """
    print("\n=== rollback-check ===")
    ok = True
    # (a) canonical — still green
    req = urllib.request.Request(
        canonical,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "workflow-cf-access-rollback/1.0",
        },
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "clientInfo": {"name": "rollback-probe", "version": "1"},
                    "capabilities": {},
                },
            }
        ).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            green = resp.status == 200 and "serverInfo" in body
            ok = ok and green
            print(
                f"(a) canonical {canonical}: "
                f"{resp.status} {'GREEN' if green else 'UNEXPECTED'}"
            )
    except Exception as e:
        ok = False
        print(f"(a) canonical {canonical}: FAILED {e}")

    # (b) internal — should now be ungated (200)
    try:
        req2 = urllib.request.Request(internal, method="HEAD")
        with urllib.request.urlopen(req2, timeout=10) as resp:
            reachable = resp.status < 400
            ok = ok and reachable
            print(
                f"(b) internal {internal}: status={resp.status} "
                f"({'GREEN: ungated' if reachable else 'UNEXPECTED: still blocked'})"
            )
    except urllib.error.HTTPError as e:
        ok = False
        print(
            f"(b) internal {internal}: {e.code} "
            f"({'UNEXPECTED: still gated' if e.code in (401, 403) else 'UNEXPECTED'})"
        )
    except Exception as e:
        ok = False
        print(f"(b) internal {internal}: {e}")
    return ok


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rollback CF Access cutover for mcp.tinyassets.io"
    )
    p.add_argument("--apply", action="store_true", help="actually mutate (default: dry-run)")
    p.add_argument(
        "--rotate-token",
        action="store_true",
        help="also delete the service token (forces re-creation on next cutover)",
    )
    p.add_argument("--skip-verify", action="store_true")
    args = p.parse_args()

    zone_id = os.environ.get("CLOUDFLARE_ZONE_ID")
    if not zone_id:
        print("CLOUDFLARE_ZONE_ID required", file=sys.stderr)
        return 2

    try:
        client = make_cloudflare_client()
    except CloudflareApiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if isinstance(client, GlobalKeyClient):
        print("auth: X-Auth-Email + X-Auth-Key (Global API Key)")
    else:
        print("auth: Bearer token")
    account_id = _resolve_account_id(client, zone_id)
    print(f"account: {account_id}")

    try:
        _delete_access_app(client, account_id, apply=args.apply)
        if args.rotate_token:
            _delete_service_token(client, account_id, apply=args.apply)
        elif not args.apply:
            print("service-token: kept (pass --rotate-token to also delete)")
    except CloudflareApiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.apply and not args.skip_verify:
        if not rollback_check(
            "https://tinyassets.io/mcp", f"https://{APP_DOMAIN}/mcp"
        ):
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())

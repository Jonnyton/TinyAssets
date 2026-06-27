"""CF Access cutover — Option 1 of the single-entry runbook.

Two auth schemes supported:
  - Bearer (CLOUDFLARE_API_TOKEN with Account:Access:Edit + Workers Scripts:Edit)
  - Global Key (CLOUDFLARE_EMAIL + CLOUDFLARE_GLOBAL_KEY) — unscoped full access

Steps:
  1. POST /accounts/{acct}/access/service_tokens  (mint tinyassets-mcp-worker)
  2. POST /accounts/{acct}/access/apps            (self-hosted app for mcp.tinyassets.io)
  3. POST /accounts/{acct}/access/apps/{uuid}/policies  (Service Auth = token)
  4. PUT  /accounts/{acct}/workers/scripts/{script}/secrets  (two secrets)
  5. Three-check verification. Exit 3 if post-apply verification fails.
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
APP_NAME = "tinyassets-mcp-worker-gate"
POLICY_NAME = "worker-only"
MCP_PROTOCOL_VERSION = "2024-11-05"


def _make_client() -> CloudflareClient:
    client = make_cloudflare_client()
    if isinstance(client, GlobalKeyClient):
        print("auth: X-Auth-Email + X-Auth-Key (Global API Key)")
    else:
        print("auth: Bearer token")
    return client


def _resolve_account_id(client: CloudflareClient, zone_id: str) -> str:
    resp = client.request("GET", f"/zones/{zone_id}")
    return resp["result"]["account"]["id"]


def _find_or_create_service_token(
    client: CloudflareClient, account_id: str, *, apply: bool
) -> dict:
    existing = client.request(
        "GET", f"/accounts/{account_id}/access/service_tokens"
    ).get("result") or []
    for t in existing:
        if t.get("name") == SERVICE_TOKEN_NAME:
            print(f"service-token: found existing id={t['id']} (reusing)")
            return t
    if not apply:
        print(
            f"service-token: would CREATE '{SERVICE_TOKEN_NAME}' (dry-run)"
        )
        return {"dry_run": True}
    resp = client.request(
        "POST",
        f"/accounts/{account_id}/access/service_tokens",
        payload={"name": SERVICE_TOKEN_NAME, "duration": "8760h"},
    )
    r = resp["result"]
    print(f"service-token: CREATED id={r['id']} client_id={r['client_id']}")
    return r


def _find_or_create_app(
    client: CloudflareClient, account_id: str, *, apply: bool
) -> dict:
    existing = client.request(
        "GET", f"/accounts/{account_id}/access/apps"
    ).get("result") or []
    for a in existing:
        if a.get("domain") == APP_DOMAIN:
            print(f"access-app: found existing uuid={a['uid']} (reusing)")
            return a
    payload = {
        "name": APP_NAME,
        "domain": APP_DOMAIN,
        "type": "self_hosted",
        "session_duration": "24h",
        "auto_redirect_to_identity": False,
        "allowed_idps": [],
    }
    if not apply:
        print(f"access-app: would CREATE domain={APP_DOMAIN} (dry-run)")
        return {"dry_run": True}
    resp = client.request(
        "POST", f"/accounts/{account_id}/access/apps", payload=payload
    )
    r = resp["result"]
    print(f"access-app: CREATED uuid={r['uid']} domain={r['domain']}")
    return r


def _ensure_policy(
    client: CloudflareClient,
    account_id: str,
    app_uuid: str,
    service_token_id: str,
    *,
    apply: bool,
) -> dict:
    existing = client.request(
        "GET", f"/accounts/{account_id}/access/apps/{app_uuid}/policies"
    ).get("result") or []
    for p in existing:
        if p.get("name") == POLICY_NAME:
            print(f"policy: found existing id={p['id']} (reusing)")
            return p
    payload = {
        "name": POLICY_NAME,
        "decision": "non_identity",
        "include": [{"service_token": {"token_id": service_token_id}}],
        "require": [],
        "exclude": [],
        "precedence": 1,
    }
    if not apply:
        print(f"policy: would CREATE '{POLICY_NAME}' (dry-run)")
        return {"dry_run": True}
    resp = client.request(
        "POST",
        f"/accounts/{account_id}/access/apps/{app_uuid}/policies",
        payload=payload,
    )
    r = resp["result"]
    print(f"policy: CREATED id={r['id']}")
    return r


def _put_worker_secret(
    client: CloudflareClient,
    account_id: str,
    script_name: str,
    name: str,
    value: str,
    *,
    apply: bool,
) -> None:
    if not apply:
        print(f"worker-secret: would PUT {name} on {script_name} (dry-run)")
        return
    client.request(
        "PUT",
        f"/accounts/{account_id}/workers/scripts/{script_name}/secrets",
        payload={"name": name, "text": value, "type": "secret_text"},
    )
    print(f"worker-secret: set {name} on {script_name}")


def three_check(canonical: str, internal: str) -> bool:
    print("\n=== three-check ===")
    ok = True
    req = urllib.request.Request(
        canonical,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "workflow-cf-access-cutover/1.0",
        },
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "clientInfo": {"name": "cutover-probe", "version": "1"},
                    "capabilities": {},
                },
            }
        ).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            green = resp.status == 200 and "serverInfo" in body
            ok = ok and green
            print(
                f"(a) canonical {canonical}: {resp.status} "
                f"{'GREEN' if green else 'UNEXPECTED'}"
            )
    except Exception as e:
        ok = False
        print(f"(a) canonical {canonical}: FAILED {e}")

    try:
        req = urllib.request.Request(internal, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            gated = resp.status >= 400
            ok = ok and gated
            print(
                f"(b) internal {internal}: status={resp.status} "
                f"({'OK' if gated else 'UNEXPECTED: still reachable'})"
            )
    except urllib.error.HTTPError as e:
        gated = e.code in (401, 403)
        ok = ok and gated
        print(
            f"(b) internal {internal}: {e.code} "
            f"({'OK: gated' if gated else 'UNEXPECTED'})"
        )
    except Exception as e:
        ok = False
        print(f"(b) internal {internal}: {e}")
    return ok


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--worker", required=True, help="Cloudflare Worker script name")
    p.add_argument("--apply", action="store_true", help="actually mutate (default: dry-run)")
    p.add_argument("--skip-verify", action="store_true")
    args = p.parse_args()

    zone_id = os.environ.get("CLOUDFLARE_ZONE_ID")
    if not zone_id:
        print("CLOUDFLARE_ZONE_ID required", file=sys.stderr)
        return 2

    try:
        client = _make_client()
        account_id = _resolve_account_id(client, zone_id)
        print(f"account: {account_id}")

        token_obj = _find_or_create_service_token(client, account_id, apply=args.apply)
        app_obj = _find_or_create_app(client, account_id, apply=args.apply)
        if args.apply and "uid" in app_obj and "id" in token_obj:
            _ensure_policy(
                client,
                account_id,
                app_obj["uid"],
                token_obj["id"],
                apply=args.apply,
            )
            if "client_id" in token_obj and "client_secret" in token_obj:
                _put_worker_secret(
                    client,
                    account_id,
                    args.worker,
                    "CF_ACCESS_CLIENT_ID",
                    token_obj["client_id"],
                    apply=args.apply,
                )
                _put_worker_secret(
                    client,
                    account_id,
                    args.worker,
                    "CF_ACCESS_CLIENT_SECRET",
                    token_obj["client_secret"],
                    apply=args.apply,
                )
            else:
                print(
                    "worker-secrets: skipped — reused existing service token; "
                    "secret not recoverable. Rotate token if Worker doesn't "
                    "already have both secrets set."
                )
    except CloudflareApiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.apply and not args.skip_verify:
        if not three_check("https://tinyassets.io/mcp", f"https://{APP_DOMAIN}/mcp"):
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())

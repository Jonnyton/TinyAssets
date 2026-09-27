"""One-shot apex DNS cutover for tinyassets.io → GitHub Pages.

Flips apex A records from the legacy GoDaddy hosting IPs to GitHub Pages'
four canonical IPs (185.199.108-111.153) while preserving the path-based
`/mcp*` Cloudflare Worker route. Stdlib-only (mirrors emergency_dns_flip).

Run via .github/workflows/site-dns-cutover.yml. Defaults to dry-run; pass
--apply to mutate. Always prints captured pre-state so rollback is one
re-run away (re-create the listed records).

Designed for one execution, but idempotent: re-running on an already-
cutover apex is a no-op (records already match GH Pages set).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emergency_dns_flip import (  # noqa: E402
    CloudflareApiError,
    make_cloudflare_client,
    resolve_zone_id,
)

GH_PAGES_IPS = [
    "185.199.108.153",
    "185.199.109.153",
    "185.199.110.153",
    "185.199.111.153",
]
APEX = "tinyassets.io"
WWW = "www.tinyassets.io"
WWW_TARGET = "tinyassets.github.io"
WORKER_ROUTE_PATTERN = "tinyassets.io/mcp*"


def list_records(client, *, zone_id, record_type, name):
    resp = client.request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        params={"type": record_type, "name": name},
    )
    return resp.get("result") or []


def list_worker_routes(client, *, zone_id):
    resp = client.request("GET", f"/zones/{zone_id}/workers/routes")
    return resp.get("result") or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="mutate; default is dry-run")
    ap.add_argument("--zone-id", default=os.getenv("CLOUDFLARE_ZONE_ID"))
    ap.add_argument("--zone-name", default=os.getenv("CLOUDFLARE_ZONE_NAME", APEX))
    args = ap.parse_args()

    try:
        client = make_cloudflare_client()
        zone_id = resolve_zone_id(client, zone_id=args.zone_id, zone_name=args.zone_name)
    except CloudflareApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    plan: list[dict] = []
    rollback: dict[str, list[dict]] = {}

    # Step 1 — capture current apex A + www records (rollback evidence).
    apex_a = list_records(client, zone_id=zone_id, record_type="A", name=APEX)
    apex_aaaa = list_records(client, zone_id=zone_id, record_type="AAAA", name=APEX)
    www_cname = list_records(client, zone_id=zone_id, record_type="CNAME", name=WWW)
    www_a = list_records(client, zone_id=zone_id, record_type="A", name=WWW)
    rollback["apex_A_pre"] = apex_a
    rollback["apex_AAAA_pre"] = apex_aaaa
    rollback["www_CNAME_pre"] = www_cname
    rollback["www_A_pre"] = www_a

    print("=" * 70)
    print("PRE-CUTOVER STATE (rollback evidence)")
    print("=" * 70)
    print(f"apex A records ({len(apex_a)}):")
    for r in apex_a:
        print(f"  - {r.get('content')} (id={r.get('id')}, proxied={r.get('proxied')})")
    print(f"apex AAAA records ({len(apex_aaaa)}):")
    for r in apex_aaaa:
        print(f"  - {r.get('content')} (id={r.get('id')}, proxied={r.get('proxied')})")
    print(f"www CNAME records ({len(www_cname)}):")
    for r in www_cname:
        print(f"  - {r.get('content')} (id={r.get('id')}, proxied={r.get('proxied')})")
    print(f"www A records ({len(www_a)}):")
    for r in www_a:
        print(f"  - {r.get('content')} (id={r.get('id')}, proxied={r.get('proxied')})")

    # Step 2 — verify /mcp* Worker route exists. Refuse to proceed if missing.
    routes = list_worker_routes(client, zone_id=zone_id)
    mcp_route = [r for r in routes if r.get("pattern") == WORKER_ROUTE_PATTERN]
    print()
    print("=" * 70)
    print("WORKER ROUTE CHECK (must survive cutover)")
    print("=" * 70)
    print(f"Found {len(routes)} worker routes; matching pattern '{WORKER_ROUTE_PATTERN}': {len(mcp_route)}")
    for r in mcp_route:
        print(f"  - id={r.get('id')} script={r.get('script')}")
    if not mcp_route:
        print(f"REFUSING TO CUT OVER: '{WORKER_ROUTE_PATTERN}' Worker route is missing.", file=sys.stderr)
        print("Restore it before flipping apex DNS or /mcp will go dark.", file=sys.stderr)
        return 3

    # Step 3 — compute plan.
    existing_apex_ips = {r.get("content") for r in apex_a}
    target_ips = set(GH_PAGES_IPS)
    to_delete_apex_a = [r for r in apex_a if r.get("content") not in target_ips]
    to_create_apex_a_ips = sorted(target_ips - existing_apex_ips)
    to_delete_apex_aaaa = list(apex_aaaa)
    to_delete_www_a = list(www_a)

    www_cname_ok = (
        len(www_cname) == 1
        and www_cname[0].get("content") == WWW_TARGET
        and www_cname[0].get("proxied") is True
    )

    plan.append({"op": "delete_apex_A", "items": [r.get("id") for r in to_delete_apex_a]})
    plan.append({"op": "create_apex_A", "ips": to_create_apex_a_ips})
    plan.append({"op": "delete_apex_AAAA", "items": [r.get("id") for r in to_delete_apex_aaaa]})
    plan.append({"op": "delete_www_A", "items": [r.get("id") for r in to_delete_www_a]})
    plan.append({"op": "ensure_www_CNAME", "ok": www_cname_ok})

    print()
    print("=" * 70)
    print(f"PLAN ({'APPLY' if args.apply else 'DRY-RUN'})")
    print("=" * 70)
    print(f"  - Delete {len(to_delete_apex_a)} apex A record(s) not in GH Pages set")
    print(f"  - Create {len(to_create_apex_a_ips)} new apex A record(s) (proxied)")
    print(f"  - Delete {len(to_delete_apex_aaaa)} apex AAAA record(s)")
    print(f"  - Delete {len(to_delete_www_a)} www A record(s) (replaced by CNAME)")
    print(f"  - www CNAME → {WWW_TARGET} proxied: {'already correct' if www_cname_ok else 'will upsert'}")

    if not args.apply:
        print()
        print("Dry-run complete. Re-run with --apply to mutate.")
        print()
        print("Rollback evidence (JSON):")
        print(json.dumps(rollback, sort_keys=True, indent=2))
        return 0

    # Step 4 — apply.
    print()
    print("=" * 70)
    print("APPLYING")
    print("=" * 70)

    # Delete apex AAAA + www A first (these are unambiguous removals).
    for r in to_delete_apex_aaaa:
        rid = r["id"]
        client.request("DELETE", f"/zones/{zone_id}/dns_records/{rid}")
        print(f"deleted apex AAAA {r.get('content')} (id={rid})")
    for r in to_delete_www_a:
        rid = r["id"]
        client.request("DELETE", f"/zones/{zone_id}/dns_records/{rid}")
        print(f"deleted www A {r.get('content')} (id={rid})")

    # Add the new apex A records BEFORE deleting the old ones — Cloudflare
    # supports multiple A records at apex, and adding-before-deleting keeps
    # the apex resolvable continuously.
    for ip in to_create_apex_a_ips:
        client.request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            payload={
                "type": "A",
                "name": APEX,
                "content": ip,
                "ttl": 1,
                "proxied": True,
                "comment": "github pages apex (site_apex_cutover.py)",
            },
        )
        print(f"created apex A {ip} (proxied)")

    # Now safe to delete the legacy apex A records.
    for r in to_delete_apex_a:
        rid = r["id"]
        client.request("DELETE", f"/zones/{zone_id}/dns_records/{rid}")
        print(f"deleted legacy apex A {r.get('content')} (id={rid})")

    # Ensure www CNAME.
    if not www_cname_ok:
        if www_cname:
            # Update the existing record (regardless of count, just patch the
            # first; if multiple, delete the rest after).
            first = www_cname[0]
            client.request(
                "PATCH",
                f"/zones/{zone_id}/dns_records/{first['id']}",
                payload={
                    "type": "CNAME",
                    "name": WWW,
                    "content": WWW_TARGET,
                    "ttl": 1,
                    "proxied": True,
                    "comment": "github pages www (site_apex_cutover.py)",
                },
            )
            print(f"patched www CNAME → {WWW_TARGET}")
            for extra in www_cname[1:]:
                client.request("DELETE", f"/zones/{zone_id}/dns_records/{extra['id']}")
                print(f"deleted extra www CNAME {extra.get('content')} (id={extra['id']})")
        else:
            client.request(
                "POST",
                f"/zones/{zone_id}/dns_records",
                payload={
                    "type": "CNAME",
                    "name": WWW,
                    "content": WWW_TARGET,
                    "ttl": 1,
                    "proxied": True,
                    "comment": "github pages www (site_apex_cutover.py)",
                },
            )
            print(f"created www CNAME → {WWW_TARGET}")

    # Step 5 — re-verify Worker route (paranoia).
    routes_after = list_worker_routes(client, zone_id=zone_id)
    mcp_after = [r for r in routes_after if r.get("pattern") == WORKER_ROUTE_PATTERN]
    if not mcp_after:
        print("FATAL: /mcp* Worker route disappeared during cutover.", file=sys.stderr)
        return 4
    print(f"post-cutover: /mcp* Worker route still present (id={mcp_after[0].get('id')})")

    # Step 6 — print post-state.
    apex_a_post = list_records(client, zone_id=zone_id, record_type="A", name=APEX)
    print()
    print("POST-CUTOVER apex A records:")
    for r in apex_a_post:
        print(f"  - {r.get('content')} (proxied={r.get('proxied')})")

    print()
    print("Rollback evidence (JSON):")
    print(json.dumps(rollback, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

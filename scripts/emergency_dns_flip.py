"""Emergency Cloudflare DNS/Worker-route flip tool.

Stdlib-only on purpose: this must run from GitHub Actions or a fresh clone
without installing an SDK. It defaults to dry-run; pass ``--apply`` to mutate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API_BASE = "https://api.cloudflare.com/client/v4"
DNS_TYPES = {
    "A", "AAAA", "CAA", "CERT", "CNAME", "DNSKEY", "DS", "HTTPS", "LOC",
    "MX", "NAPTR", "NS", "OPENPGPKEY", "PTR", "SMIMEA", "SRV", "SSHFP",
    "SVCB", "TLSA", "TXT", "URI",
}


class CloudflareApiError(RuntimeError):
    """Cloudflare request or safety validation failed."""


class CloudflareClient:
    def __init__(self, token: str, *, base_url: str = API_BASE) -> None:
        if not token:
            raise CloudflareApiError("CLOUDFLARE_API_TOKEN is required")
        self.token = token
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "workflow-emergency-dns/1.0",
        }
        if payload is not None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise CloudflareApiError(
                f"Cloudflare HTTP {exc.code} for {method} {path}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            msg = f"Cloudflare request failed for {method} {path}: {exc}"
            raise CloudflareApiError(msg) from exc

        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            preview = body[:200].decode("utf-8", errors="replace")
            raise CloudflareApiError(f"Cloudflare returned non-JSON body: {preview!r}") from exc

        if isinstance(decoded, dict) and decoded.get("success") is False:
            raise CloudflareApiError(
                f"Cloudflare API rejected {method} {path}: {decoded.get('errors')}"
            )
        if not isinstance(decoded, dict):
            raise CloudflareApiError(f"Cloudflare returned unexpected payload: {decoded!r}")
        return decoded


class GlobalKeyClient(CloudflareClient):
    """CloudflareClient variant using X-Auth-Email + X-Auth-Key (Global API Key)."""

    def __init__(self, email: str, global_key: str, *, base_url: str = API_BASE) -> None:
        if not email or not global_key:
            raise CloudflareApiError("CLOUDFLARE_EMAIL + CLOUDFLARE_GLOBAL_KEY required")
        self.token = None  # type: ignore[assignment]
        self.base_url = base_url.rstrip("/")
        self._email = email
        self._key = global_key

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        headers = {
            "X-Auth-Email": self._email,
            "X-Auth-Key": self._key,
            "Accept": "application/json",
            "User-Agent": "workflow-emergency-dns/1.0",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise CloudflareApiError(
                f"Cloudflare HTTP {exc.code} for {method} {path}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise CloudflareApiError(
                f"Cloudflare request failed for {method} {path}: {exc}"
            ) from exc

        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CloudflareApiError(
                f"Cloudflare returned non-JSON body: {body[:200]!r}"
            ) from exc
        if isinstance(decoded, dict) and decoded.get("success") is False:
            raise CloudflareApiError(
                f"Cloudflare API rejected {method} {path}: {decoded.get('errors')}"
            )
        if not isinstance(decoded, dict):
            raise CloudflareApiError(f"Cloudflare returned unexpected payload: {decoded!r}")
        return decoded


def make_cloudflare_client(
    *,
    token: str | None = None,
    email: str | None = None,
    global_key: str | None = None,
    base_url: str = API_BASE,
) -> CloudflareClient:
    """Auto-detect auth scheme and return the appropriate client.

    Priority: explicit args > env vars. Global Key wins over Bearer when both
    are present (Global Key is needed for account-level Access endpoints).
    Falls back to Bearer if only CLOUDFLARE_API_TOKEN is available.
    """
    _email = email or os.environ.get("CLOUDFLARE_EMAIL", "")
    _gkey = global_key or os.environ.get("CLOUDFLARE_GLOBAL_KEY", "")
    _token = token or os.environ.get("CLOUDFLARE_API_TOKEN", "")

    if _email and _gkey:
        return GlobalKeyClient(_email, _gkey, base_url=base_url)
    if _token:
        return CloudflareClient(_token, base_url=base_url)
    raise CloudflareApiError(
        "No Cloudflare credentials found. "
        "Set CLOUDFLARE_EMAIL + CLOUDFLARE_GLOBAL_KEY, or CLOUDFLARE_API_TOKEN."
    )


@dataclass(frozen=True)
class ChangeResult:
    action: str
    resource: str
    details: dict[str, Any]


def _single_match(items: list[dict[str, Any]], *, resource: str) -> dict[str, Any] | None:
    if len(items) > 1:
        raise CloudflareApiError(
            f"{resource} matched {len(items)} records/routes; refusing ambiguous mutation"
        )
    return items[0] if items else None


def _list_dns_records(
    client: Any,
    *,
    zone_id: str,
    record_type: str,
    name: str,
) -> list[dict[str, Any]]:
    response = client.request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        params={"type": record_type, "name": name},
    )
    result = response.get("result") or []
    if not isinstance(result, list):
        raise CloudflareApiError(f"unexpected DNS record list payload: {result!r}")
    return result


def _dns_payload(
    *,
    record_type: str,
    name: str,
    content: str,
    ttl: int,
    proxied: bool | None,
    comment: str | None,
) -> dict[str, Any]:
    record_type = record_type.upper()
    if record_type not in DNS_TYPES:
        raise CloudflareApiError(f"unsupported DNS record type: {record_type}")
    if not name.strip():
        raise CloudflareApiError("record name is required")
    if not content.strip():
        raise CloudflareApiError("record content is required")
    if ttl != 1 and not (60 <= ttl <= 86400):
        raise CloudflareApiError("ttl must be 1 (automatic) or between 60 and 86400")

    payload: dict[str, Any] = {
        "type": record_type,
        "name": name.strip(),
        "content": content.strip(),
        "ttl": ttl,
    }
    if proxied is not None:
        payload["proxied"] = proxied
    if comment:
        payload["comment"] = comment
    return payload


def upsert_dns_record(
    client: Any,
    *,
    zone_id: str,
    record_type: str,
    name: str,
    content: str,
    ttl: int,
    proxied: bool | None,
    comment: str | None,
    dry_run: bool,
) -> ChangeResult:
    record_type = record_type.upper()
    existing = _single_match(
        _list_dns_records(client, zone_id=zone_id, record_type=record_type, name=name),
        resource=f"{record_type} {name}",
    )
    payload = _dns_payload(
        record_type=record_type,
        name=name,
        content=content,
        ttl=ttl,
        proxied=proxied,
        comment=comment,
    )
    if dry_run:
        action = "would_update" if existing else "would_create"
        return ChangeResult(action, f"dns:{record_type}:{name}", {"payload": payload})

    if existing:
        record_id = str(existing["id"])
        client.request("PATCH", f"/zones/{zone_id}/dns_records/{record_id}", payload=payload)
        return ChangeResult("updated", f"dns:{record_type}:{name}", {"record_id": record_id})

    response = client.request("POST", f"/zones/{zone_id}/dns_records", payload=payload)
    record_id = (response.get("result") or {}).get("id")
    return ChangeResult("created", f"dns:{record_type}:{name}", {"record_id": record_id})


def delete_dns_record(
    client: Any,
    *,
    zone_id: str,
    record_type: str,
    name: str,
    dry_run: bool,
) -> ChangeResult:
    record_type = record_type.upper()
    existing = _single_match(
        _list_dns_records(client, zone_id=zone_id, record_type=record_type, name=name),
        resource=f"{record_type} {name}",
    )
    if not existing:
        return ChangeResult("noop", f"dns:{record_type}:{name}", {"reason": "not_found"})
    record_id = str(existing["id"])
    if dry_run:
        return ChangeResult("would_delete", f"dns:{record_type}:{name}", {"record_id": record_id})
    client.request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
    return ChangeResult("deleted", f"dns:{record_type}:{name}", {"record_id": record_id})


def _list_worker_routes(client: Any, *, zone_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", f"/zones/{zone_id}/workers/routes")
    result = response.get("result") or []
    if not isinstance(result, list):
        raise CloudflareApiError(f"unexpected Worker route list payload: {result!r}")
    return result


def _matching_worker_route(
    client: Any,
    *,
    zone_id: str,
    pattern: str,
) -> dict[str, Any] | None:
    matches = [
        route for route in _list_worker_routes(client, zone_id=zone_id)
        if route.get("pattern") == pattern
    ]
    return _single_match(matches, resource=f"Worker route {pattern}")


def upsert_worker_route(
    client: Any,
    *,
    zone_id: str,
    pattern: str,
    script: str,
    dry_run: bool,
) -> ChangeResult:
    if not pattern.strip():
        raise CloudflareApiError("Worker route pattern is required")
    if not script.strip():
        raise CloudflareApiError("Worker script name is required")
    existing = _matching_worker_route(client, zone_id=zone_id, pattern=pattern)
    payload = {"pattern": pattern.strip(), "script": script.strip()}
    if dry_run:
        action = "would_update" if existing else "would_create"
        return ChangeResult(action, f"worker-route:{pattern}", {"payload": payload})

    if existing:
        route_id = str(existing["id"])
        client.request("PUT", f"/zones/{zone_id}/workers/routes/{route_id}", payload=payload)
        return ChangeResult("updated", f"worker-route:{pattern}", {"route_id": route_id})

    response = client.request("POST", f"/zones/{zone_id}/workers/routes", payload=payload)
    route_id = (response.get("result") or {}).get("id")
    return ChangeResult("created", f"worker-route:{pattern}", {"route_id": route_id})


def delete_worker_route(
    client: Any,
    *,
    zone_id: str,
    pattern: str,
    dry_run: bool,
) -> ChangeResult:
    existing = _matching_worker_route(client, zone_id=zone_id, pattern=pattern)
    if not existing:
        return ChangeResult("noop", f"worker-route:{pattern}", {"reason": "not_found"})
    route_id = str(existing["id"])
    if dry_run:
        return ChangeResult("would_delete", f"worker-route:{pattern}", {"route_id": route_id})
    client.request("DELETE", f"/zones/{zone_id}/workers/routes/{route_id}")
    return ChangeResult("deleted", f"worker-route:{pattern}", {"route_id": route_id})


def resolve_zone_id(client: CloudflareClient, *, zone_id: str | None, zone_name: str | None) -> str:
    if zone_id:
        return zone_id
    if not zone_name:
        raise CloudflareApiError("provide --zone-id or --zone-name/CLOUDFLARE_ZONE_NAME")
    response = client.request("GET", "/zones", params={"name": zone_name})
    zones = response.get("result") or []
    if not isinstance(zones, list):
        raise CloudflareApiError(f"unexpected zone list payload: {zones!r}")
    match = _single_match(zones, resource=f"zone {zone_name}")
    if not match:
        raise CloudflareApiError(f"Cloudflare zone not found: {zone_name}")
    return str(match["id"])


def parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {value!r}")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Dry-run or apply an emergency Cloudflare flip.")
    ap.add_argument(
        "--action",
        required=True,
        choices=[
            "upsert-record",
            "delete-record",
            "upsert-worker-route",
            "delete-worker-route",
        ],
    )
    ap.add_argument("--zone-id", default=os.getenv("CLOUDFLARE_ZONE_ID"))
    ap.add_argument("--zone-name", default=os.getenv("CLOUDFLARE_ZONE_NAME", "tinyassets.io"))
    ap.add_argument("--api-token", default=os.getenv("CLOUDFLARE_API_TOKEN"))
    ap.add_argument("--record-type", default="CNAME")
    ap.add_argument("--name", help="DNS record name, for example mcp.tinyassets.io")
    ap.add_argument("--content", help="DNS record target/content")
    ap.add_argument("--ttl", type=int, default=1, help="1 = Cloudflare automatic TTL")
    ap.add_argument("--proxied", type=parse_bool)
    ap.add_argument("--comment")
    ap.add_argument("--pattern", default="tinyassets.io/mcp*", help="Worker route pattern")
    ap.add_argument("--script", default="tinyassets-mcp-router", help="Worker script name")
    ap.add_argument("--apply", action="store_true", help="mutate Cloudflare; default is dry-run")
    ap.add_argument("--json", action="store_true", help="print machine-readable result")
    return ap


def _run(args: argparse.Namespace) -> ChangeResult:
    client = make_cloudflare_client(token=args.api_token)
    zone_id = resolve_zone_id(client, zone_id=args.zone_id, zone_name=args.zone_name)
    dry_run = not args.apply

    if args.action == "upsert-record":
        if not args.name or not args.content:
            raise CloudflareApiError("--name and --content are required for upsert-record")
        return upsert_dns_record(
            client,
            zone_id=zone_id,
            record_type=args.record_type,
            name=args.name,
            content=args.content,
            ttl=args.ttl,
            proxied=args.proxied,
            comment=args.comment,
            dry_run=dry_run,
        )
    if args.action == "delete-record":
        if not args.name:
            raise CloudflareApiError("--name is required for delete-record")
        return delete_dns_record(
            client,
            zone_id=zone_id,
            record_type=args.record_type,
            name=args.name,
            dry_run=dry_run,
        )
    if args.action == "upsert-worker-route":
        return upsert_worker_route(
            client,
            zone_id=zone_id,
            pattern=args.pattern,
            script=args.script,
            dry_run=dry_run,
        )
    return delete_worker_route(
        client,
        zone_id=zone_id,
        pattern=args.pattern,
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except CloudflareApiError as exc:
        print(f"emergency_dns_flip: {exc}", file=sys.stderr)
        return 2

    payload = {
        "action": result.action,
        "resource": result.resource,
        "details": result.details,
        "dry_run": not args.apply,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        dry_run_note = " (dry-run; pass --apply to mutate)" if not args.apply else ""
        print(f"{result.action}: {result.resource}{dry_run_note}")
        if result.details:
            print(json.dumps(result.details, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

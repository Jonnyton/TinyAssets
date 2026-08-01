#!/usr/bin/env python3
"""Check the public OAuth discovery contract required for ChatGPT continuity."""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections.abc import Callable
from typing import Any

FetchJson = Callable[[str], dict[str, Any]]
WriteLine = Callable[[str], Any]


def _contains(values: Any, expected: str) -> bool:
    return isinstance(values, list) and expected in values


def _normalize_url(value: Any) -> str:
    return value.rstrip("/") if isinstance(value, str) else ""


def _authorization_server(resource_metadata: dict[str, Any]) -> str:
    values = resource_metadata.get("authorization_servers", [])
    return _normalize_url(values[0]) if isinstance(values, list) and values else ""


def check_discovery_contract(
    mcp_url: str,
    resource_metadata: dict[str, Any],
    authorization_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Return a public, secret-free continuity report for two metadata documents."""
    expected_resource = _normalize_url(mcp_url)
    authorization_server = _authorization_server(resource_metadata)
    issues: list[str] = []

    if _normalize_url(resource_metadata.get("resource")) != expected_resource:
        issues.append("resource_mismatch")
    if not authorization_server:
        issues.append("authorization_server_missing")
    elif _normalize_url(authorization_metadata.get("issuer")) != authorization_server:
        issues.append("authorization_server_issuer_mismatch")
    if not _contains(resource_metadata.get("bearer_methods_supported"), "header"):
        issues.append("bearer_header_missing")
    resource_scopes = resource_metadata.get("scopes_supported")
    if not _contains(resource_scopes, "offline_access"):
        issues.append("resource_offline_access_scope_missing")

    if not authorization_server:
        return {
            "schema_version": 1,
            "ok": False,
            "resource": expected_resource,
            "authorization_server": "",
            "issues": issues,
        }

    if not authorization_metadata.get("authorization_endpoint"):
        issues.append("authorization_endpoint_missing")
    if not authorization_metadata.get("token_endpoint"):
        issues.append("token_endpoint_missing")
    if not authorization_metadata.get("registration_endpoint"):
        issues.append("dcr_registration_endpoint_missing")
    grants = authorization_metadata.get("grant_types_supported")
    if not _contains(grants, "authorization_code"):
        issues.append("authorization_code_grant_missing")
    authorization_scopes = authorization_metadata.get("scopes_supported")
    if not _contains(authorization_scopes, "offline_access"):
        issues.append("authorization_offline_access_scope_missing")
    if not _contains(grants, "refresh_token"):
        issues.append("refresh_token_grant_missing")
    if not _contains(
        authorization_metadata.get("code_challenge_methods_supported"), "S256"
    ):
        issues.append("pkce_s256_missing")
    if not _contains(
        authorization_metadata.get("token_endpoint_auth_methods_supported"), "none"
    ):
        issues.append("public_client_token_auth_missing")
    if not authorization_metadata.get("client_id_metadata_document_supported"):
        issues.append("cimd_not_advertised")

    return {
        "schema_version": 1,
        "ok": not issues,
        "resource": expected_resource,
        "authorization_server": authorization_server,
        "issues": issues,
    }


def inspect_discovery_contract(
    mcp_url: str,
    fetch_json: FetchJson,
) -> dict[str, Any]:
    """Fetch public discovery documents and evaluate their continuity contract."""
    resource_url = f"{mcp_url.rstrip('/')}/.well-known/oauth-protected-resource"
    resource_metadata = fetch_json(resource_url)
    authorization_server = _authorization_server(resource_metadata)
    if not authorization_server:
        return check_discovery_contract(mcp_url, resource_metadata, {})
    authorization_metadata = fetch_json(
        f"{authorization_server}/.well-known/oauth-authorization-server"
    )
    return check_discovery_contract(mcp_url, resource_metadata, authorization_metadata)


def run_check(
    mcp_url: str,
    *,
    fetch_json: FetchJson,
    write: WriteLine,
) -> int:
    """Write one JSON report and return a shell-friendly contract status."""
    report = inspect_discovery_contract(mcp_url, fetch_json)
    write(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["ok"] else 1


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "TinyAssets-OAuth-Check/1"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"discovery response was not an object: {url}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default="https://tinyassets.io/mcp")
    args = parser.parse_args()
    return run_check(args.mcp_url, fetch_json=_fetch_json, write=print)


if __name__ == "__main__":
    raise SystemExit(main())

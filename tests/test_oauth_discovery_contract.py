from __future__ import annotations

import json

MCP_URL = "https://tinyassets.io/mcp"
AUTHKIT = "https://tinyassets.authkit.app"


def _resource_metadata(**overrides):
    metadata = {
        "resource": MCP_URL,
        "authorization_servers": [AUTHKIT],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "bearer_methods_supported": ["header"],
    }
    metadata.update(overrides)
    return metadata


def _authorization_metadata(**overrides):
    metadata = {
        "issuer": AUTHKIT,
        "authorization_endpoint": f"{AUTHKIT}/oauth2/authorize",
        "token_endpoint": f"{AUTHKIT}/oauth2/token",
        "registration_endpoint": f"{AUTHKIT}/oauth2/register",
        "client_id_metadata_document_supported": True,
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
    }
    metadata.update(overrides)
    return metadata


def test_chatgpt_continuity_contract_accepts_cimd_refresh_and_dcr_compatibility():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(),
        _authorization_metadata(),
    )

    assert result == {
        "schema_version": 1,
        "ok": True,
        "resource": MCP_URL,
        "authorization_server": AUTHKIT,
        "issues": [],
    }


def test_chatgpt_continuity_contract_identifies_live_dcr_only_failure():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(),
        _authorization_metadata(client_id_metadata_document_supported=False),
    )

    assert result["ok"] is False
    assert result["issues"] == ["cimd_not_advertised"]


def test_chatgpt_continuity_contract_requires_refresh_scope_and_grant():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(scopes_supported=["openid", "profile", "email"]),
        _authorization_metadata(
            grant_types_supported=["authorization_code"],
            scopes_supported=["openid", "profile", "email"],
        ),
    )

    assert result["issues"] == [
        "resource_offline_access_scope_missing",
        "authorization_offline_access_scope_missing",
        "refresh_token_grant_missing",
    ]


def test_chatgpt_continuity_contract_reports_resource_and_public_client_mismatch():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(resource="https://tinyassets.io"),
        _authorization_metadata(
            code_challenge_methods_supported=[],
            token_endpoint_auth_methods_supported=["client_secret_basic"],
        ),
    )

    assert result["issues"] == [
        "resource_mismatch",
        "pkce_s256_missing",
        "public_client_token_auth_missing",
    ]


def test_live_check_fetches_the_resource_then_its_advertised_authorization_server():
    from scripts.check_oauth_discovery_contract import inspect_discovery_contract

    calls = []

    def fetch_json(url):
        calls.append(url)
        if url.endswith("oauth-protected-resource"):
            return _resource_metadata()
        return _authorization_metadata()

    result = inspect_discovery_contract(MCP_URL, fetch_json)

    assert calls == [
        f"{MCP_URL}/.well-known/oauth-protected-resource",
        f"{AUTHKIT}/.well-known/oauth-authorization-server",
    ]
    assert result["ok"] is True


def test_cli_check_emits_one_json_report_and_nonzero_for_dcr_only_metadata():
    from scripts.check_oauth_discovery_contract import run_check

    lines = []

    def fetch_json(url):
        if url.endswith("oauth-protected-resource"):
            return _resource_metadata()
        return _authorization_metadata(client_id_metadata_document_supported=False)

    exit_code = run_check(MCP_URL, fetch_json=fetch_json, write=lines.append)

    assert exit_code == 1
    assert len(lines) == 1
    assert json.loads(lines[0])["issues"] == ["cimd_not_advertised"]


def test_contract_requires_the_complete_public_auth_code_discovery_surface():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(bearer_methods_supported=[]),
        _authorization_metadata(
            issuer="https://other.authkit.app",
            authorization_endpoint="",
            token_endpoint="",
            registration_endpoint="",
            grant_types_supported=["refresh_token"],
        ),
    )

    assert result["issues"] == [
        "authorization_server_issuer_mismatch",
        "bearer_header_missing",
        "authorization_endpoint_missing",
        "token_endpoint_missing",
        "dcr_registration_endpoint_missing",
        "authorization_code_grant_missing",
    ]


def test_live_check_reports_missing_authorization_server_without_a_second_fetch():
    from scripts.check_oauth_discovery_contract import inspect_discovery_contract

    calls = []

    def fetch_json(url):
        calls.append(url)
        return _resource_metadata(authorization_servers=[])

    result = inspect_discovery_contract(MCP_URL, fetch_json)

    assert calls == [f"{MCP_URL}/.well-known/oauth-protected-resource"]
    assert result["authorization_server"] == ""
    assert result["issues"] == ["authorization_server_missing"]


def test_contract_does_not_accept_string_substrings_as_metadata_lists():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(
            scopes_supported="offline_access",
            bearer_methods_supported="header",
        ),
        _authorization_metadata(
            scopes_supported="offline_access",
            grant_types_supported="authorization_code refresh_token",
            code_challenge_methods_supported="S256",
            token_endpoint_auth_methods_supported="none",
        ),
    )

    assert result["issues"] == [
        "bearer_header_missing",
        "resource_offline_access_scope_missing",
        "authorization_code_grant_missing",
        "authorization_offline_access_scope_missing",
        "refresh_token_grant_missing",
        "pkce_s256_missing",
        "public_client_token_auth_missing",
    ]


def test_contract_normalizes_trailing_slashes_on_resource_and_issuer_urls():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        f"{MCP_URL}/",
        _resource_metadata(resource=f"{MCP_URL}/"),
        _authorization_metadata(issuer=f"{AUTHKIT}/"),
    )

    assert result["ok"] is True
    assert result["resource"] == MCP_URL
    assert result["authorization_server"] == AUTHKIT


def test_live_check_rejects_non_string_authorization_server_without_fetching_it():
    from scripts.check_oauth_discovery_contract import inspect_discovery_contract

    calls = []

    def fetch_json(url):
        calls.append(url)
        return _resource_metadata(authorization_servers=[{"issuer": AUTHKIT}])

    result = inspect_discovery_contract(MCP_URL, fetch_json)

    assert calls == [f"{MCP_URL}/.well-known/oauth-protected-resource"]
    assert result["authorization_server"] == ""
    assert result["issues"] == ["authorization_server_missing"]


def test_contract_reports_non_string_issuer_as_a_safe_mismatch():
    from scripts.check_oauth_discovery_contract import check_discovery_contract

    result = check_discovery_contract(
        MCP_URL,
        _resource_metadata(),
        _authorization_metadata(issuer={"value": AUTHKIT}),
    )

    assert result["issues"] == ["authorization_server_issuer_mismatch"]

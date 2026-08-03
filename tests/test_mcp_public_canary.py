"""PR-178: mcp_public_canary --assert-handles drift guard (offline)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mcp_public_canary",
    Path(__file__).resolve().parents[1] / "scripts" / "mcp_public_canary.py",
)
canary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(canary)


def _scripted_post(
    tool_names,
    status_payload=None,
    *,
    structured_status=False,
    converse_status=401,
    converse_challenge=(
        'Bearer resource_metadata="https://example/mcp/'
        '.well-known/oauth-protected-resource"'
    ),
):
    """Return a fake _post that replays an MCP handshake advertising tool_names."""
    if status_payload is None:
        status_payload = {
            "active_host": {"llm_endpoint_bound": True},
            "release_state": {"git_sha": "abc123"},
            "request_identity": {"principal_fingerprint": "v1:abc"},
            "identity_evidence": {"status": "available"},
        }

    def _post(
        url,
        payload,
        timeout,
        session_id=None,
        accepted_http_statuses=frozenset(),
    ):
        method = payload.get("method")
        if method == "initialize":
            body = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "tinyassets", "version": "0.1.0"},
                },
            }).encode()
            return 200, {"mcp-session-id": "sess-1"}, body
        if method == "notifications/initialized":
            return 202, {}, b""
        if method == "tools/list":
            body = json.dumps({
                "jsonrpc": "2.0", "id": 2,
                "result": {"tools": [{"name": n} for n in tool_names]},
            }).encode()
            return 200, {}, body
        if method == "tools/call":
            if payload["params"]["name"] == "converse":
                assert payload["params"] == {
                    "name": "converse",
                    "arguments": {"message": "mcp-public-canary auth boundary probe"},
                }
                assert 401 in accepted_http_statuses
                if converse_status == 401:
                    return 401, {"www-authenticate": converse_challenge}, (
                        b'{"error":"authentication_required"}'
                    )
                body = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 3,
                    "error": {"code": -32602, "message": "Resource not found"},
                }).encode()
                return converse_status, {}, body
            assert payload["params"] == {"name": "get_status", "arguments": {}}
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(status_payload)}
                ]
            }
            if structured_status:
                result["content"][0]["text"] = (
                    '{"active_host":\n... [truncated; full payload in structuredContent]'
                )
                result["structuredContent"] = status_payload
            body = json.dumps({
                "jsonrpc": "2.0",
                "id": 3,
                "result": result,
            }).encode()
            return 200, {}, body
        raise AssertionError(f"unexpected method {method}")

    return _post


_CANONICAL_PLUS_STATUS = [
    "read_graph", "write_graph", "run_graph", "read_page", "write_page",
    "converse", "get_status",
]


def test_assert_handles_passes_on_exact_surface(monkeypatch):
    monkeypatch.setattr(canary, "_post", _scripted_post(_CANONICAL_PLUS_STATUS))
    # No exception == green.
    canary.assert_canonical_handles("https://example/mcp", 5.0)


def test_assert_handles_fails_on_legacy_leak(monkeypatch):
    leaky = _CANONICAL_PLUS_STATUS + ["universe", "extensions"]
    monkeypatch.setattr(canary, "_post", _scripted_post(leaky))
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert "universe" in exc.value.msg


@pytest.mark.parametrize(
    "extra_handle",
    ["contribution", "dataset", "manifest", "forge", "promotion"],
)
def test_assert_handles_rejects_data_commons_catalog_handles(
    monkeypatch, extra_handle
):
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS + [extra_handle]),
    )
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert extra_handle in exc.value.msg


def test_assert_handles_fails_on_missing_handle(monkeypatch):
    short = [n for n in _CANONICAL_PLUS_STATUS if n != "run_graph"]
    monkeypatch.setattr(canary, "_post", _scripted_post(short))
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert "run_graph" in exc.value.msg


def test_assert_handles_fails_when_get_status_is_missing(monkeypatch):
    short = [n for n in _CANONICAL_PLUS_STATUS if n != "get_status"]
    monkeypatch.setattr(canary, "_post", _scripted_post(short))
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert "get_status" in exc.value.msg


def test_advertised_tool_names_round_trips(monkeypatch):
    monkeypatch.setattr(canary, "_post", _scripted_post(_CANONICAL_PLUS_STATUS))
    names = canary.advertised_tool_names("https://example/mcp", 5.0)
    assert names == set(_CANONICAL_PLUS_STATUS)


def test_converse_auth_gate_reaches_canonical_bearer_challenge(monkeypatch):
    monkeypatch.setattr(canary, "_post", _scripted_post(_CANONICAL_PLUS_STATUS))

    canary.assert_converse_auth_gate("https://example/mcp", 5.0)


def test_converse_auth_gate_rejects_resource_not_found(monkeypatch):
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS, converse_status=200),
    )

    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_converse_auth_gate("https://example/mcp", 5.0)

    assert exc.value.code == 6
    assert "expected HTTP 401" in exc.value.msg


def test_converse_auth_gate_rejects_protected_resource_metadata_drift(
    monkeypatch,
):
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(
            _CANONICAL_PLUS_STATUS,
            converse_challenge=(
                'Bearer resource_metadata="https://wrong.example/'
                '.well-known/oauth-protected-resource"'
            ),
        ),
    )

    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_converse_auth_gate("https://example/mcp", 5.0)

    assert exc.value.code == 6
    assert "resource metadata drift" in exc.value.msg


def test_status_surface_assertion_calls_get_status_and_checks_uptime_fields(
    monkeypatch,
):
    monkeypatch.setattr(canary, "_post", _scripted_post(_CANONICAL_PLUS_STATUS))

    identity_state = canary.assert_status_surface("https://example/mcp", 5.0)

    assert identity_state == "available"


def test_status_surface_assertion_accepts_explicit_identity_degradation(
    monkeypatch,
):
    status_payload = {
        "active_host": {"llm_endpoint_bound": False},
        "release_state": {"git_sha": "abc123"},
        "request_identity": {"principal_fingerprint": None},
        "identity_evidence": {
            "status": "unavailable",
            "reason": "key_not_provisioned",
        },
    }
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS, status_payload),
    )

    identity_state = canary.assert_status_surface("https://example/mcp", 5.0)

    assert identity_state == "unavailable:key_not_provisioned"


def test_status_surface_prefers_full_structured_content_over_truncated_text(
    monkeypatch,
):
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS, structured_status=True),
    )

    identity_state = canary.assert_status_surface("https://example/mcp", 5.0)

    assert identity_state == "available"


@pytest.mark.parametrize("missing_field", ["active_host", "release_state"])
def test_status_surface_assertion_fails_when_uptime_field_is_missing(
    monkeypatch,
    missing_field,
):
    status_payload = {
        "active_host": {"llm_endpoint_bound": True},
        "release_state": {"git_sha": "abc123"},
        "request_identity": {"principal_fingerprint": None},
        "identity_evidence": {
            "status": "unavailable",
            "reason": "key_not_provisioned",
        },
    }
    status_payload.pop(missing_field)
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS, status_payload),
    )

    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_status_surface("https://example/mcp", 5.0)

    assert exc.value.code == 5
    assert missing_field in exc.value.msg


def test_assert_handles_retry_includes_get_status_uptime_assertion(monkeypatch):
    status_stub = {
        "identity_evidence": {
            "status": "unavailable",
            "reason": "key_not_provisioned",
        },
        "request_identity": {"principal_fingerprint": None},
    }
    monkeypatch.setattr(
        canary,
        "_post",
        _scripted_post(_CANONICAL_PLUS_STATUS, status_stub),
    )

    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles_with_retry(
            "https://example/mcp",
            5.0,
            retries=1,
            delay=0.0,
            _sleep=lambda _: None,
        )

    assert exc.value.code == 5
    assert "active_host" in exc.value.msg
    assert "release_state" in exc.value.msg


def test_retry_recovers_from_transient_blip(monkeypatch):
    """A transient failure that clears on a later attempt must NOT fail."""
    good = _scripted_post(_CANONICAL_PLUS_STATUS)
    calls = {"n": 0}

    def flaky(
        url,
        payload,
        timeout,
        session_id=None,
        accepted_http_statuses=frozenset(),
    ):
        if payload.get("method") == "initialize":
            calls["n"] += 1
            if calls["n"] == 1:
                raise canary.CanaryError(2, "transient unreachable")
        return good(url, payload, timeout, session_id, accepted_http_statuses)

    monkeypatch.setattr(canary, "_post", flaky)
    # Should pass on the 2nd attempt; no real sleeping.
    canary.assert_canonical_handles_with_retry(
        "https://example/mcp", 5.0, retries=3, delay=0.0, _sleep=lambda _: None
    )


def test_retry_propagates_persistent_drift(monkeypatch):
    """A genuine, persistent regression still fails after retries exhaust."""
    monkeypatch.setattr(
        canary, "_post", _scripted_post(_CANONICAL_PLUS_STATUS + ["universe"])
    )
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_canonical_handles_with_retry(
            "https://example/mcp", 5.0, retries=3, delay=0.0, _sleep=lambda _: None
        )
    assert exc.value.code == 4


def _initialize_urlopen(server_name: str):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": server_name, "version": "0.1.0"},
                    },
                }
            ).encode()

    return lambda *args, **kwargs: Response()


def test_probe_result_accepts_exact_expected_public_name(monkeypatch):
    monkeypatch.setattr(
        canary.urllib.request,
        "urlopen",
        _initialize_urlopen("TinyAssets"),
    )

    canary.probe_result(
        "https://example/mcp",
        5.0,
        expected_name="TinyAssets",
    )


def test_probe_result_rejects_case_drift_in_public_name(monkeypatch):
    monkeypatch.setattr(
        canary.urllib.request,
        "urlopen",
        _initialize_urlopen("tinyassets"),
    )

    with pytest.raises(canary.CanaryError) as exc:
        canary.probe_result(
            "https://example/mcp",
            5.0,
            expected_name="TinyAssets",
        )

    assert exc.value.code == 1
    assert "expected 'TinyAssets'" in exc.value.msg
    assert "got 'tinyassets'" in exc.value.msg

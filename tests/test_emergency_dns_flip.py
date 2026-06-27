from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import emergency_dns_flip as dns_flip  # noqa: E402


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None, payload=None):
        self.calls.append({
            "method": method,
            "path": path,
            "params": params,
            "payload": payload,
        })
        if not self.responses:
            return {}
        return self.responses.pop(0)


def test_upsert_dns_record_creates_when_no_record_exists():
    client = FakeClient([{"result": []}, {"result": {"id": "new-record"}}])

    result = dns_flip.upsert_dns_record(
        client,
        zone_id="zone123",
        record_type="CNAME",
        name="mcp.tinyassets.io",
        content="fallback.example.net",
        ttl=1,
        proxied=True,
        comment="emergency flip",
        dry_run=False,
    )

    assert result.action == "created"
    assert client.calls[0]["method"] == "GET"
    assert client.calls[0]["path"] == "/zones/zone123/dns_records"
    assert client.calls[0]["params"] == {"type": "CNAME", "name": "mcp.tinyassets.io"}
    assert client.calls[1]["method"] == "POST"
    assert client.calls[1]["payload"] == {
        "type": "CNAME",
        "name": "mcp.tinyassets.io",
        "content": "fallback.example.net",
        "ttl": 1,
        "proxied": True,
        "comment": "emergency flip",
    }


def test_upsert_dns_record_patches_single_existing_record():
    client = FakeClient([
        {"result": [{"id": "record123"}]},
        {"result": {"id": "record123"}},
    ])

    result = dns_flip.upsert_dns_record(
        client,
        zone_id="zone123",
        record_type="CNAME",
        name="mcp.tinyassets.io",
        content="new-target.example.net",
        ttl=1,
        proxied=False,
        comment=None,
        dry_run=False,
    )

    assert result.action == "updated"
    assert client.calls[1]["method"] == "PATCH"
    assert client.calls[1]["path"] == "/zones/zone123/dns_records/record123"
    assert client.calls[1]["payload"]["content"] == "new-target.example.net"
    assert client.calls[1]["payload"]["proxied"] is False
    assert "comment" not in client.calls[1]["payload"]


def test_upsert_dns_record_dry_run_does_not_mutate():
    client = FakeClient([{"result": []}])

    result = dns_flip.upsert_dns_record(
        client,
        zone_id="zone123",
        record_type="A",
        name="api.tinyassets.io",
        content="203.0.113.10",
        ttl=300,
        proxied=None,
        comment=None,
        dry_run=True,
    )

    assert result.action == "would_create"
    assert [call["method"] for call in client.calls] == ["GET"]


def test_duplicate_dns_record_match_fails_closed():
    client = FakeClient([{"result": [{"id": "one"}, {"id": "two"}]}])

    with pytest.raises(dns_flip.CloudflareApiError, match="matched 2"):
        dns_flip.upsert_dns_record(
            client,
            zone_id="zone123",
            record_type="CNAME",
            name="mcp.tinyassets.io",
            content="fallback.example.net",
            ttl=1,
            proxied=True,
            comment=None,
            dry_run=False,
        )

    assert [call["method"] for call in client.calls] == ["GET"]


def test_delete_worker_route_deletes_exact_pattern_match():
    client = FakeClient([
        {"result": [
            {"id": "route-1", "pattern": "tinyassets.io/mcp*", "script": "tinyassets-mcp-router"},
            {"id": "route-2", "pattern": "tinyassets.io/catalog*", "script": "catalog"},
        ]},
        {"result": {"id": "route-1"}},
    ])

    result = dns_flip.delete_worker_route(
        client,
        zone_id="zone123",
        pattern="tinyassets.io/mcp*",
        dry_run=False,
    )

    assert result.action == "deleted"
    assert client.calls[1]["method"] == "DELETE"
    assert client.calls[1]["path"] == "/zones/zone123/workers/routes/route-1"


# ---------------------------------------------------------------------------
# CLI dry-run tests — exercise _run() via mocked make_cloudflare_client
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent
_EMERGENCY_DNS_WORKFLOW = _REPO / ".github" / "workflows" / "emergency-dns.yml"


def _cli_dry_run(monkeypatch, action, extra_argv=None):
    """Run the CLI in dry-run mode with a mocked client. Returns (rc, calls)."""
    calls = []

    class CapturingClient:
        def request(self, method, path, *, params=None, payload=None):
            calls.append({"method": method, "path": path, "payload": payload})
            if method == "GET" and "dns_records" in path:
                return {"result": []}
            if method == "GET" and "workers/routes" in path:
                return {"result": []}
            if method == "GET" and path.startswith("/zones/"):
                return {"result": {"id": "zone-abc"}}
            return {"result": {}}

    mock_client = CapturingClient()

    argv = [
        "emergency_dns_flip.py",
        "--action", action,
        "--zone-id", "zone-abc",
        # no --apply → dry-run
    ] + (extra_argv or [])

    monkeypatch.setattr(sys, "argv", argv)
    with patch(
        "emergency_dns_flip.make_cloudflare_client", return_value=mock_client
    ):
        rc = dns_flip.main()

    return rc, calls


class TestCLIDryRun:
    def test_upsert_record_dry_run_exits_0(self, monkeypatch, capsys):
        rc, calls = _cli_dry_run(
            monkeypatch,
            "upsert-record",
            ["--name", "mcp.tinyassets.io", "--content", "fallback.example.net"],
        )
        assert rc == 0

    def test_upsert_record_dry_run_no_mutating_calls(self, monkeypatch, capsys):
        _, calls = _cli_dry_run(
            monkeypatch,
            "upsert-record",
            ["--name", "mcp.tinyassets.io", "--content", "fallback.example.net"],
        )
        mutating = [c for c in calls if c["method"] in ("POST", "PATCH", "PUT", "DELETE")]
        assert mutating == [], f"Unexpected mutating calls in dry-run: {mutating}"

    def test_upsert_record_dry_run_prints_dry_run(self, monkeypatch, capsys):
        _cli_dry_run(
            monkeypatch,
            "upsert-record",
            ["--name", "mcp.tinyassets.io", "--content", "fallback.example.net"],
        )
        out = capsys.readouterr().out
        assert "dry" in out.lower(), f"Expected 'dry' in output, got: {out!r}"

    def test_upsert_worker_route_dry_run_no_mutating_calls(self, monkeypatch, capsys):
        _, calls = _cli_dry_run(monkeypatch, "upsert-worker-route")
        mutating = [c for c in calls if c["method"] in ("POST", "PATCH", "PUT", "DELETE")]
        assert mutating == []

    def test_delete_record_dry_run_no_mutating_calls(self, monkeypatch, capsys):
        _, calls = _cli_dry_run(
            monkeypatch,
            "delete-record",
            ["--name", "mcp.tinyassets.io"],
        )
        mutating = [c for c in calls if c["method"] in ("POST", "PATCH", "PUT", "DELETE")]
        assert mutating == []


# ---------------------------------------------------------------------------
# emergency-dns.yml structural tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _YAML_AVAILABLE, reason="pyyaml not installed")
class TestEmergencyDnsTinyAssets:
    def _load(self):
        return yaml.safe_load(_EMERGENCY_DNS_WORKFLOW.read_text(encoding="utf-8"))

    def _triggers(self, wf):
        return wf.get(True, {}) or {}

    def test_workflow_parses(self):
        self._load()

    def test_has_workflow_dispatch(self):
        wf = self._load()
        assert "workflow_dispatch" in self._triggers(wf)

    def test_apply_input_defaults_false(self):
        wf = self._load()
        dispatch = self._triggers(wf).get("workflow_dispatch") or {}
        apply_input = (dispatch.get("inputs") or {}).get("apply") or {}
        assert apply_input.get("default") is False, (
            "apply input must default to false so manual triggers are safe dry-runs"
        )

    def test_has_action_input(self):
        wf = self._load()
        dispatch = self._triggers(wf).get("workflow_dispatch") or {}
        inputs = dispatch.get("inputs") or {}
        assert "action" in inputs

    def test_no_secrets_in_workflow_body(self):
        text = _EMERGENCY_DNS_WORKFLOW.read_text(encoding="utf-8")
        assert "CLOUDFLARE_API_TOKEN" not in text or "secrets.CLOUDFLARE_API_TOKEN" in text, (
            "Token must be read from GitHub secrets, not hardcoded"
        )

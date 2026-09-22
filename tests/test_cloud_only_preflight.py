"""Focused tests for scripts/cloud_only_preflight.py.

No real API calls: every provider read is monkeypatched at the module's single
read-only HTTP helper. These assert the script's *bounds* -- read-only, no shell,
sanitized output, missing permission is `unknown` and never a pass -- because
those bounds are the reason the script is allowed to hold hosted credentials.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "cloud_only_preflight",
    Path(__file__).resolve().parents[1] / "scripts" / "cloud_only_preflight.py",
)
pf = importlib.util.module_from_spec(_SPEC)
sys.modules["cloud_only_preflight"] = pf
_SPEC.loader.exec_module(pf)


CI_ENV = {"CI": "true"}


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- bounds: read-only, no shell, no arbitrary exec -----------------------

def test_container_probe_argv_is_fixed_and_shell_free():
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _Completed(stdout="OK:123456789")

    pf.probe_container_metadata("svc", runner=runner)
    argv = seen["argv"]
    assert argv[:4] == ["docker", "exec", "svc", "python"]
    assert argv[4] == "-c"
    # The probe body is the module literal, not anything caller-derived.
    assert argv[5] == pf._PROBE_SOURCE
    assert pf.METADATA_URL in argv[5]
    assert "shell" not in seen["kwargs"], "probe must never run through a shell"


def test_probe_source_is_a_module_literal_not_caller_input():
    # Nothing in the probe body is formattable by a caller at call time.
    before = pf._PROBE_SOURCE
    pf.probe_container_metadata("svc", runner=lambda *a, **k: _Completed(stdout="OK:1"))
    assert pf._PROBE_SOURCE == before


def test_no_mutating_http_verb_anywhere_in_the_script():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "cloud_only_preflight.py"
    ).read_text(encoding="utf-8")
    for verb in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "method='POST'"):
        assert verb not in source, f"preflight must be read-only; found {verb}"
    assert 'method="GET"' in source


# --- bounds: missing permission is unknown, never pass --------------------

@pytest.mark.parametrize(
    "reason_code",
    ["http_401", "http_403", "unreachable", "bad_response"],
)
def test_droplet_permission_failure_is_unknown_not_pass(monkeypatch, reason_code):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, reason_code))
    result = pf.resolve_expected_droplet("tok", "1.2.3.4")
    assert result["verdict"] == pf.UNKNOWN
    assert result["verdict"] != pf.PASS
    assert reason_code in result["reason"]


def test_missing_secret_is_unknown_for_every_fact():
    assert pf.resolve_expected_droplet(None, None)["verdict"] == pf.UNKNOWN
    assert pf.audit_tunnel_connectors(None, "a", "t", {"1.2.3.4"})["verdict"] == pf.UNKNOWN
    assert pf.audit_tunnel_connectors("tok", None, None, {"1.2.3.4"})["verdict"] == pf.UNKNOWN
    assert pf.audit_public_dns("tok", None, "tinyassets.io")["verdict"] == pf.UNKNOWN


def test_unsuccessful_cloudflare_payload_is_unknown(monkeypatch):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: ({"success": False}, "ok"))
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"1.2.3.4"})
    assert result["verdict"] == pf.UNKNOWN


def test_run_without_ci_refuses_and_reads_nothing(monkeypatch, capsys):
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: pytest.fail("no provider read off hosted CI")
    )
    code = pf.run([], env={"DO_API_TOKEN": "tok"})
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == pf.UNKNOWN
    assert payload["reason"] == "not_hosted_ci"


# --- bounds: sanitized output ---------------------------------------------

def test_output_never_contains_ids_addresses_or_tokens(monkeypatch, capsys):
    def fake_get_json(url, headers, timeout=15.0):
        if url.startswith(pf.DO_DROPLETS_URL[:40]):
            return (
                {
                    "droplets": [
                        {
                            "id": 987654321,
                            "networks": {"v4": [{"ip_address": "203.0.113.7"}]},
                        }
                    ]
                },
                "ok",
            )
        if "cfd_tunnel" in url:
            return ({"success": True, "result": [{"origin_ip": "203.0.113.7"}]}, "ok")
        return (
            {
                "success": True,
                "result": [
                    {"type": "CNAME", "content": "abc-def.cfargotunnel.com", "proxied": True}
                ],
            },
            "ok",
        )

    monkeypatch.setattr(pf, "_get_json", fake_get_json)
    code = pf.run(
        ["--skip-container-probe"],
        env={
            "CI": "true",
            "DO_API_TOKEN": "secret-do-token",
            "DO_DROPLET_HOST": "203.0.113.7",
            "CLOUDFLARE_API_TOKEN": "secret-cf-token",
            "CLOUDFLARE_ACCOUNT_ID": "acct-1",
            "CLOUDFLARE_TUNNEL_ID": "tunnel-1",
            "CLOUDFLARE_ZONE_ID": "zone-1",
        },
    )
    out = capsys.readouterr().out
    assert code == 0
    for leak in (
        "secret-do-token",
        "secret-cf-token",
        "203.0.113.7",
        "987654321",
        "cfargotunnel.com",
        "acct-1",
        "tunnel-1",
    ):
        assert leak not in out, f"preflight leaked {leak!r}"
    payload = json.loads(out)
    assert payload["enforcement"] == "none"
    assert payload["boundary_closed"] is False
    assert payload["status"] == pf.PASS


def test_sanitize_strips_internal_address_set():
    raw = [pf.fact("expected_droplet", pf.PASS, "resolved", _addresses=["203.0.113.7"])]
    clean = pf.sanitize(raw)
    assert "_addresses" not in clean[0]
    assert "203.0.113.7" not in json.dumps(clean)


def test_instance_id_is_reported_only_as_a_digest():
    result = pf.probe_container_metadata(
        "svc", runner=lambda *a, **k: _Completed(stdout="OK:987654321")
    )
    assert result["instance_digest"] == pf.digest("987654321")
    assert "987654321" not in json.dumps(result)


# --- verdict semantics ----------------------------------------------------

def test_off_droplet_connector_is_a_refusal_with_counts_only(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {
                "success": True,
                "result": [{"origin_ip": "203.0.113.7"}, {"origin_ip": "198.51.100.9"}],
            },
            "ok",
        ),
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.REFUSE
    assert result["connectors_out_of_set"] == 1
    assert result["connectors_in_set"] == 1
    assert "198.51.100.9" not in json.dumps(result)


def test_metadata_unreachable_in_container_is_a_refusal_not_unknown():
    result = pf.probe_container_metadata(
        "svc", runner=lambda *a, **k: _Completed(stdout="UNREACHABLE:URLError")
    )
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "metadata_unreachable_in_container"


def test_docker_absent_is_unknown():
    def runner(*a, **k):
        raise FileNotFoundError

    assert pf.probe_container_metadata("svc", runner=runner)["verdict"] == pf.UNKNOWN


def test_probe_timeout_is_unknown():
    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=30)

    assert pf.probe_container_metadata("svc", runner=runner)["verdict"] == pf.UNKNOWN


def test_unproxied_direct_dns_target_is_a_refusal(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {
                "success": True,
                "result": [
                    {"type": "A", "content": "198.51.100.9", "proxied": False}
                ],
            },
            "ok",
        ),
    )
    result = pf.audit_public_dns("tok", "zone", "tinyassets.io")
    assert result["verdict"] == pf.REFUSE
    assert "198.51.100.9" not in json.dumps(result)


def test_any_unknown_downgrades_overall_status(monkeypatch, capsys):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, "http_403"))
    code = pf.run(["--skip-container-probe"], env=dict(CI_ENV, DO_API_TOKEN="tok"))
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == pf.UNKNOWN

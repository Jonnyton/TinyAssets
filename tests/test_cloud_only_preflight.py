"""Focused tests for scripts/cloud_only_preflight.py.

No real API calls: every provider read is monkeypatched at the module's single
read-only HTTP helper. These assert the script's *bounds* -- read-only, no
shell, no redirects, bounded reads, sanitized output, missing permission is
`unknown` and never a pass -- because those bounds are the reason the script is
allowed to hold hosted credentials.

A second group asserts the specific false positives the 2026-09-22 review
reproduced (`docs/reviews/2026-09-22-cloud-only-preflight-review.md`): an
unmatched host resolving to the only visible droplet, an empty connector list
reading as clean, a skipped required fact permitting an overall pass, and
`origin_ip` read off the wrong nesting level of the Cloudflare response.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cloud_only_preflight.py"
_SPEC = importlib.util.spec_from_file_location("cloud_only_preflight", _SCRIPT)
pf = importlib.util.module_from_spec(_SPEC)
sys.modules["cloud_only_preflight"] = pf
_SPEC.loader.exec_module(pf)


CI_ENV = {"CI": "true"}


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _target():
    return pf.RemoteProbeTarget("198.51.100.8", "deploy", "/k/key", "/k/known_hosts")


def _ok_runner(stdout):
    return lambda *a, **k: _Completed(stdout=stdout)


# =========================================================================
# bounds: read-only, no shell, no arbitrary exec
# =========================================================================

def test_container_probe_argv_is_fixed_and_shell_free():
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _Completed(stdout="OK:123456789")

    pf.probe_container_metadata("svc", _target(), runner=runner)
    argv = seen["argv"]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    # The remote command is the fixed literal, quoted, not caller-derived.
    remote = argv[-1]
    assert remote.startswith("docker exec svc python -c ")
    assert pf.METADATA_URL in remote
    assert "shell" not in seen["kwargs"], "probe must never run through a shell"


def test_probe_source_is_a_module_literal_not_caller_input():
    before = pf._PROBE_SOURCE
    pf.probe_container_metadata("svc", _target(), runner=_ok_runner("OK:1"))
    assert pf._PROBE_SOURCE == before


def test_probe_rejects_a_service_name_with_shell_metacharacters():
    def runner(*a, **k):
        pytest.fail("a malformed service name must never reach an argv")

    result = pf.probe_container_metadata("svc; rm -rf /", _target(), runner=runner)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "malformed_container_service"


def test_probe_rejects_ssh_target_with_shell_metacharacters():
    target, reason, _ = pf.resolve_remote_probe_target(
        {"DO_DROPLET_HOST": "host && curl evil", "DO_SSH_USER": "deploy"}
    )
    assert target is None
    assert reason == "malformed_ssh_target"


def test_no_mutating_http_verb_anywhere_in_the_script():
    source = _SCRIPT.read_text(encoding="utf-8")
    for verb in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "method='POST'"):
        assert verb not in source, f"preflight must be read-only; found {verb}"
    assert 'method="GET"' in source


# =========================================================================
# bounds: no redirects, no proxy inheritance, bounded reads
# =========================================================================

def test_opener_refuses_redirects_and_ignores_ambient_proxies(monkeypatch):
    handlers = {type(h).__name__ for h in pf._OPENER.handlers}
    assert "_NoRedirect" in handlers
    assert pf._NoRedirect().redirect_request(
        None, None, 302, "Found", {}, "https://elsewhere.example/"
    ) is None
    # urllib omits an empty ProxyHandler from handlers: it has no methods to
    # register. Exercise a freshly constructed real opener with hostile ambient
    # proxies instead of asserting an implementation detail of the handler list.
    import runpy

    monkeypatch.setattr(pf.urllib.request, "getproxies", lambda: {
        "https": "http://synthetic-proxy.invalid:9999",
    })
    isolated = runpy.run_path(str(_SCRIPT))

    class TransportReached(Exception):
        pass

    def intercept(_handler, request):
        assert not request.has_proxy()
        raise TransportReached

    monkeypatch.setattr(pf.urllib.request.HTTPSHandler, "https_open", intercept)
    with pytest.raises(TransportReached):
        isolated["_OPENER"].open("https://synthetic-api.invalid/")


def test_redirect_response_is_unknown_not_followed(monkeypatch):
    def raiser(req, timeout=None):
        raise pf.urllib.error.HTTPError(req.full_url, 302, "Found", {}, None)

    monkeypatch.setattr(pf._OPENER, "open", raiser)
    payload, reason = pf._get_json("https://api.example/x", {"Authorization": "Bearer t"})
    assert payload is None
    assert reason == "redirect_refused"


def test_oversized_body_is_unknown_not_a_truncated_parse(monkeypatch):
    class _Resp:
        status = 200

        def read(self, n=None):
            return b"{" + b"x" * (pf.MAX_RESPONSE_BYTES + 8)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pf._OPENER, "open", lambda req, timeout=None: _Resp())
    payload, reason = pf._get_json("https://api.example/x", {})
    assert payload is None
    assert reason == "response_too_large"


def test_non_object_json_payload_is_unknown(monkeypatch):
    class _Resp:
        status = 200

        def read(self, n=None):
            return b"[1, 2, 3]"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pf._OPENER, "open", lambda req, timeout=None: _Resp())
    payload, reason = pf._get_json("https://api.example/x", {})
    assert payload is None
    assert reason == "unexpected_payload_shape"


# =========================================================================
# REVIEW FINDING 1: unmatched host must never resolve to the only droplet
# =========================================================================

def test_unmatched_host_with_a_sole_visible_droplet_is_unknown_not_pass(monkeypatch):
    """The exact synthetic case the review reproduced as a PASS."""
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {
                "droplets": [
                    {"id": 111, "networks": {"v4": [{"ip_address": "203.0.113.7"}]}}
                ],
                "meta": {"total": 1},
            },
            "ok",
        ),
    )
    result = pf.resolve_expected_droplet("tok", "198.51.100.8")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "host_hint_matched_no_droplet"
    assert "_instance_tag" not in result


def test_exact_inventory_match_resolves(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {
                "droplets": [
                    {"id": 111, "networks": {"v4": [{"ip_address": "203.0.113.7"}]}},
                    {"id": 222, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}},
                ],
                "meta": {"total": 2},
            },
            "ok",
        ),
    )
    result = pf.resolve_expected_droplet("tok", "198.51.100.8")
    assert result["verdict"] == pf.PASS
    assert result["_instance_tag"] == pf.correlation_tag("222")


def test_host_matching_two_droplets_is_unknown(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {
                "droplets": [
                    {"id": 111, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}},
                    {"id": 222, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}},
                ],
                "meta": {"total": 2},
            },
            "ok",
        ),
    )
    result = pf.resolve_expected_droplet("tok", "198.51.100.8")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "host_hint_matched_multiple_droplets"


def test_missing_host_hint_is_unknown_with_no_fallback(monkeypatch):
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: pytest.fail("must not read without a host")
    )
    result = pf.resolve_expected_droplet("tok", None)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "missing_DO_DROPLET_HOST"


def test_non_ip_host_hint_is_unknown_not_silently_unmatched(monkeypatch):
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: pytest.fail("must not read on a bad host")
    )
    result = pf.resolve_expected_droplet("tok", "droplet.example.com")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "do_droplet_host_not_an_ip_literal"


# --- malformed / incomplete droplet inventory -----------------------------

@pytest.mark.parametrize(
    "payload,reason",
    [
        ({"droplets": {}, "meta": {"total": 1}}, "malformed_droplet_list"),
        ({"droplets": [], "meta": {"total": 0}}, "no_droplets_visible"),
        (
            {"droplets": [{"id": 1, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}}],
             "meta": {"total": 9}},
            "do_api_incomplete_page",
        ),
        (
            {"droplets": [{"id": 1, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}}]},
            "do_api_incomplete_page",
        ),
        (
            {"droplets": ["not-an-object"], "meta": {"total": 1}},
            "malformed_droplet_record",
        ),
        (
            {"droplets": [{"id": 1, "networks": "nope"}], "meta": {"total": 1}},
            "malformed_droplet_record",
        ),
        (
            {"droplets": [{"networks": {"v4": [{"ip_address": "198.51.100.8"}]}}],
             "meta": {"total": 1}},
            "malformed_droplet_record",
        ),
        (
            {"droplets": [{"id": 1, "networks": {"v4": [{"ip_address": 12345}]}}],
             "meta": {"total": 1}},
            "malformed_droplet_record",
        ),
    ],
)
def test_malformed_or_incomplete_droplet_inventory_is_unknown(monkeypatch, payload, reason):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (payload, "ok"))
    result = pf.resolve_expected_droplet("tok", "198.51.100.8")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == reason


# =========================================================================
# REVIEW FINDING 2: an empty connector list is not success
# =========================================================================

def test_empty_connector_list_is_unknown_not_pass(monkeypatch):
    """The exact synthetic case the review reproduced as a PASS."""
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: ({"success": True, "result": [], "result_info": {"total_count": 0}}, "ok"),
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "no_connectors_reported"


def test_clients_with_empty_conns_arrays_are_unknown_not_pass(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {"success": True, "result": [{"id": "c1", "conns": []}],
             "result_info": {"total_count": 1}},
            "ok",
        ),
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "no_active_connections_reported"


# --- REVIEW FINDING: origin_ip lives in conns[], per the official API docs -

def _cf_connections(conns_origins, total=None):
    """A response in the documented shape: result[] -> client -> conns[] -> origin_ip.

    Per developers.cloudflare.com .../tunnels/cloudflared/connections/methods/get/
    `origin_ip` is a field of each `conns` entry, never of the client object.
    """
    result = [
        {
            "id": f"client-{i}",
            "arch": "linux_amd64",
            "version": "2025.1.0",
            "conns": [
                {"id": f"conn-{i}-{j}", "client_id": f"client-{i}",
                 "colo_name": "sjc01", "origin_ip": origin}
                for j, origin in enumerate(origins)
            ],
        }
        for i, origins in enumerate(conns_origins)
    ]
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": result,
        "result_info": {
            "count": len(result),
            "page": 1,
            "per_page": 100,
            "total_count": len(result) if total is None else total,
        },
    }


def test_origin_ip_is_read_from_the_nested_conns_array(monkeypatch):
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: (_cf_connections([["203.0.113.7", "203.0.113.7"]]), "ok")
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.PASS
    assert result["connectors_in_set"] == 2
    assert result["connectors_out_of_set"] == 0


def test_origin_ip_only_at_the_client_level_is_unknown_not_pass(monkeypatch):
    """The pre-fix shape. A client object with a top-level origin_ip and no
    `conns` must not be readable as a clean connector."""
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {"success": True, "result": [{"id": "c1", "origin_ip": "203.0.113.7"}],
             "result_info": {"total_count": 1}},
            "ok",
        ),
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "connector_without_conns"


def test_off_droplet_connector_is_a_refusal_with_counts_only(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (_cf_connections([["203.0.113.7"], ["198.51.100.9"]]), "ok"),
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.REFUSE
    assert result["connectors_out_of_set"] == 1
    assert result["connectors_in_set"] == 1
    assert "198.51.100.9" not in json.dumps(result)


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({"success": False, "result": []}, "cf_api_unsuccessful"),
        ({"result": [{"conns": []}]}, "cf_api_unsuccessful"),
        ({"success": True, "result": "nope"}, "cf_api_no_result"),
        ({"success": True, "result": ["not-an-object"],
          "result_info": {"total_count": 1}}, "malformed_connector_record"),
        ({"success": True, "result": [{"conns": ["nope"]}],
          "result_info": {"total_count": 1}}, "malformed_connection_record"),
        ({"success": True, "result": [{"conns": [{"colo_name": "sjc01"}]}],
          "result_info": {"total_count": 1}}, "connection_without_origin"),
        ({"success": True, "result": [{"conns": [{"origin_ip": None}]}],
          "result_info": {"total_count": 1}}, "connection_without_origin"),
    ],
)
def test_malformed_connector_payloads_are_unknown(monkeypatch, payload, reason):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (payload, "ok"))
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == reason


def test_truncated_connector_page_is_unknown_not_pass(monkeypatch):
    """An off-droplet connector could sit on the unread page."""
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: (_cf_connections([["203.0.113.7"]], total=7), "ok")
    )
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "cf_api_incomplete_page"


def test_missing_result_info_is_incomplete_not_assumed_whole(monkeypatch):
    payload = _cf_connections([["203.0.113.7"]])
    payload.pop("result_info")
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (payload, "ok"))
    result = pf.audit_tunnel_connectors("tok", "acct", "tun", {"203.0.113.7"})
    assert result["verdict"] == pf.UNKNOWN


# =========================================================================
# REVIEW FINDING 3: identity comparison, and no skipping a required fact
# =========================================================================

def test_observed_identity_is_compared_with_expected(monkeypatch):
    observed = pf.probe_container_metadata(
        "svc", _target(), runner=_ok_runner("OK:222")
    )
    expected = pf.fact(
        "expected_droplet", pf.PASS, "resolved", _instance_tag=pf.correlation_tag("222")
    )
    result = pf.compare_cloud_identity(observed, expected)
    assert result["verdict"] == pf.PASS
    assert result["identity_match"] is True


def test_identity_mismatch_is_a_refusal():
    observed = pf.probe_container_metadata("svc", _target(), runner=_ok_runner("OK:111"))
    expected = pf.fact(
        "expected_droplet", pf.PASS, "resolved", _instance_tag=pf.correlation_tag("222")
    )
    result = pf.compare_cloud_identity(observed, expected)
    assert result["verdict"] == pf.REFUSE
    assert result["identity_match"] is False


@pytest.mark.parametrize(
    "observed,expected,reason",
    [
        (
            pf.unknown("container_metadata", "x", "y"),
            pf.fact("expected_droplet", PASS := "pass", "resolved", _instance_tag="t"),
            "container_identity_unknown",
        ),
        (
            pf.fact("container_metadata", "pass", "reachable", _instance_tag="t"),
            pf.unknown("expected_droplet", "x", "y"),
            "expected_identity_unknown",
        ),
        (
            pf.fact("container_metadata", "refuse", "metadata_unreachable_in_container"),
            pf.fact("expected_droplet", "pass", "resolved", _instance_tag="t"),
            "no_observed_identity",
        ),
    ],
)
def test_identity_comparison_stays_unknown_when_either_side_is(observed, expected, reason):
    result = pf.compare_cloud_identity(observed, expected)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == reason


def test_skipping_the_container_probe_reports_unknown_and_cannot_pass(monkeypatch, capsys):
    """The review's third finding: --skip-container-probe removed the fact entirely
    and permitted an overall PASS."""
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, "http_403"))
    code = pf.run(["--skip-container-probe"], env=dict(CI_ENV))
    payload = json.loads(capsys.readouterr().out)
    names = [f["fact"] for f in payload["facts"]]
    assert "container_metadata" in names, "a required fact is never skipped out"
    skipped = next(f for f in payload["facts"] if f["fact"] == "container_metadata")
    assert skipped["verdict"] == pf.UNKNOWN
    assert skipped["reason"] == "container_probe_skipped_by_operator"
    assert skipped["requirement"]
    assert payload["status"] == pf.UNKNOWN
    assert code == 2


# =========================================================================
# REVIEW FINDING 4: the local Docker daemon is not production
# =========================================================================

def test_no_local_docker_probe_path_exists():
    captured = []

    def runner(argv, **kwargs):
        captured.append(argv)
        assert not kwargs.get("shell", False)
        return _Completed(stdout="OK:42")

    pf.probe_container_metadata("svc", _target(), runner=runner)
    assert len(captured) == 1
    assert captured[0][0] == "ssh"
    # Docker appears only in the fixed remote command sent through SSH.
    assert captured[0][-1].startswith("docker exec svc python -c ")


def test_unwired_remote_path_is_unknown_and_never_falls_back(monkeypatch):
    def runner(*a, **k):
        pytest.fail("no probe may run without a wired remote path")

    result = pf.probe_container_metadata(
        "svc", None, "ssh_key_not_provisioned", "wire it", runner=runner,
    )
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "ssh_key_not_provisioned"
    assert result["requirement"] == "wire it"


@pytest.mark.parametrize(
    "env,reason",
    [
        ({}, "missing_DO_DROPLET_HOST_or_DO_SSH_USER"),
        ({"DO_DROPLET_HOST": "198.51.100.8"}, "missing_DO_DROPLET_HOST_or_DO_SSH_USER"),
        (
            {"DO_DROPLET_HOST": "198.51.100.8", "DO_SSH_USER": "deploy"},
            "ssh_key_not_provisioned",
        ),
        (
            {"DO_DROPLET_HOST": "198.51.100.8", "DO_SSH_USER": "deploy",
             "DO_SSH_KEY_PATH": "/k/key"},
            "known_hosts_not_provisioned",
        ),
    ],
)
def test_remote_probe_path_reports_the_precise_missing_requirement(env, reason):
    target, got, requirement = pf.resolve_remote_probe_target(
        env, exists=lambda p: p == "/k/key"
    )
    assert target is None
    assert got == reason
    assert requirement, "a typed unknown must state what would resolve it"


def test_remote_probe_path_resolves_from_existing_deploy_secrets():
    target, reason, _ = pf.resolve_remote_probe_target(
        {
            "DO_DROPLET_HOST": "198.51.100.8",
            "DO_SSH_USER": "deploy",
            "DO_SSH_KEY_PATH": "/k/key",
            "DO_SSH_KNOWN_HOSTS": "/k/known_hosts",
        },
        exists=lambda p: True,
    )
    assert reason == "ok"
    assert target is not None


def test_probe_report_input_must_match_the_fixed_probe_grammar():
    def opener(path, encoding=None):
        import io

        return io.StringIO("the droplet is fine, trust me")

    result = pf.read_probe_report("report.txt", opener=opener)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "probe_report_malformed"


def test_valid_probe_report_is_accepted_and_marked_as_reported():
    def opener(path, encoding=None):
        import io

        return io.StringIO("OK:222\n")

    result = pf.read_probe_report("report.txt", opener=opener)
    assert result["verdict"] == pf.PASS
    assert result["evidence_source"] == "reported"
    assert result["_instance_tag"] == pf.correlation_tag("222")


def test_unreadable_probe_report_is_unknown():
    def opener(path, encoding=None):
        raise OSError("nope")

    assert pf.read_probe_report("missing.txt", opener=opener)["verdict"] == pf.UNKNOWN


@pytest.mark.parametrize(
    "stdout,reason",
    [
        ("OK:", "empty_id"),
        ("OK:not-a-number", "malformed_instance_id"),
        ("something else entirely", "unparsed_probe_output"),
        ("", "unparsed_probe_output"),
    ],
)
def test_malformed_probe_output_is_unknown(stdout, reason):
    result = pf.probe_container_metadata("svc", _target(), runner=_ok_runner(stdout))
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == reason


def test_metadata_unreachable_in_container_is_a_refusal_not_unknown():
    result = pf.probe_container_metadata(
        "svc", _target(), runner=_ok_runner("UNREACHABLE:URLError")
    )
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "metadata_unreachable_in_container"


def test_ssh_client_absent_is_unknown():
    def runner(*a, **k):
        raise FileNotFoundError

    result = pf.probe_container_metadata("svc", _target(), runner=runner)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "ssh_client_unavailable"


def test_probe_timeout_is_unknown():
    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=45)

    assert pf.probe_container_metadata("svc", _target(), runner=runner)["verdict"] == pf.UNKNOWN


def test_probe_failure_stderr_is_never_echoed():
    runner = lambda *a, **k: _Completed(  # noqa: E731
        returncode=255, stderr="Permission denied (publickey) for deploy@198.51.100.8"
    )
    result = pf.probe_container_metadata("svc", _target(), runner=runner)
    assert result["verdict"] == pf.UNKNOWN
    assert "198.51.100.8" not in json.dumps(result)
    assert "publickey" not in json.dumps(result)


# =========================================================================
# REVIEW FINDING 5: DNS must bind the selected tunnel and the Worker route
# =========================================================================

def _cf_records(records):
    return {
        "success": True,
        "result": records,
        "result_info": {"count": len(records), "total_count": len(records)},
    }


def test_internal_origin_bound_to_the_selected_tunnel_passes(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            _cf_records([{"type": "CNAME", "content": "tun-1.cfargotunnel.com", "proxied": True}]),
            "ok",
        ),
    )
    result = pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", "tun-1")
    assert result["verdict"] == pf.PASS
    assert result["bound_to_selected_tunnel"] is True


def test_a_different_tunnel_cname_is_a_refusal_not_a_pass(monkeypatch):
    """The review's finding: any tunnel CNAME was accepted, not the selected one."""
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            _cf_records([{"type": "CNAME", "content": "OTHER-TUNNEL.cfargotunnel.com"}]),
            "ok",
        ),
    )
    result = pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", "tun-1")
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "bound_to_a_different_tunnel"
    assert result["bound_to_selected_tunnel"] is False


def test_internal_origin_name_is_required_and_the_apex_is_not_substituted():
    result = pf.audit_internal_origin_dns("tok", "zone", None, "tun-1")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "missing_internal_origin_name"
    assert "TINYASSETS_INTERNAL_ORIGIN_NAME" in result["requirement"]


def test_internal_origin_without_a_selected_tunnel_id_is_unknown():
    result = pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", None)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "missing_CLOUDFLARE_TUNNEL_ID"


def test_unproxied_direct_dns_target_is_a_refusal(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            _cf_records([{"type": "A", "content": "198.51.100.9", "proxied": False}]),
            "ok",
        ),
    )
    result = pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", "tun-1")
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "not_a_tunnel_cname"
    assert "198.51.100.9" not in json.dumps(result)


def test_truncated_dns_page_is_unknown(monkeypatch):
    payload = _cf_records([{"type": "CNAME", "content": "tun-1.cfargotunnel.com"}])
    payload["result_info"]["total_count"] = 4
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (payload, "ok"))
    result = pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", "tun-1")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "cf_api_incomplete_page"


def test_worker_route_bound_to_the_expected_script_passes(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {"success": True, "result": [{"pattern": "tinyassets.io/*", "script": "ta-router"}]},
            "ok",
        ),
    )
    result = pf.audit_public_worker_route("tok", "zone", "tinyassets.io", "ta-router")
    assert result["verdict"] == pf.PASS
    assert result["bound_to_expected_worker"] is True


def test_worker_route_bound_to_another_script_is_a_refusal(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {"success": True, "result": [{"pattern": "tinyassets.io/*", "script": "someone-else"}]},
            "ok",
        ),
    )
    result = pf.audit_public_worker_route("tok", "zone", "tinyassets.io", "ta-router")
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "route_bound_to_unexpected_script"


def test_worker_route_for_another_hostname_does_not_count(monkeypatch):
    monkeypatch.setattr(
        pf,
        "_get_json",
        lambda *a, **k: (
            {"success": True, "result": [{"pattern": "other.example/*", "script": "ta-router"}]},
            "ok",
        ),
    )
    result = pf.audit_public_worker_route("tok", "zone", "tinyassets.io", "ta-router")
    assert result["verdict"] == pf.REFUSE
    assert result["reason"] == "no_route_for_public_name"
    assert result["routes_matching_public_name"] == 0


def test_worker_route_without_an_expected_script_name_is_unknown():
    result = pf.audit_public_worker_route("tok", "zone", "tinyassets.io", None)
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "missing_expected_worker_name"


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({"success": False, "result": []}, "cf_api_unsuccessful"),
        ({"success": True, "result": "nope"}, "cf_api_no_result"),
        ({"success": True, "result": []}, "no_routes"),
        ({"success": True, "result": ["nope"]}, "malformed_route_record"),
        ({"success": True, "result": [{"script": "ta-router"}]}, "route_without_pattern"),
    ],
)
def test_malformed_worker_route_payloads_are_unknown(monkeypatch, payload, reason):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (payload, "ok"))
    result = pf.audit_public_worker_route("tok", "zone", "tinyassets.io", "ta-router")
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == reason


# =========================================================================
# REVIEW FINDING 6: CI=true is not hosted trust; custody stays unverified
# =========================================================================

def test_hosted_custody_is_always_unknown():
    result = pf.hosted_custody_fact()
    assert result["verdict"] == pf.UNKNOWN
    assert result["reason"] == "workflow_placement_and_custody_unverified"
    assert "CI=true does not establish either" in result["requirement"]


def test_overall_pass_is_unreachable_while_custody_is_unverified(monkeypatch, capsys):
    """Every provider fact clean, real remote probe matching -- still not a pass."""
    monkeypatch.setattr(
        pf,
        "resolve_remote_probe_target",
        lambda env, **k: (_target(), "ok", ""),
    )
    monkeypatch.setattr(
        pf,
        "probe_container_metadata",
        lambda *a, **k: pf.fact(
            "container_metadata", pf.PASS, "reachable",
            _instance_tag=pf.correlation_tag("222"),
        ),
    )

    def fake_get_json(url, headers, timeout=15.0):
        if url.startswith(pf.DO_DROPLETS_URL[:40]):
            return (
                {
                    "droplets": [
                        {"id": 222, "networks": {"v4": [{"ip_address": "198.51.100.8"}]}}
                    ],
                    "meta": {"total": 1},
                },
                "ok",
            )
        if "cfd_tunnel" in url:
            return (_cf_connections([["198.51.100.8"]]), "ok")
        if "workers/routes" in url:
            return (
                {"success": True,
                 "result": [{"pattern": "tinyassets.io/*", "script": "ta-router"}]},
                "ok",
            )
        return (
            _cf_records([{"type": "CNAME", "content": "tunnel-1.cfargotunnel.com"}]),
            "ok",
        )

    monkeypatch.setattr(pf, "_get_json", fake_get_json)
    code = pf.run([], env=dict(CI_ENV, **{
        "DO_API_TOKEN": "secret-do-token",
        "DO_DROPLET_HOST": "198.51.100.8",
        "CLOUDFLARE_API_TOKEN": "secret-cf-token",
        "CLOUDFLARE_ACCOUNT_ID": "acct-1",
        "CLOUDFLARE_TUNNEL_ID": "tunnel-1",
        "CLOUDFLARE_ZONE_ID": "zone-1",
        "TINYASSETS_INTERNAL_ORIGIN_NAME": "mcp.tinyassets.io",
        "TINYASSETS_WORKER_NAME": "ta-router",
    }))
    payload = json.loads(capsys.readouterr().out)
    by_name = {f["fact"]: f for f in payload["facts"]}
    assert by_name["cloud_identity_match"]["identity_match"] is True
    assert by_name["tunnel_connectors"]["verdict"] == pf.PASS
    assert by_name["internal_origin_dns"]["verdict"] == pf.PASS
    assert by_name["public_worker_route"]["verdict"] == pf.PASS
    # ...and still not an overall pass, because custody is unverified.
    assert by_name["hosted_credential_custody"]["verdict"] == pf.UNKNOWN
    assert payload["status"] == pf.UNKNOWN
    assert payload["hosted_trust"] == "unverified"
    assert code == 2


def test_run_without_ci_refuses_and_reads_nothing(monkeypatch, capsys):
    monkeypatch.setattr(
        pf, "_get_json", lambda *a, **k: pytest.fail("no provider read off hosted CI")
    )
    code = pf.run([], env={"DO_API_TOKEN": "tok"})
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == pf.UNKNOWN
    assert payload["reason"] == "not_hosted_ci"
    assert payload["hosted_trust"] == "unverified"
    assert "accidental-use guard" in payload["note"]


def test_ci_guard_is_documented_as_a_guard_not_as_proof():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "accidental-use guard" in source
    for claim in ("proves hosted", "hosted provenance proven", "custody verified"):
        assert claim not in source


# =========================================================================
# REVIEW FINDING 7: no non-reversibility claim for a salted numeric id
# =========================================================================

def test_no_claim_that_the_salted_digest_is_non_reversible():
    source = _SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    for claim in ("non-reversible", "nonreversible", "irreversible", "anonymize", "anonymized"):
        assert claim not in lowered or "not" in lowered, claim
    # The enumerability is stated outright, and the tag is not a privacy control.
    assert "NOT a privacy control" in source
    assert "enumerable" in lowered


def test_identifiers_never_reach_the_output_only_booleans_and_counts(monkeypatch, capsys):
    monkeypatch.setattr(
        pf, "resolve_remote_probe_target", lambda env, **k: (_target(), "ok", "")
    )
    monkeypatch.setattr(
        pf,
        "probe_container_metadata",
        lambda *a, **k: pf.fact(
            "container_metadata", pf.PASS, "reachable",
            _instance_tag=pf.correlation_tag("987654321"),
        ),
    )

    def fake_get_json(url, headers, timeout=15.0):
        if url.startswith(pf.DO_DROPLETS_URL[:40]):
            return (
                {
                    "droplets": [
                        {"id": 987654321,
                         "networks": {"v4": [{"ip_address": "198.51.100.8"}]}}
                    ],
                    "meta": {"total": 1},
                },
                "ok",
            )
        if "cfd_tunnel" in url:
            return (_cf_connections([["198.51.100.8"]]), "ok")
        if "workers/routes" in url:
            return (
                {"success": True,
                 "result": [{"pattern": "tinyassets.io/*", "script": "ta-router"}]},
                "ok",
            )
        return (
            _cf_records([{"type": "CNAME", "content": "tunnel-1.cfargotunnel.com"}]),
            "ok",
        )

    monkeypatch.setattr(pf, "_get_json", fake_get_json)
    pf.run([], env=dict(CI_ENV, **{
        "DO_API_TOKEN": "secret-do-token",
        "DO_DROPLET_HOST": "198.51.100.8",
        "CLOUDFLARE_API_TOKEN": "secret-cf-token",
        "CLOUDFLARE_ACCOUNT_ID": "acct-1",
        "CLOUDFLARE_TUNNEL_ID": "tunnel-1",
        "CLOUDFLARE_ZONE_ID": "zone-1",
        "TINYASSETS_INTERNAL_ORIGIN_NAME": "mcp.tinyassets.io",
        "TINYASSETS_WORKER_NAME": "ta-router",
    }))
    out = capsys.readouterr().out
    for leak in (
        "secret-do-token", "secret-cf-token", "198.51.100.8", "987654321",
        "cfargotunnel.com", "acct-1", "tunnel-1", "zone-1",
        "mcp.tinyassets.io", "ta-router",
        pf.correlation_tag("987654321"),
    ):
        assert leak not in out, f"preflight leaked {leak!r}"
    payload = json.loads(out)
    assert payload["enforcement"] == "none"
    assert payload["boundary_closed"] is False


def test_sanitize_strips_every_internal_key():
    raw = [
        pf.fact("expected_droplet", pf.PASS, "resolved",
                _addresses=["203.0.113.7"], _instance_tag="deadbeef"),
    ]
    clean = pf.sanitize(raw)
    assert "_addresses" not in clean[0]
    assert "_instance_tag" not in clean[0]
    assert "203.0.113.7" not in json.dumps(clean)
    assert "deadbeef" not in json.dumps(clean)


# =========================================================================
# general: missing permission is unknown, and unknowns dominate
# =========================================================================

@pytest.mark.parametrize(
    "reason_code",
    ["http_401", "http_403", "unreachable", "bad_response", "redirect_refused",
     "response_too_large", "unexpected_payload_shape"],
)
def test_provider_read_failure_is_unknown_not_pass(monkeypatch, reason_code):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, reason_code))
    for result in (
        pf.resolve_expected_droplet("tok", "198.51.100.8"),
        pf.audit_tunnel_connectors("tok", "acct", "tun", {"198.51.100.8"}),
        pf.audit_internal_origin_dns("tok", "zone", "mcp.tinyassets.io", "tun"),
        pf.audit_public_worker_route("tok", "zone", "tinyassets.io", "ta-router"),
    ):
        assert result["verdict"] == pf.UNKNOWN
        assert reason_code in result["reason"]
        assert result["requirement"]


def test_missing_secret_is_unknown_for_every_fact():
    assert pf.resolve_expected_droplet(None, None)["verdict"] == pf.UNKNOWN
    assert pf.audit_tunnel_connectors(None, "a", "t", {"1.2.3.4"})["verdict"] == pf.UNKNOWN
    assert pf.audit_tunnel_connectors("tok", None, None, {"1.2.3.4"})["verdict"] == pf.UNKNOWN
    assert pf.audit_tunnel_connectors("tok", "a", "t", set())["verdict"] == pf.UNKNOWN
    assert pf.audit_internal_origin_dns(None, "z", "m", "t")["verdict"] == pf.UNKNOWN
    assert pf.audit_internal_origin_dns("tok", None, "m", "t")["verdict"] == pf.UNKNOWN
    assert pf.audit_public_worker_route(None, "z", "n", "w")["verdict"] == pf.UNKNOWN
    assert pf.audit_public_worker_route("tok", None, "n", "w")["verdict"] == pf.UNKNOWN


def test_every_unknown_states_a_precise_requirement():
    for result in (
        pf.resolve_expected_droplet(None, None),
        pf.audit_tunnel_connectors(None, "a", "t", {"1.2.3.4"}),
        pf.audit_internal_origin_dns("tok", None, "m", "t"),
        pf.audit_public_worker_route("tok", "z", "n", None),
        pf.hosted_custody_fact(),
    ):
        assert result["verdict"] == pf.UNKNOWN
        assert result["requirement"].strip(), f"{result['reason']} has no requirement"


def test_a_single_refusal_dominates_unknowns():
    clean = [
        {"verdict": pf.PASS}, {"verdict": pf.UNKNOWN}, {"verdict": pf.REFUSE},
    ]
    assert pf._overall(clean) == (pf.REFUSE, 1)


def test_any_unknown_downgrades_overall_status(monkeypatch, capsys):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, "http_403"))
    code = pf.run(["--skip-container-probe"], env=dict(CI_ENV, DO_API_TOKEN="tok"))
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == pf.UNKNOWN


def test_output_always_declares_it_enforces_nothing(monkeypatch, capsys):
    monkeypatch.setattr(pf, "_get_json", lambda *a, **k: (None, "http_403"))
    pf.run(["--skip-container-probe"], env=dict(CI_ENV))
    payload = json.loads(capsys.readouterr().out)
    assert payload["enforcement"] == "none"
    assert payload["boundary_closed"] is False
    assert payload["hosted_trust"] == "unverified"

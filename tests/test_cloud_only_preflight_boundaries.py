"""Execute the embedded probe and check whole-surface observation bounds."""

import io
from email.message import Message
from pathlib import Path
from urllib.response import addinfourl

import pytest
import yaml

from tests.test_cloud_only_preflight import pf


def _execute_probe(monkeypatch, capsys, body, status=200):
    requests = []
    responses = []

    def transport(_handler, request):
        requests.append(request.full_url)
        assert not request.has_proxy()
        headers = Message()
        if status == 302:
            headers["Location"] = "http://other.invalid/metadata"
        response = addinfourl(io.BytesIO(body), headers, request.full_url, status)
        response.msg = "Found" if status == 302 else "OK"
        responses.append(response)
        return response

    monkeypatch.setattr(pf.urllib.request, "getproxies", lambda: {
        "http": "http://untrusted.invalid:8080",
    })
    monkeypatch.setattr(pf.urllib.request.HTTPHandler, "http_open", transport)
    monkeypatch.setattr(pf.urllib.request.HTTPSHandler, "https_open", transport)
    try:
        exec(compile(pf._PROBE_SOURCE, "<fixed-probe>", "exec"), {})
    except SystemExit as exc:
        assert exc.code == 0
    return capsys.readouterr().out.strip(), requests, responses


def test_actual_probe_rejects_redirect_without_following(monkeypatch, capsys):
    output, requests, _ = _execute_probe(monkeypatch, capsys, b"123", 302)
    assert requests == [pf.METADATA_URL]
    assert output == "UNREACHABLE:HTTPError"


def test_actual_probe_rejects_valid_but_truncated_prefix(monkeypatch, capsys):
    output, requests, responses = _execute_probe(
        monkeypatch, capsys, b"123" + b" " * 300,
    )
    assert requests == [pf.METADATA_URL]
    assert output == "OVERSIZE"
    assert responses[0].closed


def test_actual_probe_closes_successful_response(monkeypatch, capsys):
    output, requests, responses = _execute_probe(monkeypatch, capsys, b"123\n")
    assert output == "OK:123"
    assert requests == [pf.METADATA_URL]
    assert responses[0].closed


@pytest.mark.parametrize("pattern", ["tinyassets.io/mcp*", "https://tinyassets.io/mcp*"])
def test_exact_canonical_worker_configuration(monkeypatch, pattern):
    monkeypatch.setattr(pf, "_get_json", lambda *a: (
        {"success": True, "result": [{"pattern": pattern, "script": "expected"}]}, "ok",
    ))
    assert pf.audit_public_worker_route("t", "z", "tinyassets.io", "expected")[
        "verdict"
    ] == pf.PASS


@pytest.mark.parametrize("override", [
    {"pattern": "tinyassets.io/mcp/app", "script": None},
    {"pattern": "tinyassets.io/mcp/app", "script": "other"},
    {"pattern": "tinyassets.io/mcp/unlisted*", "script": "other"},
    {"pattern": "tinyassets.io/mcp/unlisted", "script": None},
])
def test_unexpected_subpath_cannot_hide_between_probe_urls(monkeypatch, override):
    monkeypatch.setattr(pf, "_get_json", lambda *a: (
        {"success": True, "result": [
            {"pattern": "tinyassets.io/mcp*", "script": "expected"}, override,
        ]}, "ok",
    ))
    assert pf.audit_public_worker_route("t", "z", "tinyassets.io", "expected")[
        "verdict"
    ] != pf.PASS


def test_three_exact_probe_urls_do_not_prove_descendant_coverage(monkeypatch):
    monkeypatch.setattr(pf, "_get_json", lambda *a: (
        {"success": True, "result": [
            {"pattern": "tinyassets.io" + path, "script": "expected"}
            for path in pf.CANONICAL_PUBLIC_PATHS
        ]}, "ok",
    ))
    assert pf.audit_public_worker_route("t", "z", "tinyassets.io", "expected")[
        "verdict"
    ] != pf.PASS


def test_unrelated_path_is_not_mcp_coverage(monkeypatch):
    monkeypatch.setattr(pf, "_get_json", lambda *a: (
        {"success": True, "result": [
            {"pattern": "tinyassets.io/other*", "script": "expected"},
        ]}, "ok",
    ))
    assert pf.audit_public_worker_route("t", "z", "tinyassets.io", "expected")[
        "verdict"
    ] != pf.PASS


def test_observation_workflow_has_no_inputs_or_pr_trigger():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/cloud-only-preflight.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert workflow["on"] == {"workflow_dispatch": ""}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["observe"]
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    assert "github.ref" in steps[0]["env"]["REF"]
    assert "repository.default_branch" in steps[0]["env"]["DEFAULT_BRANCH"]
    assert "exit 1" in steps[0]["run"]
    checkout = next(step for step in steps if "checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] == "false"
    assert not any("upload-artifact" in step.get("uses", "") for step in steps)
    assert any(step.get("if") == "always()" and "rm -f" in step.get("run", "")
               for step in steps)

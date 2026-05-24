"""Offline unit tests for selfhost_smoke.py parity assertions.

Tests the assert_parity() logic and the SmokeError exit-code contract.
Live end-to-end probing requires a running Row D deployment and is
exercised manually per the Row F acceptance checklist.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import selfhost_smoke as smoke  # noqa: E402
from verify_llm_binding import VerifyError  # noqa: E402

# ---------------------------------------------------------------------------
# assert_parity
# ---------------------------------------------------------------------------

def test_parity_identical_tools_and_keys_passes():
    tools = {"get_status", "universe", "wiki"}
    status = {"daemon_running": True, "phase": "idle"}
    smoke.assert_parity(tools, tools.copy(), status, status.copy())


def test_parity_tool_missing_from_tunnel_raises():
    canonical_tools = {"get_status", "universe", "wiki"}
    tunnel_tools = {"get_status", "universe"}
    with pytest.raises(smoke.SmokeError) as exc_info:
        smoke.assert_parity(canonical_tools, tunnel_tools, {}, {})
    assert exc_info.value.code == 3
    assert "wiki" in str(exc_info.value)


def test_parity_extra_tool_in_tunnel_raises():
    canonical_tools = {"get_status"}
    tunnel_tools = {"get_status", "extra_tool"}
    with pytest.raises(smoke.SmokeError) as exc_info:
        smoke.assert_parity(canonical_tools, tunnel_tools, {}, {})
    assert exc_info.value.code == 3
    assert "extra_tool" in str(exc_info.value)


def test_parity_status_key_mismatch_raises():
    tools = {"get_status"}
    status_a = {"daemon_running": True, "phase": "idle"}
    status_b = {"daemon_running": True}
    with pytest.raises(smoke.SmokeError) as exc_info:
        smoke.assert_parity(tools, tools.copy(), status_a, status_b)
    assert exc_info.value.code == 3
    assert "phase" in str(exc_info.value)


def test_parity_both_empty_status_passes():
    tools = {"get_status"}
    smoke.assert_parity(tools, tools.copy(), {}, {})


# ---------------------------------------------------------------------------
# run() exit codes via mocked probe_url
# ---------------------------------------------------------------------------

def _make_probe_result(tools, status):
    return (set(tools), status)


def test_run_exit_0_when_access_gate_holds(monkeypatch):
    tools = {"get_status", "universe"}
    status = {"phase": "idle"}
    monkeypatch.setattr(smoke, "probe_url", lambda url, timeout, label: (tools, status))
    monkeypatch.setattr(smoke, "assert_tunnel_access_blocked", lambda url, timeout: 403)
    rc = smoke.run(
        smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10,
        llm_check_fn=lambda url, timeout: {"llm_endpoint_bound": "anthropic"},
    )
    assert rc == 0


def test_run_exit_3_when_tools_differ(monkeypatch):
    def _probe(url, timeout, label):
        if label == "canonical":
            return ({"get_status", "wiki"}, {"phase": "idle"})
        return ({"get_status"}, {"phase": "idle"})

    monkeypatch.setattr(smoke, "probe_url", _probe)
    rc = smoke.run(
        smoke.CANONICAL_URL,
        smoke.TUNNEL_URL,
        10,
        internal_parity=True,
    )
    assert rc == 3


def test_run_exit_2_when_network_fails(monkeypatch):
    def _probe(url, timeout, label):
        raise smoke.SmokeError(2, f"network down on {url}")

    monkeypatch.setattr(smoke, "probe_url", _probe)
    rc = smoke.run(smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10)
    assert rc == 2


# ---------------------------------------------------------------------------
# CLI arg parsing
# ---------------------------------------------------------------------------

def test_main_passes_custom_urls_to_run(monkeypatch):
    seen = {}

    def _run(canonical, tunnel, timeout, *, internal_parity=False):
        seen["canonical"] = canonical
        seen["tunnel"] = tunnel
        seen["timeout"] = timeout
        seen["internal_parity"] = internal_parity
        return 0

    monkeypatch.setattr(smoke, "run", _run)
    rc = smoke.main([
        "--canonical", "https://example.com/mcp",
        "--tunnel", "https://tunnel.example.com/mcp",
        "--timeout", "5",
    ])
    assert rc == 0
    assert seen["canonical"] == "https://example.com/mcp"
    assert seen["tunnel"] == "https://tunnel.example.com/mcp"
    assert seen["timeout"] == 5.0
    assert seen["internal_parity"] is False


# ---------------------------------------------------------------------------
# LLM-binding integration in run()
# ---------------------------------------------------------------------------

_TOOLS = {"get_status", "universe"}
_STATUS = {"phase": "idle"}


def test_run_exit_0_when_parity_and_llm_bound(monkeypatch):
    monkeypatch.setattr(smoke, "probe_url", lambda url, timeout, label: (_TOOLS, _STATUS))
    rc = smoke.run(
        smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10,
        internal_parity=True,
        llm_check_fn=lambda url, timeout: {"llm_endpoint_bound": "anthropic"},
    )
    assert rc == 0


def test_run_fails_when_llm_unbound(monkeypatch):
    monkeypatch.setattr(smoke, "probe_url", lambda url, timeout, label: (_TOOLS, _STATUS))
    monkeypatch.setattr(smoke, "assert_tunnel_access_blocked", lambda url, timeout: 403)

    def _unbound(url, timeout):
        raise VerifyError(3, "llm_endpoint_bound is 'unset'")

    rc = smoke.run(
        smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10,
        llm_check_fn=_unbound,
    )
    assert rc == 3


def test_run_fails_when_llm_network_error(monkeypatch):
    monkeypatch.setattr(smoke, "probe_url", lambda url, timeout, label: (_TOOLS, _STATUS))
    monkeypatch.setattr(smoke, "assert_tunnel_access_blocked", lambda url, timeout: 403)

    def _net_err(url, timeout):
        raise VerifyError(2, "network error")

    rc = smoke.run(
        smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10,
        llm_check_fn=_net_err,
    )
    assert rc == 2


def test_run_parity_fail_skips_llm_check(monkeypatch):
    """Parity gate fires before LLM check — LLM fn must not be called."""
    called = []

    def _probe(url, timeout, label):
        if label == "canonical":
            return ({"get_status", "wiki"}, _STATUS)
        return ({"get_status"}, _STATUS)

    def _llm(url, timeout):
        called.append(True)
        return {"llm_endpoint_bound": "anthropic"}

    monkeypatch.setattr(smoke, "probe_url", _probe)
    rc = smoke.run(
        smoke.CANONICAL_URL, smoke.TUNNEL_URL, 10,
        internal_parity=True,
        llm_check_fn=_llm,
    )
    assert rc == 3
    assert called == [], "LLM check should not run when parity fails"

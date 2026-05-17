"""Task #10 — direct tests for `workflow.api.status` after decomp Step 3.

The legacy test files (test_get_status_primitive.py, test_sandbox_*, etc.)
still cover the chatbot-facing `workflow.universe_server` MCP wrapper. This
file exercises `workflow.api.status` directly to lock in the canonical
implementation surface.
"""

from __future__ import annotations

import json

import pytest

from workflow.api import status as status_mod
from workflow.api.status import _policy_hash, get_status

# ── module surface ──────────────────────────────────────────────────────────


def test_module_exposes_expected_public_names():
    """The new submodule's contract surface — guards against silent removal."""
    expected = {"get_status", "_policy_hash"}
    missing = expected - set(dir(status_mod))
    assert not missing, f"status.py is missing public names: {missing}"


# ── _policy_hash unit ───────────────────────────────────────────────────────


def test_policy_hash_is_deterministic():
    """Same payload → same hash (ordering-independent)."""
    a = {"x": 1, "y": [1, 2, 3], "z": {"nested": True}}
    b = {"z": {"nested": True}, "y": [1, 2, 3], "x": 1}
    assert _policy_hash(a) == _policy_hash(b)


def test_policy_hash_differs_for_different_payloads():
    assert _policy_hash({"a": 1}) != _policy_hash({"a": 2})


def test_policy_hash_returns_sha256_hex():
    h = _policy_hash({"k": "v"})
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_policy_hash_handles_empty_dict():
    h = _policy_hash({})
    assert len(h) == 64


# ── get_status smoke shapes ─────────────────────────────────────────────────


@pytest.fixture
def status_env(tmp_path, monkeypatch):
    """Isolated data dir + universe so get_status touches no host files."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "test-universe")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "test-host")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "test-user")
    universe = tmp_path / "test-universe"
    universe.mkdir()
    # Minimal dispatcher config so load_dispatcher_config doesn't error.
    (universe / "dispatcher.json").write_text("{}")
    return universe


def test_get_status_returns_str_json(status_env):
    raw = get_status()
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_get_status_returns_versioned_contract_keys(status_env):
    """schema_version=1 contract — all top-level keys present."""
    parsed = json.loads(get_status())
    expected_keys = {
        "schema_version",
        "active_host",
        "tier_routing_policy",
        "evidence",
        "evidence_caveats",
        "caveats",
        "actionable_next_steps",
        "session_boundary",
        "storage_utilization",
        "per_provider_cooldown_remaining",
        "sandbox_status",
        "missing_data_files",
        "supervisor_liveness",
        "auto_ship_health",
        "open_brain",
        "universe_id",
        "universe_exists",
    }
    assert expected_keys <= set(parsed.keys()), (
        f"missing keys: {expected_keys - set(parsed.keys())}"
    )
    assert parsed["schema_version"] == 1


def test_get_status_active_host_shape(status_env):
    parsed = json.loads(get_status())
    host = parsed["active_host"]
    assert set(host.keys()) >= {"host_id", "served_llm_type", "llm_endpoint_bound"}
    assert host["host_id"] == "test-host"


def test_get_status_evidence_includes_policy_hash(status_env):
    """Round-trip: the `evidence.policy_hash` field is a sha256 hex string."""
    parsed = json.loads(get_status())
    h = parsed["evidence"]["policy_hash"]
    assert isinstance(h, str)
    assert len(h) == 64


def test_get_status_includes_read_only_open_brain_surface(status_env, tmp_path):
    from workflow.daemon_brain import capture_daemon_memory
    from workflow.daemon_registry import create_daemon

    daemon = create_daemon(
        tmp_path,
        display_name="Status Brain Daemon",
        created_by="pytest",
        soul_mode="soul",
        soul_text="Status Brain Daemon observes memory cost.",
    )
    capture_daemon_memory(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        memory_kind="policy",
        content="Report open-brain token cost as status, not as a decision.",
        source_type="pytest",
        source_id="get-status-open-brain",
        reliability="test_observed",
        temporal_bounds={"valid_from": "2026-05-17"},
        language_type="policy",
    )

    parsed = json.loads(get_status())

    assert parsed["open_brain"]["read_only"] is True
    assert parsed["open_brain"]["daemon_count"] == 1
    assert parsed["open_brain"]["daemons"][0]["daemon_id"] == daemon["daemon_id"]
    assert (
        parsed["open_brain"]["daemons"][0]["cost_ledger"]["estimated_total_tokens"]
        > 0
    )


def test_get_status_explicit_universe_id_overrides_default(status_env, tmp_path):
    """Passing universe_id="other" should resolve to that universe id."""
    other = tmp_path / "other-universe"
    other.mkdir()
    (other / "dispatcher.json").write_text("{}")
    parsed = json.loads(get_status(universe_id="other-universe"))
    assert parsed["universe_id"] == "other-universe"
    assert parsed["universe_exists"] is True


def test_get_status_nonexistent_universe_marks_universe_exists_false(status_env):
    parsed = json.loads(get_status(universe_id="not-real-universe"))
    assert parsed["universe_id"] == "not-real-universe"
    assert parsed["universe_exists"] is False
    # A nonexistent-universe caveat should be present.
    assert any("does not exist" in c for c in parsed["caveats"])


def test_get_status_session_boundary_account_user_set(status_env):
    parsed = json.loads(get_status())
    sb = parsed["session_boundary"]
    assert sb["account_user"] == "test-user"
    # No prior activity log → prior_session_context_available is False.
    assert sb["prior_session_context_available"] is False


def test_get_status_caveats_warn_when_no_provider_bound(status_env, monkeypatch):
    """When no LLM env-var is set AND no CLI is on PATH, caveats warn unbound."""
    import shutil
    for var in (
        "OLLAMA_HOST", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY",
        "XAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    # Also stub which() so codex/claude CLI presence on the dev machine
    # doesn't flip endpoint_hint away from "unset".
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    parsed = json.loads(get_status())
    assert any("No default LLM provider detected" in c for c in parsed["caveats"])

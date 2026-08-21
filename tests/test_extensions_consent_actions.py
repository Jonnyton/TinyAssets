"""Tests for the ``extensions`` MCP actions added by PR-122 Phase 2 Slice 1.

- ``grant_effector_consent(sink, destination[, granted_by])``
- ``revoke_effector_consent(sink, destination)``
- ``list_effector_consents([sink], [active_only])``

The Slice 1 dispatch reuses existing ``extensions(...)`` kwargs to avoid
inflating the tool signature; the chatbot passes ``intent=<sink>`` and
``project_id=<destination>``. ``author`` is the optional granter override
(defaults to ``_current_actor()``).
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, action, **kwargs) -> dict:
    return json.loads(us.extensions(action=action, **kwargs))


# ---------------------------------------------------------------------------
# grant_effector_consent
# ---------------------------------------------------------------------------


def test_grant_then_list_roundtrip(us_env):
    us, base = us_env
    granted = _call(
        us,
        "grant_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
        author="host",
    )
    assert granted["status"] == "granted"
    assert granted["consent"]["sink"] == "github_pull_request"
    assert granted["consent"]["destination"] == "Jonnyton/TinyAssets"
    assert granted["consent"]["granted_by"] == "host"
    assert granted["consent"]["revoked_at"] is None

    listed = _call(
        us,
        "list_effector_consents",
        intent="github_pull_request",
    )
    assert listed["sink_filter"] == "github_pull_request"
    assert listed["active_only"] is True
    destinations = {row["destination"] for row in listed["consents"]}
    assert destinations == {"Jonnyton/TinyAssets"}


def test_grant_defaults_granted_by_to_current_actor(us_env):
    us, base = us_env
    granted = _call(
        us,
        "grant_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
        # author omitted -> defaults to UNIVERSE_SERVER_USER == "tester"
    )
    assert granted["status"] == "granted"
    assert granted["consent"]["granted_by"] == "tester"


def test_grant_requires_sink(us_env):
    us, _ = us_env
    result = _call(
        us,
        "grant_effector_consent",
        intent="",  # missing sink
        project_id="Jonnyton/TinyAssets",
        author="host",
    )
    assert "error" in result
    assert result["failure_class"] == "missing_sink"


def test_grant_requires_destination(us_env):
    us, _ = us_env
    result = _call(
        us,
        "grant_effector_consent",
        intent="github_pull_request",
        project_id="",  # missing destination
        author="host",
    )
    assert "error" in result
    assert result["failure_class"] == "missing_destination"


# ---------------------------------------------------------------------------
# revoke_effector_consent
# ---------------------------------------------------------------------------


def test_revoke_after_grant(us_env):
    us, _ = us_env
    _call(
        us,
        "grant_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
        author="host",
    )
    revoked = _call(
        us,
        "revoke_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
    )
    assert revoked["status"] == "revoked"
    assert revoked["sink"] == "github_pull_request"
    assert revoked["destination"] == "Jonnyton/TinyAssets"
    # list with active_only=True (default) -> empty.
    active = _call(
        us, "list_effector_consents", intent="github_pull_request",
    )
    assert active["consents"] == []


def test_revoke_never_granted_is_no_active_grant(us_env):
    us, _ = us_env
    result = _call(
        us,
        "revoke_effector_consent",
        intent="github_pull_request",
        project_id="never-granted/repo",
    )
    # Soft-success: end-state is "not granted" which is already true.
    assert result["status"] == "no_active_grant"


def test_revoke_requires_sink_and_destination(us_env):
    us, _ = us_env
    no_sink = _call(
        us,
        "revoke_effector_consent",
        intent="",
        project_id="Jonnyton/TinyAssets",
    )
    assert no_sink["failure_class"] == "missing_sink"
    no_dest = _call(
        us,
        "revoke_effector_consent",
        intent="github_pull_request",
        project_id="",
    )
    assert no_dest["failure_class"] == "missing_destination"


# ---------------------------------------------------------------------------
# list_effector_consents
# ---------------------------------------------------------------------------


def test_list_active_only_default_filters_revoked(us_env):
    us, _ = us_env
    _call(
        us, "grant_effector_consent",
        intent="github_pull_request", project_id="repo-a", author="host",
    )
    _call(
        us, "grant_effector_consent",
        intent="github_pull_request", project_id="repo-b", author="host",
    )
    _call(
        us, "revoke_effector_consent",
        intent="github_pull_request", project_id="repo-a",
    )
    active = _call(
        us, "list_effector_consents", intent="github_pull_request",
    )
    assert {r["destination"] for r in active["consents"]} == {"repo-b"}


def test_list_no_sink_filter_returns_all_sinks(us_env):
    us, _ = us_env
    _call(
        us, "grant_effector_consent",
        intent="github_pull_request", project_id="repo-a", author="host",
    )
    _call(
        us, "grant_effector_consent",
        intent="twitter_post", project_id="@tinyassets", author="host",
    )
    all_active = _call(us, "list_effector_consents")
    sinks = {r["sink"] for r in all_active["consents"]}
    assert sinks == {"github_pull_request", "twitter_post"}

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
    # Consent grant/revoke is OWNER-ONLY + derives the grantor from the
    # authenticated actor (Codex R7 C3). Mock the owner identity for the happy
    # path; the caller-supplied `author` is ignored.
    from tinyassets.api import permissions as _perms
    monkeypatch.setattr(_perms, "current_actor_is_universe_owner", lambda uid: True)
    monkeypatch.setattr(_perms, "current_actor_id", lambda: "tester")
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
        author="host",  # caller-supplied grantor is IGNORED (Codex R7 C3)
    )
    assert granted["status"] == "granted"
    assert granted["consent"]["sink"] == "github_pull_request"
    assert granted["consent"]["destination"] == "Jonnyton/TinyAssets"
    # grantor is the AUTHENTICATED actor, not the caller-supplied "host".
    assert granted["consent"]["granted_by"] == "tester"
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


def test_grant_non_owner_refused(us_env, monkeypatch):
    """Codex R7 C3: a non-owner cannot grant effector consent — the raw-merge
    (and every) consent authorizes external writes and is owner-only."""
    us, _ = us_env
    from tinyassets.api import permissions as _perms
    monkeypatch.setattr(_perms, "current_actor_is_universe_owner", lambda uid: False)
    result = _call(
        us, "grant_effector_consent",
        intent="github_raw_merge", project_id="Jonnyton/TinyAssets", author="attacker",
    )
    assert result["failure_class"] == "owner_required"


def test_revoke_non_owner_refused(us_env, monkeypatch):
    us, _ = us_env
    from tinyassets.api import permissions as _perms
    monkeypatch.setattr(_perms, "current_actor_is_universe_owner", lambda uid: False)
    result = _call(
        us, "revoke_effector_consent",
        intent="github_pull_request", project_id="Jonnyton/TinyAssets",
    )
    assert result["failure_class"] == "owner_required"


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


# ---------------------------------------------------------------------------
# End-to-end — grant + run effector (no subprocess)
# ---------------------------------------------------------------------------


def test_grant_and_revoke_visible_to_effector(us_env, monkeypatch):
    """A grant recorded via the MCP action must immediately gate the
    effector's consent check, and a subsequent revoke must close it."""
    us, base = us_env
    from tinyassets.effectors import EXTERNAL_WRITE_SINK_GITHUB_PR
    from tinyassets.effectors.github_pr import (
        _CAPABILITIES_ENV,
        run_github_pr_effector,
    )

    # Round-2 P1.2 — capability lookup is via the JSON-map env. Set a
    # map containing only the destination under test so the lookup
    # resolves to ``tok``.
    monkeypatch.setenv(
        _CAPABILITIES_ENV,
        json.dumps({"Jonnyton/TinyAssets": "tok"}),
    )
    # Codex R7 F4: the effector reads consent from the SAME per-universe dir the
    # MCP grant writes to. Resolve the target universe dir the way the MCP does.
    from tinyassets.api.helpers import _request_universe, _universe_dir
    universe_dir = _universe_dir(_request_universe(""))
    packet = {
        "sink": EXTERNAL_WRITE_SINK_GITHUB_PR,
        "destination": "Jonnyton/TinyAssets",
        "payload": {
            "title": "x",
            "body": "x",
            "head_branch": "auto/x",
            "base_branch": "main",
            "draft": True,
            # BUG-111 (commit 28b12b99): a real write materializes a
            # head branch from the packet's change set BEFORE
            # ``gh pr create``; an empty change set fails closed with
            # ``missing_changes`` rather than opening an empty PR. This
            # test exercises consent visibility, not the materialize
            # path, so it carries a minimal change set and mocks
            # ``_materialize_branch`` below.
            "changes_json": {"PROBE.md": "probe\n"},
        },
        "idempotency_hint": "h-1",
    }

    # Before grant: consent missing.
    before = run_github_pr_effector(
        node_id="emit",
        output_keys=["pr_packet"],
        run_state={"pr_packet": packet},
        base_path=universe_dir,
        run_id="run-before",
    )
    assert before["reason"] == "missing_consent"

    # Grant via MCP.
    _call(
        us,
        "grant_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
        author="host",
    )

    # After grant: gate clears; with subprocess mocked the real-write
    # path should run.
    from types import SimpleNamespace
    from unittest.mock import patch
    fake = SimpleNamespace(
        returncode=0,
        stdout="https://github.com/Jonnyton/TinyAssets/pull/55\n",
        stderr="",
    )
    with patch(
        "tinyassets.effectors.github_pr._materialize_branch",
        return_value={"materialized": True, "head_branch": "auto/x"},
    ), patch(
        "tinyassets.effectors.github_pr.subprocess.run",
        return_value=fake,
    ):
        after = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe_dir,
            run_id="run-after",
        )
    assert after.get("pr_number") == 55

    # Revoke via MCP.
    _call(
        us,
        "revoke_effector_consent",
        intent="github_pull_request",
        project_id="Jonnyton/TinyAssets",
    )

    # After revoke (with a NEW hint to bypass the idempotency dedup
    # of run-after): consent missing again.
    packet_new_hint = dict(packet)
    packet_new_hint["idempotency_hint"] = "h-2"
    revoked_result = run_github_pr_effector(
        node_id="emit",
        output_keys=["pr_packet"],
        run_state={"pr_packet": packet_new_hint},
        base_path=universe_dir,
        run_id="run-revoked",
    )
    assert revoked_result["reason"] == "missing_consent"


def test_consent_is_per_universe_isolated(tmp_path):
    """Codex R7 F4: a grant in universe A is NOT usable in universe B — consent
    is per-universe (cross-owner tenant isolation), stored + read from the same
    universe dir."""
    from tinyassets.storage.effector_consents import grant_consent, is_consent_active

    univ_a = tmp_path / "u-A"
    univ_b = tmp_path / "u-B"
    univ_a.mkdir()
    univ_b.mkdir()
    grant_consent(univ_a, sink="github_raw_merge", destination="Owner/Repo", granted_by="owner")
    # Usable in A, invisible in B.
    assert is_consent_active(univ_a, sink="github_raw_merge", destination="Owner/Repo")
    assert not is_consent_active(univ_b, sink="github_raw_merge", destination="Owner/Repo")



def test_explicit_universe_consent_is_ab_isolated(us_env):
    """Codex R10 #5: an owner targeting an EXPLICIT universe gates + writes THAT
    universe's consent, not their home/default. A grant threaded with
    universe_id=A is usable in A and NOT in B."""
    us, base = us_env
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.storage.effector_consents import is_consent_active

    granted = _call(
        us, "grant_effector_consent",
        intent="github_raw_merge", project_id="Owner/Repo",
        universe_id="u-A",
    )
    assert granted["status"] == "granted"

    # The grant is usable in universe A's dir and invisible in universe B's.
    dir_a = _universe_dir("u-A")
    dir_b = _universe_dir("u-B")
    assert is_consent_active(dir_a, sink="github_raw_merge", destination="Owner/Repo")
    assert not is_consent_active(dir_b, sink="github_raw_merge", destination="Owner/Repo")

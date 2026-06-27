"""Tests for tinyassets.storage.effector_consents.

PR-122 Phase 2 Slice 1 — per-destination consent grants. The user must
explicitly grant that this universe's effectors may write to a specific
destination (e.g. ``"Jonnyton/TinyAssets"``) via a specific sink (e.g.
``"github_pull_request"``).
"""

from __future__ import annotations

import time

import pytest

from tinyassets.storage.effector_consents import (
    consents_db_path,
    grant_consent,
    initialize_consents_db,
    is_consent_active,
    list_consents,
    revoke_consent,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_initialize_creates_db_and_schema(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    path = initialize_consents_db(universe)
    assert path.exists()
    assert path == consents_db_path(universe)


# ---------------------------------------------------------------------------
# grant_consent
# ---------------------------------------------------------------------------


def test_grant_then_is_active_returns_true(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record = grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
        granted_at=1700.0,
    )
    assert record["granted_at"] == 1700.0
    assert record["granted_by"] == "host"
    assert record["revoked_at"] is None
    assert is_consent_active(
        universe, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is True


def test_is_active_returns_false_for_unmatched_destination(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
    )
    assert is_consent_active(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/other-repo",
    ) is False
    # Sink mismatch.
    assert is_consent_active(
        universe, sink="twitter_post", destination="Jonnyton/TinyAssets",
    ) is False


def test_is_active_is_case_sensitive(tmp_path):
    """No wildcard / fuzzy matching in Slice 1; exact match only."""
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
    )
    assert is_consent_active(
        universe, sink="github_pull_request", destination="jonnyton/workflow",
    ) is False


def test_grant_rejects_empty_fields(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    with pytest.raises(ValueError):
        grant_consent(
            universe, sink="", destination="x", granted_by="host",
        )
    with pytest.raises(ValueError):
        grant_consent(
            universe, sink="github_pull_request", destination="",
            granted_by="host",
        )
    with pytest.raises(ValueError):
        grant_consent(
            universe, sink="github_pull_request",
            destination="x", granted_by="",
        )


def test_grant_refresh_clears_prior_revoke(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
        granted_at=1000.0,
    )
    revoke_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        revoked_at=1500.0,
    )
    assert is_consent_active(
        universe, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is False
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host-2",
        granted_at=2000.0,
    )
    assert is_consent_active(
        universe, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is True
    rows = list_consents(
        universe, sink="github_pull_request", active_only=False,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["granted_by"] == "host-2"
    assert row["granted_at"] == 2000.0
    assert row["revoked_at"] is None


# ---------------------------------------------------------------------------
# revoke_consent
# ---------------------------------------------------------------------------


def test_revoke_flips_revoked_at(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
    )
    hit = revoke_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        revoked_at=3000.0,
    )
    assert hit is True
    rows = list_consents(
        universe, sink="github_pull_request", active_only=False,
    )
    assert rows[0]["revoked_at"] == 3000.0
    assert is_consent_active(
        universe, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is False


def test_revoke_missing_row_returns_false(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    hit = revoke_consent(
        universe, sink="github_pull_request", destination="never-granted",
    )
    assert hit is False


def test_revoke_with_empty_fields_is_no_op(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
    )
    assert revoke_consent(universe, sink="", destination="x") is False
    assert revoke_consent(
        universe, sink="github_pull_request", destination="",
    ) is False
    assert is_consent_active(
        universe, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is True


# ---------------------------------------------------------------------------
# list_consents
# ---------------------------------------------------------------------------


def test_list_active_only_default(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe, sink="github_pull_request",
        destination="repo-a", granted_by="host", granted_at=100.0,
    )
    grant_consent(
        universe, sink="github_pull_request",
        destination="repo-b", granted_by="host", granted_at=200.0,
    )
    revoke_consent(
        universe, sink="github_pull_request",
        destination="repo-a", revoked_at=300.0,
    )
    active = list_consents(universe, sink="github_pull_request")
    assert {r["destination"] for r in active} == {"repo-b"}

    all_rows = list_consents(
        universe, sink="github_pull_request", active_only=False,
    )
    assert {r["destination"] for r in all_rows} == {"repo-a", "repo-b"}


def test_list_orders_by_granted_at_desc(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    grant_consent(
        universe, sink="github_pull_request",
        destination="repo-a", granted_by="host", granted_at=100.0,
    )
    grant_consent(
        universe, sink="github_pull_request",
        destination="repo-b", granted_by="host", granted_at=200.0,
    )
    rows = list_consents(universe, sink="github_pull_request")
    assert [r["destination"] for r in rows] == ["repo-b", "repo-a"]


def test_universes_are_isolated(tmp_path):
    u1 = tmp_path / "u1"
    u2 = tmp_path / "u2"
    u1.mkdir()
    u2.mkdir()
    grant_consent(
        u1, sink="github_pull_request",
        destination="Jonnyton/TinyAssets", granted_by="host",
    )
    assert is_consent_active(
        u2, sink="github_pull_request", destination="Jonnyton/TinyAssets",
    ) is False


def test_default_granted_at_uses_wall_clock(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    before = time.time()
    grant_consent(
        universe,
        sink="github_pull_request",
        destination="Jonnyton/TinyAssets",
        granted_by="host",
    )
    after = time.time()
    rows = list_consents(universe, sink="github_pull_request")
    assert before <= rows[0]["granted_at"] <= after

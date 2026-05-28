"""Tests for Task #4 observability fix — universe list + get_status diagnostics.

Covers:
- `_action_list_universes` returning a `note` field when universes list is
  empty, distinguishing base-dir-missing / empty / all-filtered.
- `get_status` returning a `universe_exists` boolean so the chatbot can tell
  when `_default_universe()` fell through to a hardcoded fallback that
  doesn't correspond to a real directory.
"""

from __future__ import annotations

import json

import pytest

from workflow.api.universe import _action_list_universes
from workflow.universe_server import get_status


@pytest.fixture
def empty_base(tmp_path, monkeypatch):
    """Point WORKFLOW_DATA_DIR at an empty existing directory."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def missing_base(tmp_path, monkeypatch):
    """Point WORKFLOW_DATA_DIR at a path that does not exist."""
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(missing))
    return missing


@pytest.fixture
def hidden_only_base(tmp_path, monkeypatch):
    """Base dir contains only hidden entries — all filtered out by the
    `name.startswith('.')` guard."""
    (tmp_path / ".hidden1").mkdir()
    (tmp_path / ".hidden2").mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def populated_base(tmp_path, monkeypatch):
    """Base dir contains one legitimate universe."""
    udir = tmp_path / "alpha"
    udir.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def operational_dirs_base(tmp_path, monkeypatch):
    """Base dir contains storage subsystem directories beside universes."""
    (tmp_path / "alpha").mkdir()
    for name in ("wiki", "runs", "lance", "output"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    return tmp_path


class TestListUniversesEmptyNote:
    def test_missing_base_returns_does_not_exist_note(self, missing_base):
        result = json.loads(_action_list_universes())
        assert result["universes"] == []
        assert result["count"] == 0
        assert "does not exist" in result["note"]

    def test_empty_base_returns_empty_note(self, empty_base):
        result = json.loads(_action_list_universes())
        assert result["universes"] == []
        assert result["count"] == 0
        assert "empty" in result["note"]

    def test_hidden_only_base_returns_filtered_note(self, hidden_only_base):
        result = json.loads(_action_list_universes())
        assert result["universes"] == []
        assert result["count"] == 0
        assert "hidden or non-directories" in result["note"]

    def test_populated_base_has_no_note(self, populated_base):
        result = json.loads(_action_list_universes())
        assert result["count"] == 1
        assert result["universes"][0]["id"] == "alpha"
        assert "note" not in result

    def test_operational_storage_dirs_are_not_universes(self, operational_dirs_base):
        result = json.loads(_action_list_universes())
        assert result["count"] == 1
        assert [u["id"] for u in result["universes"]] == ["alpha"]


class TestGetStatusUniverseExists:
    def test_missing_universe_dir_flags_false(self, empty_base):
        """_default_universe() falls through to "default-universe"; the
        directory does not exist on disk. universe_exists must be False so
        the chatbot narrates the fallback accurately instead of reporting
        a live universe."""
        result = json.loads(get_status())
        assert result["universe_exists"] is False
        assert any(
            "does not exist on disk" in c for c in result["caveats"]
        ), f"Expected a 'does not exist' caveat; got {result['caveats']}"
        assert any(
            "Create universe" in step
            for step in result["actionable_next_steps"]
        )

    def test_existing_universe_dir_flags_true(self, populated_base):
        result = json.loads(get_status(universe_id="alpha"))
        assert result["universe_exists"] is True
        assert not any(
            "does not exist on disk" in c for c in result["caveats"]
        )

    def test_explicit_missing_universe_flags_false(self, populated_base):
        """Explicit universe_id that does not exist — same diagnostic."""
        result = json.loads(get_status(universe_id="ghost"))
        assert result["universe_exists"] is False
        assert any(
            "does not exist on disk" in c for c in result["caveats"]
        )

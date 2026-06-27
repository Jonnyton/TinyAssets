"""Task #23 — get_memory_scope_status MCP action (self-auditing §4.1).

Guards:
- Returns schema_version=1.
- Returns tiered_scope_enabled=False + flag_state="off" when TINYASSETS_TIERED_SCOPE unset.
- Returns tiered_scope_enabled=True + flag_state="on" when TINYASSETS_TIERED_SCOPE=on.
- active_enforcement_tiers is ["universe_id"] when flag is off.
- active_enforcement_tiers is all 4 tiers when flag is on.
- all_scope_tiers always has exactly 4 entries.
- retrieval_stats_by_tier is always an empty dict (not yet instrumented).
- recent_scope_mismatch_warnings is a list (empty when no log).
- caveats is non-empty on both paths.
- actionable_next_steps is non-empty on both paths.
- Action reachable via extensions(action="get_memory_scope_status").
- Response includes universe_id field.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def ext_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.delenv("TINYASSETS_TIERED_SCOPE", raising=False)
    from tinyassets import universe_server as us
    yield us, base


def _scope_status(us, **kwargs) -> dict:
    return json.loads(us.extensions(action="get_memory_scope_status", **kwargs))


class TestMemoryScopeStatusFlagOff:
    def test_schema_version(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["schema_version"] == 1

    def test_flag_state_off_when_unset(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["flag_state"] == "off"

    def test_tiered_scope_enabled_false(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["tiered_scope_enabled"] is False

    def test_active_tiers_only_universe_when_off(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["active_enforcement_tiers"] == ["universe_id"]

    def test_all_scope_tiers_four_entries(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert len(result["all_scope_tiers"]) == 4
        assert "universe_id" in result["all_scope_tiers"]
        assert "goal_id" in result["all_scope_tiers"]
        assert "branch_id" in result["all_scope_tiers"]
        assert "user_id" in result["all_scope_tiers"]

    def test_retrieval_stats_empty_dict(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["retrieval_stats_by_tier"] == {}

    def test_recent_mismatches_is_list(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert isinstance(result["recent_scope_mismatch_warnings"], list)

    def test_caveats_non_empty_when_off(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert len(result["caveats"]) >= 1

    def test_actionable_next_steps_non_empty_when_off(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert len(result["actionable_next_steps"]) >= 1

    def test_universe_id_present(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert "universe_id" in result

    def test_caveats_mention_universe_id_only(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        combined = " ".join(result["caveats"])
        assert "universe_id" in combined


class TestMemoryScopeStatusFlagOn:
    @pytest.fixture
    def env_on(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        base = tmp_path / "output"
        base.mkdir()
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
        monkeypatch.setenv("TINYASSETS_TIERED_SCOPE", "on")
        from tinyassets import universe_server as us
        yield us, base

    def test_flag_state_on_when_set(self, env_on) -> None:
        us, _ = env_on
        result = _scope_status(us)
        assert result["flag_state"] == "on"

    def test_tiered_scope_enabled_true(self, env_on) -> None:
        us, _ = env_on
        result = _scope_status(us)
        assert result["tiered_scope_enabled"] is True

    def test_active_tiers_all_four_when_on(self, env_on) -> None:
        us, _ = env_on
        result = _scope_status(us)
        assert set(result["active_enforcement_tiers"]) == {
            "universe_id", "goal_id", "branch_id", "user_id"
        }

    def test_caveats_non_empty_when_on(self, env_on) -> None:
        us, _ = env_on
        result = _scope_status(us)
        assert len(result["caveats"]) >= 1

    def test_actionable_next_steps_non_empty_when_on(self, env_on) -> None:
        us, _ = env_on
        result = _scope_status(us)
        assert len(result["actionable_next_steps"]) >= 1


class TestMemoryScopeStatusMismatchWarnings:
    def test_no_warnings_when_no_log(self, ext_env) -> None:
        us, _ = ext_env
        result = _scope_status(us)
        assert result["recent_scope_mismatch_warnings"] == []

    def test_mismatch_lines_surfaced_from_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = tmp_path / "output"
        base.mkdir()
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
        monkeypatch.delenv("TINYASSETS_TIERED_SCOPE", raising=False)

        # Write a fake activity.log with a mismatch line into the default universe dir.
        from tinyassets import universe_server as us
        from tinyassets.api.helpers import _default_universe
        uid = _default_universe()
        udir = base / uid
        udir.mkdir(parents=True, exist_ok=True)
        log = udir / "activity.log"
        log.write_text(
            "2026-04-25T00:00:00Z [info] normal line\n"
            "2026-04-25T00:01:00Z [warning] retrieval.scope_mismatch: dropped facts row\n"
            "2026-04-25T00:02:00Z [info] another normal line\n",
            encoding="utf-8",
        )

        result = _scope_status(us)
        assert len(result["recent_scope_mismatch_warnings"]) == 1
        assert "retrieval.scope_mismatch" in result["recent_scope_mismatch_warnings"][0]
        assert len(result["caveats"]) >= 2  # always-present + mismatch caveat


class TestMemoryScopeStatusDispatch:
    def test_action_reachable_via_extensions(self, ext_env) -> None:
        us, _ = ext_env
        raw = us.extensions(action="get_memory_scope_status")
        result = json.loads(raw)
        assert "flag_state" in result
        assert "tiered_scope_enabled" in result
        assert "schema_version" in result

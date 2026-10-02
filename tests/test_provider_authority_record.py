"""Provider authority lives in a platform record, never in the agent-editable config.

``config.yaml`` is the agent's own (founder-approved self-improving harness), so
the fields the router and provider binding trust -- ``allowed_providers``,
``engine_assignment_*``, ``provider_authority_bindings`` -- are read only from
``tinyassets.provider_authority``'s record (command-center-cutover E6,
target-architecture D8a). Writing them into config.yaml must change nothing.
"""

from __future__ import annotations

import json

import pytest

from tinyassets import provider_authority as pa
from tinyassets.config import (
    load_universe_config,
    write_provider_assignment_projection,
    write_universe_config_fields,
)


def _home(tmp_path):
    home = tmp_path / "u-home"
    home.mkdir()
    return home


def _config(home, text: str) -> None:
    (home / "config.yaml").write_text(text, encoding="utf-8")


def test_the_first_read_migrates_todays_values_out_of_config_yaml(tmp_path):
    home = _home(tmp_path)
    _config(home, "preferred_writer: codex\nallowed_providers:\n  - codex\n"
                  "engine_assignment_state: ready\nengine_assignment_generation: 3\n")

    loaded = load_universe_config(home)

    assert loaded.allowed_providers == ["codex"]
    assert loaded.engine_assignment_state == "ready"
    assert loaded.engine_assignment_generation == 3
    assert loaded.preferred_writer == "codex"
    record = json.loads(pa.record_path(home).read_text(encoding="utf-8"))
    assert record["allowed_providers"] == ["codex"] and record["engine_assignment_generation"] == 3


def test_writing_authority_into_config_yaml_changes_nothing(tmp_path, caplog):
    """The escalation this closes: the agent widens its own routing ceiling."""
    home = _home(tmp_path)
    _config(home, "allowed_providers:\n  - codex\n")
    assert load_universe_config(home).allowed_providers == ["codex"]  # migrated once

    _config(home, "allowed_providers:\n  - codex\n  - claude-code\n  - api_key_http:evil\n"
                  "engine_assignment_state: ready\nengine_assignment_generation: 99\n"
                  "provider_authority_bindings:\n  claude-code: {binding_id: forged}\n")
    loaded = load_universe_config(home)

    assert loaded.allowed_providers == ["codex"]
    assert loaded.engine_assignment_state == "unassigned"
    assert loaded.engine_assignment_generation == 0
    assert loaded.provider_authority_bindings == {}
    assert "ignored" in caplog.text


def test_a_never_assigned_home_gets_a_default_record_so_the_hole_never_opens(tmp_path):
    home = _home(tmp_path)
    assert load_universe_config(home).allowed_providers is None
    _config(home, "allowed_providers: [api_key_http:evil]\n")
    assert load_universe_config(home).allowed_providers is None


def test_an_unreadable_record_fails_closed(tmp_path):
    home = _home(tmp_path)
    pa.record_path(home).parent.mkdir()
    pa.record_path(home).write_text("{not json", encoding="utf-8")
    assert load_universe_config(home).allowed_providers == []


def test_a_missing_home_gets_defaults_and_is_never_created(tmp_path):
    ghost = tmp_path / "u-gone"
    assert load_universe_config(ghost).allowed_providers is None
    assert not ghost.exists()


def test_the_assignment_writer_puts_authority_in_the_record_and_strips_config(tmp_path):
    home = _home(tmp_path)
    _config(home, "allowed_providers: [codex]\nstyle: terse\n")
    write_provider_assignment_projection(
        home, state="ready", generation=2, provider="codex",
        binding={"binding_id": "b1"},
    )
    config_text = (home / "config.yaml").read_text(encoding="utf-8")
    for name in pa.AUTHORITY_FIELDS:
        assert name not in config_text
    assert "style: terse" in config_text and "preferred_writer: codex" in config_text
    loaded = load_universe_config(home)
    assert loaded.allowed_providers == ["codex"]
    assert loaded.provider_authority_bindings == {"codex": {"binding_id": "b1"}}


def test_the_generic_config_writer_refuses_authority(tmp_path):
    home = _home(tmp_path)
    with pytest.raises(ValueError, match="platform record"):
        write_universe_config_fields(home, allowed_providers=["claude-code"])
    write_universe_config_fields(home, preferred_writer="codex")  # preferences still fine


def test_the_record_is_invisible_to_the_agents_tool_jail():
    """Hidden home entries are never bound into the tool jail (universe_tools)."""
    assert pa.record_path("/h").parent.name.startswith(".")

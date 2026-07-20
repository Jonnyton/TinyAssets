from __future__ import annotations

import pytest

from tinyassets import daemon_registry


def test_create_soulless_daemon_uses_project_wide_daemon_id(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Quiet Worker",
        created_by="host",
        soul_mode="soulless",
    )

    assert daemon["daemon_id"].startswith("daemon::quiet-worker::")
    assert daemon["legacy_author_id"].startswith("author::quiet-worker::")
    assert daemon["display_name"] == "Quiet Worker"
    assert daemon["soul_mode"] == "soulless"
    assert daemon["has_soul"] is False
    assert daemon["domain_claims"] == []
    assert "soul_text" not in daemon


def test_create_soul_daemon_preserves_soul_claims_and_hash(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Lab Navigator",
        created_by="host",
        soul_mode="soul",
        soul_text="I prefer research nodes and cite uncertainty.",
        domain_claims=["scientist", "literature-review"],
    )

    loaded = daemon_registry.get_daemon(
        tmp_path, daemon_id=daemon["daemon_id"], include_soul=True,
    )
    assert loaded["soul_mode"] == "soul"
    assert loaded["has_soul"] is True
    assert loaded["domain_claims"] == ["scientist", "literature-review"]
    assert loaded["soul_text"] == "I prefer research nodes and cite uncertainty."
    assert len(loaded["soul_hash"]) == 64


def test_soul_daemon_requires_non_empty_soul_text(tmp_path):
    with pytest.raises(ValueError, match="soul_text is required"):
        daemon_registry.create_daemon(
            tmp_path,
            display_name="Empty Soul",
            created_by="host",
            soul_mode="soul",
            soul_text=" ",
        )


def test_duplicate_soul_hash_requires_lineage(tmp_path):
    first = daemon_registry.create_daemon(
        tmp_path,
        display_name="Original Steward",
        created_by="host",
        soul_mode="soul",
        soul_text="Preserve request records and route carefully.",
    )

    with pytest.raises(ValueError, match="duplicate soul_hash requires lineage_parent_id"):
        daemon_registry.create_daemon(
            tmp_path,
            display_name="Copied Steward",
            created_by="host",
            soul_mode="soul",
            soul_text="Preserve request records and route carefully.",
        )

    fork = daemon_registry.create_daemon(
        tmp_path,
        display_name="Forked Steward",
        created_by="host",
        soul_mode="soul",
        soul_text="Preserve request records and route carefully.",
        lineage_parent_id=first["daemon_id"],
    )

    assert fork["soul_hash"] == first["soul_hash"]
    assert fork["lineage_parent_id"] == first["daemon_id"]


def test_list_daemons_maps_existing_default_author_to_default_daemon(tmp_path):
    daemons = daemon_registry.list_daemons(tmp_path)

    assert len(daemons) == 1
    assert daemons[0]["display_name"] == "House Daemon"
    assert daemons[0]["daemon_id"].startswith("daemon::")
    assert daemons[0]["soul_mode"] == "soulless"


def test_summon_and_banish_daemon_wrap_runtime_instance(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Codex Runner",
        created_by="host",
        soul_text="Pick implementation work and finish it.",
    )

    runtime = daemon_registry.summon_daemon(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id="default-universe",
        provider_name="codex",
        model_name="gpt-5.4",
        created_by="host",
    )

    assert runtime["daemon_id"] == daemon["daemon_id"]
    assert runtime["legacy_author_id"] == daemon["legacy_author_id"]
    assert runtime["provider_name"] == "codex"
    assert runtime["model_name"] == "gpt-5.4"
    assert runtime["status"] == "provisioned"
    assert runtime["metadata"]["daemon_soul_hash"] == daemon["soul_hash"]

    retired = daemon_registry.banish_daemon(
        tmp_path, runtime_instance_id=runtime["runtime_instance_id"],
    )
    assert retired["runtime_instance_id"] == runtime["runtime_instance_id"]
    assert retired["status"] == "retired"


def test_summon_rejects_model_mismatch_for_bound_daemon(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Soren Cross Checker",
        created_by="host",
        soul_text="Check Claude-written loop patches.",
        metadata={"current_llm": "gpt-5.5", "model_track": "openai_flagship"},
    )

    with pytest.raises(ValueError, match="daemon model identity mismatch"):
        daemon_registry.summon_daemon(
            tmp_path,
            daemon_id=daemon["daemon_id"],
            universe_id="default-universe",
            provider_name="codex",
            model_name="gpt-5.4",
            created_by="host",
        )

    runtime = daemon_registry.summon_daemon(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id="default-universe",
        provider_name="codex",
        model_name="gpt-5.5",
        created_by="host",
    )

    assert runtime["model_name"] == "gpt-5.5"


def test_runtime_control_is_owner_scoped(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Control Runner",
        created_by="host",
        soul_text="Accept direct host control.",
    )
    runtime = daemon_registry.summon_daemon(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id="default-universe",
        provider_name="codex",
        model_name="gpt-5.4",
        created_by="host",
    )

    refused = daemon_registry.control_runtime_instance(
        tmp_path,
        runtime_instance_id=runtime["runtime_instance_id"],
        actor_id="someone-else",
        action="pause",
    )
    assert refused["effect"] == "refused"
    assert refused["authority_scope"] == "none"

    paused = daemon_registry.control_runtime_instance(
        tmp_path,
        runtime_instance_id=runtime["runtime_instance_id"],
        actor_id="host",
        action="pause",
    )
    assert paused["effect"] == "applied"
    assert paused["authority_scope"] == "owner"
    assert paused["runtime"]["status"] == "paused"


def test_update_daemon_behavior_records_versioned_policy(tmp_path):
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Policy Runner",
        created_by="host",
        soul_text="Let policy guide work selection.",
    )

    result = daemon_registry.update_daemon_behavior(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        actor_id="host",
        behavior_update={"preferred_domains": ["workflow-platform"]},
        apply_now=True,
    )

    assert result["effect"] == "applied"
    assert result["daemon"]["metadata"]["behavior_version"] == 1
    assert result["daemon"]["metadata"]["behavior_policy"] == {
        "preferred_domains": ["workflow-platform"],
    }


def test_provider_capacity_warning_is_advisory():
    assert daemon_registry.provider_capacity_warning(
        "claude-code", running_count=0,
    ) is None

    warning = daemon_registry.provider_capacity_warning(
        "claude-code", running_count=2,
    )

    assert warning is not None
    assert warning["provider_name"] == "claude-code"
    assert warning["next_count"] == 3
    assert warning["can_override"] is True


def test_select_project_loop_daemon_prefers_latest_soul_default(tmp_path):
    daemon_registry.create_daemon(
        tmp_path,
        display_name="Old Loop Default",
        created_by="host",
        soul_text="Prefer old maintenance work.",
        metadata={"project_loop_default": True},
    )
    selected = daemon_registry.create_daemon(
        tmp_path,
        display_name="Developer Loop Default",
        created_by="host",
        soul_text="Prefer project uptime and verified development work.",
        metadata={"project_loop_default": True},
        domain_claims=["developer", "workflow-platform"],
    )

    loop_daemon = daemon_registry.select_project_loop_daemon(
        tmp_path,
        include_soul=True,
    )

    assert loop_daemon is not None
    assert loop_daemon["daemon_id"] == selected["daemon_id"]
    assert loop_daemon["soul_text"] == (
        "Prefer project uptime and verified development work."
    )
    assert loop_daemon["domain_claims"] == ["developer", "workflow-platform"]


def test_select_project_loop_daemon_ignores_soulless_defaults(tmp_path):
    daemon_registry.create_daemon(
        tmp_path,
        display_name="Soulless Loop Default",
        created_by="host",
        soul_mode="soulless",
        metadata={"project_loop_default": True},
    )

    assert daemon_registry.select_project_loop_daemon(tmp_path) is None

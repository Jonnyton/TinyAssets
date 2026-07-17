"""Round-23 regressions for authoritative, non-ambient execution scope."""

from __future__ import annotations

import pytest

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.credential_vault import (
    RetiredSubscriptionLaneError,
    quarantine_legacy_subscription_records,
    write_credential_vault,
)
from tinyassets.execution_context import (
    get_execution_universe,
    pin_execution_universe,
)
from tinyassets.graph_compiler import _run_with_timeout
from tinyassets.providers.router import _preflight_retired_universe
from tinyassets.runs import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    _invoke_graph_resume,
    create_run,
    execute_branch,
    execute_branch_async,
    execute_branch_version_async,
    get_run,
    initialize_runs_db,
    list_runs,
    wait_for,
)
from tinyassets.sandbox_policy import ExecutionScope


def _provider_branch(branch_id: str = "r23-provider") -> BranchDefinition:
    return BranchDefinition(
        branch_def_id=branch_id,
        name="R23 provider",
        entry_point="call",
        node_defs=[
            NodeDefinition(
                node_id="call",
                display_name="Call",
                prompt_template="say hi",
                output_keys=["answer"],
            ),
        ],
        graph_nodes=[GraphNodeRef(id="call", node_def_id="call")],
        edges=[EdgeDefinition(from_node="call", to_node="END")],
    )


def _retire(universe_dir) -> None:
    write_credential_vault(universe_dir, [{
        "credential_type": "llm_subscription",
        "service": "claude",
        "oauth_token": "legacy",
    }])
    quarantine_legacy_subscription_records(universe_dir)


def test_sync_run_gates_authoritative_universe_not_fresh_process_global(
    tmp_path, monkeypatch,
):
    retired = tmp_path / "u-retired"
    fresh = tmp_path / "u-fresh"
    retired.mkdir()
    fresh.mkdir()
    _retire(retired)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))

    calls = {"count": 0}

    def provider(*_args, **_kwargs):
        calls["count"] += 1
        return "ambient-host-identity-used"

    outcome = execute_branch(
        tmp_path,
        branch=_provider_branch(),
        inputs={},
        actor="universe:u-retired",
        provider_call=provider,
        _enqueue_universe_id="u-retired",
    )

    assert outcome.status == RUN_STATUS_FAILED
    assert calls["count"] == 0


def test_completed_run_resets_pin_before_next_retired_preflight(
    tmp_path, monkeypatch,
):
    fresh = tmp_path / "u-fresh"
    retired = tmp_path / "u-retired"
    fresh.mkdir()
    retired.mkdir()
    _retire(retired)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))

    execute_branch(
        tmp_path,
        branch=_provider_branch("r23-pin-reset"),
        inputs={},
        provider_call=lambda *_args, **_kwargs: "ok",
    )

    assert get_execution_universe() is None
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(retired))
    with pytest.raises(RetiredSubscriptionLaneError):
        _preflight_retired_universe(None)


def test_execution_pin_crosses_node_timeout_thread_pool(tmp_path):
    universe = tmp_path / "u-threaded"
    universe.mkdir()

    with pin_execution_universe(universe):
        observed = _run_with_timeout(
            get_execution_universe,
            timeout_s=2,
            node_id="thread-hop",
        )

    assert observed == universe
    assert get_execution_universe() is None


def test_router_preflight_in_timeout_pool_prefers_pin_over_retired_global(
    tmp_path, monkeypatch,
):
    fresh = tmp_path / "u-fresh"
    retired_global = tmp_path / "u-retired-global"
    fresh.mkdir()
    retired_global.mkdir()
    _retire(retired_global)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(retired_global))

    with pin_execution_universe(fresh):
        _run_with_timeout(
            lambda: _preflight_retired_universe(None),
            timeout_s=2,
            node_id="router-thread-hop",
        )


def test_explicit_universe_id_scope_mismatch_fails_closed(tmp_path):
    first = tmp_path / "u-first"
    second = tmp_path / "u-second"
    first.mkdir()
    second.mkdir()
    calls = {"count": 0}

    outcome = execute_branch(
        tmp_path,
        branch=_provider_branch("r23-mismatch"),
        inputs={},
        provider_call=lambda *_a, **_k: calls.__setitem__(
            "count", calls["count"] + 1
        ) or "ambient",
        _enqueue_universe_id="u-first",
        execution_scope=ExecutionScope.bound(second),
    )

    assert outcome.status == RUN_STATUS_FAILED
    assert "unknown" in outcome.error
    assert calls["count"] == 0


def test_async_run_persists_and_gates_authoritative_universe(
    tmp_path, monkeypatch,
):
    retired = tmp_path / "u-retired"
    fresh = tmp_path / "u-fresh"
    retired.mkdir()
    fresh.mkdir()
    _retire(retired)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))
    calls = {"count": 0}

    def provider(*_args, **_kwargs):
        calls["count"] += 1
        return "ambient"

    queued = execute_branch_async(
        tmp_path,
        branch=_provider_branch("r23-async"),
        inputs={},
        actor="universe:u-retired",
        provider_call=provider,
        _enqueue_universe_id="u-retired",
    )
    wait_for(queued.run_id, timeout=5)
    record = get_run(tmp_path, queued.run_id)

    assert record is not None
    assert record["status"] == RUN_STATUS_FAILED
    assert record["universe_id"] == "u-retired"
    assert calls["count"] == 0


def test_version_run_gates_authoritative_universe(tmp_path, monkeypatch):
    from tinyassets.branch_versions import publish_branch_version

    retired = tmp_path / "u-retired"
    fresh = tmp_path / "u-fresh"
    retired.mkdir()
    fresh.mkdir()
    _retire(retired)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))
    version = publish_branch_version(
        tmp_path,
        _provider_branch("r23-version").to_dict(),
        publisher="test",
    )
    calls = {"count": 0}

    queued = execute_branch_version_async(
        tmp_path,
        branch_version_id=version.branch_version_id,
        inputs={},
        actor="universe:u-retired",
        provider_call=lambda *_a, **_k: calls.__setitem__(
            "count", calls["count"] + 1
        ) or "ambient",
        _enqueue_universe_id="u-retired",
    )
    wait_for(queued.run_id, timeout=5)

    assert get_run(tmp_path, queued.run_id)["status"] == RUN_STATUS_FAILED
    assert calls["count"] == 0


def test_resume_chokepoint_uses_persisted_universe_not_global(
    tmp_path, monkeypatch,
):
    retired = tmp_path / "u-retired"
    fresh = tmp_path / "u-fresh"
    retired.mkdir()
    fresh.mkdir()
    _retire(retired)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))
    initialize_runs_db(tmp_path)
    run_id = create_run(
        tmp_path,
        branch_def_id="r23-resume",
        thread_id="",
        inputs={},
        actor="universe:u-retired",
        universe_id="u-retired",
    )
    calls = {"count": 0}

    outcome = _invoke_graph_resume(
        tmp_path,
        run_id=run_id,
        branch=_provider_branch("r23-resume"),
        thread_id=run_id,
        provider_call=lambda *_a, **_k: calls.__setitem__(
            "count", calls["count"] + 1
        ) or "ambient",
    )

    assert outcome.status == RUN_STATUS_FAILED
    assert calls["count"] == 0


def test_nested_branch_inherits_bound_scope_across_real_child_run(
    tmp_path, monkeypatch,
):
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    fresh = tmp_path / "u-fresh"
    retired_global = tmp_path / "u-retired-global"
    fresh.mkdir()
    retired_global.mkdir()
    _retire(retired_global)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(retired_global))
    initialize_author_server(tmp_path)
    child = _provider_branch("r23-child")
    save_branch_definition(tmp_path, branch_def=child.to_dict())
    parent = BranchDefinition(
        branch_def_id="r23-parent",
        name="R23 parent",
        entry_point="child",
        node_defs=[NodeDefinition(
            node_id="child",
            display_name="Child",
            invoke_branch_spec={
                "branch_def_id": child.branch_def_id,
                "inputs_mapping": {},
                "output_mapping": {"child_answer": "answer"},
                "wait_mode": "blocking",
            },
            output_keys=["child_answer"],
        )],
        graph_nodes=[GraphNodeRef(id="child", node_def_id="child")],
        edges=[EdgeDefinition(from_node="child", to_node="END")],
    )

    outcome = execute_branch(
        tmp_path,
        branch=parent,
        inputs={},
        actor="universe:u-fresh",
        provider_call=lambda *_a, **_k: "ok",
        _enqueue_universe_id="u-fresh",
    )

    assert outcome.status == RUN_STATUS_COMPLETED
    records = list_runs(tmp_path, limit=10)
    assert {row["universe_id"] for row in records} == {"u-fresh"}

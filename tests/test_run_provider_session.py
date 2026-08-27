from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.exceptions import ProviderAuthorityHeldError
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage.provider_work_authority import db_path as authority_db_path


class _CountingProvider(BaseProvider):
    def __init__(self) -> None:
        self.name = "codex"
        self.family = "codex"
        self.calls: list[ModelConfig] = []

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        self.calls.append(config)
        return ProviderResponse(
            text="foreground-ok",
            provider=self.name,
            model="test-model",
            family=self.family,
            latency_ms=1.0,
            input_tokens=70,
            output_tokens=30,
            cost_microunits=5,
        )


def _branch(*, node_count: int, author: str = "acct_alice") -> BranchDefinition:
    nodes = [
        NodeDefinition(
            node_id=f"n{index}",
            display_name=f"Writer {index}",
            prompt_template=f"Write foreground result {index}.",
            output_keys=[f"answer_{index}"],
            model_hint="writer",
            llm_policy={"preferred": {"provider": "codex"}},
        )
        for index in range(1, node_count + 1)
    ]
    graph_nodes = [GraphNodeRef(id=node.node_id, node_def_id=node.node_id) for node in nodes]
    edges = [EdgeDefinition(from_node="START", to_node="n1")]
    edges.extend(
        EdgeDefinition(from_node=f"n{index}", to_node=f"n{index + 1}")
        for index in range(1, node_count)
    )
    edges.append(EdgeDefinition(from_node=f"n{node_count}", to_node="END"))
    return BranchDefinition(
        branch_def_id=f"branch_foreground_{node_count}",
        name="Foreground provider authority",
        author=author,
        visibility="private",
        graph_nodes=graph_nodes,
        edges=edges,
        entry_point="n1",
        node_defs=nodes,
        state_schema=[
            {"name": f"answer_{index}", "type": "str", "default": ""}
            for index in range(1, node_count + 1)
        ],
    )


def _seed_serving_assignment(
    base_path: Path,
    *,
    owner_user_id: str = "acct_alice",
    universe_id: str = "universe_alice",
) -> None:
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    universe_dir = base_path / universe_id
    universe_dir.mkdir(exist_ok=True)
    (universe_dir / "config.yaml").write_text(
        "preferred_writer: codex\nallowed_providers:\n  - codex\n",
        encoding="utf-8",
    )
    write_credential_vault(
        universe_dir,
        [
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "auth_json_b64": "e30=",
            }
        ],
        owner_user_id=owner_user_id,
        universe_id=universe_id,
    )
    definition = publish_definition(
        base_path,
        author_id=owner_user_id,
        payload={
            "schema_version": 1,
            "name": "Foreground agent",
            "description": "Serves foreground Branch runs.",
            "tags": ["test"],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    agent = create_binding(
        base_path,
        universe_id=universe_id,
        definition_id=definition["agent_definition_id"],
        created_by=owner_user_id,
        payload={"schema_version": 1, "name": "Foreground agent", "role": "writer"},
    )
    connected = bind_serving_provider(
        base_path=base_path,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    set_serving(
        base_path=base_path,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )


def _run_branch(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
    branch: BranchDefinition,
    *,
    authority_case: str = "active",
    mock_provider: bool = False,
) -> tuple[dict[str, Any], _CountingProvider, dict[str, Any]]:
    from tinyassets.api import runs as api_runs
    from tinyassets.daemon_server import save_branch_definition, set_founder_home
    from tinyassets.providers import call as call_module
    from tinyassets.runs import execute_branch_async, get_run, wait_for

    authenticate_request("acct_alice")
    set_founder_home(
        tmp_path,
        founder_sub="acct_alice",
        universe_id=(
            "universe_other" if authority_case == "cross_universe" else "universe_alice"
        ),
        platform_generated=True,
    )
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    universe_dir = tmp_path / "universe_alice"
    universe_dir.mkdir(exist_ok=True)
    (universe_dir / "config.yaml").write_text(
        "preferred_writer: codex\nallowed_providers:\n  - codex\n",
        encoding="utf-8",
    )
    if authority_case != "missing":
        _seed_serving_assignment(tmp_path)
    if authority_case in {"revoked", "stale"}:
        conn = sqlite3.connect(authority_db_path(tmp_path))
        if authority_case == "revoked":
            conn.execute(
                "UPDATE provider_work_bindings SET state = 'revoked' "
                "WHERE record_json LIKE '%\"allowed_operations\":[\"converse\"]%'"
            )
        else:
            conn.execute(
                "UPDATE provider_assignments SET generation = generation + 1 "
                "WHERE universe_id = 'universe_alice'"
            )
        conn.commit()
        conn.close()

    captured: dict[str, Any] = {}
    captured["effects"] = []

    def capture_execute(*args: Any, provider_call=None, **kwargs: Any):
        captured["provider_call"] = provider_call
        return execute_branch_async(*args, provider_call=provider_call, **kwargs)

    monkeypatch.setattr(api_runs, "_ensure_runs_recovery", lambda: None)
    monkeypatch.setattr(api_runs, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(
        api_runs,
        "_universe_dir",
        lambda _uid: tmp_path / "universe_alice",
    )
    monkeypatch.setattr(
        api_runs,
        "_request_universe",
        lambda uid="": uid or "universe_alice",
    )
    monkeypatch.setattr("tinyassets.runs.execute_branch_async", capture_execute)
    monkeypatch.setattr(
        "tinyassets.runs._run_external_write_effectors",
        lambda *args, **kwargs: captured["effects"].append((args, kwargs)),
    )

    provider = _CountingProvider()
    provider_router = ProviderRouter({provider.name: provider})

    def governed_provider_call(
        prompt,
        system="",
        *,
        role="writer",
        config=None,
        universe_context=None,
        operation=None,
        **_kwargs,
    ):
        return provider_router.call_sync(
            role,
            prompt,
            system,
            config,
            universe_context=universe_context,
            operation=operation,
        ).text

    injected_provider_call = (
        (lambda prompt, _system="", **_kwargs: f"fixture:{prompt}")
        if mock_provider
        else governed_provider_call
    )
    monkeypatch.setattr(call_module, "call_provider", injected_provider_call)
    bind_run_provider = api_runs._bind_run_provider_call
    monkeypatch.setattr(
        api_runs,
        "_bind_run_provider_call",
        lambda _ambient_provider_call, universe_id: bind_run_provider(
            injected_provider_call,
            universe_id,
        ),
    )
    response = json.loads(
        api_runs._action_run_branch(
            {
                "branch_def_id": branch.branch_def_id,
                "universe_id": "universe_alice",
            }
        )
    )
    assert "run_id" in response, response
    wait_for(response["run_id"], timeout=10)
    record = get_run(tmp_path, response["run_id"])
    assert record is not None
    response["terminal_status"] = record["status"]
    response["terminal_error"] = record["error"]
    return response, provider, captured


def test_mock_foreground_run_needs_no_serving_binding_or_run_receipt(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        _branch(node_count=1),
        authority_case="missing",
        mock_provider=True,
    )

    assert response["terminal_status"] == "completed", response["terminal_error"]
    assert provider.calls == []
    assert len(captured["effects"]) == 1
    db = authority_db_path(tmp_path)
    if db.exists():
        with sqlite3.connect(db) as conn:
            receipt_table = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'provider_work_receipts'"
            ).fetchone()[0]
            assert receipt_table == 0 or conn.execute(
                "SELECT COUNT(*) FROM provider_work_receipts"
            ).fetchone()[0] == 0


def test_foreground_run_launches_active_serving_provider_and_settles_once(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    response, provider, _captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        _branch(node_count=1),
    )

    assert response["terminal_status"] == "completed", response["terminal_error"]
    assert len(provider.calls) == 1
    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    reservation = conn.execute(
        "SELECT state, actual_total_tokens, actual_cost_microunits "
        "FROM provider_invocation_reservations"
    ).fetchone()
    receipt = conn.execute(
        "SELECT work_item_kind, work_item_id FROM provider_work_receipts"
    ).fetchone()
    claim = conn.execute(
        "SELECT state FROM provider_work_execution_claims"
    ).fetchone()
    conn.close()

    assert dict(reservation) == {
        "state": "succeeded",
        "actual_total_tokens": 100,
        "actual_cost_microunits": 5,
    }
    assert dict(receipt) == {
        "work_item_kind": "run",
        "work_item_id": response["run_id"],
    }
    assert claim["state"] == "released"


def test_foreground_run_mints_one_carrier_per_node_and_refuses_n_plus_one(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        _branch(node_count=2),
    )

    assert response["terminal_status"] == "completed", response["terminal_error"]
    assert len(provider.calls) == 2
    with pytest.raises(ProviderAuthorityHeldError):
        captured["provider_call"]("one call too many")
    with pytest.raises(PermissionError, match="operation"):
        captured["provider_call"]("wrong operation", operation="converse")

    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT reservation_id, invocation_key, ordinal, state "
        "FROM provider_invocation_reservations ORDER BY ordinal"
    ).fetchall()
    conn.close()
    assert [row["ordinal"] for row in rows] == [1, 2]
    assert len({row["reservation_id"] for row in rows}) == 2
    assert len({row["invocation_key"] for row in rows}) == 2
    assert [row["state"] for row in rows] == ["succeeded", "succeeded"]


@pytest.mark.parametrize(
    "authority_case",
    ["missing", "stale", "revoked", "cross_universe"],
)
def test_foreground_run_authority_mismatch_launches_nothing_and_runs_no_effects(
    authority_case: str,
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        _branch(node_count=1),
        authority_case=authority_case,
    )

    assert response["terminal_status"] == "failed"
    assert "Connect your provider before running this universe" in response[
        "terminal_error"
    ]
    assert provider.calls == []
    assert captured["effects"] == []


def test_foreground_run_rejects_policy_outside_active_provider_before_effects(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    branch = _branch(node_count=1)
    branch.node_defs[0].llm_policy = {
        "preferred": {"provider": "claude-code"},
    }
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        branch,
    )

    assert response["terminal_status"] == "failed"
    assert provider.calls == []
    assert captured["effects"] == []


def test_foreground_run_rejects_branch_not_authored_by_authenticated_principal(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        _branch(node_count=1, author="acct_bob"),
    )

    assert response["terminal_status"] == "failed"
    assert provider.calls == []
    assert captured["effects"] == []


def test_foreground_run_rejects_unsupported_provider_role_before_launch(
    tmp_path: Path,
    monkeypatch,
    authenticate_request,
) -> None:
    branch = _branch(node_count=1)
    branch.node_defs[0].model_hint = "reader"
    response, provider, captured = _run_branch(
        tmp_path,
        monkeypatch,
        authenticate_request,
        branch,
    )

    assert response["terminal_status"] == "failed"
    assert provider.calls == []
    assert captured["effects"] == []

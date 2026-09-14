"""Actual claimed queue/admission/agent path; only remote transports are synthetic."""

import json
import sqlite3

import pytest

from tests import test_background_budget_finalization_e2e as background
from tests import test_workflow_http_agent as foreground
from tests.test_run_provider_session import _seed_open_serving_assignment
from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
from tinyassets.daemon_server import grant_universe_access, set_founder_home
from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.runs import get_run_by_branch_task_id
from tinyassets.storage.provider_work_authority import db_path

http_wire = foreground.http_wire
work_agent = foreground.work_agent


def run(tmp_path, monkeypatch, *, native=False):
    seed = background._seed_branch_version
    monkeypatch.setattr(background, "_seed_branch_version",
                        lambda root, **kwargs: seed(root, agent=True, **kwargs))
    access = None if native else ModelAccess("discovered")
    set_founder_home(tmp_path, founder_sub="acct_alice", universe_id="universe_alice",
                     platform_generated=True)
    grant_universe_access(tmp_path, universe_id="universe_alice", actor_id="acct_alice",
                          permission="admin", granted_by="acct_alice")
    source = "codex" if native else _seed_open_serving_assignment(
        tmp_path, monkeypatch, model_access=access,
    )
    task_id, _, _, _, _ = background._run_consumer_once(
        tmp_path, monkeypatch, model_access=access,
        setup_serving=None if native else lambda: None,
        policy={"preferred": {"provider": source, "model": "" if native else "synthetic-model"},
                "fallback_chain": []},
    )
    return Epoch2BranchTaskAdapter(tmp_path).get(task_id), get_run_by_branch_task_id(
        tmp_path, branch_task_id=task_id,
    )


def test_background_tool_then_model_share_original_work_receipt(tmp_path, monkeypatch, work_agent):
    task, result = run(tmp_path, monkeypatch)
    if task.status != "succeeded":
        pytest.fail(str(result) + "\n" + "\n".join(work_agent.errors))
    assert len(work_agent.wires) == 2 and len(work_agent.tools) == 1
    turn = work_agent.latest()
    assert turn.state == "completed"
    with sqlite3.connect(db_path(tmp_path)) as conn:
        rows = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations ORDER BY ordinal",
        )]
        receipt = json.loads(conn.execute(
            "SELECT record_json FROM provider_work_receipts",
        ).fetchone()[0])
    assert len(rows) == 2 and all(row["state"] == "succeeded" for row in rows)
    assert {row["receipt_id"] for row in rows} == {turn.work_receipt_id} == {receipt["receipt_id"]}
    assert receipt["work_item_kind"] == "background_attempt"
    assert len({row["claim_id"] for row in rows}) == 1
    assert len({row["invocation_key"] for row in rows}) == 2
    assert sum(row["actual_total_tokens"] for row in rows) == 14
    assert "known work result" in json.dumps(work_agent.wires[1]["body"])


@pytest.mark.parametrize("mode", ["unknown_tool", "unknown_inference", "later_capacity"])
def test_background_never_replays_effectful_or_unknown_work(
    tmp_path, monkeypatch, work_agent, mode,
):
    work_agent.mode = mode
    task, result = run(tmp_path, monkeypatch)
    assert task.status == "failed", result
    assert len(work_agent.wires) == (2 if mode == "later_capacity" else 1)
    assert len(work_agent.tools) == (0 if mode == "unknown_inference" else 1)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_turns").fetchone() == (1,)


@pytest.mark.parametrize("stage", ["before_tool", "after_tool"])
@pytest.mark.parametrize("change", ["cancel", "activation", "consumer", "lease", "member", "admin"])
def test_background_fresh_authority_stops_before_first_tool(
    tmp_path, monkeypatch, work_agent, change, stage,
):
    def mutate():
        with sqlite3.connect(db_path(tmp_path)) as conn:
            if change == "cancel":
                conn.execute("UPDATE branch_tasks_v2 SET status = 'cancel_requested'")
            elif change == "activation":
                conn.execute("UPDATE automation_activations SET epoch = epoch + 1")
            elif change == "consumer":
                conn.execute("UPDATE branch_tasks_v2 SET claimed_by = 'another-consumer'")
            elif change == "lease":
                conn.execute("UPDATE branch_tasks_v2 SET lease_expires_at = '2020-01-01T00:00:00Z'")
            elif change == "member":
                conn.execute("UPDATE provider_work_bindings SET state = 'revoked'")
            else:
                conn.execute("UPDATE universe_acl SET permission = 'read'")

    setattr(work_agent, stage, mutate)
    task, result = run(tmp_path, monkeypatch)
    assert task.status != "succeeded", result
    assert len(work_agent.wires) == 1
    assert len(work_agent.tools) == (1 if stage == "after_tool" else 0)
    assert work_agent.latest().rounds[0].tools[0].state == (
        "completed" if stage == "after_tool" else "planned"
    )


@pytest.mark.parametrize("outcome", ["success", "known_capacity", "unknown_capacity"])
def test_native_background_uses_work_authority_and_no_effects_evidence(
    tmp_path, monkeypatch, work_agent, outcome,
):
    from tinyassets.exceptions import ProviderRateLimitedError
    from tinyassets.providers.agent_capacity_boundary import NativeCompletionEvidence
    from tinyassets.providers.base import ProviderResponse
    from tinyassets.storage.agent_turn_journal import AgentTurnJournal

    calls = []

    async def native(self, prompt, system, config, *, universe_dir=None):
        turn = work_agent.latest()
        assert turn.state == "native_started" and turn.authority_kind == "work_invocation"
        assert config.engine_mcp_actor_id == "acct_alice"
        assert config.engine_mcp_graph_id == "universe_alice"
        assert config.agent_request is None and config.selected_model is None
        calls.append(prompt)
        if outcome != "success":
            exc = ProviderRateLimitedError("synthetic background capacity", retry_after=30)
            exc.attempt_telemetry = {"side_effect_state": "none"}
            if outcome == "known_capacity":
                exc.native_evidence = NativeCompletionEvidence("codex", True, True, "none")
            raise exc
        return ProviderResponse(
            text="background native work completed", provider="codex", model="native-default",
            family="codex", latency_ms=1, input_tokens=3, output_tokens=4, cost_microunits=0,
            native_evidence=NativeCompletionEvidence("codex", True, True, "committed"),
        )

    monkeypatch.setattr(background._CountingProvider, "agent_execution_kind", "native_agent",
                        raising=False)
    monkeypatch.setattr(background._CountingProvider, "complete", native)
    task, result = run(tmp_path, monkeypatch, native=True)
    assert (task.status == "succeeded") == (outcome == "success"), (result, work_agent.errors)
    assert len(calls) == 1 and work_agent.wires == [] and work_agent.tools == []
    journal = AgentTurnJournal(tmp_path)
    with journal._ledger.connection() as conn:
        turns = [journal.get("acct_alice", "universe_alice", row[0]) for row in conn.execute(
            "SELECT turn_id FROM agent_turns ORDER BY created_at",
        )]
    recorded = [turn for turn in turns if turn.rounds]
    assert len(recorded) == 1
    assert recorded[0].state == {
        "success": "completed", "known_capacity": "held_native_capacity",
        "unknown_capacity": "held_native_unknown",
    }[outcome]
    if outcome == "known_capacity":
        assert recorded[0].rounds[0].reply.evidence.protocol_complete
    elif outcome == "unknown_capacity":
        assert len(turns) == 1
    if outcome != "success":
        with sqlite3.connect(db_path(tmp_path)) as conn:
            reservation = json.loads(conn.execute(
                "SELECT record_json FROM provider_invocation_reservations ORDER BY ordinal LIMIT 1",
            ).fetchone()[0])
        assert reservation["state"] == "indeterminate"
        assert reservation["actual_total_tokens"] is None


def test_background_agent_cannot_exceed_existing_attempt_count(tmp_path, monkeypatch, work_agent):
    work_agent.mode = "ongoing_tools"
    task, result = run(tmp_path, monkeypatch)
    assert task.status != "succeeded", result
    assert len(work_agent.wires) == len(work_agent.tools) == 2
    with sqlite3.connect(db_path(tmp_path)) as conn:
        receipt = json.loads(conn.execute(
            "SELECT record_json FROM provider_work_receipts",
        ).fetchone()[0])
        assert conn.execute("SELECT COUNT(*) FROM agent_turns").fetchone() == (1,)
        assert conn.execute(
            "SELECT COUNT(*) FROM provider_invocation_reservations",
        ).fetchone() == (2,)
    assert receipt["max_invocations"] == 2
    assert all(tool.state == "completed"
               for step in work_agent.latest().rounds for tool in step.tools)


@pytest.mark.parametrize("phase", ["route", "discovery"])
def test_background_prelaunch_failures_do_not_spend_provider_budget(
    tmp_path, monkeypatch, work_agent, phase,
):
    if phase == "route":
        monkeypatch.setattr("tinyassets.engine_mcp_http.read_engine_mcp_route", lambda **k: None)
    else:
        work_agent.mode = "discovery_failure"
    task, result = run(tmp_path, monkeypatch)
    assert task.status != "succeeded", result
    assert work_agent.wires == [] and work_agent.tools == []
    with sqlite3.connect(db_path(tmp_path)) as conn:
        rows = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations",
        )]
    assert len(rows) == (0 if phase == "route" else 1)
    assert all(row["state"] == "cancelled_before_launch" for row in rows)
    assert all(row["actual_total_tokens"] == row["actual_cost_microunits"] == 0 for row in rows)


@pytest.mark.parametrize("field", ["provider_request", "provider_invocation", "served_provider",
                                  "agent_model_plan", "model_selection", "universe_dir"])
def test_background_rejects_caller_context_substitution_before_admission(tmp_path, field):
    from dataclasses import replace
    from types import SimpleNamespace

    from tinyassets.background_served_provider import _BackgroundAssignedProviderSession
    from tinyassets.providers.base import ModelConfig, UniverseContext

    session = _BackgroundAssignedProviderSession(
        tmp_path, SimpleNamespace(universe_id="universe_alice"), None, None,
    )
    value = tmp_path / "another-root" / "universe_alice" if field == "universe_dir" else object()
    context = replace(UniverseContext(universe_dir=tmp_path / "universe_alice", config=None),
                      **{field: value})
    with pytest.raises(PermissionError, match="cannot be substituted"):
        session._call("writer", "prompt", "", ModelConfig(), None, {"universe_context": context})
    assert session._call_index == 0

"""Activities yield through the real HTTP compiler/router/journal lifecycle."""

import json
import sqlite3

import pytest

from tests import test_workflow_http_agent as workflow_tests
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_run_provider_session import _branch, _run_branch
from tinyassets import activity_runner, agent_activities, engine_mcp_server, shared_self
from tinyassets.foreground_run_provider import _ForegroundRunProviderSession
from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.storage.provider_work_authority import db_path

pytestmark = pytest.mark.usefixtures("cloud_runtime")
http_wire = workflow_tests.http_wire
work_agent = workflow_tests.work_agent


@pytest.mark.parametrize("batched_tool", [False, True])
@pytest.mark.parametrize("immediate_answer", [False, True])
def test_http_activity_yield_stops_tools_and_inference_and_releases_claim(
    tmp_path, monkeypatch, authenticate_request, work_agent, batched_tool, immediate_answer,
):
    universe = tmp_path / "universe_alice"
    universe.mkdir(exist_ok=True)
    record = agent_activities.create(
        universe, owner_principal="acct_alice", title="Ask before sending", brief="b",
        origin_kind="ask",
    )
    aid = record["activity_id"]
    generation = agent_activities.claim(universe, aid, replaceable=lambda _: False)
    prepare = _ForegroundRunProviderSession.prepare
    run_ids = []

    def bind_before_start(session, **kwargs):
        prepare(session, **kwargs)
        run_ids.append(kwargs["run_id"])
        assert agent_activities.bind_run(universe, aid, generation, kwargs["run_id"])

    monkeypatch.setattr(_ForegroundRunProviderSession, "prepare", bind_before_start)
    shared_turn = shared_self.prepare_shared_self_turn

    def prepare_activity(*args, activity):
        assert activity["activity_id"] == aid and activity["runner_generation"] == generation
        assert activity["runner_token"] == run_ids[0]
        return shared_turn(*args)

    monkeypatch.setattr(shared_self, "prepare_shared_self_turn", prepare_activity)
    monkeypatch.setattr(engine_mcp_server, "_GRAPH_ID", universe.name)
    monkeypatch.setattr(engine_mcp_server, "_calling_session", lambda: f"activity:{aid}")
    proxy = ApiKeyHttpProvider._resolve_proxy(None)

    class AskThenAct:
        def close(self):
            proxy.close()

        def request(self, verb, document):
            result = proxy.request(verb, document)
            body = json.loads(result["body"])
            message = body["choices"][0]["message"]
            if "tool_calls" in message:
                message["tool_calls"][0]["function"] = {
                    "name": "write_graph", "arguments": json.dumps({
                        "target": "pending_request", "operation": "ask", "payload_json": "{}",
                    }),
                }
                if batched_tool:
                    message["tool_calls"].append({
                        "id": "must-not-run", "type": "function", "function": {
                            "name": "write_graph", "arguments": '{"target":"branch"}',
                        },
                    })
            return {**result, "body": json.dumps(body)}

    monkeypatch.setattr(ApiKeyHttpProvider, "_resolve_proxy", lambda *a, **k: AskThenAct())

    def yield_after_ask():
        assert work_agent.tools[-1][1]["target"] == "pending_request"
        result = engine_mcp_server._yield_activity({"request_id": "req-http-yield"})
        assert result["activity_waiting"]
        if immediate_answer:
            assert agent_activities.answered(universe, aid, "req-http-yield")

    work_agent.after_tool = yield_after_ask
    branch = _branch(node_count=1)
    branch.branch_def_id = activity_runner.branch_def_id(universe.name)
    branch.node_defs[0].tools_allowed = ["universe_self"]
    branch.node_defs[0].llm_policy = {"preferred": {"model": "synthetic-model"},
                                    "fallback_chain": []}
    result = _run_branch(tmp_path, monkeypatch, authenticate_request, branch,
                         open_provider=True, model_access=ModelAccess("discovered"))[0]
    assert result["terminal_status"] == "completed", result
    assert len(work_agent.wires) == 1 and len(work_agent.tools) == 1 and work_agent.closed
    turn = work_agent.latest()
    assert len(turn.rounds) == 1 and turn.rounds[0].tools[0].state == "completed"
    assert "known work result" in turn.rounds[0].tools[0].result_json
    if batched_tool:
        assert turn.rounds[0].tools[1].state == "not_sent"
        assert turn.state == "held_tool_not_sent"
    else:
        assert turn.state == "abandoned", "the settled round closes without another inference"
    current = agent_activities.get(universe, aid)
    assert current["status"] == (agent_activities.SCHEDULED if immediate_answer
                                 else agent_activities.WAITING_ON_YOU)
    assert current["retiring_token"] == run_ids[0] and not current["runner_token"]
    assert activity_runner.state(tmp_path, run_ids[0]) == activity_runner.ENDED
    with sqlite3.connect(db_path(tmp_path)) as conn:
        assert conn.execute("SELECT state FROM provider_work_execution_claims").fetchall() == [
            ("released",),
        ]
        assert conn.execute("SELECT state FROM provider_invocation_reservations").fetchall() == [
            ("succeeded",),
        ]


def test_activity_binding_cannot_inherit_a_replacement_run(tmp_path):
    universe = tmp_path / "u-alpha"
    universe.mkdir()
    record = agent_activities.create(
        universe, owner_principal="acct_alice", title="t", brief="b", origin_kind="ask",
    )
    aid = record["activity_id"]
    generation = agent_activities.claim(universe, aid, replaceable=lambda _: False)
    assert agent_activities.bind_run(universe, aid, generation, "old-run")
    binding = activity_runner.ActivityRunBinding(universe, aid, generation, "old-run")
    binding.check()
    replacement = agent_activities.claim(universe, aid, replaceable=lambda _: True)
    assert agent_activities.bind_run(universe, aid, replacement, "new-run")
    with pytest.raises(PermissionError, match="activity_runner_superseded"):
        binding.check()
    assert not agent_activities.holds(universe, aid, replacement, run_id="old-run")
    assert agent_activities.holds(universe, aid, replacement, run_id="new-run")


@pytest.mark.parametrize("status", [agent_activities.PAUSED, agent_activities.COMPLETED])
def test_owner_pause_or_stop_is_not_reclassified_as_a_yield(tmp_path, status):
    universe = tmp_path / "u-alpha"
    universe.mkdir()
    record = agent_activities.create(
        universe, owner_principal="acct_alice", title="t", brief="b", origin_kind="ask",
    )
    aid = record["activity_id"]
    generation = agent_activities.claim(universe, aid, replaceable=lambda _: False)
    assert agent_activities.bind_run(universe, aid, generation, "run-1")
    binding = activity_runner.ActivityRunBinding(universe, aid, generation, "run-1")
    agent_activities.transition(universe, aid, status, result_summary="partial result")
    with pytest.raises(PermissionError, match="activity_runner_superseded"):
        binding.check()
    assert agent_activities.get(universe, aid)["result_summary"] == "partial result"

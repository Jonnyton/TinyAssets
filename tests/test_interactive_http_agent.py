"""Real writer/router/adapter/journal/client composition, synthetic remote wires."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from tests import test_selected_model_authority as authority_tests
from tinyassets import engine_mcp_http, engine_tool_client, universe_intelligence
from tinyassets.providers import call as provider_calls
from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.providers.base import ModelConfig
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
from tinyassets.storage.agent_turn_journal import AgentTurnJournal

rig = authority_tests.rig
reader = authority_tests.reader
served = authority_tests.served


@pytest.fixture
def agent(served, monkeypatch):
    from tinyassets.daemon_server import set_founder_home

    base = served.rig.base
    uid = served.context.universe_dir.name
    set_founder_home(base, founder_sub="owner", universe_id=uid, platform_generated=True)
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", uid)
    engine_mcp_http._write_routes(
        base,
        [
            SimpleNamespace(
                universe_id=uid,
                owner="owner",
                port=8790,
                secret="s" * 43,
            )
        ],
    )
    journal = AgentTurnJournal(base)

    def latest():
        with journal._ledger.connection() as conn:
            row = conn.execute(
                "SELECT turn_id FROM agent_turns ORDER BY created_at DESC"
            ).fetchone()
        return journal.get("owner", uid, row[0])

    state = SimpleNamespace(
        served=served,
        journal=journal,
        latest=latest,
        wires=[],
        tools=[],
        requested_rounds=1,
        fail_tool=False,
        closed=False,
        before_reply=None,
        unknown_inference=False,
        config=ModelConfig(
            engine_mcp_enabled=True,
            engine_mcp_actor_id="owner",
            engine_mcp_graph_id=uid,
            max_tokens=1024,
            absolute_cap_s=120,
        ),
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            state.closed = True

        def is_connected(self):
            return not state.closed

        async def list_tools_mcp(self, *, cursor=None):
            return ListToolsResult(
                tools=[
                    Tool(name=name, inputSchema={"type": "object"})
                    for name in SERVED_ENGINE_MCP_TOOLS
                ]
            )

        async def call_tool_mcp(self, name, arguments):
            assert latest().rounds[-1].tools[0].state == "started"
            state.tools.append((name, arguments))
            if state.fail_tool:
                raise RuntimeError("synthetic post-dispatch disconnect")
            return CallToolResult(content=[TextContent(type="text", text="exact result 🪐")])

    class Proxy:
        def close(self):
            pass

        def request(self, verb, document):
            assert latest().state == "inference_started"
            assert latest().rounds[-1].candidate.reservation_id
            state.wires.append((verb, document))
            if state.unknown_inference:
                return {"error": "synthetic post-dispatch disconnect"}
            if state.before_reply is not None:
                state.before_reply()
            tools = len(state.wires) <= state.requested_rounds
            message = {"role": "assistant", "content": None if tools else "finished exact answer"}
            if tools:
                message["tool_calls"] = [
                    {
                        "id": "same-wire-id",
                        "type": "function",
                        "function": {
                            "name": "read_graph",
                            "arguments": ' {"target": "status"} ',
                        },
                    }
                ]
            return {
                "status": 200,
                "body": json.dumps(
                    {
                        "model": "actual-answer-model",
                        "choices": [
                            {"message": message, "finish_reason": "tool_calls" if tools else "stop"}
                        ],
                    }
                ),
            }

    monkeypatch.setattr(engine_tool_client, "_make_client", lambda *_: Client())
    monkeypatch.setattr(ApiKeyHttpProvider, "_resolve_proxy", lambda *args, **kwargs: Proxy())
    monkeypatch.setattr(provider_calls, "_real_router", served.router)
    monkeypatch.setattr(provider_calls, "_force_mock", False)
    return state


def run(agent, observer=None):
    return universe_intelligence._call_writer(
        "exact user prompt",
        system="exact system",
        universe_context=agent.served.context,
        config=agent.config,
        response_observer=observer,
    )


def test_actual_writer_runs_tool_then_continues_and_reports_only_final_response(agent):
    receipts = []
    assert run(agent, receipts.append) == "finished exact answer"
    assert len(agent.wires) == 2 and len(agent.tools) == 1 and agent.closed
    assert agent.latest().state == "completed"
    assert len(receipts) == 1 and receipts[0].agent_reply.stop == "completed"
    assert receipts[0].reported_model == "actual-answer-model"
    messages = agent.wires[-1][1]["body"]["messages"]
    assert json.loads(messages[-1]["content"])["content"][0]["text"] == "exact result 🪐"
    with agent.journal._ledger.connection() as conn:
        rows = conn.execute("SELECT * FROM served_provider_budget_reservations").fetchall()
        assert len(rows) == 2


def test_more_than_two_inferences_use_sealed_real_binding_allowance(agent):
    agent.requested_rounds = 3
    assert run(agent) == "finished exact answer"
    assert len(agent.wires) == 4 and len(agent.tools) == 3
    assert len(agent.latest().rounds) == 4


def test_unknown_tool_outcome_never_replayed_or_followed_by_inference(agent):
    agent.fail_tool = True
    with pytest.raises(engine_tool_client.EngineToolError, match="unknown"):
        run(agent)
    assert len(agent.wires) == len(agent.tools) == 1
    assert agent.latest().state == "held_tool_unknown"


def test_cancelled_tool_is_held_not_replayed(agent, monkeypatch):
    async def cancelled(self, name, arguments):
        raise asyncio.CancelledError

    monkeypatch.setattr(engine_tool_client.EngineToolSession, "call", cancelled)
    with pytest.raises(asyncio.CancelledError):
        run(agent)
    assert len(agent.wires) == 1 and agent.latest().state == "held_tool_unknown"


def test_claim_refusal_records_no_launched_round_and_sends_nothing(agent, monkeypatch):
    from tinyassets.auth import middleware
    from tinyassets.exceptions import ProviderAuthorityHeldError

    def refused(*args, **kwargs):
        raise PermissionError("synthetic revoked capability")

    monkeypatch.setattr(middleware, "consume_provider_request_invocation", refused)
    with pytest.raises(ProviderAuthorityHeldError):
        run(agent)
    assert not agent.wires and not agent.tools
    assert agent.latest().state == "abandoned" and not agent.latest().rounds


def test_failed_intent_commit_never_dispatches_network(agent, monkeypatch):
    from tinyassets.exceptions import AllProvidersExhaustedError

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(AgentTurnJournal, "begin_round", fail)
    with pytest.raises(AllProvidersExhaustedError):
        run(agent)
    assert not agent.wires and not agent.tools
    assert agent.latest().state == "abandoned"
    with agent.journal._ledger.connection() as conn:
        rows = conn.execute(
            "SELECT state, actual_total_tokens, actual_cost_microunits "
            "FROM served_provider_budget_reservations"
        ).fetchall()
        assert [tuple(row) for row in rows] == [("succeeded", 0, 0)]


def test_known_result_storage_failure_never_repeats_the_action(agent, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic result storage failure")

    monkeypatch.setattr(AgentTurnJournal, "finish_tool", fail)
    with pytest.raises(RuntimeError, match="result storage"):
        run(agent)
    assert len(agent.wires) == len(agent.tools) == 1
    assert agent.latest().rounds[-1].tools[0].state == "started"


def test_home_revoked_after_inference_refuses_tool_and_does_not_recreate_home(agent):
    from tinyassets.storage.current_home import CurrentHomeChanged

    def revoke():
        with agent.journal._ledger.connection() as conn:
            conn.execute("DELETE FROM founder_home WHERE founder_sub = 'owner'")

    agent.before_reply = revoke
    with pytest.raises(CurrentHomeChanged):
        run(agent)
    assert len(agent.wires) == 1 and not agent.tools
    assert agent.latest().state == "inference_started"


def test_agent_requires_discovered_tool_support_before_network(agent, monkeypatch):
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers import discovery_snapshot

    original = discovery_snapshot.read_http_discovery_document

    def text_only(**kwargs):
        document = original(**kwargs)
        if "benchmarks" not in kwargs["url"]:
            for model in document["data"]:
                model["supported_parameters"] = []
        return document

    monkeypatch.setattr(discovery_snapshot, "read_http_discovery_document", text_only)
    with pytest.raises(ProviderAuthorityHeldError):
        run(agent)
    assert not agent.wires and not agent.tools and agent.latest().state == "abandoned"


def test_unknown_inference_outcome_is_not_settled_as_zero_spend(agent):
    from tinyassets.exceptions import AllProvidersExhaustedError

    agent.unknown_inference = True
    with pytest.raises(AllProvidersExhaustedError):
        run(agent)
    assert len(agent.wires) == 1 and not agent.tools
    assert agent.latest().state == "held_transport"
    with agent.journal._ledger.connection() as conn:
        rows = conn.execute("SELECT state FROM served_provider_budget_reservations").fetchall()
        assert [row[0] for row in rows] == ["indeterminate"]


@pytest.mark.parametrize("failure", ["claim", "intent", "history"])
def test_later_pre_intent_failure_closes_known_progress(agent, monkeypatch, failure):
    from tinyassets.auth import middleware
    from tinyassets.exceptions import AllProvidersExhaustedError, ProviderAuthorityHeldError
    from tinyassets.interactive_http_agent import InteractiveHttpAgentTurn
    from tinyassets.storage.agent_turn_journal import reset_blockers

    target, name = {
        "claim": (middleware, "consume_provider_request_invocation"),
        "intent": (AgentTurnJournal, "begin_round"),
        "history": (InteractiveHttpAgentTurn, "_history"),
    }[failure]
    original = getattr(target, name)

    def refuse_later(*args, **kwargs):
        if agent.tools:
            raise PermissionError("synthetic later pre-intent failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, refuse_later)
    expected = {
        "claim": ProviderAuthorityHeldError,
        "intent": AllProvidersExhaustedError,
        "history": PermissionError,
    }[failure]
    with pytest.raises(expected):
        run(agent)
    turn = agent.latest()
    assert turn.state == "abandoned" and len(turn.rounds) == 1
    assert len(agent.wires) == len(agent.tools) == 1
    assert turn.rounds[0].tools[0].state == "completed"
    assert "exact result" in turn.rounds[0].tools[0].result_json
    with agent.journal._ledger.connection() as conn:
        assert reset_blockers(conn, "owner", agent.served.context.universe_dir.name) == []

"""The agent node: a converse turn as a workflow step (change agent-node-and-tool-grants).

Real background queue, admission, work receipt, agent loop, persona assembly and
ENGINE MCP HANDLERS: the in-memory client talks to ``engine_mcp_server.mcp``
itself, so ``write_brain`` / ``read_brain`` / ``write_graph`` run their own
pins, identity binding and owner checks. Only the model's HTTP wire is scripted.
"""

import json
import sqlite3

import pytest
from fastmcp import Client

from tests import test_background_budget_finalization_e2e as background
from tests import test_background_work_agent as background_agent
from tests import test_workflow_http_agent as foreground
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tinyassets import engine_mcp_server, engine_tool_client
from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
from tinyassets.shared_self import prepare_shared_self_turn as _REAL_PREPARE
from tinyassets.storage.provider_work_authority import db_path

http_wire = foreground.http_wire
work_agent = foreground.work_agent

pytestmark = pytest.mark.usefixtures("cloud_runtime")

MARK = "I am the background agent node, and I remember the orchard ledger."


def _call(name, **arguments):
    return {"name": name, "arguments": json.dumps(arguments)}


def _agent_branch(tools_allowed, *, author="acct_alice"):
    def seed(tmp_path, *, policy=None, agent=False):
        from tinyassets.branch_versions import publish_branch_version
        from tinyassets.daemon_server import initialize_author_server, save_branch_definition

        node = NodeDefinition(
            node_id="steward", display_name="Steward",
            prompt_template="Keep the orchard ledger in your brain.",
            llm_policy=policy, tools_allowed=list(tools_allowed),
        )
        branch = BranchDefinition(
            branch_def_id="branch_repo_spec_loop", name="Agent step", author=author,
            visibility="private",
            graph_nodes=[GraphNodeRef(id="steward", node_def_id="steward")],
            edges=[EdgeDefinition(from_node="steward", to_node="END")],
            entry_point="steward", node_defs=[node], state_schema=[],
        )
        initialize_author_server(tmp_path)
        save_branch_definition(tmp_path, branch_def=branch.to_dict())
        return publish_branch_version(tmp_path, branch.to_dict(), publisher=author)
    return seed


@pytest.fixture
def engine(tmp_path, monkeypatch, work_agent):
    """Real prepare + real engine handlers; a scripted model on the HTTP wire."""
    import tinyassets.api.visibility as visibility
    from tinyassets.daemon_server import ensure_universe_registered
    from tinyassets.universe_bundle import seed_okf_bundle

    udir = tmp_path / "universe_alice"
    udir.mkdir(exist_ok=True)
    seed_okf_bundle(udir, purpose="Tend the orchard ledger.", loop_branch_def_id="")
    ensure_universe_registered(tmp_path, universe_id="universe_alice", universe_path=udir)
    visibility.set_universe_visibility("universe_alice", "private", source="owner")
    monkeypatch.setattr("tinyassets.shared_self.prepare_shared_self_turn", _REAL_PREPARE)
    monkeypatch.setattr(engine_mcp_server, "_ACTOR_ID", "acct_alice")
    monkeypatch.setattr(engine_mcp_server, "_GRAPH_ID", "universe_alice")
    state = work_agent
    state.routes, state.offered, state.results, state.script = [], [], [], []

    def client(route, timeout):
        state.routes.append((route.actor_id, route.graph_id))
        return Client(engine_mcp_server.mcp)

    class Proxy:
        def close(self):
            pass

        def request(self, verb, document):
            body = document["body"]
            body = json.loads(body) if isinstance(body, str) else body
            state.wires.append(document)
            state.offered.append(sorted(t["function"]["name"] for t in body.get("tools") or []))
            state.results.extend(m.get("content") for m in body.get("messages") or []
                                 if m.get("role") == "tool")
            calls = state.script.pop(0) if state.script else []
            message = {"role": "assistant", "content": None if calls else "steward done"}
            if calls:
                message["tool_calls"] = [
                    {"id": f"tool-{index}", "type": "function", "function": call}
                    for index, call in enumerate(calls)
                ]
            return {"status": 200, "body": json.dumps({
                "model": "actual-work-model", "choices": [{
                    "message": message, "finish_reason": "tool_calls" if calls else "stop",
                }], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "cost": 0},
            })}

    monkeypatch.setattr(engine_tool_client, "_make_client", client)
    monkeypatch.setattr(ApiKeyHttpProvider, "_resolve_proxy", lambda *a, **k: Proxy())
    return state


def _run(tmp_path, monkeypatch, tools_allowed, *, author="acct_alice"):
    monkeypatch.setattr(background, "_seed_branch_version", _agent_branch(tools_allowed,
                                                                          author=author))
    # background_agent.run wraps the seed to pass agent=True; ours ignores it.
    return background_agent.run(tmp_path, monkeypatch)


def _branches_authored_in_alice(tmp_path):
    from tinyassets.daemon_server import list_branch_definitions

    return [b for b in list_branch_definitions(tmp_path, author="acct_alice")
            if b.get("name") == "Orchard follow-up"]


def test_background_agent_node_uses_its_own_brain_and_graph_on_a_private_universe(
    tmp_path, monkeypatch, engine,
):
    engine.script = [[
        _call("write_brain", identity=MARK),
        _call("read_brain"),
        _call("write_graph", target="branch", operation="create", payload_json=json.dumps({
            "name": "Orchard follow-up", "entry_point": "note",
            "node_defs": [{"node_id": "note", "display_name": "Note",
                           "prompt_template": "Summarise the orchard ledger."}],
            "edges": [{"from_node": "note", "to_node": "END"}],
        })),
    ]]
    task, result = _run(tmp_path, monkeypatch, ["agent"])
    assert task.status == "succeeded", (result, engine.errors)

    # Every tool reached the route pinned to the run's own owner and universe.
    assert set(engine.routes) == {("acct_alice", "universe_alice")}
    # 1. brain write landed in the universe's own file ...
    assert MARK in (tmp_path / "universe_alice" / "identity.md").read_text(encoding="utf-8")
    # 2. ... and the agent read it back in the same turn (the tool result the model saw).
    assert any(MARK in (content or "") for content in engine.results), engine.results
    # 3. write_graph built a branch owned by this universe's owner.
    assert len(_branches_authored_in_alice(tmp_path)) == 1
    # The node's answer is the run's output, and both rounds are metered on the one receipt.
    assert "steward done" in json.dumps(result)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        rows = [json.loads(r[0]) for r in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations ORDER BY ordinal")]
    assert len(rows) == 2 and all(row["state"] == "succeeded" for row in rows)
    assert sum(row["actual_total_tokens"] for row in rows) == 14
    # The marker alone grants what the owner's chat has.
    assert engine.offered[0] == sorted(SERVED_ENGINE_MCP_TOOLS)


def test_a_narrowed_grant_offers_and_allows_only_the_granted_tools(
    tmp_path, monkeypatch, engine,
):
    engine.script = [[_call("read_brain"), _call("write_brain", identity=MARK)]]
    task, result = _run(tmp_path, monkeypatch, ["agent", "read_brain"])

    assert engine.offered[0] == ["read_brain"]
    # The ungranted write never reached the handler: the brain is unchanged, and the
    # turn stops rather than completing with an effect it was not given.
    assert MARK not in (tmp_path / "universe_alice" / "identity.md").read_text(encoding="utf-8")
    assert task.status != "succeeded", result


def test_an_unknown_grant_refuses_before_any_model_round(tmp_path, monkeypatch, engine):
    task, result = _run(tmp_path, monkeypatch, ["agent", "write_brian"])
    assert task.status != "succeeded", result
    assert engine.wires == [] and engine.routes == []


def test_another_authors_branch_never_drives_the_owners_tools(tmp_path, monkeypatch, engine):
    """A prompt written by another user must not steer the owner's agent tools, even
    in a run the owner's universe admitted."""
    engine.script = [[_call("write_brain", identity=MARK)]]
    task, result = _run(tmp_path, monkeypatch, ["agent"], author="acct_bob")
    assert task.status != "succeeded", result
    assert engine.wires == [] and engine.routes == []
    assert MARK not in (tmp_path / "universe_alice" / "identity.md").read_text(encoding="utf-8")


def test_the_tools_cannot_be_pointed_at_another_users_universe(tmp_path, monkeypatch, engine):
    """No served tool takes a universe; an injected id is ignored and the pinned one
    is used. Bob's private brain stays untouched and unread."""
    from tinyassets.universe_bundle import seed_okf_bundle

    bob = tmp_path / "universe_bob"
    seed_okf_bundle(bob, purpose="Bob's private work.", loop_branch_def_id="")
    before = (bob / "identity.md").read_text(encoding="utf-8")
    engine.script = [[
        _call("write_brain", identity=MARK, universe_id="universe_bob", graph_id="universe_bob"),
        _call("read_graph", target="status", graph_id="universe_bob"),
    ]]
    _run(tmp_path, monkeypatch, ["agent"])
    assert set(engine.routes) == {("acct_alice", "universe_alice")}
    assert (bob / "identity.md").read_text(encoding="utf-8") == before
    assert all("universe_bob" not in (content or "") for content in engine.results)

"""Real canonical handles connect two owners and process a structured occurrence."""
# ruff: noqa: F811 -- imported pytest fixtures
import json

import pytest

from tests.test_delivery_runtime import provider_probe  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import runs
from tinyassets import universe_server as server
from tinyassets.storage import deliveries


@pytest.fixture
def linked(env):
    base, authenticate = env
    def auth(owner):
        authenticate(owner, capabilities=[
            "tinyassets.extensions.read", "tinyassets.extensions.write",
            "tinyassets.extensions.costly",
        ])
    auth("receiver")
    receiver = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({"branch_def_id": "b-receiver", "node_id": "entry",
                                 "input_keys": ["topic"], "allowed_senders": ["sender"]}),
    ))
    assert "receiver_id" in receiver, receiver
    auth("sender")
    link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-sender",
        payload_json=json.dumps({"branch_def_id": "b-sender", "node_id": "entry",
                                 "receiver_id": receiver["receiver_id"],
                                 "expected_generation": 1, "mapping": {"result": "topic"}}),
    ))
    assert "link_id" in link, link
    return base, auth, receiver, link


def _send(link, value="exact input 🍉", *, occurrence="one", graph="u-sender"):
    return json.loads(server.run_graph(
        operation="deliver_output", graph_id=graph,
        inputs_json=json.dumps({"link_id": link["link_id"], "occurrence_id": occurrence,
                               "outputs": {"result": value}}),
    ))


def test_real_handles_expose_connect_deliver_and_inspect_both_sides(linked, provider_probe):
    base, auth, receiver, link = linked
    contract = json.loads(server.read_graph(target="receiver", query=receiver["receiver_id"]))
    assert "snapshot_json" not in contract
    sent = _send(link)
    assert "delivery_id" in sent, sent
    assert "run_id" not in sent
    auth("receiver")
    own = json.loads(server.read_graph(
        target="delivery", graph_id="u-receiver", query=sent["delivery_id"],
    ))
    runs.wait_for(own["run_id"], timeout=10)
    auth("sender")
    result = json.loads(server.read_graph(
        target="delivery", graph_id="u-sender", query=sent["delivery_id"],
    ))
    assert result["status"] == "completed", result
    assert "run_id" not in result
    assert "receiver-private" not in json.dumps(result)
    assert _send(link)["delivery_id"] == sent["delivery_id"]
    assert len(provider_probe) == 1
    assert _send(link, "different")["error"]
    auth("outsider")
    assert _send(link, graph="u-sender")["error"]
    assert json.loads(server.read_graph(
        target="delivery", graph_id="u-outsider", query=sent["delivery_id"],
    ))["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_delivery_attempts").fetchone()[0] == 1


@pytest.mark.parametrize("value", [{"handle_id": "foreign"}, 123])
def test_invalid_values_never_reserve_or_execute(linked, provider_probe, value):
    base, _, _, link = linked
    assert _send(link, value)["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 0
    assert provider_probe == []


def test_disconnected_link_refuses_new_occurrence(linked, provider_probe):
    base, _, _, link = linked
    response = json.loads(server.write_graph(
        target="output_link", operation="disconnect", graph_id="u-sender",
        payload_json=json.dumps({"link_id": link["link_id"]}),
    ))
    assert response["disconnected"] is True
    assert _send(link)["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 0


def test_receiver_revocation_refuses_new_intake(linked, provider_probe):
    base, auth, receiver, link = linked
    auth("receiver")
    revoked = json.loads(server.write_graph(
        target="receiver", operation="revoke", graph_id="u-receiver",
        payload_json=json.dumps({"receiver_id": receiver["receiver_id"], "expected_generation": 1}),
    ))
    assert revoked["revoked"] is True
    auth("sender")
    assert _send(link)["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_receiver_admission_refusal_never_reserves_a_run(linked, provider_probe, monkeypatch):
    from types import SimpleNamespace
    base, _, _, link = linked
    monkeypatch.setattr("tinyassets.engine_admissions.admit_detail",
                        lambda *a, **k: SimpleNamespace(ticket=None))
    response = _send(link)
    assert response["detail"] == "receiver_resource_admission_refused"
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert provider_probe == []


def test_sender_ledger_targets_delivery_not_private_run(linked, provider_probe, monkeypatch):
    _, _, _, link = linked
    ledger = []
    monkeypatch.setattr("tinyassets.api.branches._append_global_ledger",
                        lambda *args, **kwargs: ledger.append((args, kwargs)))
    response = _send(link)
    assert "delivery_id" in response
    writes = [kwargs for args, kwargs in ledger if args[0] == "deliver_output"]
    assert len(writes) == 1
    assert writes[0]["target"] == response["delivery_id"]


def test_served_wrappers_pin_management_and_delivery_to_owner(linked, provider_probe, monkeypatch):
    from tinyassets import engine_mcp_server as engine
    base, auth, receiver, link = linked
    monkeypatch.setattr(engine, "_GRAPH_ID", "u-sender")
    monkeypatch.setattr(engine, "_ACTOR_ID", "sender")
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "u-sender")
    read = engine.read_graph(target="receiver", query=receiver["receiver_id"])
    assert receiver["receiver_id"] in read
    result = engine.run_graph(operation="deliver_output", inputs_json=json.dumps({
        "link_id": link["link_id"], "occurrence_id": "engine-send", "outputs": {"result": "exact"},
    }))
    assert "delivery_id" in result, result
    auth("receiver")
    with deliveries.transaction(base) as conn:
        run_id = conn.execute("SELECT run_id FROM graph_delivery_attempts").fetchone()[0]
    runs.wait_for(run_id, timeout=10)
    assert provider_probe
    denied = engine.write_graph(target="receiver", operation="create", payload_json=json.dumps({
        "universe_id": "u-receiver", "branch_def_id": "b-receiver", "node_id": "entry",
        "input_keys": ["topic"], "allowed_senders": ["sender"],
    }))
    assert "invalid_delivery_request" in denied

"""Installed protocol capabilities, never remote claims or new user authority."""

from dataclasses import replace

import pytest

from tests import test_discovery_snapshot as snapshots
from tests import test_interactive_http_agent as interactive
from tests.test_model_discovery_capability import DESCRIPTOR
from tinyassets.providers import discovery_protocols as discovery
from tinyassets.providers import protocol_encoders as protocols
from tinyassets.providers.agent_inference import AgentInferenceRequest
from tinyassets.providers.model_selection import SelectedModel

rig = interactive.rig
reader = interactive.reader
served = interactive.served
agent = interactive.agent


def test_remote_tool_claim_cannot_supply_missing_executor_capability(rig, reader, monkeypatch):
    existing = protocols.PROTOCOLS[rig.definition.protocol]
    monkeypatch.setitem(protocols.PROTOCOLS, rig.definition.protocol,
                        replace(existing, agent_factory=None))
    result = snapshots._refresh(rig)
    assert result.models.models[0].tools is True
    assert result.models.executor_tools is False


def test_unknown_wire_contract_has_no_agent_executor():
    assert protocols.agent_codec_for("uninstalled:future-wire") is None
    assert protocols.agent_codec_for("anthropic_messages") is None


def test_legacy_text_dispatch_and_headers_keep_their_contract():
    for name, contract in protocols.PROTOCOLS.items():
        assert protocols.ENCODERS[name] == (contract.encode, contract.decode)
        assert protocols.static_headers_for(name) == dict(contract.headers)
        detached = protocols.static_headers_for(name)
        detached["x-not-a-grant"] = "test"
        assert "x-not-a-grant" not in protocols.static_headers_for(name)


@pytest.mark.parametrize("cost", [None, 0])
def test_real_loop_uses_installed_codec_and_declared_usage_for_unfamiliar_profile(
    agent, monkeypatch, cost,
):
    # A synthetic installed profile tests dispatch extensibility, not a new
    # publicly configurable protocol or live account compatibility claim.
    alias = "unfamiliar-source-contract-v1"
    usage_seen, encoded, decoded = [], [], []

    def usage(raw):
        usage_seen.append(raw)
        return cost

    old = discovery.discovery_protocol(DESCRIPTOR["protocol"])
    monkeypatch.setitem(discovery._PROTOCOLS, alias, replace(old, usage_decoder=usage))
    agent.served.rig.publish(descriptor={**DESCRIPTOR, "protocol": alias})
    name = agent.served.rig.definition.protocol
    installed = protocols.PROTOCOLS[name]
    codec = protocols.agent_codec_for(name)

    def encode(**kwargs):
        encoded.append(kwargs["model"])
        return codec.encode(**kwargs)

    def decode(*args, **kwargs):
        decoded.append(kwargs["requested_model"])
        return codec.decode(*args, **kwargs)

    monkeypatch.setitem(protocols.PROTOCOLS, name, replace(
        installed, agent_factory=lambda: protocols.AgentCodec(encode, decode),
    ))
    receipts = []
    assert interactive.run(agent, receipts.append) == "finished exact answer"
    assert len(agent.wires) == len(decoded) == len(usage_seen) == 2
    assert len(encoded) >= 2 and set(encoded) == {"new-company/new-model"}
    assert len(agent.tools) == 1 and agent.latest().state == "completed"
    assert receipts[0].cost_microunits == cost
    assert receipts[0].reported_model == "actual-answer-model"


def test_request_refuses_missing_codec_even_if_captured_selection_claims_tools(monkeypatch):
    contract = discovery.discovery_protocol(DESCRIPTOR["protocol"])
    installed = protocols.PROTOCOLS[contract.inference_protocol]
    monkeypatch.setitem(protocols.PROTOCOLS, contract.inference_protocol,
                        replace(installed, agent_factory=None))
    selection = SelectedModel(
        "owned:future", "new-model", DESCRIPTOR["protocol"], (), "digest", 32000, True,
    )
    request = AgentInferenceRequest(tools=[{
        "type": "function", "function": {
            "name": "read", "description": "", "parameters": {"type": "object"},
        },
    }])
    with pytest.raises(PermissionError, match="protocol is unsupported"):
        request.encode(prompt="hello", system="", selection=selection,
                       temperature=None, max_tokens=10)


def test_missing_usage_contract_does_not_infer_free_usage(agent, monkeypatch):
    old = discovery.discovery_protocol(DESCRIPTOR["protocol"])
    monkeypatch.setitem(discovery._PROTOCOLS, DESCRIPTOR["protocol"],
                        replace(old, usage_decoder=None))
    receipts = []
    assert interactive.run(agent, receipts.append) == "finished exact answer"
    assert receipts[0].cost_microunits is None

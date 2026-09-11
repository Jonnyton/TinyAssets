"""Envelope decoupling and frozen pre-change differential proof, no network."""

import copy
import json
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest

from tests import _legacy_agent_wire_oracle as oracle
from tests.test_agent_chat_codec import (
    MODEL,
    NAMES,
    SOURCE,
    call,
    completed_round,
    definitions,
    response,
)
from tinyassets.providers import agent_chat_codec as core
from tinyassets.providers.agent_wire_codec import AgentWireShape, installed_agent_wire
from tinyassets.providers.protocol_encoders import agent_codec_for


def document():
    return json.loads(Path(__file__).parents[1].joinpath(
        "tinyassets/providers/agent_wire_shape.json",
    ).read_text("utf-8"))


def context():
    return {"source_ref": SOURCE, "requested_model": MODEL, "tool_names": NAMES}


def request(**kwargs):
    return {"prompt": "  original\n🪐 ", "system": " same system\n",
            "source_ref": SOURCE, "model": MODEL, "tools": definitions(), **kwargs}


def result(function, *args, **kwargs):
    try:
        value = function(*args, **kwargs)
    except (ValueError, TypeError, OverflowError) as exc:
        return type(exc).__name__, str(exc)
    return "ok", asdict(value)


@pytest.mark.parametrize("finish", ["stop", "tool_calls", "length", "content_filter",
                                        "error", "future", None, 3])
@pytest.mark.parametrize("message", [
    {"content": "done", "tool_calls": []},
    {"content": None, "tool_calls": [call()]},
    {"content": None, "tool_calls": [call(arguments="not json")]},
    {"content": "no", "refusal": " denied "},
    {"content": None, "tool_calls": [call()], "reasoning": "secret"},
    {"content": None, "tool_calls": [call()], "future": "opaque"},
    {"content": [], "tool_calls": []},
    {"role": "user", "content": "bad"},
])
def test_canonical_states_match_frozen_decoder(finish, message):
    body = {"model": " actual/model ", "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            "choices": [{"finish_reason": finish, "message": message}]}
    assert result(installed_agent_wire().decode, body, **context()) == result(
        oracle.decode_openai_chat_agent, body, **context(),
    )


@pytest.mark.parametrize("field", ["model", "usage", "choices", "error"])
@pytest.mark.parametrize("value", [None, False, 0, -1, "", " model ", "\n", "x" * 201,
                                    [], {}, [None], {"prompt_tokens": True},
                                    {"prompt_tokens": -1, "completion_tokens": 1.5}])
def test_envelope_and_telemetry_match_frozen_decoder(field, value):
    body = response([], content="final", finish="stop")
    body[field] = value
    assert result(installed_agent_wire().decode, body, **context()) == result(
        oracle.decode_openai_chat_agent, body, **context(),
    )


@pytest.mark.parametrize("same_source", [True, False])
@pytest.mark.parametrize("temperature", [None, 0, 0.25, True, float("inf"), 10**400])
@pytest.mark.parametrize("max_tokens", [None, 1, 44, False, 0])
def test_portable_requests_match_frozen_bytes(same_source, temperature, max_tokens):
    history = (core.CapturedToolRound(round=completed_round(), tools=definitions()),)
    kwargs = request(history=history, temperature=temperature, max_tokens=max_tokens,
                     source_ref=SOURCE if same_source else "other/source")

    def encoded(fn):
        try:
            path, body = fn(**kwargs)
            return path, json.dumps(body, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, OverflowError) as exc:
            return type(exc).__name__, str(exc)

    assert encoded(installed_agent_wire().encode) == encoded(
        oracle.encode_openai_chat_agent_portable,
    )


def test_engine_adapter_does_not_use_compatibility_wrappers(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("engine called a historical protocol wrapper")

    for name in ("encode_openai_chat_agent", "encode_openai_chat_agent_portable",
                 "decode_openai_chat_agent"):
        monkeypatch.setattr(core, name, forbidden)
    codec = agent_codec_for("openai_chat")
    path, body = codec.encode(**request())
    assert path == "/v1/chat/completions" and body["model"] == MODEL
    assert codec.decode(response([], content="ok", finish="stop"), **context()).text == "ok"


def test_alternate_installed_envelope_uses_same_core_and_exact_history():
    doc = document()
    doc["path"] = "/engine/answer"
    doc["request"] = {name: "wire_" + name for name in doc["request"]}
    doc["response"] = {"choices": "/result/candidates", "error": "/failure",
                       "model": "/receipt/actual", "input_tokens": "/meter/in",
                       "output_tokens": "/meter/out"}
    doc["choice"] = {"message": "/answer/body", "finish": "/answer/stop", "error": "/fault"}
    shape = AgentWireShape.compile(doc)
    body = {"result": {"candidates": [{"answer": {
        "body": {"content": None, "tool_calls": [call()]}, "stop": "tool_calls",
    }}]}, "receipt": {"actual": "opaque/latest"}, "meter": {"in": 9, "out": 2}}
    reply = shape.decode(body, **context())
    assert reply.stop == "tool_requests" and reply.reported_model == "opaque/latest"
    assert (reply.input_tokens, reply.output_tokens) == (9, 2)
    historical = core.CapturedToolRound(round=completed_round(), tools=definitions())
    kwargs = request(history=(historical,), source_ref="other/source")
    path, wire = shape.encode(**kwargs)
    canonical = core.build_portable_agent_body(**kwargs)
    assert path == "/engine/answer"
    assert wire == {"wire_" + name: value for name, value in canonical.items()}
    assert [m["content"] for m in wire["wire_messages"] if m["role"] == "tool"] == [
        item.result_json for item in historical.round.outcomes
    ]
    assert set(wire) == {"wire_model", "wire_messages", "wire_tools", "wire_tool_choice"}
    assert core.build_agent_body(**request())["messages"][:2] == canonical["messages"][:2]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(credentials="forbidden"),
    lambda d: d.update(path="https://example.test/request"),
    lambda d: d.update(path="//example.test/request"),
    lambda d: d.update(path="/../request"),
    lambda d: d.update(path="/request?key=secret"),
    lambda d: d.update(path="/request#fragment"),
    lambda d: d["request"].update(model="messages"),
    lambda d: d["request"].update(model="x" * 65),
    lambda d: d["request"].update(model=["model"]),
    lambda d: d["request"].pop("tools"),
    lambda d: d["response"].update(model=""),
    lambda d: d["response"].update(error="/bad~2escape"),
    lambda d: d["response"].update(model="/x" * 17),
    lambda d: d["choice"].update(callback="python.module"),
])
def test_descriptor_is_closed_and_bounded(mutate):
    doc = document()
    mutate(doc)
    with pytest.raises(ValueError):
        AgentWireShape.compile(doc)


def test_compiled_shape_is_detached_immutable_and_cwd_independent(tmp_path, monkeypatch):
    doc = document()
    shape = AgentWireShape.compile(doc)
    original = copy.deepcopy(doc)
    doc["request"]["model"] = "changed"
    assert dict(shape.request_fields)["model"] == original["request"]["model"]
    with pytest.raises(FrozenInstanceError):
        shape.path = "/changed"
    installed_agent_wire.cache_clear()
    monkeypatch.chdir(tmp_path)
    assert installed_agent_wire().path == original["path"]


@pytest.mark.parametrize("root_error,choice_error", [(False, None), ({}, None),
                                                     (None, "denied"), (None, False)])
def test_errors_block_all_tools(root_error, choice_error):
    body = response([call()])
    body["error"] = root_error
    body["choices"][0]["error"] = choice_error
    with pytest.raises(ValueError, match="unavailable"):
        installed_agent_wire().decode(body, **context())

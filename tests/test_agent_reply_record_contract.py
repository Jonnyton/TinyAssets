"""Version-one reply compatibility without synthetic provider HTTP responses."""

from copy import deepcopy
from dataclasses import asdict, replace
from itertools import product

import pytest

from tests._agent_reply_legacy_oracle import legacy_decode, legacy_load_reply
from tests.test_agent_turn_journal import candidate
from tinyassets.providers import agent_chat_codec as codec
from tinyassets.storage import agent_turn_records as records


def observe(fn, *args, **kwargs):
    try:
        return ("ok", fn(*args, **kwargs))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return ("error", type(exc))


def decode(fn, body):
    return fn(
        body, source_ref="owned:future", requested_model="opaque-llm",
        tool_names=frozenset({"tool"}),
    )


def call(**overrides):
    return {"id": "batch-id", "type": "function", "function": {
        "name": "tool", "arguments": '{ "exact": "🪐", "n": 1 }',
    }, **overrides}


@pytest.mark.parametrize("finish", [
    "stop", "tool_calls", "length", "content_filter", "future-stop", "error", None, 3,
])
def test_wire_and_persisted_semantics_match_frozen_original(finish):
    calls = [None, [], [call()], [call(), call()], [call(type="future")]]
    extras = [{}, {"future": "data"}, {"future": None}, {"audio": "unsupported"},
              {"reasoning": "private"}, {"reasoning_details": [{"type": "opaque"}]}]
    for content, refusal, batch, extra in product(
        [None, "", " ", "exact\nreply 🪐"], [None, "", " ", "declined", 3], calls, extras,
    ):
        body = {"choices": [{"finish_reason": finish, "message": {
            "role": "assistant", "content": content, "refusal": refusal,
            "tool_calls": batch, **extra,
        }}], "usage": {"prompt_tokens": 0, "completion_tokens": 3},
            "model": "reported:future"}
        expected = observe(decode, legacy_decode, body)
        assert observe(decode, codec.decode_openai_chat_agent, body) == expected, body
        if expected[0] != "ok":
            continue
        reply = expected[1]
        raw = records.dump({"version": 1, **asdict(reply)})
        loaded = observe(legacy_load_reply, raw, candidate())
        assert observe(records.load_reply, raw, candidate()) == loaded, body
        if loaded[0] == "ok":
            assert records.reply_json(loaded[1], candidate()) == raw


def seed_reply(*, tools=False, finish="stop", extra=None):
    return decode(legacy_decode, {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": "exact answer",
        **({"tool_calls": [call()]} if tools else {}), **(extra or {}),
    }}]})


@pytest.mark.parametrize("reply", [
    seed_reply(), seed_reply(tools=True), seed_reply(finish="length"),
    seed_reply(finish="content_filter"), seed_reply(extra={"refusal": "no"}),
    seed_reply(tools=True, extra={"future": "held continuation"}),
])
def test_corrupted_records_keep_original_acceptance_and_rejection(reply):
    base = {"version": 1, **asdict(reply)}
    changes = [
        {"stop": stop} for stop in records.STOP_STATE
    ] + [
        {field: value}
        for field, values in {
            "version": [None, True, 2], "text": [None, "", 3, "changed"],
            "refusal": [None, "", " ", "no", 3],
            "raw_finish_reason": ["error", "tool_calls", "future", None, 3],
            "dropped_fields": [[], ["future"], [3], None],
            "input_tokens": [-1, True, records.MAX_INT + 1, "1"],
            "output_tokens": [-1, True, None],
            "reported_model": [None, " ", "unfamiliar", 3],
            "source_ref": ["foreign", "", None],
            "requested_model": ["changed", "", None],
            "tool_requests": [[], None, [{"call_id": "not-exact"}]],
            "continuation_json": ["{}", "[]", '{"role":"assistant","role":"tool"}',
                                  '{"role":"assistant","content":3}'],
        }.items() for value in values
    ]
    for change in changes:
        raw = records.dump({**deepcopy(base), **change})
        assert observe(records.load_reply, raw, candidate()) == observe(
            legacy_load_reply, raw, candidate(),
        ), change


def test_record_loader_does_not_call_a_wire_decoder(monkeypatch):
    reply = seed_reply(tools=True)
    raw = records.dump({"version": 1, **asdict(reply)})

    def forbidden(*args, **kwargs):
        pytest.fail("journal validation called a provider response decoder")

    monkeypatch.setattr(codec, "decode_openai_chat_agent", forbidden)
    assert records.load_reply(raw, candidate()) == reply
    assert records.reply_json(reply, candidate()) == raw


@pytest.mark.parametrize("source,model", [("", "m"), ("source", ""), ("x\n", "m")])
def test_invalid_captured_identity_is_not_bypassed(source, model):
    reply = replace(seed_reply(), source_ref=source, requested_model=model)
    raw = records.dump({"version": 1, **asdict(reply)})
    context = candidate(source, model)
    assert observe(records.load_reply, raw, context) == observe(legacy_load_reply, raw, context)
    assert observe(records.load_reply, raw, context)[0] == "error"

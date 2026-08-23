"""Protocol encoders for the api_key_http compute executor (compute-agnostic).

Covers: openai_chat + anthropic_messages request encode (correct shape/path, no
credential embedded) and response decode (text + usage extraction, and fail-loud
on every malformed/error shape — never a silent empty completion, Hard Rule #8).
"""

from __future__ import annotations

import json

import pytest

from tinyassets.providers import protocol_encoders as pe
from tinyassets.providers.protocol_encoders import ProtocolDecodeError

# --------------------------------------------------------------------------- #
# openai_chat encode
# --------------------------------------------------------------------------- #


def test_openai_encode_shape_and_path() -> None:
    path, body = pe.encode_openai_chat(
        prompt="hello", system="be terse", model="moonshotai/kimi-k2",
        temperature=0.2, max_tokens=1024,
    )
    assert path == "/v1/chat/completions"
    assert body["model"] == "moonshotai/kimi-k2"
    assert body["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 1024


def test_openai_encode_omits_empty_system_and_optional_fields() -> None:
    path, body = pe.encode_openai_chat(prompt="hi", system="", model="gpt-5")
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "temperature" not in body
    assert "max_tokens" not in body


def test_encoded_body_carries_no_credential() -> None:
    # The encoder must NEVER embed auth — the broker worker applies the bearer.
    _, body = pe.encode_openai_chat(prompt="p", system="s", model="m")
    blob = json.dumps(body).lower()
    assert "authorization" not in blob
    assert "bearer" not in blob
    assert "api_key" not in blob and "api-key" not in blob


# --------------------------------------------------------------------------- #
# openai_chat decode
# --------------------------------------------------------------------------- #


def test_openai_decode_text_and_usage() -> None:
    text, in_tok, out_tok = pe.decode_openai_chat(
        {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }
    )
    assert text == "the answer"
    assert (in_tok, out_tok) == (11, 7)


def test_openai_decode_missing_usage_is_none() -> None:
    text, in_tok, out_tok = pe.decode_openai_chat(
        {"choices": [{"message": {"content": "x"}}]}
    )
    assert text == "x"
    assert in_tok is None and out_tok is None


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-dict",
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},  # empty content = fail loud
        {"choices": [{"message": {"content": "   \n\t "}}]},  # whitespace-only = fail loud
        {"choices": [{"message": {}}]},
        {"error": {"message": "rate limited"}},
    ],
)
def test_openai_decode_fails_loud(bad: object) -> None:
    with pytest.raises(ProtocolDecodeError):
        pe.decode_openai_chat(bad)


# --------------------------------------------------------------------------- #
# anthropic_messages encode/decode
# --------------------------------------------------------------------------- #


def test_anthropic_encode_system_is_top_level_and_max_tokens_required() -> None:
    path, body = pe.encode_anthropic_messages(
        prompt="q", system="persona", model="claude-x", max_tokens=None
    )
    assert path == "/v1/messages"
    assert body["system"] == "persona"
    assert body["messages"] == [{"role": "user", "content": "q"}]
    assert isinstance(body["max_tokens"], int) and body["max_tokens"] > 0  # defaulted


def test_anthropic_decode_joins_text_blocks() -> None:
    text, in_tok, out_tok = pe.decode_anthropic_messages(
        {
            "content": [
                {"type": "text", "text": "part1 "},
                {"type": "tool_use", "name": "x"},
                {"type": "text", "text": "part2"},
            ],
            "usage": {"input_tokens": 3, "output_tokens": 5},
        }
    )
    assert text == "part1 part2"
    assert (in_tok, out_tok) == (3, 5)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "error", "error": {"message": "overloaded"}},
        {"content": []},
        {"content": [{"type": "tool_use"}]},  # no text block
        {"content": [{"type": "text", "text": "   "}]},  # whitespace-only = fail loud
        "nope",
    ],
)
def test_anthropic_decode_fails_loud(bad: object) -> None:
    with pytest.raises(ProtocolDecodeError):
        pe.decode_anthropic_messages(bad)


def test_encoder_dispatch_table_covers_both_protocols() -> None:
    assert set(pe.ENCODERS) == {"openai_chat", "anthropic_messages"}
    for _proto, (enc, dec) in pe.ENCODERS.items():
        assert callable(enc) and callable(dec)

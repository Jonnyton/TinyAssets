"""Immutable, authority-free data for exactly one HTTP agent inference."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from typing import TYPE_CHECKING, Any

from tinyassets.providers import agent_chat_codec as codec

if TYPE_CHECKING:
    from tinyassets.providers.model_selection import SelectedModel


@dataclass(frozen=True, slots=True, init=False)
class AgentInferenceRequest:
    tools_json: str = field(repr=False)
    history: tuple[codec.CapturedToolRound, ...] = field(repr=False)

    def __init__(self, *, tools, history=()) -> None:
        if not isinstance(history, tuple) or any(
            not isinstance(item, codec.CapturedToolRound) for item in history
        ):
            raise ValueError("captured immutable agent history required")
        object.__setattr__(self, "tools_json", codec._dump({"tools": codec._definitions(tools)}))
        object.__setattr__(self, "history", history)

    def tools(self) -> tuple[dict[str, Any], ...]:
        return codec._definitions(codec._object(self.tools_json)["tools"])

    def encode(
        self,
        *,
        prompt: str,
        system: str,
        selection: SelectedModel,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, dict[str, Any]]:
        from tinyassets.providers.protocol_encoders import agent_codec_for

        if selection is None or not selection.supports_tools:
            raise PermissionError("selected model lacks admitted agent tool support")
        contract = selection.contract()
        agent_codec = agent_codec_for(contract.inference_protocol)
        if agent_codec is None:
            raise PermissionError("agent inference protocol is unsupported")
        path, body = agent_codec.encode(
            prompt=prompt,
            system=system,
            source_ref=selection.provider,
            model=selection.model_id,
            tools=self.tools(),
            history=self.history,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return path, contract.constrain_inference(body, selection.cost_caps)


def input_size(prompt, system, config) -> int:
    """Conservative byte estimate shared by context checks and reservation."""
    request = config.agent_request
    if request is None:
        return len((f"{system}\n\n{prompt}" if system else prompt).encode("utf-8"))
    if type(request) is not AgentInferenceRequest:
        raise PermissionError("invalid internal agent inference request")
    _, body = request.encode(
        prompt=prompt,
        system=system,
        selection=config.selected_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    # Use the broker's ordinary JSON encoding, including every wire field.
    return len(json.dumps(body).encode("utf-8"))


def output_for_settlement(response) -> str:
    """Missing usage counts tool calls/reasoning too, not an empty text result."""
    if response.agent_reply is None:
        return response.text
    return json.dumps(
        {
            "message": codec._object(response.agent_reply.continuation_json),
            "refusal": response.agent_reply.refusal,
        }
    )


def openrouter_usage_cost(raw_json: str) -> int | None:
    """Documented account charge in USD -> ceiling micros, never a zero guess.

    Parse the original numeric token as Decimal so float conversion cannot erase
    a sub-micro charge. This is observation, not permission to spend.
    """
    try:
        value = json.loads(raw_json, parse_float=Decimal, object_pairs_hook=codec._pairs)
        usage = value.get("usage")
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if type(cost) not in (int, Decimal):
            return None
        cost = Decimal(cost)
        if not cost.is_finite() or cost < 0 or cost > Decimal("9223372036854.775807"):
            return None
        if 0 < cost < Decimal("0.000001"):
            return 1
        with localcontext() as context:
            context.prec = max(32, len(cost.as_tuple().digits) + 7)
            return int((cost * 10**6).to_integral_value(rounding=ROUND_CEILING))
    except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
        return None

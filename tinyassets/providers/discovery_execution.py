"""Finite execution data for source contracts; no IO, publication or authority.

The source declares ceiling semantics, not proof its server honors them. The
publisher and installed executor must establish charge closure before using
these shapes. No descriptor may supply the local body validator or account ID.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext

from tinyassets.providers.discovery_catalogue import (
    _DECIMAL_TOKEN,
    Pointer,
    _document,
    _fields,
    _names,
    identifier,
)
from tinyassets.providers.model_capacity import CapacitySignal, retry_after_seconds

_UNITS = frozenset({"input_million_tokens_usd", "output_million_tokens_usd", "request_usd"})
_PROTECTED = frozenset({"model", "messages", "tools", "tool_choice", "credentials",
                        "headers", "endpoint", "url", "temperature", "max_tokens"})


def _scale(value):
    if type(value) is not int or value not in {10**n for n in range(19)}:
        raise ValueError("invalid source contract scale")
    return value


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate response key")
        result[name] = value
    return result


def _constant(value):
    raise ValueError("nonfinite response constant")


@dataclass(frozen=True, slots=True)
class UsageShape:
    cost: Pointer
    scale: int
    encoding: str
    legacy: bool = False

    @classmethod
    def compile(cls, document, *, legacy=False):
        _document(document)
        _fields(document, {"cost", "scale", "encoding"})
        encoding = document["encoding"]
        if type(encoding) is not str or encoding not in {"string", "number", "either"}:
            raise ValueError("invalid usage encoding")
        if type(legacy) is not bool:
            raise ValueError("invalid usage compatibility mode")
        return cls(Pointer.compile(document["cost"]), _scale(document["scale"]), encoding, legacy)

    def decode(self, raw_json):
        """Observed integer micros, rounding positive fractions UP, never to free."""
        try:
            # Matches the existing broker's maximum; limits this standalone parser too.
            if type(raw_json) is not str or (
                not self.legacy and len(raw_json.encode("utf-8")) > 5 * 1024 * 1024
            ):
                return None
            options = {} if self.legacy else {"parse_constant": _constant}
            document = json.loads(raw_json, parse_float=Decimal,
                                  object_pairs_hook=_unique, **options)
            value = self.cost.read(document)
            if type(value) is str and self.encoding in {"string", "either"}:
                if len(value) > 80 or _DECIMAL_TOKEN.fullmatch(value) is None:
                    return None
            elif type(value) in (int, Decimal) and self.encoding in {"number", "either"}:
                if not self.legacy and len(str(value)) > 80:
                    return None
            else:
                return None
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0:
                return None
            if amount == 0:
                return 0
            with localcontext() as context:
                context.prec = max(100, len(amount.as_tuple().digits) + 7)
                if amount > Decimal(2**63 - 1) / self.scale:
                    return None
                if 0 < amount < Decimal(1) / self.scale:
                    return 1
                return int((amount * self.scale).to_integral_value(rounding=ROUND_CEILING))
        except (ValueError, TypeError, InvalidOperation, OverflowError, RecursionError):
            return None


@dataclass(frozen=True, slots=True)
class CapacityShape:
    cases: tuple[tuple[int, str, str], ...]
    retry_after: bool

    @classmethod
    def compile(cls, document):
        _document(document)
        _fields(document, {"cases", "retry_after"})
        raw = document["cases"]
        if type(raw) is not list or len(raw) > 32 or type(document["retry_after"]) is not bool:
            raise ValueError("invalid capacity shape")
        cases = []
        for case in raw:
            _fields(case, {"status", "scope", "reason"})
            status = case["status"]
            if (type(status) is not int or not 400 <= status <= 599
                    or type(case["scope"]) is not str or type(case["reason"]) is not str):
                raise ValueError("invalid capacity case")
            signal = CapacitySignal(case["scope"], case["reason"])
            cases.append((status, signal.scope, signal.failure_class))
        if len({case[0] for case in cases}) != len(cases):
            raise ValueError("duplicate capacity status")
        return cls(tuple(cases), document["retry_after"])

    def decode(self, status, headers):
        if type(status) is not int:
            return None
        for expected, scope, reason in self.cases:
            if status == expected:
                return CapacitySignal(scope, reason,
                                      retry_after_seconds(headers) if self.retry_after else None)
        return None


def _output_pointer(value):
    pointer = Pointer.compile(value)
    if (not pointer.tokens or pointer.tokens[0] in _PROTECTED
            or any(not identifier(token) for token in pointer.tokens)):
        raise ValueError("protected or invalid ceiling path")
    return pointer


def _put(document, pointer, value):
    current = document
    for key in pointer.tokens[:-1]:
        if key not in current:
            current[key] = {}
        if type(current[key]) is not dict:
            raise ValueError("ceiling path conflicts with request")
        current = current[key]
    if pointer.tokens[-1] in current:
        raise ValueError("ceiling path conflicts with request")
    current[pointer.tokens[-1]] = value


@dataclass(frozen=True, slots=True)
class RequestCeilings:
    """Exact cap injection and reservation for the executor's bounded token/request units.

This compiler does not certify source price coverage or allow extra quantities.
The full source compiler must match every price/constant effect to these caps.
"""

    required: frozenset[str]
    allowed: frozenset[str]
    outputs: tuple[tuple[str, Pointer, int], ...]
    constants: tuple[tuple[Pointer, str, tuple[str, ...]], ...]
    prefixes: tuple[str, ...]
    suffixes: tuple[str, ...]
    substrings: tuple[str, ...]
    legacy: bool = False

    @classmethod
    def compile(cls, document, *, components=_UNITS, legacy=False):
        _document(document)
        _fields(document, {"required", "allowed", "caps", "constants", "model_exclusions"})
        required, allowed = frozenset(_names(document["required"])), frozenset(
            _names(document["allowed"]),
        )
        if not {"model"} <= required <= allowed:
            raise ValueError("invalid required request keys")
        raw_caps = document["caps"]
        # Expanded components/compatibility are installed-code inputs, never
        # descriptor flags. Public SourceContract still requires its closed units.
        if (type(legacy) is not bool or type(components) is not frozenset
                or not 1 <= len(components) <= 64 or any(not identifier(x) for x in components)):
            raise ValueError("invalid installed ceiling components")
        if type(raw_caps) is not dict or raw_caps.keys() != components:
            raise ValueError("unsupported or incomplete reservation units")
        outputs = []
        for component, raw in raw_caps.items():
            _fields(raw, {"path", "divisor"})
            outputs.append((component, _output_pointer(raw["path"]), _scale(raw["divisor"])))
        raw_constants = document["constants"]
        if type(raw_constants) is not list or len(raw_constants) > 64:
            raise ValueError("invalid request constants")
        constants = []
        for raw in raw_constants:
            _fields(raw, {"path", "value", "charge_components"})
            effects = _names(raw["charge_components"])
            if not effects or not set(effects) <= components:
                raise ValueError("request constant has unbounded charge effects")
            # JSON bytes detach nested caller data. Outer compilation must validate
            # these declared effects against the executor's actual quantity bounds.
            constants.append((_output_pointer(raw["path"]),
                              json.dumps(raw["value"], allow_nan=False), effects))
        paths = [pointer.tokens for _, pointer, _ in outputs]
        paths.extend(pointer.tokens for pointer, _, _ in constants)
        for index, path in enumerate(paths):
            if path[0] in allowed:
                raise ValueError("ceiling overlaps an installed request field")
            if any(path[:len(other)] == other or other[:len(path)] == path
                   for other in paths[:index]):
                raise ValueError("overlapping request ceiling paths")
        excluded = document["model_exclusions"]
        _fields(excluded, {"prefixes", "suffixes", "substrings"})
        return cls(required, allowed, tuple(outputs), tuple(constants),
                   _names(excluded["prefixes"]), _names(excluded["suffixes"]),
                   _names(excluded["substrings"]), legacy)

    @property
    def components(self):
        return frozenset(component for component, _, _ in self.outputs)

    def _caps(self, caps):
        if self.legacy and len(caps) != len(self.outputs):
            raise ValueError("incomplete accepted ceilings")
        if not self.legacy and (
            type(caps) is not tuple
            or any(type(item) is not tuple or len(item) != 2 for item in caps)
        ):
            raise ValueError("invalid accepted ceilings")
        result = {}
        for component, amount in caps:
            if (type(component) is not str or component in result
                    or type(amount) is not int or not 0 <= amount <= 10**18):
                raise ValueError("invalid accepted ceiling")
            result[component] = amount
        if result.keys() != self.components:
            raise ValueError("incomplete accepted ceilings")
        return result

    def constrain(self, body, caps, *, validate_body):
        """Validator is installed local code supplied by the executor, never source data."""
        is_object = isinstance(body, dict) if self.legacy else type(body) is dict
        if not is_object or not self.required <= body.keys() <= self.allowed:
            raise ValueError("unsupported fields in constrained request")
        model = body.get("model")
        valid_model = isinstance(model, str) if self.legacy else identifier(model)
        if (not valid_model or any(model.startswith(x) for x in self.prefixes)
                or any(model.endswith(x) for x in self.suffixes)
                or any(x in model for x in self.substrings)):
            raise ValueError("unsupported model indirection")
        validate_body(body)
        amounts = self._caps(caps)
        result = deepcopy(body) if self.legacy else json.loads(json.dumps(body, allow_nan=False))
        for component, pointer, divisor in self.outputs:
            amount = amounts[component]
            whole, fraction = divmod(amount, divisor)
            digits = len(str(divisor)) - 1
            value = (str(whole) if not digits
                     else f"{whole}.{fraction:0{digits}d}".rstrip("0").rstrip("."))
            _put(result, pointer, value)
        for pointer, raw, _ in self.constants:
            _put(result, pointer, json.loads(raw))
        return result

    def cost_upper_bound(self, caps, context_tokens, output_tokens):
        amounts = self._caps(caps)
        if any(type(value) is not int or not 0 <= value <= 10**18
               for value in (context_tokens, output_tokens)):
            raise ValueError("invalid reservation quantities")
        return ((context_tokens * amounts["input_million_tokens_usd"] + 999999) // 1000000
                + (output_tokens * amounts["output_million_tokens_usd"] + 999999) // 1000000
                + amounts["request_usd"])

    def affordable_output(self, caps, context_tokens, remaining_cost):
        if type(remaining_cost) is not int or remaining_cost < 0:
            raise ValueError("invalid remaining cost")
        available = remaining_cost - self.cost_upper_bound(caps, context_tokens, 0)
        if available < 0:
            return 0
        price = self._caps(caps)["output_million_tokens_usd"]
        return None if price == 0 else available * 1000000 // price

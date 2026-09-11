"""Bounded data-driven discovery decoding, without IO or authority assertions.

These compiled shapes interpret data only. Publication, semantic provenance,
price enforcement and executor admission belong to the complete source contract.
Neither a compiled shape nor remote fields establish those facts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext

from tinyassets.providers.model_policy import Charge, Model, Pricing, Scores

_MISSING = object()
_MALFORMED = object()


class CatalogDecodeError(ValueError):
    """Fixed credential-free error for unusable discovery data."""


def identifier(value):
    return (isinstance(value, str) and 0 < len(value) <= 200
            and value.isprintable() and value == value.strip())


def exact_scaled(value, scale, *, string_only):
    if string_only and not isinstance(value, str):
        return None
    if type(value) not in (str, int, float) or len(str(value)) > 80:
        return None
    try:
        with localcontext() as context:
            context.prec = 100
            amount = Decimal(str(value))
            if (not amount.is_finite() or amount < 0 or amount.adjusted() > 18
                    or (amount != 0 and amount.adjusted() < -80)):
                return None
            scaled = amount * scale
            if scaled != scaled.to_integral_value() or scaled > 10**18:
                return None
            return int(scaled)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _document(value):
    try:
        raw = json.dumps(value, allow_nan=False, ensure_ascii=True)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("invalid discovery shape document") from None
    if len(raw) > 65536:
        raise ValueError("discovery shape document is too large")


def _fields(value, required, optional=()):
    if (type(value) is not dict or not set(required) <= value.keys()
            or value.keys() - set(required) - set(optional)):
        raise ValueError("invalid discovery shape fields")


def _names(value, *, maximum=64):
    if (type(value) is not list or len(value) > maximum
            or any(not identifier(item) for item in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid discovery field names")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Pointer:
    tokens: tuple[str, ...]

    @classmethod
    def compile(cls, value):
        if type(value) is not str or len(value) > 512 or (value and not value.startswith("/")):
            raise ValueError("invalid discovery pointer")
        parts = value.split("/")[1:] if value else []
        if len(parts) > 16:
            raise ValueError("discovery pointer is too deep")
        for part in parts:
            index = 0
            while index < len(part):
                if part[index] == "~":
                    if index + 1 == len(part) or part[index + 1] not in "01":
                        raise ValueError("invalid discovery pointer escape")
                    index += 1
                index += 1
        return cls(tuple(part.replace("~1", "/").replace("~0", "~") for part in parts))

    def read(self, value, *, default=None, malformed=None):
        for part in self.tokens:
            if isinstance(value, dict):
                if part not in value:
                    return default
                value = value[part]
            elif (isinstance(value, list) and part.isascii() and part.isdecimal()
                  and (part == "0" or not part.startswith("0")) and len(part) <= 10):
                index = int(part)
                if index >= len(value):
                    return default
                value = value[index]
            else:
                return malformed
        return value


def _pointer(document, name):
    return Pointer.compile(document[name]) if name in document else None


def _read(pointer, value):
    return None if pointer is None else pointer.read(value)


@dataclass(frozen=True, slots=True)
class Rows:
    rows: Pointer
    count: Pointer | None
    next_page: Pointer | None
    maximum: int | None
    strict_completeness: bool = True

    def read(self, payload):
        rows = self.rows.read(payload)
        if not isinstance(rows, list):
            raise CatalogDecodeError("catalogue response must contain a data list")
        if self.maximum is not None and len(rows) > self.maximum:
            raise CatalogDecodeError("catalogue response exceeds the row limit")
        if any(not isinstance(row, dict) for row in rows):
            raise CatalogDecodeError("catalogue entries must be objects")
        count = (_MISSING if self.count is None else self.count.read(
            payload, default=_MISSING, malformed=_MALFORMED,
        ))
        if not self.strict_completeness and count in (_MISSING, _MALFORMED):
            count = None
        absent = count is _MISSING or (not self.strict_completeness and count is None)
        if not absent and (type(count) is not int or count != len(rows)):
            raise CatalogDecodeError("catalogue response is incomplete or has an invalid count")
        next_page = (_MISSING if self.next_page is None else self.next_page.read(
            payload, default=_MISSING, malformed=_MALFORMED,
        ))
        if not self.strict_completeness and next_page in (_MISSING, _MALFORMED):
            next_page = None
        if self.strict_completeness:
            incomplete = not (next_page is _MISSING or next_page is None
                              or (type(next_page) is str and next_page == ""))
        else:
            incomplete = bool(next_page)
        if incomplete:
            raise CatalogDecodeError("catalogue response is incomplete")
        return rows


@dataclass(frozen=True, slots=True)
class PriceFields:
    fields: tuple[tuple[str, str, int], ...]
    required: tuple[str, ...]
    overrides: Pointer | None
    metadata: frozenset[str]
    conditions: frozenset[str]
    maximum_overrides: int | None

    @classmethod
    def compile(cls, document, *, legacy=False):
        _document(document)
        _fields(document, {"fields", "required"}, {"overrides", "metadata", "conditions"})
        raw = document["fields"]
        if type(raw) is not dict or not raw or len(raw) > 64:
            raise ValueError("invalid discovery price fields")
        fields = []
        for name, field in raw.items():
            _fields(field, {"component", "scale"})
            if (not identifier(name) or not identifier(field["component"])
                    or type(field["scale"]) is not int
                    or field["scale"] not in {10**n for n in range(19)}):
                raise ValueError("invalid discovery price component or scale")
            fields.append((name, field["component"], field["scale"]))
        if len({item[1] for item in fields}) != len(fields):
            raise ValueError("duplicate discovery price component")
        required = _names(document["required"])
        metadata = frozenset(_names(document.get("metadata", [])))
        conditions = frozenset(_names(document.get("conditions", [])))
        if set(required) - raw.keys() or (metadata | conditions) & raw.keys():
            raise ValueError("discovery price metadata overlaps charges")
        return cls(tuple(fields), required, _pointer(document, "overrides"), metadata,
                   conditions, None if legacy else 128)

    def decode(self, raw, freshness):
        if not isinstance(raw, dict):
            return Pricing()
        mapping = {name: (component, scale) for name, component, scale in self.fields}
        amounts, unknown = {}, set()

        def collect(prices, *, override=False):
            for name, value in prices.items():
                if name in mapping:
                    component, scale = mapping[name]
                    amount = exact_scaled(value, scale, string_only=True)
                    if amount is None:
                        unknown.add(component)
                    else:
                        amounts[component] = max(amount, amounts.get(component, 0))
                elif name in (self.conditions if override else self.metadata):
                    continue
                else:
                    unknown.add(str(name))

        collect(raw)
        for name in self.required:
            if name not in raw:
                unknown.add(mapping[name][0])
        # Missing is different from a present null/invalid override field.
        if self.overrides is not None:
            overrides = self.overrides.read(raw, default=_MISSING, malformed=_MALFORMED)
            marker = self.overrides.tokens[-1] if self.overrides.tokens else "overrides"
            if overrides is _MISSING:
                overrides = []
            if (not isinstance(overrides, list)
                    or any(not isinstance(item, dict) for item in overrides)):
                unknown.add(marker)
            elif self.maximum_overrides is not None and len(overrides) > self.maximum_overrides:
                raise CatalogDecodeError("catalogue price overrides exceed the limit")
            else:
                for override in overrides:
                    collect(override, override=True)
        charges = tuple(Charge(name, amount, True) for name, amount in amounts.items()
                        if name not in unknown)
        return Pricing(freshness, charges, unknown_components=frozenset(unknown))


@dataclass(frozen=True, slots=True)
class CatalogueShape:
    rows: Rows
    model_id: Pointer
    join_key: Pointer | None
    inputs: Pointer
    outputs: Pointer
    tools: Pointer
    tools_member: str | None
    contexts: tuple[Pointer, ...]
    prices: Pointer
    price_fields: PriceFields
    default_model: Pointer | None

    @classmethod
    def compile(cls, document, prices, *, legacy=False):
        _document(document)
        _fields(document, {"rows", "model_id", "inputs", "outputs", "tools", "contexts", "prices"},
                {"count", "next_page", "join_key", "tools_member", "default_model"})
        if "tools_member" in document and not identifier(document["tools_member"]):
            raise ValueError("invalid discovery tools member")
        contexts = document["contexts"]
        if type(contexts) is not list or not 1 <= len(contexts) <= 16:
            raise ValueError("invalid discovery context pointers")
        return cls(
            Rows(Pointer.compile(document["rows"]), _pointer(document, "count"),
                 _pointer(document, "next_page"), None if legacy else 10000, not legacy),
            Pointer.compile(document["model_id"]), _pointer(document, "join_key"),
            Pointer.compile(document["inputs"]), Pointer.compile(document["outputs"]),
            Pointer.compile(document["tools"]), document.get("tools_member"),
            tuple(Pointer.compile(path) for path in contexts), Pointer.compile(document["prices"]),
            PriceFields.compile(prices, legacy=legacy), _pointer(document, "default_model"),
        )

    def decode(self, payload, *, connection, benchmarks=None):
        models, seen = [], set()

        def strings(value):
            if not isinstance(value, list) or any(not identifier(item) for item in value):
                return frozenset()
            return frozenset(value)

        for row in self.rows.read(payload):
            model_id = self.model_id.read(row)
            if not identifier(model_id) or model_id in seen:
                raise CatalogDecodeError("catalogue has an invalid or duplicate model identifier")
            seen.add(model_id)
            raw_tools = self.tools.read(row)
            tools = None
            if self.tools_member is None:
                tools = raw_tools if type(raw_tools) is bool else None
            elif isinstance(raw_tools, list) and all(identifier(item) for item in raw_tools):
                tools = self.tools_member in raw_tools
            limits = [path.read(row) for path in self.contexts]
            known = [limit for limit in limits if type(limit) is int and limit > 0]
            key = _read(self.join_key, row)
            models.append(Model(
                model_id, tools, strings(self.inputs.read(row)), min(known) if known else None,
                self.price_fields.decode(self.prices.read(row), connection.freshness),
                (benchmarks or {}).get(key if identifier(key) else model_id),
                strings(self.outputs.read(row)),
            ))
        result = replace(connection, models=tuple(models))
        if self.default_model is not None:
            default = self.default_model.read(payload)
            result = replace(result, default_model_id=(
                default if identifier(default) and default in seen else None
            ))
        return result


@dataclass(frozen=True, slots=True)
class BenchmarkShape:
    rows: Rows
    source: str
    source_field: Pointer
    model_id: Pointer
    timestamp: Pointer
    agentic: Pointer
    general: Pointer
    scale: int

    @classmethod
    def compile(cls, document, *, legacy=False):
        _document(document)
        _fields(document, {"rows", "source", "source_field", "model_id", "timestamp",
                           "agentic", "general", "scale"}, {"count", "next_page"})
        if (not identifier(document["source"]) or type(document["scale"]) is not int
                or document["scale"] not in {10**n for n in range(19)}):
            raise ValueError("invalid benchmark source or scale")
        return cls(
            Rows(Pointer.compile(document["rows"]), _pointer(document, "count"),
                 _pointer(document, "next_page"), None if legacy else 10000, not legacy),
            document["source"], Pointer.compile(document["source_field"]),
            Pointer.compile(document["model_id"]), Pointer.compile(document["timestamp"]),
            Pointer.compile(document["agentic"]), Pointer.compile(document["general"]),
            document["scale"],
        )

    def decode(self, payload, *, now: datetime, max_age: timedelta):
        if now.utcoffset() is None or max_age < timedelta(0):
            raise ValueError("benchmark freshness needs aware time and nonnegative maximum age")
        rows = self.rows.read(payload)
        freshness = "missing"
        timestamp = self.timestamp.read(payload)
        if isinstance(timestamp, str):
            try:
                as_of = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if as_of.utcoffset() is not None and as_of <= now:
                    freshness = "fresh" if now - as_of <= max_age else "stale"
            except ValueError:
                pass
        scores, duplicates = {}, set()
        for row in rows:
            key = self.model_id.read(row)
            if self.source_field.read(row) != self.source or not identifier(key):
                continue
            if key in scores:
                duplicates.add(key)
            scores[key] = Scores(
                self.source, freshness,
                exact_scaled(self.agentic.read(row), self.scale, string_only=False),
                exact_scaled(self.general.read(row), self.scale, string_only=False),
            )
        return {key: value for key, value in scores.items() if key not in duplicates}

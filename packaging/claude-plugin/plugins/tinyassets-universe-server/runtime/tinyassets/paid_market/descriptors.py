"""Pure capability descriptors and public market-class projection (V1).

Two identities, never aliases:

* ``descriptor_id``   — exact validated *supply* content identity.
* ``market_class_id`` — separately derived public *demand* aggregation identity.

Nothing here executes, reserves, prices, or settles.  There is no mutable
registry: every call takes an explicitly injected owning-domain validator
selected by exact ``(schema_version, lane, profile_schema_revision)``, and the
validator attests the immutable content-addressed profile revision.

Untrusted bytes go through :func:`verify_canonical_descriptor`, which is the
only path that may emit ``not_canonical``.  Trusted structured input goes
through :func:`construct_descriptor` / :func:`validate_descriptor`, which never
accept caller serialization, a caller-chosen id, or a caller-chosen comparison
direction.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

__all__ = [
    "CAPABILITY_DOMAIN",
    "CAPABILITY_SCHEMA_VERSION",
    "MARKET_CLASS_DOMAIN",
    "MARKET_CLASS_SCHEMA_VERSION",
    "IDENTIFIER_PATTERN",
    "MAX_CANONICAL_BYTES",
    "MAX_MEMBERS",
    "ConstructedDescriptor",
    "DescriptorError",
    "ProfileSchemaValidator",
    "canonical_bytes",
    "construct_descriptor",
    "lane_field_names",
    "lane_fields",
    "match_descriptor",
    "project_market_class",
    "validate_descriptor",
    "verify_canonical_descriptor",
]

CAPABILITY_DOMAIN = "tinyassets.capability-descriptor"
CAPABILITY_SCHEMA_VERSION = "capability-descriptor/v1"
MARKET_CLASS_DOMAIN = "tinyassets.market-class"
MARKET_CLASS_SCHEMA_VERSION = "market-class/v1"

MAX_CANONICAL_BYTES = 65_536
MAX_DEPTH = 8
MAX_MEMBERS = 64
MAX_VALUES = 64
MAX_SCALAR_LEAVES = 1_024
MAX_INTEGER = 9_007_199_254_740_991

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._:/+-]{0,127}\Z")
IDENTIFIER_PATTERN = _IDENTIFIER

# Comparison direction is owned by the lane field schema, never by caller data.
IDENTIFIER = "identifier"
RANGE_CONTAINS = "range_contains"  # exact demand value lies inside [min, max]
RANGE_AT_LEAST = "range_at_least"  # offered min >= demand minimum
RANGE_AT_MOST = "range_at_most"  # offered max <= demand maximum
SET_SUBSET = "set_subset"  # demand required_values subset of offered values

_LANE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "inference": (
        ("model_revision", IDENTIFIER),
        ("runtime_revision", IDENTIFIER),
        ("quantization", IDENTIFIER),
        ("context_tokens", RANGE_CONTAINS),
        ("latency_ms", RANGE_AT_MOST),
        ("throughput_tokens_per_second", RANGE_AT_LEAST),
        ("modalities", SET_SUBSET),
        ("structured_output_classes", SET_SUBSET),
        ("tool_classes", SET_SUBSET),
        ("token_categories", SET_SUBSET),
    ),
    "training": (
        ("resource_revision", IDENTIFIER),
        ("accelerator_memory_bytes", RANGE_CONTAINS),
        ("topology_classes", SET_SUBSET),
        ("interconnect_revisions", SET_SUBSET),
        ("runtime_revisions", SET_SUBSET),
        ("container_formats", SET_SUBSET),
        ("interruption_classes", SET_SUBSET),
        ("attestation_classes", SET_SUBSET),
    ),
    "task": (
        ("task_protocol_revision", IDENTIFIER),
        ("sandbox_revision", IDENTIFIER),
        ("environment_revision", IDENTIFIER),
        ("input_media_types", SET_SUBSET),
        ("output_media_types", SET_SUBSET),
        ("machine_gate_classes", SET_SUBSET),
        ("cancellation_classes", SET_SUBSET),
        ("retry_classes", SET_SUBSET),
    ),
    "fabrication": (
        ("process_revision", IDENTIFIER),
        ("material_spec_revisions", SET_SUBSET),
        ("build_x", RANGE_CONTAINS),
        ("build_y", RANGE_CONTAINS),
        ("build_z", RANGE_CONTAINS),
        ("tolerance", RANGE_AT_MOST),
        ("inspection_classes", SET_SUBSET),
        ("certification_classes", SET_SUBSET),
        ("service_regions", SET_SUBSET),
    ),
}

# Declared descriptor order; the three policy fields are materialized
# fail-closed by the trusted constructor when absent.
_DESCRIPTOR_FIELDS = (
    "lane",
    "profile_schema_revision",
    "unit_semantics",
    "region",
    "privacy_class",
    "reliability_class",
    "profile",
)
_DESCRIPTOR_REQUIRED = ("lane", "profile_schema_revision", "unit_semantics", "profile")
_POLICY_DEFAULTS = {
    "region": "unspecified",
    "privacy_class": "public_only",
    "reliability_class": "best_effort_unverified",
}
_ENVELOPE_FIELDS = ("domain", "schema_version", "descriptor")
_DEMAND_FIELDS = (
    "lane",
    "profile_schema_revision",
    "unit_semantics",
    "region",
    "privacy_class",
    "reliability_class",
    "requirements",
)


class DescriptorError(ValueError):
    """Caller-side demand or projection input is structurally unusable.

    Untrusted *descriptor* input never raises — it returns a stable invalid
    result.  A malformed *demand* is a caller bug and fails loudly.
    """


class ProfileSchemaValidator(Protocol):
    """Owning-domain validator, injected per call.

    Pure, synchronous, deterministic, bounded, non-rewriting: no I/O, no clock,
    no randomness, no prices, no credentials, no mutable execution state.
    """

    schema_version: str
    lane: str
    supported_revisions: frozenset[str]
    attested_revision: str
    threshold_buckets: Mapping[str, Sequence[tuple[int | None, str]]]
    region_classes: Mapping[str, str]
    privacy_classes: Mapping[str, str]
    reliability_classes: Mapping[str, str]

    def validate_profile(self, profile: Mapping[str, Any]) -> bool:
        """Accept or refuse the profile without rewriting it."""


@dataclass(frozen=True)
class _Invalid(Exception):
    code: str
    path: str

    def as_result(self, status: str = "invalid") -> dict[str, str]:
        return {"status": status, "code": self.code, "path": self.path}


@dataclass(frozen=True)
class ConstructedDescriptor:
    status: str
    descriptor_id: str | None = None
    canonical_bytes: bytes = b""
    descriptor: Mapping[str, Any] | None = None
    code: str | None = None
    path: str | None = None

    def as_result(self) -> dict[str, str]:
        if self.status == "valid":
            assert self.descriptor_id is not None
            return {"status": "valid", "descriptor_id": self.descriptor_id}
        assert self.code is not None and self.path is not None
        return {"status": "invalid", "code": self.code, "path": self.path}


def lane_fields(lane: str) -> tuple[tuple[str, str], ...]:
    """Closed field schema for one lane, in declared order."""
    try:
        return _LANE_FIELDS[lane]
    except KeyError:  # pragma: no cover - guarded by callers
        raise DescriptorError("unsupported lane") from None


def lane_field_names() -> frozenset[str]:
    """Every V1 profile field name across all lanes."""
    return frozenset(
        name for fields in _LANE_FIELDS.values() for name, _ in fields
    )


def canonical_bytes(payload: object) -> bytes:
    """The one permitted serializer; no alternate encoder is accepted."""
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DescriptorError("payload is not canonically serializable") from exc


# --------------------------------------------------------------------------
# Structured construction
# --------------------------------------------------------------------------


def construct_descriptor(
    body: object, *, validator: ProfileSchemaValidator | None
) -> ConstructedDescriptor:
    """Validate a typed descriptor body and derive its canonical identity.

    Never emits ``not_canonical``: this path builds canonical bytes rather than
    accepting them.
    """
    try:
        descriptor = _normalized_descriptor(body, root="/descriptor")
        _check_validator(descriptor, validator, root="/descriptor")
    except _Invalid as invalid:
        return ConstructedDescriptor(
            status="invalid", code=invalid.code, path=invalid.path
        )
    envelope = {
        "domain": CAPABILITY_DOMAIN,
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "descriptor": descriptor,
    }
    raw = canonical_bytes(envelope)
    if len(raw) > MAX_CANONICAL_BYTES:
        return ConstructedDescriptor(
            status="invalid", code="limit_exceeded", path="/descriptor"
        )
    return ConstructedDescriptor(
        status="valid",
        descriptor_id="sha256:" + hashlib.sha256(raw).hexdigest(),
        canonical_bytes=raw,
        descriptor=descriptor,
    )


def validate_descriptor(
    body: object, *, validator: ProfileSchemaValidator | None
) -> dict[str, str]:
    return construct_descriptor(body, validator=validator).as_result()


def _normalized_descriptor(body: object, *, root: str) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise _Invalid("malformed_descriptor", root)
    _require_object_shape(body, _DESCRIPTOR_FIELDS, _DESCRIPTOR_REQUIRED, root)

    lane = body["lane"]
    _require_identifier(lane, f"{root}/lane")
    if lane not in _LANE_FIELDS:
        raise _Invalid("invalid_identifier", f"{root}/lane")
    _require_identifier(
        body["profile_schema_revision"], f"{root}/profile_schema_revision"
    )
    unit_semantics = _normalized_unit_semantics(
        body["unit_semantics"], f"{root}/unit_semantics"
    )
    # Absent means the fail-closed default; explicit null is still a type error.
    policy = {
        name: (_POLICY_DEFAULTS[name] if name not in body else body[name])
        for name in _POLICY_DEFAULTS
    }
    for name, value in policy.items():
        _require_identifier(value, f"{root}/{name}")

    profile = _normalized_profile(body["profile"], lane, f"{root}/profile")
    return {
        "lane": lane,
        "profile_schema_revision": body["profile_schema_revision"],
        "unit_semantics": unit_semantics,
        "region": policy["region"],
        "privacy_class": policy["privacy_class"],
        "reliability_class": policy["reliability_class"],
        "profile": profile,
    }


def _normalized_unit_semantics(raw: object, path: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _Invalid("invalid_type", path)
    _require_object_shape(raw, ("delivered_unit", "scale"), ("delivered_unit", "scale"), path)
    _require_identifier(raw["delivered_unit"], f"{path}/delivered_unit")
    scale = raw["scale"]
    _require_integer(scale, f"{path}/scale")
    if scale < 1:
        raise _Invalid("invalid_range", f"{path}/scale")
    return {"delivered_unit": raw["delivered_unit"], "scale": scale}


def _normalized_profile(raw: object, lane: str, path: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _Invalid("invalid_type", path)
    fields = _LANE_FIELDS[lane]
    names = tuple(name for name, _ in fields)
    _require_object_shape(raw, names, names, path)

    profile: dict[str, Any] = {}
    for name, kind in fields:
        field_path = f"{path}/{name}"
        value = raw[name]
        if kind == IDENTIFIER:
            _require_identifier(value, field_path)
            profile[name] = value
        elif kind == SET_SUBSET:
            profile[name] = _normalized_set(value, field_path)
        else:
            profile[name] = _normalized_range(value, field_path)
    return profile


def _normalized_set(raw: object, path: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _Invalid("invalid_type", path)
    _require_object_shape(raw, ("unit", "values"), ("unit", "values"), path)
    _require_identifier(raw["unit"], f"{path}/unit")
    values = raw["values"]
    if not isinstance(values, list):
        raise _Invalid("invalid_type", f"{path}/values")
    if not values:
        # A required set with no supported member uses explicit `none`.
        raise _Invalid("missing_field", f"{path}/values")
    if len(values) > MAX_VALUES:
        raise _Invalid("limit_exceeded", f"{path}/values")
    for index, value in enumerate(values):
        _require_identifier(value, f"{path}/values/{index}")
    if len(set(values)) != len(values):
        raise _Invalid("duplicate_value", f"{path}/values")
    return {"unit": raw["unit"], "values": sorted(values)}


def _normalized_range(raw: object, path: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _Invalid("invalid_type", path)
    _require_object_shape(raw, ("min", "max", "unit"), ("min", "max", "unit"), path)
    _require_integer(raw["min"], f"{path}/min")
    _require_integer(raw["max"], f"{path}/max")
    _require_identifier(raw["unit"], f"{path}/unit")
    if raw["min"] > raw["max"]:
        raise _Invalid("invalid_range", path)
    return {"max": raw["max"], "min": raw["min"], "unit": raw["unit"]}


def _require_object_shape(
    raw: Mapping[Any, Any],
    allowed: Sequence[str],
    required: Sequence[str],
    path: str,
) -> None:
    """Missing fields in declared order, then unknown fields ASCII-sorted."""
    keys = set(raw)
    for name in required:
        if name not in keys:
            raise _Invalid("missing_field", f"{path}/{name}")
    unknown = sorted(str(key) for key in keys - set(allowed))
    if unknown:
        # Never echo a caller key: the known parent plus `<?>`.
        raise _Invalid("unknown_field", f"{path}/<?>")


def _require_identifier(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise _Invalid("invalid_type", path)
    if not _IDENTIFIER.fullmatch(value):
        raise _Invalid("invalid_identifier", path)


def _require_integer(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid("invalid_type", path)
    if value < 0 or value > MAX_INTEGER:
        raise _Invalid("invalid_range", path)


def _check_validator(
    descriptor: Mapping[str, Any],
    validator: ProfileSchemaValidator | None,
    *,
    root: str,
) -> None:
    path = f"{root}/profile_schema_revision"
    revision = descriptor["profile_schema_revision"]
    if validator is None:
        raise _Invalid("domain_validator_unavailable", path)
    if (
        getattr(validator, "schema_version", None) != CAPABILITY_SCHEMA_VERSION
        or getattr(validator, "lane", None) != descriptor["lane"]
    ):
        raise _Invalid("domain_validator_unavailable", path)
    if revision not in getattr(validator, "supported_revisions", frozenset()):
        raise _Invalid("unsupported_profile_schema_revision", path)
    if getattr(validator, "attested_revision", None) != revision:
        raise _Invalid("domain_validator_revision_mismatch", path)
    try:
        # A deep copy keeps a rewriting validator from influencing the digest.
        accepted = validator.validate_profile(deepcopy(dict(descriptor["profile"])))
    except Exception:  # noqa: BLE001 - exception text must never escape
        raise _Invalid("domain_validation_failed", f"{root}/profile") from None
    if accepted is not True:
        raise _Invalid("domain_validation_failed", f"{root}/profile")


# --------------------------------------------------------------------------
# Canonical-byte decoder / verifier — the only emitter of not_canonical
# --------------------------------------------------------------------------


def verify_canonical_descriptor(
    raw: object, *, validator: ProfileSchemaValidator | None
) -> dict[str, str]:
    if not isinstance(raw, (bytes, bytearray)):
        return {"status": "invalid", "code": "malformed_descriptor", "path": ""}
    raw = bytes(raw)
    if len(raw) > MAX_CANONICAL_BYTES:
        return {"status": "invalid", "code": "limit_exceeded", "path": ""}
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return {"status": "invalid", "code": "malformed_descriptor", "path": ""}

    try:
        parsed = _guarded_parse(text)
        _enforce_node_limits(parsed)
        if not isinstance(parsed, Mapping):
            raise _Invalid("malformed_descriptor", "")
        _require_object_shape(parsed, _ENVELOPE_FIELDS, _ENVELOPE_FIELDS, "")
        if parsed["domain"] != CAPABILITY_DOMAIN:
            raise _Invalid("unsupported_schema_version", "/domain")
        if parsed["schema_version"] != CAPABILITY_SCHEMA_VERSION:
            raise _Invalid("unsupported_schema_version", "/schema_version")
        descriptor = _normalized_descriptor(parsed["descriptor"], root="/descriptor")
    except _Invalid as invalid:
        return invalid.as_result()

    regenerated = canonical_bytes(
        {
            "domain": CAPABILITY_DOMAIN,
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "descriptor": descriptor,
        }
    )
    if regenerated != raw:
        return {"status": "invalid", "code": "not_canonical", "path": ""}
    try:
        _check_validator(descriptor, validator, root="/descriptor")
    except _Invalid as invalid:
        return invalid.as_result()
    return {
        "status": "valid",
        "descriptor_id": "sha256:" + hashlib.sha256(regenerated).hexdigest(),
    }


def _guarded_parse(text: str) -> Any:
    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len(pairs) > MAX_MEMBERS:
            raise _Invalid("limit_exceeded", "")
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise _Invalid("malformed_descriptor", "")
            seen.add(key)
        return dict(pairs)

    def parse_constant(name: str) -> Any:
        raise _Invalid("invalid_type", "")

    try:
        return json.loads(
            text,
            object_pairs_hook=object_pairs_hook,
            parse_constant=parse_constant,
        )
    except _Invalid:
        raise
    except RecursionError:
        raise _Invalid("limit_exceeded", "") from None
    except ValueError:
        raise _Invalid("malformed_descriptor", "") from None


def _enforce_node_limits(parsed: Any) -> None:
    scalars = 0
    stack: list[tuple[Any, int]] = [(parsed, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise _Invalid("limit_exceeded", "")
        if isinstance(node, Mapping):
            if len(node) > MAX_MEMBERS:
                raise _Invalid("limit_exceeded", "")
            for value in node.values():
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            if len(node) > MAX_VALUES:
                raise _Invalid("limit_exceeded", "")
            for value in node:
                stack.append((value, depth + 1))
        else:
            scalars += 1
            if scalars > MAX_SCALAR_LEAVES:
                raise _Invalid("limit_exceeded", "")


# --------------------------------------------------------------------------
# Compatibility — direction is schema-owned, never caller data
# --------------------------------------------------------------------------


def match_descriptor(
    body: object,
    demand: object,
    *,
    validator: ProfileSchemaValidator | None,
) -> dict[str, str]:
    constructed = construct_descriptor(body, validator=validator)
    if constructed.status != "valid":
        return constructed.as_result()
    assert constructed.descriptor is not None
    parsed_demand = _normalized_demand(demand, constructed.descriptor["lane"])
    try:
        _compare(constructed.descriptor, parsed_demand)
    except _Invalid as invalid:
        return invalid.as_result("incompatible")
    assert constructed.descriptor_id is not None
    return {"status": "compatible", "descriptor_id": constructed.descriptor_id}


def _normalized_demand(demand: object, lane: str) -> dict[str, Any]:
    """Build one bounded ASCII representation before matching or identity."""
    if not isinstance(demand, Mapping):
        raise DescriptorError("demand must be an object")
    unknown = set(demand) - set(_DEMAND_FIELDS)
    if unknown:
        raise DescriptorError("unknown demand field")
    missing = set(_DEMAND_FIELDS) - set(demand)
    if missing:
        raise DescriptorError("missing demand field")

    normalized_lane = _canonical_demand_identifier(demand["lane"])
    if normalized_lane != lane:
        raise DescriptorError("demand lane does not select this descriptor schema")
    unit_semantics = demand["unit_semantics"]
    if not isinstance(unit_semantics, Mapping) or set(unit_semantics) != {
        "delivered_unit",
        "scale",
    }:
        raise DescriptorError("demand unit_semantics is malformed")
    scale = unit_semantics["scale"]
    if (
        isinstance(scale, bool)
        or not isinstance(scale, int)
        or scale < 1
        or scale > MAX_INTEGER
    ):
        raise DescriptorError("demand scale is invalid")

    requirements = demand["requirements"]
    if not isinstance(requirements, Mapping):
        raise DescriptorError("demand requirements must be an object")
    known = {name for name, _ in _LANE_FIELDS[lane]}
    if set(requirements) - known:
        raise DescriptorError("unknown demand requirement field")

    normalized_requirements: dict[str, dict[str, Any]] = {}
    for name, kind in _LANE_FIELDS[lane]:
        if name not in requirements:
            continue
        required = requirements[name]
        if not isinstance(required, Mapping):
            raise DescriptorError("demand requirement must be an object")
        if kind == IDENTIFIER:
            if set(required) != {"value"}:
                raise DescriptorError("identifier requirement takes exactly `value`")
            normalized_requirements[name] = {
                "value": _canonical_demand_identifier(required["value"])
            }
        elif kind == SET_SUBSET:
            if set(required) != {"unit", "required_values"}:
                raise DescriptorError(
                    "set requirement takes `unit` and `required_values`"
                )
            values = required["required_values"]
            if not isinstance(values, list) or not values:
                raise DescriptorError(
                    "set requirement needs non-empty required_values"
                )
            if len(values) > MAX_VALUES:
                raise DescriptorError("set requirement exceeds the value limit")
            normalized_requirements[name] = {
                "unit": _canonical_demand_identifier(required["unit"]),
                "required_values": sorted(
                    {_canonical_demand_identifier(value) for value in values}
                ),
            }
        else:
            if set(required) != {"unit", "value"}:
                raise DescriptorError("numeric requirement takes `unit` and `value`")
            value = required["value"]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > MAX_INTEGER
            ):
                raise DescriptorError(
                    "numeric requirement value must be a bounded integer"
                )
            normalized_requirements[name] = {
                "unit": _canonical_demand_identifier(required["unit"]),
                "value": value,
            }

    normalized = {
        "lane": normalized_lane,
        "profile_schema_revision": _canonical_demand_identifier(
            demand["profile_schema_revision"]
        ),
        "unit_semantics": {
            "delivered_unit": _canonical_demand_identifier(
                unit_semantics["delivered_unit"]
            ),
            "scale": scale,
        },
        "region": _canonical_demand_identifier(demand["region"]),
        "privacy_class": _canonical_demand_identifier(demand["privacy_class"]),
        "reliability_class": _canonical_demand_identifier(
            demand["reliability_class"]
        ),
        "requirements": normalized_requirements,
    }
    if len(canonical_bytes(normalized)) > MAX_CANONICAL_BYTES:
        raise DescriptorError("demand exceeds the canonical byte limit")
    return normalized


def _canonical_demand_identifier(value: object) -> str:
    if not isinstance(value, str):
        raise DescriptorError("demand identifier must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError:
        raise DescriptorError("demand identifier must normalize to ASCII") from None
    if not _IDENTIFIER.fullmatch(normalized):
        raise DescriptorError("demand identifier is invalid")
    return normalized


def _compare(descriptor: Mapping[str, Any], demand: Mapping[str, Any]) -> None:
    if demand["profile_schema_revision"] != descriptor["profile_schema_revision"]:
        raise _Invalid(
            "unsupported_profile_schema_revision", "/descriptor/profile_schema_revision"
        )
    if demand["unit_semantics"] != descriptor["unit_semantics"]:
        raise _Invalid("unit_mismatch", "/descriptor/unit_semantics")
    for name, code in (
        ("region", "region_mismatch"),
        ("privacy_class", "privacy_mismatch"),
        ("reliability_class", "reliability_mismatch"),
    ):
        if demand[name] != descriptor[name]:
            raise _Invalid(code, f"/descriptor/{name}")

    requirements = demand["requirements"]
    profile = descriptor["profile"]
    for name, kind in _LANE_FIELDS[descriptor["lane"]]:
        path = f"/descriptor/profile/{name}"
        if name not in requirements:
            raise _Invalid("facet_missing", path)
        required = requirements[name]
        if not isinstance(required, Mapping):
            raise DescriptorError("demand requirement must be an object")
        offered = profile[name]
        if kind == IDENTIFIER:
            if set(required) != {"value"}:
                raise DescriptorError("identifier requirement takes exactly `value`")
            if required["value"] != offered:
                # Scalar selection is a singleton required subset.
                raise _Invalid("facet_not_in_set", path)
        elif kind == SET_SUBSET:
            if set(required) != {"unit", "required_values"}:
                raise DescriptorError("set requirement takes `unit` and `required_values`")
            if required["unit"] != offered["unit"]:
                raise _Invalid("unit_mismatch", f"{path}/unit")
            wanted = required["required_values"]
            if not isinstance(wanted, list) or not wanted:
                raise DescriptorError("set requirement needs non-empty required_values")
            if not set(wanted) <= set(offered["values"]):
                raise _Invalid("facet_not_in_set", f"{path}/values")
        else:
            if set(required) != {"unit", "value"}:
                raise DescriptorError("numeric requirement takes `unit` and `value`")
            if required["unit"] != offered["unit"]:
                raise _Invalid("unit_mismatch", f"{path}/unit")
            value = required["value"]
            if isinstance(value, bool) or not isinstance(value, int):
                raise DescriptorError("numeric requirement value must be an integer")
            if kind == RANGE_CONTAINS:
                if value < offered["min"]:
                    raise _Invalid("range_below_min", path)
                if value > offered["max"]:
                    raise _Invalid("range_above_max", path)
            elif kind == RANGE_AT_LEAST:
                if offered["min"] < value:
                    raise _Invalid("range_below_min", path)
            else:  # RANGE_AT_MOST
                if offered["max"] > value:
                    raise _Invalid("range_above_max", path)


# --------------------------------------------------------------------------
# Public market-class projection — separate identity, demand-shaped
# --------------------------------------------------------------------------


def project_market_class(
    body: object,
    demand: object,
    *,
    validator: ProfileSchemaValidator | None,
) -> dict[str, str]:
    """Derive the public aggregation identity for a compatible pair.

    Supply headroom, extra set members, and private demand never enter it.
    """
    unclassified = {"status": "unclassified", "code": "market_class_unavailable"}
    constructed = construct_descriptor(body, validator=validator)
    if constructed.status != "valid":
        return unclassified
    descriptor = constructed.descriptor
    assert descriptor is not None and validator is not None
    parsed_demand = _normalized_demand(demand, descriptor["lane"])
    try:
        # A public class exists only after the pair is proven compatible.
        _compare(descriptor, parsed_demand)
    except _Invalid:
        return unclassified

    classes = _public_classes(descriptor, validator)
    if classes is None:
        return unclassified
    requirements = _public_requirements(descriptor, parsed_demand, validator)
    if requirements is None:
        return unclassified

    envelope = {
        "domain": MARKET_CLASS_DOMAIN,
        "schema_version": MARKET_CLASS_SCHEMA_VERSION,
        "descriptor": {
            "descriptor_schema_version": CAPABILITY_SCHEMA_VERSION,
            "lane": descriptor["lane"],
            "profile_schema_revision": descriptor["profile_schema_revision"],
            "unit_semantics": descriptor["unit_semantics"],
            "region_class": classes["region_class"],
            "privacy_class": classes["privacy_class"],
            "reliability_class": classes["reliability_class"],
            "public_requirements": requirements,
        },
    }
    raw = canonical_bytes(envelope)
    if len(raw) > MAX_CANONICAL_BYTES:
        return unclassified
    return {
        "status": "classified",
        "market_class_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def _public_classes(
    descriptor: Mapping[str, Any], validator: ProfileSchemaValidator
) -> dict[str, str] | None:
    tables = (
        ("region_class", "region", getattr(validator, "region_classes", {})),
        ("privacy_class", "privacy_class", getattr(validator, "privacy_classes", {})),
        (
            "reliability_class",
            "reliability_class",
            getattr(validator, "reliability_classes", {}),
        ),
    )
    projected: dict[str, str] = {}
    for public_name, facet, table in tables:
        mapped = table.get(descriptor[facet])
        if not isinstance(mapped, str) or not _IDENTIFIER.fullmatch(mapped):
            return None
        projected[public_name] = mapped
    return projected


def _public_requirements(
    descriptor: Mapping[str, Any],
    demand: Mapping[str, Any],
    validator: ProfileSchemaValidator,
) -> list[dict[str, Any]] | None:
    buckets = getattr(validator, "threshold_buckets", {})
    requirements = demand["requirements"]
    projected: list[dict[str, Any]] = []
    for name, kind in _LANE_FIELDS[descriptor["lane"]]:
        required = requirements[name]
        if kind == IDENTIFIER:
            projected.append(
                {"field": name, "kind": "exact", "value": required["value"]}
            )
        elif kind == SET_SUBSET:
            projected.append(
                {
                    "field": name,
                    "kind": "required_subset",
                    "unit": required["unit"],
                    "values": sorted(required["required_values"]),
                }
            )
        else:
            bucket = _bucket_for(buckets.get(name), required["value"])
            if bucket is None:
                return None
            projected.append(
                {
                    "bucket": bucket,
                    "field": name,
                    "kind": "threshold",
                    "unit": required["unit"],
                }
            )
    projected.sort(key=lambda item: item["field"])
    if len({item["field"] for item in projected}) != len(projected):
        return None
    return projected


def _bucket_for(
    table: Sequence[tuple[int | None, str]] | None, value: int
) -> str | None:
    if not table:
        return None
    for bound, bucket in table:
        if bound is None or value <= bound:
            return bucket if _IDENTIFIER.fullmatch(bucket) else None
    return None

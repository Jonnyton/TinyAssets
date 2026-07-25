"""Pure quote provenance and exact landed-total validation.

Descriptor construction is intentionally out of scope here.  Quotes bind opaque,
already-validated descriptor and market-class identities supplied by their
owning domain contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Mapping, Protocol


class QuoteError(ValueError):
    """A quote is malformed, stale, unverified, or economically incomplete."""


class QuoteAuthorityVerifier(Protocol):
    def verify(
        self,
        *,
        issuer_id: str,
        key_id: str,
        algorithm: str,
        payload: bytes,
        signature: str,
        issued_at: int,
    ) -> bool:
        """Verify one enrolled, non-revoked issuer signature."""


@dataclass(frozen=True)
class CapacityGrant:
    grant_id: str
    tenant_id: str
    demand_commitment: str
    quote_id: str
    descriptor_id: str
    offer_id: str
    offer_version: int
    total_quantity: int
    consumed_quantity: int
    expires_at: int
    fence: int

    @classmethod
    def from_mapping(cls, raw: object) -> CapacityGrant:
        if not isinstance(raw, Mapping):
            raise QuoteError("capacity_grant must be an object")
        expected = {
            "grant_id",
            "tenant_id",
            "demand_commitment",
            "quote_id",
            "descriptor_id",
            "offer_id",
            "offer_version",
            "total_quantity",
            "consumed_quantity",
            "expires_at",
            "fence",
        }
        _require_exact_fields(raw, expected, "capacity grant")
        values = {name: raw[name] for name in expected}
        for name in (
            "grant_id",
            "tenant_id",
            "demand_commitment",
            "quote_id",
            "descriptor_id",
            "offer_id",
        ):
            _require_text(values[name], name)
        for name in (
            "offer_version",
            "total_quantity",
            "consumed_quantity",
            "expires_at",
            "fence",
        ):
            _require_int(values[name], name, minimum=0)
        if values["offer_version"] == 0:
            raise QuoteError("offer_version must be positive")
        if values["total_quantity"] == 0:
            raise QuoteError("total_quantity must be positive")
        if values["consumed_quantity"] > values["total_quantity"]:
            raise QuoteError("capacity consumption exceeds total")
        return cls(**values)  # type: ignore[arg-type]

    @property
    def remaining_quantity(self) -> int:
        return self.total_quantity - self.consumed_quantity

    def as_dict(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "tenant_id": self.tenant_id,
            "demand_commitment": self.demand_commitment,
            "quote_id": self.quote_id,
            "descriptor_id": self.descriptor_id,
            "offer_id": self.offer_id,
            "offer_version": self.offer_version,
            "total_quantity": self.total_quantity,
            "consumed_quantity": self.consumed_quantity,
            "expires_at": self.expires_at,
            "fence": self.fence,
        }


@dataclass(frozen=True)
class ValidatedQuote:
    quote_id: str
    authority_class: str
    descriptor_id: str
    market_class_id: str
    settlement_currency: str
    total_micros: int
    fee_schedule_version: str
    expires_at: int
    executable: bool
    capacity_remaining: int | None
    canonical_bytes: bytes


@dataclass(frozen=True)
class FxBinding:
    source_currency: str
    target_currency: str
    numerator: int
    denominator: int
    observed_at: int
    expires_at: int
    digest: str
    approved: bool


_QUOTE_FIELDS = {
    "schema_version",
    "quote_id",
    "authority_class",
    "issuer_id",
    "origin",
    "lane",
    "descriptor_id",
    "descriptor_version",
    "market_class_id",
    "demand_commitment",
    "terms_digest",
    "eligibility_digest",
    "settlement_currency",
    "components",
    "declared_total_micros",
    "service_attributes",
    "fee_schedule_version",
    "observed_at",
    "issued_at",
    "expires_at",
    "tenant_id",
    "nonce",
    "signature_domain",
    "key_id",
    "algorithm",
    "signature",
    "offer_id",
    "offer_version",
    "quantity",
    "capacity_grant",
}

_REQUIRED_COMPONENTS = {
    "inference": frozenset({"input", "output", "platform_fee"}),
    "training": frozenset({"accelerator", "platform_fee"}),
    "task": frozenset({"funded_outcome", "platform_fee"}),
    "fabrication": frozenset(
        {"tooling", "material", "unit", "inspection", "shipping", "platform_fee"}
    ),
}


def quote_signing_bytes(raw: Mapping[str, object]) -> bytes:
    """Validate and serialize every authority-bearing field except signature."""
    _require_exact_fields(raw, _QUOTE_FIELDS, "quote")
    if raw["schema_version"] != 1:
        raise QuoteError("unsupported quote schema_version")
    if raw["descriptor_version"] != 1:
        raise QuoteError("unsupported descriptor_version")

    for name in (
        "quote_id",
        "issuer_id",
        "origin",
        "descriptor_id",
        "market_class_id",
        "demand_commitment",
        "terms_digest",
        "eligibility_digest",
        "settlement_currency",
        "fee_schedule_version",
    ):
        _require_text(raw[name], name)
    for name in ("observed_at", "issued_at", "expires_at"):
        _require_int(raw[name], name, minimum=0)
    if raw["expires_at"] <= raw["issued_at"]:
        raise QuoteError("quote expiry must follow issue time")

    lane = raw["lane"]
    if lane not in _REQUIRED_COMPONENTS:
        raise QuoteError("unsupported quote lane")
    total = _component_total(raw["components"], lane)
    _require_int(raw["declared_total_micros"], "declared_total_micros", minimum=0)
    if raw["declared_total_micros"] != total:
        raise QuoteError("total_mismatch")
    _validate_service_attributes(raw["service_attributes"])

    authority_class = raw["authority_class"]
    firm_fields = (
        "tenant_id",
        "nonce",
        "signature_domain",
        "key_id",
        "algorithm",
        "signature",
        "offer_id",
        "offer_version",
        "quantity",
        "capacity_grant",
    )
    if authority_class == "indicative":
        if any(raw[name] is not None for name in firm_fields):
            raise QuoteError("indicative quote contains firm authority")
    elif authority_class == "native_firm":
        for name in (
            "tenant_id",
            "nonce",
            "signature_domain",
            "key_id",
            "algorithm",
            "offer_id",
        ):
            _require_text(raw[name], name)
        _require_int(raw["offer_version"], "offer_version", minimum=1)
        _require_int(raw["quantity"], "quantity", minimum=1)
        grant = CapacityGrant.from_mapping(raw["capacity_grant"])
        _require_capacity_bindings(raw, grant)
    else:
        raise QuoteError("unsupported quote authority_class")

    body = {name: raw[name] for name in sorted(_QUOTE_FIELDS - {"signature"})}
    body["domain"] = "tinyassets.paid-market.quote.v1"
    if isinstance(body["capacity_grant"], CapacityGrant):
        body["capacity_grant"] = body["capacity_grant"].as_dict()
    try:
        return json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise QuoteError("quote is not canonically serializable") from exc


def validated_quote_from_mapping(
    raw: Mapping[str, object],
    *,
    now: int,
    expected_fee_version: str,
    settlement_currency: str,
    verifier: QuoteAuthorityVerifier | None = None,
) -> ValidatedQuote:
    _require_int(now, "now", minimum=0)
    payload = quote_signing_bytes(raw)
    if raw["expires_at"] <= now:
        raise QuoteError("quote_expired")
    if raw["fee_schedule_version"] != expected_fee_version:
        raise QuoteError("fee_version_mismatch")
    if raw["settlement_currency"] != settlement_currency:
        raise QuoteError("settlement_currency_mismatch")

    authority_class = str(raw["authority_class"])
    capacity_remaining: int | None = None
    executable = False
    if authority_class == "native_firm":
        if verifier is None:
            raise QuoteError("signature_verifier_required")
        signature = raw["signature"]
        if not isinstance(signature, str) or not signature:
            raise QuoteError("signature_invalid")
        if not verifier.verify(
            issuer_id=str(raw["issuer_id"]),
            key_id=str(raw["key_id"]),
            algorithm=str(raw["algorithm"]),
            payload=payload,
            signature=signature,
            issued_at=int(raw["issued_at"]),
        ):
            raise QuoteError("signature_invalid")
        grant = CapacityGrant.from_mapping(raw["capacity_grant"])
        if grant.expires_at <= now:
            raise QuoteError("capacity_expired")
        quantity = int(raw["quantity"])
        if grant.remaining_quantity < quantity:
            raise QuoteError("capacity_exhausted")
        capacity_remaining = grant.remaining_quantity
        executable = True

    return ValidatedQuote(
        quote_id=str(raw["quote_id"]),
        authority_class=authority_class,
        descriptor_id=str(raw["descriptor_id"]),
        market_class_id=str(raw["market_class_id"]),
        settlement_currency=settlement_currency,
        total_micros=int(raw["declared_total_micros"]),
        fee_schedule_version=expected_fee_version,
        expires_at=int(raw["expires_at"]),
        executable=executable,
        capacity_remaining=capacity_remaining,
        canonical_bytes=payload,
    )


def consume_capacity(
    grant: CapacityGrant,
    *,
    amount: int,
    now: int,
    tenant_id: str,
    demand_commitment: str,
    quote_id: str,
    descriptor_id: str,
    offer_id: str,
    offer_version: int,
) -> CapacityGrant:
    """Return a narrowed grant; persistence must provide the later atomic CAS."""
    _require_int(amount, "amount", minimum=1)
    if grant.expires_at <= now:
        raise QuoteError("capacity_expired")
    expected = (
        grant.tenant_id,
        grant.demand_commitment,
        grant.quote_id,
        grant.descriptor_id,
        grant.offer_id,
        grant.offer_version,
    )
    supplied = (
        tenant_id,
        demand_commitment,
        quote_id,
        descriptor_id,
        offer_id,
        offer_version,
    )
    if supplied != expected:
        raise QuoteError("capacity_binding_mismatch")
    if amount > grant.remaining_quantity:
        raise QuoteError("capacity_exhausted")
    return replace(
        grant, consumed_quantity=grant.consumed_quantity + amount
    )


def convert_total(
    amount_micros: int,
    source_currency: str,
    target_currency: str,
    *,
    now: int,
    fx: FxBinding | None = None,
) -> int:
    _require_int(amount_micros, "amount_micros", minimum=0)
    if source_currency == target_currency:
        return amount_micros
    if (
        fx is None
        or not fx.approved
        or fx.source_currency != source_currency
        or fx.target_currency != target_currency
        or fx.observed_at > now
        or fx.expires_at <= now
        or fx.numerator <= 0
        or fx.denominator <= 0
        or not fx.digest
    ):
        raise QuoteError("fx_binding_invalid")
    return int(Fraction(amount_micros * fx.numerator, fx.denominator))


def _component_total(raw: object, lane: object) -> int:
    if not isinstance(raw, list) or not raw:
        raise QuoteError("components must be a non-empty list")
    names: set[str] = set()
    total = 0
    for component in raw:
        if not isinstance(component, Mapping):
            raise QuoteError("component must be an object")
        _require_exact_fields(
            component, {"name", "quantity", "unit_price_micros"}, "component"
        )
        name = component["name"]
        _require_text(name, "component name")
        if name in names:
            raise QuoteError("duplicate priced component")
        names.add(name)
        _require_int(component["quantity"], "component quantity", minimum=1)
        _require_int(
            component["unit_price_micros"],
            "component unit_price_micros",
            minimum=0,
        )
        if name == "platform_fee" and component["unit_price_micros"] <= 0:
            raise QuoteError("positive platform_fee is required")
        total += int(component["quantity"]) * int(component["unit_price_micros"])
    missing = _REQUIRED_COMPONENTS[str(lane)] - names
    if missing:
        raise QuoteError(f"missing priced component: {sorted(missing)[0]}")
    return total


def _validate_service_attributes(raw: object) -> None:
    if not isinstance(raw, list):
        raise QuoteError("service_attributes must be a list")
    names: set[str] = set()
    for item in raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            or isinstance(item[1], (dict, list))
            or item[1] is None
        ):
            raise QuoteError("invalid service attribute")
        if item[0] in names:
            raise QuoteError("duplicate service attribute")
        names.add(item[0])


def _require_capacity_bindings(
    raw: Mapping[str, object], grant: CapacityGrant
) -> None:
    bindings = (
        (grant.tenant_id, raw["tenant_id"]),
        (grant.demand_commitment, raw["demand_commitment"]),
        (grant.quote_id, raw["quote_id"]),
        (grant.descriptor_id, raw["descriptor_id"]),
        (grant.offer_id, raw["offer_id"]),
        (grant.offer_version, raw["offer_version"]),
    )
    if any(left != right for left, right in bindings):
        raise QuoteError("capacity_binding_mismatch")
    if grant.expires_at != raw["expires_at"]:
        raise QuoteError("capacity_expiry_mismatch")
    if int(raw["quantity"]) > grant.remaining_quantity:
        raise QuoteError("capacity_exhausted")


def _require_exact_fields(
    raw: Mapping[object, object], expected: set[str], label: str
) -> None:
    keys = set(raw)
    unknown = keys - expected
    missing = expected - keys
    if unknown:
        raise QuoteError(f"unknown {label} field")
    if missing:
        raise QuoteError(f"missing {label} field")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise QuoteError(f"{name} must be non-empty text")


def _require_int(value: object, name: str, *, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise QuoteError(f"{name} must be an integer >= {minimum}")

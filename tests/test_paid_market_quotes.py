from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy

import pytest

from tinyassets.paid_market.quotes import (
    CapacityGrant,
    FxBinding,
    QuoteError,
    consume_capacity,
    convert_total,
    quote_signing_bytes,
    validated_quote_from_mapping,
)


class FakeIssuerVerifier:
    def __init__(self) -> None:
        self.keys = {("seller-1", "key-1", "ed25519"): b"test-key"}
        self.revoked: set[tuple[str, str, str]] = set()

    def sign(self, quote: dict[str, object]) -> str:
        return hmac.new(
            b"test-key", quote_signing_bytes(quote), hashlib.sha256
        ).hexdigest()

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
        identity = (issuer_id, key_id, algorithm)
        if identity in self.revoked or identity not in self.keys:
            return False
        expected = hmac.new(self.keys[identity], payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def _firm_quote() -> dict[str, object]:
    quote: dict[str, object] = {
        "schema_version": 1,
        "quote_id": "quote-1",
        "authority_class": "native_firm",
        "issuer_id": "seller-1",
        "origin": "native",
        "lane": "inference",
        "descriptor_id": "sha256:descriptor",
        "descriptor_version": 1,
        "market_class_id": "sha256:market-class",
        "demand_commitment": "hmac:demand",
        "terms_digest": "sha256:terms",
        "eligibility_digest": "sha256:eligibility",
        "settlement_currency": "tiny",
        "components": [
            {"name": "input", "quantity": 100, "unit_price_micros": 2},
            {"name": "output", "quantity": 200, "unit_price_micros": 5},
            {"name": "platform_fee", "quantity": 1, "unit_price_micros": 13},
        ],
        "declared_total_micros": 1_213,
        "service_attributes": [["latency_ms", 250], ["reliability_ppm", 999_000]],
        "fee_schedule_version": "fee-v1",
        "observed_at": 100,
        "issued_at": 100,
        "expires_at": 200,
        "tenant_id": "tenant-a",
        "nonce": "nonce-1",
        "signature_domain": "tinyassets.quote.v1",
        "key_id": "key-1",
        "algorithm": "ed25519",
        "signature": "",
        "offer_id": "offer-1",
        "offer_version": 3,
        "quantity": 300,
        "capacity_grant": {
            "grant_id": "grant-1",
            "tenant_id": "tenant-a",
            "demand_commitment": "hmac:demand",
            "quote_id": "quote-1",
            "descriptor_id": "sha256:descriptor",
            "offer_id": "offer-1",
            "offer_version": 3,
            "total_quantity": 300,
            "consumed_quantity": 0,
            "expires_at": 200,
            "fence": 7,
        },
    }
    verifier = FakeIssuerVerifier()
    quote["signature"] = verifier.sign(quote)
    return quote


def _indicative_quote() -> dict[str, object]:
    quote = _firm_quote()
    quote.update(
        {
            "authority_class": "indicative",
            "tenant_id": None,
            "nonce": None,
            "signature_domain": None,
            "key_id": None,
            "algorithm": None,
            "signature": None,
            "offer_id": None,
            "offer_version": None,
            "quantity": None,
            "capacity_grant": None,
        }
    )
    return quote


def test_indicative_quote_is_valid_but_never_executable() -> None:
    validated = validated_quote_from_mapping(
        _indicative_quote(),
        now=150,
        expected_fee_version="fee-v1",
        settlement_currency="tiny",
    )

    assert validated.total_micros == 1_213
    assert validated.authority_class == "indicative"
    assert validated.executable is False


def test_native_firm_quote_requires_enrolled_current_signature_and_capacity() -> None:
    verifier = FakeIssuerVerifier()
    validated = validated_quote_from_mapping(
        _firm_quote(),
        now=150,
        expected_fee_version="fee-v1",
        settlement_currency="tiny",
        verifier=verifier,
    )

    assert validated.total_micros == 1_213
    assert validated.authority_class == "native_firm"
    assert validated.executable is True
    assert validated.capacity_remaining == 300


def test_revoked_or_unknown_issuer_key_fails_closed() -> None:
    verifier = FakeIssuerVerifier()
    verifier.revoked.add(("seller-1", "key-1", "ed25519"))

    with pytest.raises(QuoteError, match="signature_invalid"):
        validated_quote_from_mapping(
            _firm_quote(),
            now=150,
            expected_fee_version="fee-v1",
            settlement_currency="tiny",
            verifier=verifier,
        )


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("quote_id",), "quote-2"),
        (("descriptor_id",), "sha256:other"),
        (("demand_commitment",), "hmac:other"),
        (("terms_digest",), "sha256:other"),
        (("eligibility_digest",), "sha256:other"),
        (("fee_schedule_version",), "fee-v2"),
        (("nonce",), "nonce-2"),
        (("expires_at",), 201),
        (("offer_id",), "offer-2"),
        (("offer_version",), 4),
        (("quantity",), 299),
        (("tenant_id",), "tenant-b"),
        (("capacity_grant", "fence"), 8),
    ],
)
def test_every_authority_field_is_covered_by_signature(
    path: tuple[str, ...], replacement: object
) -> None:
    quote = _firm_quote()
    target: dict[str, object] = quote
    for key in path[:-1]:
        target = target[key]  # type: ignore[assignment]
    target[path[-1]] = replacement

    with pytest.raises(QuoteError):
        validated_quote_from_mapping(
            quote,
            now=150,
            expected_fee_version="fee-v1",
            settlement_currency="tiny",
            verifier=FakeIssuerVerifier(),
        )


def test_server_recomputes_total_and_requires_positive_fee() -> None:
    quote = _firm_quote()
    quote["declared_total_micros"] = 1

    with pytest.raises(QuoteError, match="total_mismatch"):
        quote_signing_bytes(quote)

    quote = _firm_quote()
    quote["components"] = [
        {"name": "input", "quantity": 100, "unit_price_micros": 2},
        {"name": "output", "quantity": 200, "unit_price_micros": 5},
        {"name": "platform_fee", "quantity": 1, "unit_price_micros": 0},
    ]
    quote["declared_total_micros"] = 1_200
    with pytest.raises(QuoteError, match="positive platform_fee"):
        quote_signing_bytes(quote)


@pytest.mark.parametrize(
    "lane,components",
    [
        (
            "training",
            [
                {"name": "accelerator", "quantity": 8, "unit_price_micros": 10},
                {"name": "topology", "quantity": 1, "unit_price_micros": 5},
                {"name": "platform_fee", "quantity": 1, "unit_price_micros": 1},
            ],
        ),
        (
            "task",
            [
                {
                    "name": "funded_outcome",
                    "quantity": 1,
                    "unit_price_micros": 100,
                },
                {"name": "platform_fee", "quantity": 1, "unit_price_micros": 1},
            ],
        ),
        (
            "fabrication",
            [
                {"name": "tooling", "quantity": 1, "unit_price_micros": 10},
                {"name": "material", "quantity": 2, "unit_price_micros": 5},
                {"name": "unit", "quantity": 3, "unit_price_micros": 7},
                {"name": "inspection", "quantity": 1, "unit_price_micros": 2},
                {"name": "shipping", "quantity": 1, "unit_price_micros": 3},
                {"name": "platform_fee", "quantity": 1, "unit_price_micros": 1},
            ],
        ),
    ],
)
def test_lane_totals_cover_required_priced_components(
    lane: str, components: list[dict[str, object]]
) -> None:
    quote = _indicative_quote()
    quote["lane"] = lane
    quote["components"] = components
    quote["declared_total_micros"] = sum(
        int(component["quantity"]) * int(component["unit_price_micros"])
        for component in components
    )

    validated = validated_quote_from_mapping(
        quote,
        now=150,
        expected_fee_version="fee-v1",
        settlement_currency="tiny",
    )

    assert validated.total_micros == quote["declared_total_micros"]


def test_missing_lane_component_unknown_fields_and_versions_fail_loud() -> None:
    quote = _indicative_quote()
    quote["components"] = [
        {"name": "output", "quantity": 200, "unit_price_micros": 5},
        {"name": "platform_fee", "quantity": 1, "unit_price_micros": 10},
    ]
    quote["declared_total_micros"] = 1_010
    with pytest.raises(QuoteError, match="missing priced component: input"):
        quote_signing_bytes(quote)

    quote = _indicative_quote()
    quote["unexpected"] = "refuse"
    with pytest.raises(QuoteError, match="unknown quote field"):
        quote_signing_bytes(quote)

    quote = _indicative_quote()
    quote["components"][0]["unexpected"] = "refuse"  # type: ignore[index]
    with pytest.raises(QuoteError, match="unknown component field"):
        quote_signing_bytes(quote)

    quote = _indicative_quote()
    quote["schema_version"] = 2
    with pytest.raises(QuoteError, match="unsupported quote schema_version"):
        quote_signing_bytes(quote)

    quote = _indicative_quote()
    quote["descriptor_version"] = 2
    with pytest.raises(QuoteError, match="unsupported descriptor_version"):
        quote_signing_bytes(quote)


def test_quote_expiry_fee_drift_and_currency_mismatch_fail_before_ranking() -> None:
    for now, fee, currency, message in (
        (200, "fee-v1", "tiny", "quote_expired"),
        (150, "fee-v2", "tiny", "fee_version_mismatch"),
        (150, "fee-v1", "usd", "settlement_currency_mismatch"),
    ):
        with pytest.raises(QuoteError, match=message):
            validated_quote_from_mapping(
                _indicative_quote(),
                now=now,
                expected_fee_version=fee,
                settlement_currency=currency,
            )


def test_capacity_consumption_is_immutable_bound_and_conserved() -> None:
    original = CapacityGrant.from_mapping(_firm_quote()["capacity_grant"])

    partial = consume_capacity(
        original,
        amount=125,
        now=150,
        tenant_id="tenant-a",
        demand_commitment="hmac:demand",
        quote_id="quote-1",
        descriptor_id="sha256:descriptor",
        offer_id="offer-1",
        offer_version=3,
    )
    exhausted = consume_capacity(
        partial,
        amount=175,
        now=150,
        tenant_id="tenant-a",
        demand_commitment="hmac:demand",
        quote_id="quote-1",
        descriptor_id="sha256:descriptor",
        offer_id="offer-1",
        offer_version=3,
    )

    assert original.consumed_quantity == 0
    assert partial.consumed_quantity == 125
    assert exhausted.consumed_quantity == exhausted.total_quantity == 300

    with pytest.raises(QuoteError, match="capacity_exhausted"):
        consume_capacity(
            exhausted,
            amount=1,
            now=150,
            tenant_id="tenant-a",
            demand_commitment="hmac:demand",
            quote_id="quote-1",
            descriptor_id="sha256:descriptor",
            offer_id="offer-1",
            offer_version=3,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-b"),
        ("demand_commitment", "hmac:other"),
        ("quote_id", "quote-2"),
        ("descriptor_id", "sha256:other"),
        ("offer_id", "offer-2"),
        ("offer_version", 4),
    ],
)
def test_capacity_binding_mismatch_fails_without_consumption(
    field: str, value: object
) -> None:
    grant = CapacityGrant.from_mapping(_firm_quote()["capacity_grant"])
    bindings: dict[str, object] = {
        "tenant_id": "tenant-a",
        "demand_commitment": "hmac:demand",
        "quote_id": "quote-1",
        "descriptor_id": "sha256:descriptor",
        "offer_id": "offer-1",
        "offer_version": 3,
    }
    bindings[field] = value

    with pytest.raises(QuoteError, match="capacity_binding_mismatch"):
        consume_capacity(grant, amount=1, now=150, **bindings)  # type: ignore[arg-type]
    assert grant.consumed_quantity == 0


def test_fx_conversion_is_exact_bound_and_separately_approved() -> None:
    binding = FxBinding(
        source_currency="usd",
        target_currency="tiny",
        numerator=3,
        denominator=2,
        observed_at=100,
        expires_at=200,
        digest="sha256:fx",
        approved=True,
    )

    assert convert_total(5, "usd", "tiny", now=150, fx=binding) == 7
    assert convert_total(5, "tiny", "tiny", now=150) == 5

    for bad in (
        FxBinding(**{**binding.__dict__, "approved": False}),
        FxBinding(**{**binding.__dict__, "expires_at": 150}),
        FxBinding(**{**binding.__dict__, "source_currency": "eur"}),
    ):
        with pytest.raises(QuoteError, match="fx_binding_invalid"):
            convert_total(5, "usd", "tiny", now=150, fx=bad)


def test_nominal_unit_price_cannot_override_total_or_signed_descriptor() -> None:
    quote = _firm_quote()
    mutated = deepcopy(quote)
    mutated["components"][1]["unit_price_micros"] = 1  # type: ignore[index]
    mutated["declared_total_micros"] = 413

    with pytest.raises(QuoteError, match="signature_invalid"):
        validated_quote_from_mapping(
            mutated,
            now=150,
            expected_fee_version="fee-v1",
            settlement_currency="tiny",
            verifier=FakeIssuerVerifier(),
        )

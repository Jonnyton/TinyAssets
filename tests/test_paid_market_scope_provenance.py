"""Task 2.1 — quote-bound observation-scope provenance.

Scope is derived *before* execution from resolved terms, bound into the quote
at schema v2 under the v2 signing domain, and re-derived against accepted
settlement evidence.  An ordered tuple of strings is not equivalent authority
and no aggregator may pick a bucket after seeing the price.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tinyassets.paid_market.fee_schedule import (
    CANONICAL_FEE_SCHEDULE_VERSION,
    scheduled_fee_micros,
)
from tinyassets.paid_market.price_surface import (
    AccountingReceipt,
    ChainReceipt,
    DomainAcceptanceReceipt,
    PriceSurfaceError,
    ReferenceBatch,
    SettlementBinding,
    aggregate_price_surface,
    join_paid_observation,
)
from tinyassets.paid_market.quotes import (
    QuoteError,
    quote_signing_bytes,
    validated_quote_from_mapping,
)
from tinyassets.paid_market.scope import (
    SCOPE_DOMAIN,
    ScopeError,
    ScopeRevision,
    derive_public_scope_dimensions,
    validate_scope_dimensions,
)

SCOPE_REVISION = "msr:2026-07-25:aa11bb"


def _revision(**overrides: object) -> ScopeRevision:
    kwargs: dict[str, object] = {
        "revision_id": SCOPE_REVISION,
        "dimensions": ("execution_region_bucket", "slo_bucket"),
        "allowed_values": {
            "execution_region_bucket": frozenset({"us", "eu"}),
            "slo_bucket": frozenset({"batch", "interactive"}),
        },
    }
    kwargs.update(overrides)
    return ScopeRevision(**kwargs)  # type: ignore[arg-type]


def _terms() -> dict[str, str]:
    return {"execution_region_bucket": "us", "slo_bucket": "batch"}


def _dimensions() -> bytes:
    return derive_public_scope_dimensions(_revision(), _terms())


# --------------------------------------------------------------------------
# The trusted scope projector
# --------------------------------------------------------------------------


def test_dimensions_are_canonical_ascii_object_bytes() -> None:
    raw = _dimensions()

    assert isinstance(raw, bytes)
    assert raw == b'{"execution_region_bucket":"us","slo_bucket":"batch"}'
    assert json.loads(raw.decode("ascii")) == _terms()


def test_projection_is_order_independent_and_deterministic() -> None:
    reversed_terms = {"slo_bucket": "batch", "execution_region_bucket": "us"}

    assert derive_public_scope_dimensions(_revision(), reversed_terms) == _dimensions()


def test_unknown_dimension_is_refused() -> None:
    terms = _terms()
    terms["exact_destination"] = "10-downing-street"

    with pytest.raises(ScopeError) as excinfo:
        derive_public_scope_dimensions(_revision(), terms)

    assert "10-downing-street" not in str(excinfo.value)


def test_missing_dimension_is_refused() -> None:
    terms = _terms()
    del terms["slo_bucket"]

    with pytest.raises(ScopeError):
        derive_public_scope_dimensions(_revision(), terms)


def test_value_outside_the_allowlist_is_refused() -> None:
    terms = _terms()
    terms["execution_region_bucket"] = "antarctica"

    with pytest.raises(ScopeError):
        derive_public_scope_dimensions(_revision(), terms)


def test_scope_cannot_silently_reclassify_a_market_facet() -> None:
    revision = _revision(
        dimensions=("execution_region_bucket", "privacy_class", "slo_bucket"),
        allowed_values={
            "execution_region_bucket": frozenset({"us", "eu"}),
            "privacy_class": frozenset({"public_only", "private"}),
            "slo_bucket": frozenset({"batch", "interactive"}),
        },
    )
    terms = _terms()
    terms["privacy_class"] = "public_only"

    with pytest.raises(ScopeError) as excinfo:
        derive_public_scope_dimensions(revision, terms)

    assert "facet" in str(excinfo.value)


def test_declared_canonical_projection_derives_from_the_bound_facet() -> None:
    revision = _revision(
        dimensions=("execution_region_bucket", "region_family", "slo_bucket"),
        allowed_values={
            "execution_region_bucket": frozenset({"us", "eu"}),
            "region_family": frozenset({"amer", "emea"}),
            "slo_bucket": frozenset({"batch", "interactive"}),
        },
        projected_facets={"region_family": "region"},
        facet_projections={"region": {"us-east": "amer", "eu-west": "emea"}},
    )

    raw = derive_public_scope_dimensions(
        revision, _terms(), market_facets={"region": "us-east"}
    )
    assert json.loads(raw.decode("ascii"))["region_family"] == "amer"

    # The caller cannot supply the projected dimension itself.
    conflicting = _terms()
    conflicting["region_family"] = "emea"
    with pytest.raises(ScopeError):
        derive_public_scope_dimensions(
            revision, conflicting, market_facets={"region": "us-east"}
        )

    # An unmapped facet value produces no scope at all.
    with pytest.raises(ScopeError):
        derive_public_scope_dimensions(
            revision, _terms(), market_facets={"region": "ap-south"}
        )


@pytest.mark.parametrize(
    "candidate",
    [
        ("region:us", "batch"),
        ["region:us", "batch"],
        "region:us",
        b'{"slo_bucket":"batch", "execution_region_bucket":"us"}',
        b'["us","batch"]',
        b"",
    ],
)
def test_tuple_string_scope_is_not_equivalent_authority(candidate: object) -> None:
    with pytest.raises(ScopeError):
        validate_scope_dimensions(candidate)

    assert validate_scope_dimensions(_dimensions()) == _dimensions()


def test_scope_domain_is_named_for_provenance() -> None:
    assert SCOPE_DOMAIN == "tinyassets.market-scope"


# --------------------------------------------------------------------------
# Quote schema v2 binds the scope
# --------------------------------------------------------------------------


class FakeIssuerVerifier:
    def __init__(self) -> None:
        self.keys = {("seller-1", "key-1", "ed25519"): b"test-key"}

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
        if identity not in self.keys:
            return False
        expected = hmac.new(self.keys[identity], payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def _v1_quote() -> dict[str, object]:
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
        "service_attributes": [["latency_ms", 250]],
        "fee_schedule_version": "fee-v1",
        "observed_at": 100,
        "issued_at": 100,
        "expires_at": 200,
        "tenant_id": "tenant-a",
        "nonce": "nonce-1",
        "signature_domain": "tinyassets.paid-market.quote.v1",
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
    quote["signature"] = FakeIssuerVerifier().sign(quote)
    return quote


def _v2_quote() -> dict[str, object]:
    quote = _v1_quote()
    quote["schema_version"] = 2
    quote["signature_domain"] = "tinyassets.paid-market.quote.v2"
    quote["market_scope_revision"] = SCOPE_REVISION
    quote["public_scope_dimensions"] = _dimensions()
    quote["signature"] = FakeIssuerVerifier().sign(quote)
    return quote


def test_v1_quote_stays_verifiable_as_its_original_closed_schema() -> None:
    validated = validated_quote_from_mapping(
        _v1_quote(),
        now=150,
        expected_fee_version="fee-v1",
        settlement_currency="tiny",
        verifier=FakeIssuerVerifier(),
    )

    assert validated.schema_version == 1
    assert validated.market_scope_revision is None
    assert validated.public_scope_dimensions is None
    assert b"quote.v1" in validated.canonical_bytes


def test_v1_quote_cannot_carry_scope_fields() -> None:
    quote = _v1_quote()
    quote["market_scope_revision"] = SCOPE_REVISION
    quote["public_scope_dimensions"] = _dimensions()

    with pytest.raises(QuoteError, match="unknown"):
        quote_signing_bytes(quote)


def test_scope_provenance_requires_quote_schema_v2() -> None:
    validated = validated_quote_from_mapping(
        _v2_quote(),
        now=150,
        expected_fee_version="fee-v1",
        settlement_currency="tiny",
        verifier=FakeIssuerVerifier(),
    )

    assert validated.schema_version == 2
    assert validated.market_scope_revision == SCOPE_REVISION
    assert validated.public_scope_dimensions == _dimensions()
    assert b"tinyassets.paid-market.quote.v2" in validated.canonical_bytes


def test_v1_signature_cannot_authorize_the_new_scope_fields() -> None:
    """A v1 signature is over v1 bytes; it never spans a v2 scope binding."""
    downgraded = _v2_quote()
    v1_bytes_signature = hmac.new(
        b"test-key", quote_signing_bytes(_v1_quote()), hashlib.sha256
    ).hexdigest()
    downgraded["signature"] = v1_bytes_signature

    with pytest.raises(QuoteError, match="signature_invalid"):
        validated_quote_from_mapping(
            downgraded,
            now=150,
            expected_fee_version="fee-v1",
            settlement_currency="tiny",
            verifier=FakeIssuerVerifier(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_scope_revision", "msr:2026-07-25:tampered"),
        ("public_scope_dimensions", b'{"execution_region_bucket":"eu","slo_bucket":"batch"}'),
        ("schema_version", 1),
    ],
)
def test_changed_or_downgraded_scope_fails_verification_before_ranking(
    field: str, value: object
) -> None:
    quote = _v2_quote()
    quote[field] = value

    with pytest.raises(QuoteError):
        validated_quote_from_mapping(
            quote,
            now=150,
            expected_fee_version="fee-v1",
            settlement_currency="tiny",
            verifier=FakeIssuerVerifier(),
        )


@pytest.mark.parametrize("version", [True, False, 1.0, "1", "2", None, 0, 3])
def test_only_the_closed_schema_version_set_selects_a_signing_domain(
    version: object,
) -> None:
    """`True == 1` in Python; a bool must not select the v1 closed schema."""
    quote = _v1_quote()
    quote["schema_version"] = version

    with pytest.raises(QuoteError, match="unsupported quote schema_version"):
        quote_signing_bytes(quote)


def test_tuple_scope_substitution_in_a_quote_is_refused() -> None:
    quote = _v2_quote()
    quote["public_scope_dimensions"] = ("region:us", "batch")

    with pytest.raises(QuoteError):
        quote_signing_bytes(quote)


# --------------------------------------------------------------------------
# Settlement observations re-derive the bound scope
# --------------------------------------------------------------------------


def _binding(**overrides: object) -> SettlementBinding:
    gross = int(overrides.get("gross_micros", 40_000))  # type: ignore[arg-type]
    fee = int(  # type: ignore[arg-type]
        overrides.get(
            "fee_micros",
            scheduled_fee_micros(
                gross, fee_schedule_version=CANONICAL_FEE_SCHEDULE_VERSION
            ),
        )
    )
    kwargs: dict[str, object] = {
        "tenant_id": "tenant-a",
        "universe_id": "universe-a",
        "settlement_id": "settle-1",
        "accepted_result_id": "job-1:7:sha256:result",
        "requester_id": "buyer-1",
        "host_owner_id": "seller-1",
        "currency": "tiny",
        "token": "tiny",
        "chain": "ledger",
        "gross_micros": gross,
        "net_micros": gross - fee,
        "fee_micros": fee,
        "fee_schedule_version": CANONICAL_FEE_SCHEDULE_VERSION,
    }
    kwargs.update(overrides)
    return SettlementBinding(**kwargs)  # type: ignore[arg-type]


def _observation(**overrides: object) -> object:
    binding = _binding(**{k: v for k, v in overrides.items() if k in _binding().__dict__})
    kwargs: dict[str, object] = {
        "market_class_id": "sha256:market-class",
        "market_scope_revision": SCOPE_REVISION,
        "public_scope": _dimensions(),
        "unit_price_micros": 4_000,
        "quantity": 10,
        "observed_at": 1_000,
        "buyer_principal_root": "root-buyer",
        "seller_principal_root": "root-seller",
    }
    kwargs.update({k: v for k, v in overrides.items() if k in kwargs})
    return join_paid_observation(
        AccountingReceipt(binding=binding, transaction_id="tx-1"),
        DomainAcceptanceReceipt(
            binding=binding,
            evidence_digest="sha256:evidence",
            accepted=True,
            disputed=False,
        ),
        ChainReceipt(
            binding=binding,
            receipt_digest="sha256:chain",
            finality_status="final",
            reorged=False,
        ),
        **kwargs,  # type: ignore[arg-type]
    )


def test_observation_binds_canonical_scope_bytes() -> None:
    observation = _observation()

    assert observation.public_scope == _dimensions()
    assert observation.market_scope_revision == SCOPE_REVISION


@pytest.mark.parametrize(
    "candidate", [("region:us", "batch"), ["us"], "us", b"not-json", b'["us"]']
)
def test_observation_refuses_non_canonical_scope(candidate: object) -> None:
    with pytest.raises(PriceSurfaceError):
        _observation(public_scope=candidate)


def test_observation_requires_a_bound_scope_revision() -> None:
    with pytest.raises(PriceSurfaceError):
        _observation(market_scope_revision="")


def test_aggregate_key_is_the_full_class_revision_dimensions_triple() -> None:
    other_scope = derive_public_scope_dimensions(
        _revision(), {"execution_region_bucket": "eu", "slo_bucket": "batch"}
    )
    us = _observation()
    eu = _observation(public_scope=other_scope, settlement_id="settle-2")
    other_revision = _observation(
        market_scope_revision="msr:2026-07-25:next", settlement_id="settle-3"
    )

    surface = aggregate_price_surface(
        market_class_id="sha256:market-class",
        market_scope_revision=SCOPE_REVISION,
        public_scope=_dimensions(),
        now=1_000,
        observations=[us, eu, other_revision],
        native_asks=[],
        references=ReferenceBatch((), (), None),
        min_samples=1,
        settlement_ttl=3_600,
    )

    assert surface.raw_vwap.sample_count == 1
    assert surface.raw_vwap.source_ids == ("settle-1",)
    assert surface.public_scope == _dimensions()
    assert surface.market_scope_revision == SCOPE_REVISION


def test_aggregator_cannot_substitute_a_tuple_scope_key() -> None:
    with pytest.raises(PriceSurfaceError):
        aggregate_price_surface(
            market_class_id="sha256:market-class",
            market_scope_revision=SCOPE_REVISION,
            public_scope=("region:us", "batch"),  # type: ignore[arg-type]
            now=1_000,
            observations=[_observation()],
            native_asks=[],
            references=ReferenceBatch((), (), None),
            min_samples=1,
            settlement_ttl=3_600,
        )

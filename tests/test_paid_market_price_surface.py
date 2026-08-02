from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tinyassets.paid_market.fee_schedule import (
    CANONICAL_FEE_SCHEDULE_VERSION,
    scheduled_fee_micros,
)
from tinyassets.paid_market.forwards import FEE_PPM, canonical_fee_micros
from tinyassets.paid_market.index import SettledTrade, compute_vwap
from tinyassets.paid_market.price_surface import (
    AccountingReceipt,
    ChainReceipt,
    DomainAcceptanceReceipt,
    NativeAsk,
    PaidObservation,
    PriceSurface,
    PriceSurfaceError,
    ReferenceBatch,
    ReferenceQuote,
    ReferenceRequest,
    SettlementBinding,
    aggregate_price_surface,
    collect_references,
    join_paid_observation,
)
from tinyassets.paid_market.quotes import ValidatedQuote
from tinyassets.paid_market.scope import ScopeRevision, derive_public_scope_dimensions

SCOPE_REVISION = "msr:test:0001"
_SCOPE_CONTRACT = ScopeRevision(
    revision_id=SCOPE_REVISION,
    dimensions=("execution_region_bucket", "slo_bucket"),
    allowed_values={
        "execution_region_bucket": frozenset({"us", "eu"}),
        "slo_bucket": frozenset({"batch", "interactive"}),
    },
)
# Scope authority is canonical object bytes, not an ordered tuple of strings.
SCOPE = derive_public_scope_dimensions(
    _SCOPE_CONTRACT, {"execution_region_bucket": "us", "slo_bucket": "batch"}
)


def _canonical_fee(gross: int) -> int:
    return scheduled_fee_micros(
        gross, fee_schedule_version=CANONICAL_FEE_SCHEDULE_VERSION
    )


DESCRIPTOR_ID = "sha256:descriptor"


def _binding(**changes: object) -> SettlementBinding:
    gross = int(changes.get("gross_micros", 1_000))  # type: ignore[arg-type]
    fee = int(changes.get("fee_micros", _canonical_fee(gross)))  # type: ignore[arg-type]
    values: dict[str, object] = {
        "tenant_id": "tenant-a",
        "universe_id": "universe-a",
        "settlement_id": "settlement-1",
        "accepted_result_id": "job-1:7:sha256-result",
        "requester_id": "buyer-1",
        "host_owner_id": "seller-1",
        "descriptor_id": DESCRIPTOR_ID,
        "currency": "tiny",
        "token": "tiny-test",
        "chain": "base-sepolia",
        "gross_micros": gross,
        "net_micros": gross - fee,
        "fee_micros": fee,
        "fee_schedule_version": CANONICAL_FEE_SCHEDULE_VERSION,
        "delivered_quantity": 10,
        "buyer_principal_root": "principal:buyer",
        "seller_principal_root": "principal:seller",
        "linked_party": False,
    }
    values.update(changes)
    return SettlementBinding(**values)  # type: ignore[arg-type]


def _signed_bytes(values: dict[str, object]) -> bytes:
    """The bytes an issuer would actually have signed for these field values."""
    scope = values["public_scope_dimensions"]
    body = {
        "domain": "tinyassets.paid-market.quote.v2",
        "schema_version": 2,
        "quote_id": values["quote_id"],
        "descriptor_id": values["descriptor_id"],
        "market_class_id": values["market_class_id"],
        "market_scope_revision": values["market_scope_revision"],
        "settlement_currency": values["settlement_currency"],
        "fee_schedule_version": values["fee_schedule_version"],
        "public_scope_dimensions": (
            bytes(scope).decode("ascii")  # type: ignore[arg-type]
            if isinstance(scope, (bytes, bytearray))
            else scope
        ),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")


def _quote(**changes: object) -> ValidatedQuote:
    """A v2 quote whose signed scope is the observation's only scope authority."""
    values: dict[str, object] = {
        "quote_id": "quote-1",
        "authority_class": "native_firm",
        "descriptor_id": DESCRIPTOR_ID,
        "market_class_id": "sha256:market",
        "settlement_currency": "tiny",
        "total_micros": 1_000,
        "fee_schedule_version": CANONICAL_FEE_SCHEDULE_VERSION,
        "expires_at": 200,
        "executable": True,
        "capacity_remaining": 100,
        "schema_version": 2,
        "market_scope_revision": SCOPE_REVISION,
        "public_scope_dimensions": SCOPE,
    }
    values.update(changes)
    # Unless a test is deliberately forging one, the signed bytes agree with
    # the attributes — a `ValidatedQuote` whose fields drift from its own
    # canonical bytes is exactly the attack the join must refuse.
    values.setdefault("canonical_bytes", _signed_bytes(values))
    return ValidatedQuote(**values)  # type: ignore[arg-type]


def _empty_batch() -> ReferenceBatch:
    return ReferenceBatch((), (), None)


def _receipts(binding: SettlementBinding, source: str = "tx-1"):
    return (
        AccountingReceipt(binding=binding, transaction_id=f"tx:{source}"),
        DomainAcceptanceReceipt(
            binding=binding,
            evidence_digest=f"sha256:evidence:{source}",
            accepted=True,
            disputed=False,
        ),
        ChainReceipt(
            binding=binding,
            receipt_digest=f"sha256:chain:{source}",
            finality_status="final",
            reorged=False,
        ),
    )


def _join(binding: SettlementBinding, **overrides: object):
    """Join one settlement whose declared price reconstructs its gross."""
    source = str(overrides.pop("source", "tx-1"))
    delivered = binding.delivered_quantity
    # A malformed delivered_quantity must reach the runtime's own validation
    # rather than blowing up here, so the fixture falls back instead of dividing.
    usable = isinstance(delivered, int) and not isinstance(delivered, bool) and delivered > 0
    kwargs: dict[str, object] = {
        "quote": _quote(),
        "unit_price_micros": binding.gross_micros // delivered if usable else 100,
        "observed_at": 100,
    }
    kwargs.update(overrides)
    return join_paid_observation(*_receipts(binding, source), **kwargs)  # type: ignore[arg-type]


def _observation(
    *,
    price: int,
    quantity: int,
    observed_at: int,
    buyer_root: str | None,
    seller_root: str | None,
    source: str,
    requester_id: str = "buyer-1",
    host_owner_id: str = "seller-1",
    linked_party: bool = False,
):
    """An observation whose price is exactly what its settlement moved."""
    binding = _binding(
        settlement_id=source,
        requester_id=requester_id,
        host_owner_id=host_owner_id,
        gross_micros=price * quantity,
        delivered_quantity=quantity,
        buyer_principal_root=buyer_root,
        seller_principal_root=seller_root,
        linked_party=linked_party,
    )
    return _join(binding, observed_at=observed_at, source=source)


def test_paid_observation_requires_three_exact_matching_final_receipts() -> None:
    binding = _binding()

    observation = _join(binding, unit_price_micros=100)

    assert observation.binding is binding
    assert observation.index_eligible is True
    assert observation.binding.fee_micros == 10
    assert observation.principal_pair == (
        "principal:buyer",
        "principal:seller",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-b"),
        ("universe_id", "universe-b"),
        ("settlement_id", "settlement-2"),
        ("accepted_result_id", "job-1:8:sha256-other"),
        ("requester_id", "buyer-2"),
        ("host_owner_id", "seller-2"),
        ("currency", "usd"),
        ("token", "other"),
        ("chain", "other-chain"),
        ("gross_micros", 2_000),
        ("net_micros", 1_980),
        ("fee_micros", 20),
        ("descriptor_id", "sha256:other-descriptor"),
        ("fee_schedule_version", "tinyassets.paid-market.fee.v9"),
        ("buyer_principal_root", "principal:other"),
        ("seller_principal_root", None),
        ("linked_party", True),
    ],
)
def test_any_receipt_binding_mismatch_fails_closed(field: str, value: object) -> None:
    binding = _binding()
    changed = replace(binding, **{field: value})

    with pytest.raises(PriceSurfaceError, match="receipt_binding_mismatch"):
        join_paid_observation(
            AccountingReceipt(binding=binding, transaction_id="tx-1"),
            DomainAcceptanceReceipt(
                binding=binding,
                evidence_digest="sha256:evidence",
                accepted=True,
                disputed=False,
            ),
            ChainReceipt(
                binding=changed,
                receipt_digest="sha256:chain",
                finality_status="final",
                reorged=False,
            ),
            quote=_quote(),
            unit_price_micros=100,
            observed_at=100,
        )


@pytest.mark.parametrize(
    ("accepted", "disputed", "finality", "reorged", "message"),
    [
        (False, False, "final", False, "domain_not_accepted"),
        (True, True, "final", False, "domain_not_accepted"),
        (True, False, "pending", False, "chain_not_final"),
        (True, False, "final", True, "chain_not_final"),
    ],
)
def test_nonaccepted_nonfinal_or_reorg_receipt_never_becomes_price(
    accepted: bool,
    disputed: bool,
    finality: str,
    reorged: bool,
    message: str,
) -> None:
    binding = _binding()
    with pytest.raises(PriceSurfaceError, match=message):
        join_paid_observation(
            AccountingReceipt(binding=binding, transaction_id="tx-1"),
            DomainAcceptanceReceipt(
                binding=binding,
                evidence_digest="sha256:evidence",
                accepted=accepted,
                disputed=disputed,
            ),
            ChainReceipt(
                binding=binding,
                receipt_digest="sha256:chain",
                finality_status=finality,
                reorged=reorged,
            ),
            quote=_quote(),
            unit_price_micros=100,
            observed_at=100,
        )


def test_positive_gross_requires_fee_even_when_same_owner_or_linked() -> None:
    same_owner = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:a",
        seller_root="principal:a",
        source="same-owner",
        requester_id="user-a",
        host_owner_id="user-a",
    )
    linked = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:a",
        seller_root="principal:a",
        source="linked",
        linked_party=True,
    )

    assert same_owner.index_eligible is False
    assert linked.index_eligible is False
    assert same_owner.binding.fee_micros == linked.binding.fee_micros == 10

    no_fee = _binding(net_micros=1_000, fee_micros=0)
    with pytest.raises(PriceSurfaceError, match="canonical_fee_required"):
        _join(no_fee, unit_price_micros=100)


def test_quantity_is_settlement_evidence_not_a_caller_declaration() -> None:
    """Codex round-2 finding A: bounding `price * quantity` does not bound price.

    A settlement that moved 1,000,000 micros for 1,000 delivered units has a
    true unit price of 1,000.  Declaring `quantity=1` satisfies the product
    equality exactly while publishing a 1,000x fabricated unit price, so the
    delivered quantity has to be settlement evidence too.
    """
    settled = _binding(gross_micros=1_000_000, delivered_quantity=1_000)

    with pytest.raises(PriceSurfaceError, match="unit_price_not_settlement_derived"):
        _join(settled, unit_price_micros=1_000_000)

    assert _join(settled, unit_price_micros=1_000).unit_price_micros == 1_000
    assert _join(settled, unit_price_micros=1_000).quantity == 1_000


def test_the_join_takes_no_quantity_argument_at_all() -> None:
    """The strongest form of "not caller-supplied" is "not a parameter"."""
    import inspect

    parameters = inspect.signature(join_paid_observation).parameters
    assert "quantity" not in parameters
    assert "delivered_quantity" in SettlementBinding.__dataclass_fields__


def test_unit_price_must_reconstruct_the_settled_gross() -> None:
    """The price is bounded by authoritative money, not by a caller assertion.

    Codex money review finding 1: a positive fixed weight times an unbounded
    caller-provided price is still unbounded.  A settlement that moved 1,000
    micros cannot claim a 10^18-micro unit price.
    """
    settled = _binding(gross_micros=1_000)

    for out_of_band in (10**18, 999_000_000, 101, 99, 1):
        with pytest.raises(
            PriceSurfaceError, match="unit_price_not_settlement_derived"
        ):
            _join(settled, unit_price_micros=out_of_band)

    assert _join(settled, unit_price_micros=100).unit_price_micros == 100


def test_an_unbounded_price_cannot_reach_the_published_index() -> None:
    """The reviewer's reproduction: 3 honest 100-micro prints + one 10^18 print."""
    honest = [
        _observation(
            price=100,
            quantity=10,
            observed_at=100,
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            source=f"honest-{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(3)
    ]
    # The attacker may only publish 10^18 by actually settling 10^18 * quantity
    # micros of real money through all three authorities and paying its fee.
    with pytest.raises(PriceSurfaceError, match="unit_price_not_settlement_derived"):
        _join(
            _binding(settlement_id="attack", gross_micros=1_000),
            unit_price_micros=10**18,
        )

    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=honest,
        native_asks=[],
        references=_empty_batch(),
        min_samples=1,
        settlement_ttl=3_600,
    )
    assert surface.raw_vwap.value_micros == 100


def test_split_account_volume_cannot_evade_the_influence_cap() -> None:
    """One settlement identity, six fabricated principal pairs, still capped.

    Every wash print carries a distinct buyer/seller root and a distinct host,
    so no root- or pair-level bucket binds.  The one thing they share is the
    settlement identity the three receipts agree on.
    """
    wash = [
        _observation(
            price=1_000_000,
            quantity=1_000,
            observed_at=100,
            buyer_root=f"principal:sock-b{index}",
            seller_root=f"principal:sock-s{index}",
            source=f"wash-{index}",
            requester_id="attacker",
            host_owner_id=f"seller-{index}",
        )
        for index in range(6)
    ]
    honest = [
        _observation(
            price=100,
            quantity=10,
            observed_at=100,
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            source=f"honest-{index}",
            requester_id=f"buyer-h{index}",
            host_owner_id=f"seller-h{index}",
        )
        for index in range(3)
    ]

    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=wash + honest,
        native_asks=[],
        references=_empty_batch(),
        min_samples=1,
        settlement_ttl=3_600,
    )

    assert surface.raw_vwap.value_micros is not None
    assert surface.raw_vwap.value_micros < 1_000_000 // 2


def test_the_same_settlement_cannot_be_observed_twice() -> None:
    """Aggregation is by settlement identity, never per call."""
    once = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:b",
        seller_root="principal:s",
        source="settlement-x",
    )

    with pytest.raises(PriceSurfaceError, match="duplicate_settlement_observation"):
        aggregate_price_surface(
            market_class_id="sha256:market",
            market_scope_revision=SCOPE_REVISION,
            public_scope=SCOPE,
            now=150,
            observations=[once, once],
            native_asks=[],
            references=_empty_batch(),
            min_samples=1,
            settlement_ttl=3_600,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("linked_party", None),
        ("linked_party", 0),
        ("linked_party", 1),
        ("linked_party", "false"),
        ("buyer_principal_root", ""),
        ("seller_principal_root", ""),
        ("buyer_principal_root", 7),
        ("delivered_quantity", True),
        ("delivered_quantity", 0),
        ("delivered_quantity", -5),
    ],
)
def test_party_and_delivery_evidence_fails_closed(field: str, value: object) -> None:
    """Codex round-2 finding D: unknown must never read as benign.

    `None` is not "unlinked", an empty root is not a "known" root, and
    `True` is not a delivered quantity of 1.
    """
    with pytest.raises(PriceSurfaceError):
        _join(_binding(**{field: value}))


def test_a_bool_cannot_pass_as_the_influence_cap() -> None:
    """`True == 1` in Python; a bool must not become a 1-ppm cap."""
    with pytest.raises(PriceSurfaceError, match="principal_share_cap_ppm"):
        aggregate_price_surface(
            market_class_id="sha256:market",
            market_scope_revision=SCOPE_REVISION,
            public_scope=SCOPE,
            now=150,
            observations=[],
            native_asks=[],
            references=_empty_batch(),
            min_samples=1,
            settlement_ttl=3_600,
            principal_share_cap_ppm=True,  # type: ignore[arg-type]
        )


def test_observation_identity_comes_from_the_quote_not_the_caller() -> None:
    """Scope, market class, and descriptor are derived from the signed quote."""
    observation = _join(_binding())

    assert observation.descriptor_id == DESCRIPTOR_ID
    assert observation.quote_id == "quote-1"
    assert observation.market_class_id == "sha256:market"
    assert observation.market_scope_revision == SCOPE_REVISION
    assert observation.public_scope == SCOPE


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("descriptor_id", "sha256:other-descriptor", "descriptor_binding_mismatch"),
        ("settlement_currency", "usd", "currency_binding_mismatch"),
        (
            "fee_schedule_version",
            "tinyassets.paid-market.fee.v9",
            "fee_version_binding_mismatch",
        ),
        ("schema_version", 1, "quote_scope_unsigned"),
        ("market_scope_revision", None, "quote_scope_unsigned"),
        ("public_scope_dimensions", None, "quote_scope_unsigned"),
        ("market_class_id", "", "market_class_id is required"),
    ],
)
def test_a_quote_that_does_not_bind_this_settlement_fails_closed(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(PriceSurfaceError, match=message):
        _join(_binding(), quote=_quote(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quote_id", "quote-stolen"),
        ("descriptor_id", DESCRIPTOR_ID),
        ("market_class_id", "sha256:market"),
        ("market_scope_revision", SCOPE_REVISION),
        ("settlement_currency", "tiny"),
        ("fee_schedule_version", CANONICAL_FEE_SCHEDULE_VERSION),
        ("public_scope_dimensions", SCOPE),
    ],
)
def test_quote_attributes_must_match_the_bytes_the_issuer_signed(
    field: str, value: object
) -> None:
    """Codex round-2 finding C: holding a `ValidatedQuote` proves nothing.

    It is an ordinary public dataclass, so an attacker can keep the
    `canonical_bytes` of a genuinely signed quote and replace the attributes
    around them.  Here a quote is signed for *some other* identity and then
    has each attribute swapped back to the one this settlement expects — the
    bytes are real, the attributes are a lie, and the join must refuse it.
    """
    honest = _quote()
    foreign = _quote(
        quote_id="quote-foreign",
        descriptor_id="sha256:foreign-descriptor",
        market_class_id="sha256:foreign-market",
        market_scope_revision="msr:foreign:0001",
        settlement_currency="usd",
        fee_schedule_version="tinyassets.paid-market.fee.v9",
        public_scope_dimensions=derive_public_scope_dimensions(
            _SCOPE_CONTRACT, {"execution_region_bucket": "eu", "slo_bucket": "batch"}
        ),
    )
    forged = replace(foreign, **{field: value}, canonical_bytes=foreign.canonical_bytes)

    with pytest.raises(PriceSurfaceError, match="quote_attributes_not_signed"):
        _join(_binding(), quote=forged)

    # The same swap against a quote whose bytes really do cover it is fine.
    assert _join(_binding(), quote=honest).quote_id == "quote-1"


@pytest.mark.parametrize(
    "candidate", [b"", b"not-json", b"[]", b'"text"', b'{"domain":"other"}', None, 7]
)
def test_unreadable_or_foreign_signed_bytes_fail_closed(candidate: object) -> None:
    with pytest.raises(PriceSurfaceError):
        _join(_binding(), quote=_quote(canonical_bytes=candidate))


def test_the_join_revalidates_the_quote_scope_bytes() -> None:
    """A `ValidatedQuote` value is still not a licence to skip scope canonicality."""
    for candidate in (b"", b'["us","batch"]', b"not-json", ("region:us", "batch")):
        with pytest.raises(PriceSurfaceError, match="public_scope_not_canonical"):
            _join(_binding(), quote=_quote(public_scope_dimensions=candidate))


def test_the_surface_retains_each_source_descriptor_id_as_evidence() -> None:
    first = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:b1",
        seller_root="principal:s1",
        source="obs-1",
        requester_id="buyer-1",
        host_owner_id="seller-1",
    )
    other_descriptor = _binding(
        settlement_id="obs-2",
        requester_id="buyer-2",
        host_owner_id="seller-2",
        descriptor_id="sha256:sibling-descriptor",
        gross_micros=1_200,
        buyer_principal_root="principal:b2",
        seller_principal_root="principal:s2",
    )
    second = _join(
        other_descriptor,
        source="obs-2",
        quote=_quote(descriptor_id="sha256:sibling-descriptor"),
    )

    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=[first, second],
        native_asks=[],
        references=_empty_batch(),
        min_samples=1,
        settlement_ttl=3_600,
    )

    assert surface.observation_descriptor_ids == (
        "sha256:descriptor",
        "sha256:sibling-descriptor",
    )


def test_positive_but_non_canonical_fee_is_refused() -> None:
    """Positivity is not canonicality.

    A 1-micro fee on a 1,000,000-micro gross is positive, conserves, and is
    nowhere near the fee its bound schedule version derives.
    """
    understated = _binding(
        gross_micros=1_000_000, net_micros=999_999, fee_micros=1
    )
    with pytest.raises(PriceSurfaceError, match="canonical_fee_mismatch"):
        _join(understated)

    overstated = _binding(
        gross_micros=1_000_000, net_micros=980_000, fee_micros=20_000
    )
    with pytest.raises(PriceSurfaceError, match="canonical_fee_mismatch"):
        _join(overstated)

    canonical = _binding(
        gross_micros=1_000_000, net_micros=990_000, fee_micros=10_000
    )
    assert _join(canonical).binding.fee_micros == 10_000


def test_fee_schedule_version_must_be_a_known_canonical_schedule() -> None:
    for version in ("", "fee-v1", "tinyassets.paid-market.fee.v0"):
        unknown = _binding(fee_schedule_version=version)
        with pytest.raises(PriceSurfaceError):
            _join(unknown)


def test_settlement_fee_matches_the_landed_canonical_primitive() -> None:
    """One fee formula in the paid market — the schedule only versions it."""
    for gross in (1, 999, 1_000, 12_345, 1_000_000, 10**12):
        expected = canonical_fee_micros(gross, FEE_PPM)
        assert (
            scheduled_fee_micros(
                gross, fee_schedule_version=CANONICAL_FEE_SCHEDULE_VERSION
            )
            == expected
        )
        assert isinstance(expected, int)


class PublicCatalogAdapter:
    adapter_id = "public-catalog"

    def quote(self, request: ReferenceRequest) -> ReferenceQuote:
        return ReferenceQuote(
            source_id=self.adapter_id,
            market_class_id=request.market_class_id,
            currency=request.currency,
            total_micros=180,
            components=frozenset(request.required_components),
            observed_at=100,
            valid_until=200,
            adequate=True,
            currently_available=True,
            executable=False,
            caveats=("public price; platform cannot purchase",),
        )


class CheaperCatalogAdapter:
    adapter_id = "cheaper-catalog"

    def quote(self, request: ReferenceRequest) -> ReferenceQuote:
        return ReferenceQuote(
            source_id=self.adapter_id,
            market_class_id=request.market_class_id,
            currency=request.currency,
            total_micros=150,
            components=frozenset(request.required_components),
            observed_at=110,
            valid_until=190,
            adequate=True,
            currently_available=True,
            executable=False,
            caveats=("requires the requester's own account",),
        )


def test_reference_boundary_is_credential_blind_read_only_and_top_line_cheapest() -> None:
    request = ReferenceRequest(
        market_class_id="sha256:market",
        currency="tiny",
        region="us",
        required_components=frozenset({"usage", "tax", "egress"}),
        terms_digest="sha256:terms",
    )
    adapters = [PublicCatalogAdapter(), CheaperCatalogAdapter()]

    batch = collect_references(adapters, request, now=150)

    assert not hasattr(request, "credential")
    assert all(not hasattr(adapter, "execute") for adapter in adapters)
    assert batch.top_line_reference is not None
    assert batch.top_line_reference.source_id == "cheaper-catalog"
    assert batch.top_line_reference.total_micros == 150
    assert batch.top_line_reference.executable is False
    assert batch.failures == ()


@pytest.mark.parametrize(
    ("quote_changes", "failure"),
    [
        ({"currency": "usd"}, "currency_mismatch"),
        ({"market_class_id": "sha256:other"}, "market_class_mismatch"),
        ({"executable": True}, "executable_reference_forbidden"),
        ({"total_micros": 0}, "invalid_reference_total"),
    ],
)
def test_malformed_reference_isolated_without_fabricating_fallback(
    quote_changes: dict[str, object], failure: str
) -> None:
    class MalformedAdapter(PublicCatalogAdapter):
        adapter_id = "malformed"

        def quote(self, request: ReferenceRequest) -> ReferenceQuote:
            return replace(super().quote(request), **quote_changes)

    request = ReferenceRequest(
        market_class_id="sha256:market",
        currency="tiny",
        region="us",
        required_components=frozenset({"usage", "tax"}),
        terms_digest="sha256:terms",
    )
    batch = collect_references(
        [MalformedAdapter(), PublicCatalogAdapter()], request, now=150
    )

    assert batch.top_line_reference is not None
    assert batch.top_line_reference.source_id == "public-catalog"
    assert batch.failures == (("malformed", failure),)


def test_timeout_and_partial_reference_fail_independently() -> None:
    class TimeoutAdapter:
        adapter_id = "timeout"

        def quote(self, request: ReferenceRequest) -> ReferenceQuote:
            raise TimeoutError("fixture timeout")

    class PartialAdapter(PublicCatalogAdapter):
        adapter_id = "partial"

        def quote(self, request: ReferenceRequest) -> ReferenceQuote:
            return replace(
                super().quote(request),
                total_micros=90,
                components=frozenset({"usage"}),
            )

    request = ReferenceRequest(
        market_class_id="sha256:market",
        currency="tiny",
        region="us",
        required_components=frozenset({"usage", "tax", "egress"}),
        terms_digest="sha256:terms",
    )
    batch = collect_references(
        [TimeoutAdapter(), PartialAdapter(), PublicCatalogAdapter()],
        request,
        now=150,
    )

    assert batch.failures == (("timeout", "adapter_failure"),)
    assert batch.top_line_reference is not None
    assert batch.top_line_reference.source_id == "public-catalog"
    partial = next(quote for quote in batch.quotes if quote.source_id == "partial")
    assert partial.coverage == "partial"
    assert partial.missing_components == frozenset({"tax", "egress"})


def test_price_fields_are_independently_fresh_and_only_composite_clamps() -> None:
    observations = [
        _observation(
            price=200,
            quantity=10,
            observed_at=120 + offset,
            buyer_root=f"buyer:{offset}",
            seller_root=f"seller:{offset}",
            source=f"settlement:{offset}",
        )
        for offset in range(3)
    ]
    asks = [
        NativeAsk(
            source_id="ask-1",
            market_class_id="sha256:market",
            price_micros=175,
            observed_at=140,
            valid_until=180,
            owner_principal_root="seller:ask",
            executable=True,
        )
    ]
    request = ReferenceRequest(
        market_class_id="sha256:market",
        currency="tiny",
        region="us",
        required_components=frozenset({"usage", "tax", "egress"}),
        terms_digest="sha256:terms",
    )
    references = collect_references([CheaperCatalogAdapter()], request, now=150)

    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=observations,
        native_asks=asks,
        references=references,
        min_samples=3,
        settlement_ttl=60,
    )

    assert surface.raw_vwap.value_micros == 200
    assert surface.raw_vwap.observed_at == 122
    assert surface.raw_vwap.sample_count == 3
    assert surface.raw_vwap.owner_count == 3
    assert surface.native_ask.value_micros == 175
    assert surface.native_ask.observed_at == 140
    assert surface.external_reference.value_micros == 150
    assert surface.external_reference.observed_at == 110
    assert surface.external_reference.executable is False
    assert surface.composite_index.value_micros == 150
    assert surface.composite_clamped is True
    assert surface.raw_vwap.value_micros == 200


def test_partial_or_stale_external_reference_never_clamps() -> None:
    observations = [
        _observation(
            price=200,
            quantity=10,
            observed_at=140,
            buyer_root=f"buyer:{index}",
            seller_root=f"seller:{index}",
            source=f"settlement:{index}",
        )
        for index in range(3)
    ]
    request = ReferenceRequest(
        market_class_id="sha256:market",
        currency="tiny",
        region="us",
        required_components=frozenset({"usage", "tax"}),
        terms_digest="sha256:terms",
    )
    partial = replace(
        PublicCatalogAdapter().quote(request),
        total_micros=50,
        components=frozenset({"usage"}),
    )
    stale = replace(
        PublicCatalogAdapter().quote(request),
        source_id="stale",
        total_micros=40,
        valid_until=150,
    )

    references = collect_references(
        [
            type(
                "Partial",
                (),
                {"adapter_id": "partial", "quote": lambda self, request: partial},
            )(),
            type(
                "Stale",
                (),
                {"adapter_id": "stale", "quote": lambda self, request: stale},
            )(),
        ],
        request,
        now=150,
    )
    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=observations,
        native_asks=[],
        references=references,
        min_samples=3,
        settlement_ttl=60,
    )

    assert surface.raw_vwap.value_micros == 200
    assert surface.composite_index.value_micros == 200
    assert surface.composite_clamped is False
    assert surface.external_reference.coverage == "partial"
    assert surface.external_reference.stale is False


def test_missing_vwap_is_null_not_zero_and_zero_prices_fail_loud() -> None:
    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=[],
        native_asks=[],
        references=collect_references(
            [],
            ReferenceRequest(
                market_class_id="sha256:market",
                currency="tiny",
                region="us",
                required_components=frozenset({"usage"}),
                terms_digest="sha256:terms",
            ),
            now=150,
        ),
        min_samples=3,
        settlement_ttl=60,
    )
    assert surface.raw_vwap.value_micros is None
    assert surface.native_ask.value_micros is None
    assert surface.external_reference.value_micros is None
    assert surface.composite_index.value_micros is None

    # A zero price fails loud rather than entering the index as "free".
    with pytest.raises(PriceSurfaceError, match="unit_price_micros"):
        _join(_binding(gross_micros=1_000), unit_price_micros=0)


def test_split_accounts_with_inconsistent_caps_are_refused_and_thin_market_is_low_confidence() -> None:
    observations = [
        _observation(
            price=1_000,
            quantity=1_000,
            observed_at=140,
            buyer_root=f"buyer:{index}",
            seller_root="seller:one-principal",
            source=f"split:{index}",
        )
        for index in range(10)
    ]
    observations.extend(
        [
            _observation(
                price=100,
                quantity=10,
                observed_at=140,
                buyer_root="buyer:b",
                seller_root="seller:b",
                source="honest:b",
            ),
            _observation(
                price=100,
                quantity=10,
                observed_at=140,
                buyer_root="buyer:c",
                seller_root="seller:c",
                source="honest:c",
            ),
        ]
    )
    references = collect_references(
        [],
        ReferenceRequest(
            market_class_id="sha256:market",
            currency="tiny",
            region="us",
            required_components=frozenset({"usage"}),
            terms_digest="sha256:terms",
        ),
        now=150,
    )
    with pytest.raises(PriceSurfaceError, match="joint_influence_cap_infeasible"):
        aggregate_price_surface(
            market_class_id="sha256:market",
            market_scope_revision=SCOPE_REVISION,
            public_scope=SCOPE,
            now=150,
            observations=observations,
            native_asks=[],
            references=references,
            min_samples=3,
            settlement_ttl=60,
            principal_share_cap_ppm=250_000,
        )

    thin = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=observations[:3],
        native_asks=[],
        references=references,
        min_samples=3,
        settlement_ttl=60,
    )
    assert thin.raw_vwap.owner_count == 1
    assert thin.raw_vwap.confidence == "low"


def test_principal_root_self_trade_cannot_move_trusted_vwap() -> None:
    honest = [
        _observation(
            price=100,
            quantity=10,
            observed_at=140,
            buyer_root=f"buyer:honest:{index}",
            seller_root=f"seller:honest:{index}",
            source=f"honest:{index}",
        )
        for index in range(3)
    ]
    self_trade = _observation(
        price=1_000_000,
        quantity=1_000_000,
        observed_at=140,
        buyer_root="principal:self-dealer",
        seller_root="principal:self-dealer",
        source="self-trade",
        requester_id="account:self-dealer:buyer",
        host_owner_id="account:self-dealer:seller",
    )
    references = collect_references(
        [],
        ReferenceRequest(
            market_class_id="sha256:market",
            currency="tiny",
            region="us",
            required_components=frozenset({"usage"}),
            terms_digest="sha256:terms",
        ),
        now=150,
    )

    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=[*honest, self_trade],
        native_asks=[],
        references=references,
        min_samples=3,
        settlement_ttl=60,
        principal_share_cap_ppm=250_000,
    )

    assert self_trade.index_eligible is False
    assert surface.raw_vwap.value_micros == 100
    assert surface.raw_vwap.sample_count == 3


def test_buyer_side_wash_volume_beyond_cap_cannot_move_trusted_vwap() -> None:
    honest = [
        _observation(
            price=100,
            quantity=10,
            observed_at=140,
            buyer_root=f"buyer:honest:{index}",
            seller_root=f"seller:honest:{index}",
            source=f"honest:{index}",
        )
        for index in range(3)
    ]
    wash = [
        _observation(
            price=1_000,
            quantity=1_000,
            observed_at=140,
            buyer_root="buyer:wash-principal",
            seller_root=f"seller:wash-counterparty:{index}",
            source=f"wash:{index}",
        )
        for index in range(12)
    ]
    references = collect_references(
        [],
        ReferenceRequest(
            market_class_id="sha256:market",
            currency="tiny",
            region="us",
            required_components=frozenset({"usage"}),
            terms_digest="sha256:terms",
        ),
        now=150,
    )

    def aggregate(observations: list[PaidObservation]) -> PriceSurface:
        return aggregate_price_surface(
            market_class_id="sha256:market",
            market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
            now=150,
            observations=observations,
            native_asks=[],
            references=references,
            min_samples=3,
            settlement_ttl=60,
            principal_share_cap_ppm=250_000,
        )

    capped = aggregate([*honest, *wash])
    amplified = aggregate(
        [*honest, *(replace(observation, quantity=1_000_000) for observation in wash)]
    )

    assert capped.raw_vwap.value_micros == 325
    assert amplified.raw_vwap.value_micros == capped.raw_vwap.value_micros
    assert amplified.raw_vwap.owner_count == 4


def test_reversed_principal_pair_has_one_direction_insensitive_key() -> None:
    forward = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:a",
        seller_root="principal:b",
        source="forward",
    )
    reverse = _observation(
        price=100,
        quantity=10,
        observed_at=100,
        buyer_root="principal:b",
        seller_root="principal:a",
        source="reverse",
    )
    assert forward.principal_pair == reverse.principal_pair


def test_principal_vwap_matches_canonical_oracle_without_caps() -> None:
    observations = [
        _observation(
            price=price,
            quantity=quantity,
            observed_at=140,
            buyer_root=f"buyer:{index}",
            seller_root=f"seller:{index}",
            source=f"settlement:{index}",
        )
        for index, (price, quantity) in enumerate([(100, 10), (300, 20), (500, 30)])
    ]
    canonical, _ = compute_vwap(
        [
            SettledTrade(
                market_class_id="sha256:market",
                price_micros_per_mtok=observation.unit_price_micros,
                tokens_out=observation.quantity,
                buyer_id=observation.buyer_principal_root or "",
                seller_id=observation.seller_principal_root or "",
                settled_at=observation.observed_at,
            )
            for observation in observations
        ],
        share_cap_ppm=1_000_000,
    )
    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        market_scope_revision=SCOPE_REVISION,
        public_scope=SCOPE,
        now=150,
        observations=observations,
        native_asks=[],
        references=collect_references(
            [],
            ReferenceRequest(
                market_class_id="sha256:market",
                currency="tiny",
                region="us",
                required_components=frozenset({"usage"}),
                terms_digest="sha256:terms",
            ),
            now=150,
        ),
        min_samples=3,
        settlement_ttl=60,
        principal_share_cap_ppm=1_000_000,
    )

    assert surface.raw_vwap.value_micros == canonical

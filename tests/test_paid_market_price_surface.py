from __future__ import annotations

from dataclasses import replace

import pytest

from tinyassets.paid_market.index import SettledTrade, compute_vwap
from tinyassets.paid_market.price_surface import (
    AccountingReceipt,
    ChainReceipt,
    DomainAcceptanceReceipt,
    NativeAsk,
    PriceSurfaceError,
    ReferenceQuote,
    ReferenceRequest,
    SettlementBinding,
    aggregate_price_surface,
    collect_references,
    join_paid_observation,
)


def _binding(**changes: object) -> SettlementBinding:
    values: dict[str, object] = {
        "tenant_id": "tenant-a",
        "universe_id": "universe-a",
        "settlement_id": "settlement-1",
        "accepted_result_id": "job-1:7:sha256-result",
        "requester_id": "buyer-1",
        "host_owner_id": "seller-1",
        "currency": "tiny",
        "token": "tiny-test",
        "chain": "base-sepolia",
        "gross_micros": 1_000,
        "net_micros": 990,
        "fee_micros": 10,
    }
    values.update(changes)
    return SettlementBinding(**values)  # type: ignore[arg-type]


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
    binding = _binding(
        settlement_id=source,
        requester_id=requester_id,
        host_owner_id=host_owner_id,
    )
    return join_paid_observation(
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
        market_class_id="sha256:market",
        public_scope=("region:us", "batch"),
        unit_price_micros=price,
        quantity=quantity,
        observed_at=observed_at,
        buyer_principal_root=buyer_root,
        seller_principal_root=seller_root,
        linked_party=linked_party,
    )


def test_paid_observation_requires_three_exact_matching_final_receipts() -> None:
    binding = _binding()

    observation = join_paid_observation(
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
        market_class_id="sha256:market",
        public_scope=("region:us", "batch"),
        unit_price_micros=100,
        quantity=10,
        observed_at=100,
        buyer_principal_root="principal:buyer",
        seller_principal_root="principal:seller",
    )

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
            market_class_id="sha256:market",
            public_scope=("batch",),
            unit_price_micros=100,
            quantity=10,
            observed_at=100,
            buyer_principal_root="principal:buyer",
            seller_principal_root="principal:seller",
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
            market_class_id="sha256:market",
            public_scope=("batch",),
            unit_price_micros=100,
            quantity=10,
            observed_at=100,
            buyer_principal_root="principal:buyer",
            seller_principal_root="principal:seller",
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
        join_paid_observation(
            AccountingReceipt(binding=no_fee, transaction_id="tx"),
            DomainAcceptanceReceipt(
                binding=no_fee,
                evidence_digest="sha256:e",
                accepted=True,
                disputed=False,
            ),
            ChainReceipt(
                binding=no_fee,
                receipt_digest="sha256:c",
                finality_status="final",
                reorged=False,
            ),
            market_class_id="sha256:market",
            public_scope=("batch",),
            unit_price_micros=100,
            quantity=10,
            observed_at=100,
            buyer_principal_root="principal:a",
            seller_principal_root="principal:a",
        )


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
        public_scope=("region:us", "batch"),
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
        public_scope=("region:us", "batch"),
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
        public_scope=("region:us", "batch"),
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

    with pytest.raises(PriceSurfaceError, match="unit_price_micros"):
        _observation(
            price=0,
            quantity=10,
            observed_at=100,
            buyer_root="buyer",
            seller_root="seller",
            source="zero",
        )


def test_split_accounts_share_one_principal_cap_and_thin_market_is_low_confidence() -> None:
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
    surface = aggregate_price_surface(
        market_class_id="sha256:market",
        public_scope=("region:us", "batch"),
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
        principal_share_cap_ppm=250_000,
    )

    assert surface.raw_vwap.owner_count == 3
    assert surface.raw_vwap.value_micros == 400
    assert surface.raw_vwap.confidence == "normal"

    thin = aggregate_price_surface(
        market_class_id="sha256:market",
        public_scope=("region:us", "batch"),
        now=150,
        observations=observations[:3],
        native_asks=[],
        references=surface.references,
        min_samples=3,
        settlement_ttl=60,
    )
    assert thin.raw_vwap.owner_count == 1
    assert thin.raw_vwap.confidence == "low"


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
                capability_id="sha256:market",
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
        public_scope=("region:us", "batch"),
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

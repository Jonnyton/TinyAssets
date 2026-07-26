"""Task 2.5 — mutation and property proof for the manipulation controls.

Two kinds of evidence here:

* **Mutation probes.**  Each guard assertion runs twice: once normally, and
  once with its control forced open.  A guard that still passes with its
  control removed is vacuous, so the probe asserts the second run goes red.
* **Properties.**  A nominal unit price, a stale field, an unsupported facet,
  or a changed descriptor may never alter eligibility or silently substitute
  supply — swept across value ranges rather than pinned to one example.

No fee exemption exists anywhere in here.  Index eligibility and the canonical
settlement fee are separate controls: a self-trade is excluded from trusted
price evidence *and* still pays the fee.
"""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from tests.test_paid_market_descriptors import (  # noqa: F401 - shared fixtures
    InferenceValidator,
    _body,
    _demand,
)
from tinyassets.paid_market import descriptors, price_surface, routing
from tinyassets.paid_market.descriptors import match_descriptor, validate_descriptor
from tinyassets.paid_market.fee_schedule import (
    CANONICAL_FEE_SCHEDULE_VERSION,
    scheduled_fee_micros,
)
from tinyassets.paid_market.price_surface import (
    AccountingReceipt,
    ChainReceipt,
    DomainAcceptanceReceipt,
    NativeAsk,
    PriceSurfaceError,
    ReferenceBatch,
    ReferenceQuote,
    SettlementBinding,
    aggregate_price_surface,
    join_paid_observation,
)
from tinyassets.paid_market.quotes import ValidatedQuote
from tinyassets.paid_market.routing import (
    RouteCandidate,
    RouteRequest,
    rank_routes,
)
from tinyassets.paid_market.scope import ScopeRevision, derive_public_scope_dimensions

SCOPE_REVISION = "msr:mutation:0001"
SCOPE = derive_public_scope_dimensions(
    ScopeRevision(
        revision_id=SCOPE_REVISION,
        dimensions=("execution_region_bucket", "slo_bucket"),
        allowed_values={
            "execution_region_bucket": frozenset({"us"}),
            "slo_bucket": frozenset({"batch"}),
        },
    ),
    {"execution_region_bucket": "us", "slo_bucket": "batch"},
)


def _validator() -> InferenceValidator:
    return InferenceValidator()


def assert_control_is_load_bearing(guard) -> None:
    """The guard must fail once its control has been forced open."""
    with pytest.raises(AssertionError):
        guard()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


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


def _observation(
    *,
    price: int,
    quantity: int,
    source: str,
    buyer_root: str | None = "principal:buyer",
    seller_root: str | None = "principal:seller",
    requester_id: str = "buyer-1",
    host_owner_id: str = "seller-1",
    linked_party: bool = False,
    observed_at: int = 100,
    binding: SettlementBinding | None = None,
):
    """Price and gross are one fact: the settlement moved ``price * quantity``."""
    bound = binding or _binding(
        settlement_id=source,
        requester_id=requester_id,
        host_owner_id=host_owner_id,
        gross_micros=price * quantity,
        delivered_quantity=quantity,
        buyer_principal_root=buyer_root,
        seller_principal_root=seller_root,
        linked_party=linked_party,
    )
    return join_paid_observation(
        AccountingReceipt(binding=bound, transaction_id=f"tx:{source}"),
        DomainAcceptanceReceipt(
            binding=bound,
            evidence_digest=f"sha256:evidence:{source}",
            accepted=True,
            disputed=False,
        ),
        ChainReceipt(
            binding=bound,
            receipt_digest=f"sha256:chain:{source}",
            finality_status="final",
            reorged=False,
        ),
        quote=_quote(),
        unit_price_micros=price,
        observed_at=observed_at,
    )


def _surface(observations, **overrides):
    kwargs = {
        "market_class_id": "sha256:market",
        "market_scope_revision": SCOPE_REVISION,
        "public_scope": SCOPE,
        "now": 150,
        "observations": observations,
        "native_asks": [],
        "references": ReferenceBatch((), (), None),
        "min_samples": 1,
        "settlement_ttl": 3_600,
    }
    kwargs.update(overrides)
    return aggregate_price_surface(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Mutation probe 1 — self-trade / linked-party exclusion
# --------------------------------------------------------------------------


def _guard_self_trade_is_excluded() -> None:
    self_trade = _observation(
        price=999_000,
        quantity=10,
        source="self-trade",
        buyer_root="principal:a",
        seller_root="principal:a",
        requester_id="user-a",
        host_owner_id="user-a",
    )
    honest = _observation(price=100, quantity=10, source="honest")

    assert self_trade.index_eligible is False
    surface = _surface([self_trade, honest])
    assert surface.raw_vwap.sample_count == 1
    assert surface.raw_vwap.value_micros == 100


def _guard_linked_party_is_excluded() -> None:
    linked = _observation(
        price=999_000, quantity=10, source="linked", linked_party=True
    )
    honest = _observation(price=100, quantity=10, source="honest")

    assert linked.index_eligible is False
    assert _surface([linked, honest]).raw_vwap.value_micros == 100


def _guard_unknown_linkage_is_excluded() -> None:
    unknown = _observation(
        price=999_000, quantity=10, source="unknown", buyer_root=None
    )
    honest = _observation(price=100, quantity=10, source="honest")

    assert unknown.index_eligible is False
    assert _surface([unknown, honest]).raw_vwap.value_micros == 100


@pytest.mark.parametrize(
    "guard",
    [
        _guard_self_trade_is_excluded,
        _guard_linked_party_is_excluded,
        _guard_unknown_linkage_is_excluded,
    ],
)
def test_index_eligibility_control_is_load_bearing(guard, monkeypatch) -> None:
    guard()

    monkeypatch.setattr(price_surface, "_index_eligible", lambda *a, **k: True)
    assert_control_is_load_bearing(guard)


# --------------------------------------------------------------------------
# Mutation probe 2 — per-principal influence cap (unbounded price)
# --------------------------------------------------------------------------


def _guard_one_principal_cannot_dominate() -> None:
    """A single principal's huge print stays inside the configured cap."""
    wash = [
        _observation(
            price=1_000_000,
            quantity=1_000,
            source=f"wash-{index}",
            buyer_root="principal:whale",
            seller_root=f"principal:sock-{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(6)
    ]
    honest = [
        _observation(
            price=100,
            quantity=10,
            source=f"honest-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-h{index}",
            host_owner_id=f"seller-h{index}",
        )
        for index in range(3)
    ]

    capped = _surface(wash + honest, principal_share_cap_ppm=250_000)
    uncapped_mean = 1_000_000

    assert capped.raw_vwap.value_micros is not None
    assert capped.raw_vwap.value_micros < uncapped_mean // 2


def test_influence_cap_is_load_bearing(monkeypatch) -> None:
    _guard_one_principal_cannot_dominate()

    from fractions import Fraction

    monkeypatch.setattr(
        price_surface,
        "_capped_scales",
        lambda volumes, cap: {key: Fraction(1) for key in volumes},
    )
    assert_control_is_load_bearing(_guard_one_principal_cannot_dominate)


# --------------------------------------------------------------------------
# Mutation probe 2b — the price itself is bounded by authoritative money
# --------------------------------------------------------------------------


def _guard_an_unbounded_price_is_refused() -> None:
    """A caller-declared price that its settlement did not move is refused."""
    settled = _binding(settlement_id="unbounded", gross_micros=1_000)
    for out_of_band in (10**18, 999_000_000, 1_001, 999):
        raised = False
        try:
            _observation(
                price=out_of_band,
                quantity=10,
                source="unbounded",
                binding=settled,
            )
        except PriceSurfaceError as exc:
            raised = "unit_price_not_settlement_derived" in str(exc)
        assert raised, "an out-of-band price must not become price evidence"


def test_settlement_derived_price_control_is_load_bearing(monkeypatch) -> None:
    _guard_an_unbounded_price_is_refused()

    monkeypatch.setattr(
        price_surface, "_require_settlement_derived_price", lambda *a, **k: None
    )
    assert_control_is_load_bearing(_guard_an_unbounded_price_is_refused)


def test_a_bounded_weight_on_an_unbounded_price_is_still_unbounded() -> None:
    """Why the weight cap alone was not enough (Codex money review finding 1).

    Three honest 100-micro prints plus one 10^18-micro print: the cap bounds
    the *weight*, so without a price bound the published index still lands
    astronomically far from every honest trade.  The settlement bound removes
    the input rather than dampening it.
    """
    honest = [
        _observation(
            price=100,
            quantity=10,
            source=f"honest-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(3)
    ]
    with pytest.raises(PriceSurfaceError, match="unit_price_not_settlement_derived"):
        _observation(
            price=10**18,
            quantity=10,
            source="whale",
            binding=_binding(settlement_id="whale", gross_micros=1_000),
        )

    assert _surface(honest).raw_vwap.value_micros == 100


# --------------------------------------------------------------------------
# Mutation probe 2c — settlement-identity dampening (split accounts)
# --------------------------------------------------------------------------


def _guard_split_accounts_cannot_dominate() -> None:
    """Fresh roots per print, one settlement identity — still capped."""
    wash = [
        _observation(
            price=1_000_000,
            quantity=1_000,
            source=f"split-{index}",
            buyer_root=f"principal:sock-b{index}",
            seller_root=f"principal:sock-s{index}",
            requester_id="attacker",
            host_owner_id=f"seller-{index}",
        )
        for index in range(6)
    ]
    honest = [
        _observation(
            price=100,
            quantity=10,
            source=f"honest-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-h{index}",
            host_owner_id=f"seller-h{index}",
        )
        for index in range(3)
    ]

    published = _surface(wash + honest).raw_vwap.value_micros
    assert published is not None
    assert published < 1_000_000 // 2


def test_settlement_identity_dampening_is_load_bearing(monkeypatch) -> None:
    _guard_split_accounts_cannot_dominate()

    from fractions import Fraction

    monkeypatch.setattr(
        price_surface, "_settlement_identity_scale", lambda *a, **k: Fraction(1)
    )
    assert_control_is_load_bearing(_guard_split_accounts_cannot_dominate)


def _guard_replayed_settlement_is_refused() -> None:
    once = _observation(price=100, quantity=10, source="replayed")
    raised = False
    try:
        _surface([once, once])
    except PriceSurfaceError as exc:
        raised = "duplicate_settlement_observation" in str(exc)
    assert raised, "one settlement is one observation"


def test_settlement_uniqueness_control_is_load_bearing(monkeypatch) -> None:
    _guard_replayed_settlement_is_refused()

    monkeypatch.setattr(
        price_surface, "_require_unique_settlements", lambda observations: None
    )
    assert_control_is_load_bearing(_guard_replayed_settlement_is_refused)


# --------------------------------------------------------------------------
# Mutation probe 2d — the observation inherits one signed quote identity
# --------------------------------------------------------------------------


def _guard_a_foreign_quote_cannot_bind_this_settlement() -> None:
    for changes, code in (
        ({"descriptor_id": "sha256:foreign"}, "descriptor_binding_mismatch"),
        ({"settlement_currency": "usd"}, "currency_binding_mismatch"),
        ({"schema_version": 1}, "quote_scope_unsigned"),
        ({"market_scope_revision": None}, "quote_scope_unsigned"),
    ):
        bound = _binding(settlement_id="foreign-quote")
        raised = False
        try:
            join_paid_observation(
                AccountingReceipt(binding=bound, transaction_id="tx:foreign"),
                DomainAcceptanceReceipt(
                    binding=bound,
                    evidence_digest="sha256:evidence",
                    accepted=True,
                    disputed=False,
                ),
                ChainReceipt(
                    binding=bound,
                    receipt_digest="sha256:chain",
                    finality_status="final",
                    reorged=False,
                ),
                quote=_quote(**changes),
                unit_price_micros=100,
                observed_at=100,
            )
        except PriceSurfaceError as exc:
            raised = code in str(exc)
        assert raised, f"a quote that does not bind this settlement must fail: {code}"


def test_quote_binding_control_is_load_bearing(monkeypatch) -> None:
    _guard_a_foreign_quote_cannot_bind_this_settlement()

    monkeypatch.setattr(
        price_surface, "_require_quote_binding", lambda binding, quote: SCOPE
    )
    assert_control_is_load_bearing(_guard_a_foreign_quote_cannot_bind_this_settlement)


def _guard_forged_quote_attributes_are_refused() -> None:
    """Real signed bytes plus swapped-in attributes is still a forgery."""
    foreign = _quote(
        quote_id="quote-foreign",
        descriptor_id="sha256:foreign-descriptor",
        market_class_id="sha256:foreign-market",
    )
    forged = replace(
        foreign,
        descriptor_id=DESCRIPTOR_ID,
        market_class_id="sha256:market",
        canonical_bytes=foreign.canonical_bytes,
    )
    bound = _binding(settlement_id="forged")
    raised = False
    try:
        join_paid_observation(
            AccountingReceipt(binding=bound, transaction_id="tx:forged"),
            DomainAcceptanceReceipt(
                binding=bound,
                evidence_digest="sha256:evidence",
                accepted=True,
                disputed=False,
            ),
            ChainReceipt(
                binding=bound,
                receipt_digest="sha256:chain",
                finality_status="final",
                reorged=False,
            ),
            quote=forged,
            unit_price_micros=100,
            observed_at=100,
        )
    except PriceSurfaceError as exc:
        raised = "quote_attributes_not_signed" in str(exc)
    assert raised, "quote attributes must be re-read from the signed bytes"


def test_signed_bytes_reverification_is_load_bearing(monkeypatch) -> None:
    _guard_forged_quote_attributes_are_refused()

    monkeypatch.setattr(
        price_surface, "_require_attributes_match_signed_bytes", lambda *a, **k: None
    )
    assert_control_is_load_bearing(_guard_forged_quote_attributes_are_refused)


def test_raw_native_price_is_immutable_under_the_cap() -> None:
    """Dampening changes weights, never the recorded per-observation price."""
    observations = [
        _observation(
            price=500 + index,
            quantity=10,
            source=f"obs-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(4)
    ]
    prices_before = [item.unit_price_micros for item in observations]

    _surface(observations)

    assert [item.unit_price_micros for item in observations] == prices_before


# --------------------------------------------------------------------------
# Mutation probe 3 — canonical fee on every positive-gross settlement
# --------------------------------------------------------------------------


def _guard_zero_fee_settlement_is_refused() -> None:
    for requester, host, linked in (
        ("user-a", "user-a", False),  # self-trade
        ("buyer-1", "seller-1", True),  # linked party
        ("buyer-1", "seller-1", False),  # arm's length
    ):
        no_fee = _binding(
            requester_id=requester,
            host_owner_id=host,
            net_micros=1_000,
            fee_micros=0,
        )
        raised = False
        try:
            _observation(
                price=100,
                quantity=10,
                source="no-fee",
                linked_party=linked,
                binding=no_fee,
            )
        except PriceSurfaceError as exc:
            raised = "canonical_fee_required" in str(exc)
        assert raised, "a positive-gross settlement must retain the canonical fee"


def test_canonical_fee_control_is_load_bearing(monkeypatch) -> None:
    _guard_zero_fee_settlement_is_refused()

    monkeypatch.setattr(price_surface, "_require_canonical_fee", lambda binding: None)
    assert_control_is_load_bearing(_guard_zero_fee_settlement_is_refused)


def _guard_off_schedule_fee_is_refused() -> None:
    """Positivity is not canonicality: the fee must be the derived amount."""
    for gross, fee in ((1_000_000, 1), (1_000_000, 20_000), (1_000, 9)):
        off_schedule = _binding(
            gross_micros=gross, fee_micros=fee, net_micros=gross - fee
        )
        raised = False
        try:
            _observation(
                price=gross, quantity=1, source="off-schedule", binding=off_schedule
            )
        except PriceSurfaceError as exc:
            raised = "canonical_fee_mismatch" in str(exc)
        assert raised, "a positive fee is not automatically the canonical fee"


def test_canonical_fee_schedule_control_is_load_bearing(monkeypatch) -> None:
    _guard_off_schedule_fee_is_refused()

    # Force the schedule comparison open — positivity alone becomes the test.
    monkeypatch.setattr(price_surface, "_fee_matches_schedule", lambda binding: True)
    assert_control_is_load_bearing(_guard_off_schedule_fee_is_refused)


def test_unknown_fee_schedule_version_fails_closed() -> None:
    for version in ("", "fee-v1", "tinyassets.paid-market.fee.v2"):
        unknown = _binding(fee_schedule_version=version)
        with pytest.raises(PriceSurfaceError):
            _observation(price=100, quantity=10, source="unknown-fee", binding=unknown)


def test_excluded_volume_still_carries_its_fee() -> None:
    """Exclusion from the index is not, and cannot become, a fee waiver."""
    self_trade = _observation(
        price=100,
        quantity=10,
        source="self",
        buyer_root="principal:a",
        seller_root="principal:a",
        requester_id="user-a",
        host_owner_id="user-a",
    )
    linked = _observation(price=100, quantity=10, source="linked", linked_party=True)

    assert self_trade.index_eligible is False
    assert linked.index_eligible is False
    assert self_trade.binding.fee_micros == 10
    assert linked.binding.fee_micros == 10
    assert (
        self_trade.binding.net_micros + self_trade.binding.fee_micros
        == self_trade.binding.gross_micros
    )


# --------------------------------------------------------------------------
# Mutation probe 4 — external references never clamp raw native truth
# --------------------------------------------------------------------------


def _reference(total: int, *, observed_at: int = 100, valid_until: int = 10_000):
    return ReferenceQuote(
        source_id="external-1",
        market_class_id="sha256:market",
        currency="tiny",
        total_micros=total,
        components=frozenset({"compute"}),
        observed_at=observed_at,
        valid_until=valid_until,
        adequate=True,
        currently_available=True,
        executable=False,
        caveats=(),
        coverage="complete",
        missing_components=frozenset(),
    )


def _guard_raw_vwap_is_never_clamped() -> None:
    observations = [
        _observation(
            price=900,
            quantity=10,
            source=f"obs-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(3)
    ]
    ceiling = _reference(400)
    surface = _surface(
        observations, references=ReferenceBatch((ceiling,), (), ceiling)
    )

    assert surface.raw_vwap.value_micros == 900
    assert surface.composite_index.value_micros == 400
    assert surface.composite_clamped is True
    assert surface.composite_index.executable is False


def test_raw_native_truth_isolation_is_load_bearing(monkeypatch) -> None:
    """Mutant: let the external reference reach raw native settlement truth."""
    _guard_raw_vwap_is_never_clamped()

    original = price_surface._raw_vwap_field

    def leaking_raw(observations, **kwargs):
        field = original(observations, **kwargs)
        if field.value_micros is None:
            return field
        return replace(field, value_micros=min(field.value_micros, 400))

    monkeypatch.setattr(price_surface, "_raw_vwap_field", leaking_raw)
    assert_control_is_load_bearing(_guard_raw_vwap_is_never_clamped)


def test_composite_clamp_is_load_bearing(monkeypatch) -> None:
    """Mutant: stop the complete all-in ceiling from bounding the composite."""
    _guard_raw_vwap_is_never_clamped()

    monkeypatch.setattr(
        price_surface, "_composite_field", lambda raw, ceiling: (raw, False)
    )
    assert_control_is_load_bearing(_guard_raw_vwap_is_never_clamped)


@pytest.mark.parametrize(
    ("observed_at", "valid_until"), [(100, 120), (10_000, 20_000)]
)
def test_stale_or_future_reference_never_clamps(
    observed_at: int, valid_until: int
) -> None:
    observations = [
        _observation(
            price=900,
            quantity=10,
            source=f"obs-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(3)
    ]
    stale = _reference(400, observed_at=observed_at, valid_until=valid_until)
    # A non-current reference is never promoted to top-line ceiling.
    surface = _surface(observations, references=ReferenceBatch((stale,), (), None))

    assert surface.raw_vwap.value_micros == 900
    assert surface.composite_index.value_micros == 900
    assert surface.composite_clamped is False


def test_incomplete_reference_is_not_called_a_ceiling() -> None:
    partial = replace(
        _reference(400), coverage="partial", missing_components=frozenset({"egress"})
    )
    observations = [
        _observation(
            price=900,
            quantity=10,
            source=f"obs-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index in range(3)
    ]

    surface = _surface(observations, references=ReferenceBatch((partial,), (), None))

    assert surface.external_reference.coverage == "partial"
    assert surface.composite_clamped is False
    assert surface.composite_index.value_micros == 900


# --------------------------------------------------------------------------
# Mutation probe 5 — substitutability gate
# --------------------------------------------------------------------------


def _guard_unsupported_facet_is_not_substituted() -> None:
    demand = _demand()
    demand["requirements"]["modalities"]["required_values"] = ["audio"]

    result = match_descriptor(_body(), demand, validator=_validator())

    assert result["status"] == "incompatible"
    assert result["code"] == "facet_not_in_set"


def test_substitutability_gate_is_load_bearing(monkeypatch) -> None:
    _guard_unsupported_facet_is_not_substituted()

    monkeypatch.setattr(descriptors, "_compare", lambda descriptor, demand: None)
    assert_control_is_load_bearing(_guard_unsupported_facet_is_not_substituted)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_revision", "llama.3.70b:r8"),
        ("runtime_revision", "vllm:0.9.2"),
        ("quantization", "int4"),
    ],
)
def test_a_changed_descriptor_is_a_different_supply_identity(
    field: str, value: str
) -> None:
    original = _body()
    changed = _body()
    changed["profile"][field] = value

    original_id = validate_descriptor(original, validator=_validator())["descriptor_id"]
    changed_id = validate_descriptor(changed, validator=_validator())["descriptor_id"]
    assert original_id != changed_id

    # And it is no longer eligible for the demand that named the original.
    result = match_descriptor(changed, _demand(), validator=_validator())
    assert result["status"] == "incompatible"

    # Matching never hands back an identity other than the one it derived from
    # the body it was given — no silent substitution.
    compatible = match_descriptor(original, _demand(), validator=_validator())
    assert compatible["descriptor_id"] == original_id


# --------------------------------------------------------------------------
# Properties — price never buys eligibility
# --------------------------------------------------------------------------


def _candidate(**changes: object) -> RouteCandidate:
    values: dict[str, object] = {
        "quote_id": "quote-1",
        "quote_version": 1,
        "descriptor_id": "sha256:descriptor",
        "market_class_id": "sha256:market",
        "path": "paid",
        "authority_class": "native_firm",
        "requester_owned_authority": False,
        "total_micros": 1_000,
        "fee_micros": 10,
        "currency": "tiny",
        "fee_schedule_version": "fee-v1",
        "observed_at": 100,
        "expires_at": 500,
        "eligibility_current": True,
        "eligibility_facts": frozenset({"dpa:v3"}),
        "hard_attributes": (("region", "us"),),
        "service_attributes": (("latency_ms", 200),),
    }
    values.update(changes)
    return RouteCandidate(**values)  # type: ignore[arg-type]


def _request(**changes: object) -> RouteRequest:
    values: dict[str, object] = {
        "fulfillment": "paid",
        "settlement_currency": "tiny",
        "canonical_fee_version": "fee-v1",
        "now": 200,
        "price_cap_micros": 10_000,
        "spend_cap_remaining_micros": 10_000,
        "required_eligibility": frozenset({"dpa:v3"}),
        "hard_constraints": (("region", "us"),),
        "objective_version": "obj-v1",
        "service_weights": (("latency_ms", 0),),
        "top_line_reference_micros": None,
    }
    values.update(changes)
    return RouteRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("price", [1, 2, 7, 999, 1_000, 9_999, 10_000])
@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ({"eligibility_facts": frozenset()}, "missing_eligibility:dpa:v3"),
        ({"eligibility_current": False}, "eligibility_revoked"),
        ({"hard_attributes": (("region", "eu"),)}, "hard_constraint:region"),
        ({"expires_at": 150}, "expired"),
        ({"fee_schedule_version": "fee-v0"}, "fee_version_mismatch"),
        ({"currency": "usd"}, "currency_mismatch"),
        ({"authority_class": "indicative"}, "firm_authority_missing"),
    ],
)
def test_no_nominal_price_can_buy_eligibility(
    price: int, mutation: dict[str, object], expected_reason: str
) -> None:
    decision = rank_routes(
        _request(), [_candidate(total_micros=price, **mutation)]
    )

    assert decision.status == "no_route"
    assert decision.selected is None
    assert expected_reason in decision.candidates[0].reason_codes


@pytest.mark.parametrize("price", [1, 500, 10_000])
def test_price_only_orders_already_eligible_candidates(price: int) -> None:
    cheap_but_ineligible = _candidate(
        quote_id="cheap", total_micros=price, hard_attributes=(("region", "eu"),)
    )
    dearer_eligible = _candidate(quote_id="dear", total_micros=9_000)

    decision = rank_routes(_request(), [cheap_but_ineligible, dearer_eligible])

    assert decision.selected is not None
    assert decision.selected.quote_id == "dear"


def test_ranking_never_authorizes_anything() -> None:
    decision = rank_routes(_request(), [_candidate()])

    assert decision.selected is not None
    assert decision.locks_money is False
    assert decision.reserves_capacity is False
    assert decision.authorizes_provider is False
    assert decision.authorizes_execution is False
    assert decision.accepts_delivery is False
    assert decision.settles is False


def test_paid_candidate_without_the_canonical_fee_fails_loud() -> None:
    with pytest.raises(routing.RoutingError, match="canonical fee"):
        rank_routes(_request(), [_candidate(fee_micros=0)])


# --------------------------------------------------------------------------
# Properties — staleness never becomes executability
# --------------------------------------------------------------------------


@pytest.mark.parametrize("now", [500, 1_000, 50_000])
def test_stale_native_ask_is_never_executable(now: int) -> None:
    stale = NativeAsk(
        source_id="ask-1",
        market_class_id="sha256:market",
        price_micros=10,
        observed_at=100,
        valid_until=200,
        owner_principal_root="principal:seller",
        executable=True,
    )

    surface = _surface([], native_asks=[stale], now=now)

    assert surface.native_ask.stale is True
    assert surface.native_ask.executable is False


def test_a_fresh_field_does_not_refresh_a_stale_one() -> None:
    fresh_ask = NativeAsk(
        source_id="ask-1",
        market_class_id="sha256:market",
        price_micros=10,
        observed_at=100,
        valid_until=100_000,
        owner_principal_root="principal:seller",
        executable=True,
    )

    surface = _surface([], native_asks=[fresh_ask], now=150)

    assert surface.native_ask.executable is True
    # No settlements: VWAP stays explicitly null, never zero, never borrowed.
    assert surface.raw_vwap.value_micros is None
    assert surface.raw_vwap.sample_count == 0
    assert surface.composite_index.value_micros is None


@pytest.mark.parametrize("observed_at", [100, 200, 300])
def test_settlements_outside_the_ttl_window_leave_the_index(observed_at: int) -> None:
    observation = _observation(
        price=900, quantity=10, source="obs", observed_at=observed_at
    )

    inside = _surface([observation], now=observed_at + 10, settlement_ttl=3_600)
    outside = _surface([observation], now=observed_at + 4_000, settlement_ttl=3_600)

    assert inside.raw_vwap.value_micros == 900
    assert outside.raw_vwap.value_micros is None


# --------------------------------------------------------------------------
# Money-path conservation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("gross", [1_000, 7, 10**12])
def test_settlement_values_are_exact_integer_micros(gross: int) -> None:
    """The scheduled fee is an exact integer at every scale — no float, no drift."""
    observation = _observation(
        price=gross,
        quantity=1,
        source="exact",
        binding=_binding(gross_micros=gross, delivered_quantity=1),
    )

    assert observation.binding.net_micros + observation.binding.fee_micros == gross
    assert isinstance(observation.unit_price_micros, int)
    assert isinstance(observation.binding.fee_micros, int)
    assert observation.binding.fee_micros == _canonical_fee(gross)


@pytest.mark.parametrize("bad_net", [989, 991, 0])
def test_non_conserving_settlements_fail_loud(bad_net: int) -> None:
    with pytest.raises(PriceSurfaceError, match="settlement_conservation_mismatch"):
        _observation(
            price=100,
            quantity=1,
            source="broken",
            binding=_binding(gross_micros=1_000, net_micros=bad_net, fee_micros=10),
        )


def test_vwap_is_an_integer_and_lies_within_the_observed_price_range() -> None:
    prices = [901, 950, 1_099]
    observations = [
        _observation(
            price=price,
            quantity=10,
            source=f"obs-{index}",
            buyer_root=f"principal:b{index}",
            seller_root=f"principal:s{index}",
            requester_id=f"buyer-{index}",
            host_owner_id=f"seller-{index}",
        )
        for index, price in enumerate(prices)
    ]

    value = _surface(observations).raw_vwap.value_micros

    assert isinstance(value, int)
    assert min(prices) <= value <= max(prices)


# --------------------------------------------------------------------------
# KNOWN LIMITATION — cross-partition cap composition is not a joint solution
# --------------------------------------------------------------------------


def _composed_shares(observations, cap_ppm: int):
    """Reproduce `_raw_vwap_field`'s composition for two identity partitions.

    `observations` are ``(quantity, p1_key, p2_key)`` triples.  Returns each
    partition's per-identity share of the final weight.
    """
    p1_volumes: dict[tuple[str, str], int] = {}
    p2_volumes: dict[tuple[str, str], int] = {}
    for quantity, first, second in observations:
        p1_volumes[(first, first)] = p1_volumes.get((first, first), 0) + quantity
        p2_volumes[(second, second)] = p2_volumes.get((second, second), 0) + quantity
    p1_scales = price_surface._capped_scales(p1_volumes, cap_ppm)
    p2_scales = price_surface._capped_scales(p2_volumes, cap_ppm)

    weights = [
        (
            first,
            second,
            quantity * min(p1_scales[(first, first)], p2_scales[(second, second)]),
        )
        for quantity, first, second in observations
    ]
    total = sum(weight for _, _, weight in weights)
    first_shares: dict[str, Fraction] = {}
    second_shares: dict[str, Fraction] = {}
    for first, second, weight in weights:
        first_shares[first] = first_shares.get(first, Fraction(0)) + weight / total
        second_shares[second] = second_shares.get(second, Fraction(0)) + weight / total
    return first_shares, second_shares


def test_known_limitation_cross_partition_caps_are_not_jointly_solved() -> None:
    """This test PINS a defect, it does not assert correctness.

    Composing per-partition caps through `min()` does not solve them jointly.
    The achievable bound for a partition of ``n`` identities at cap ``c`` is
    ``max(c, 1/n)`` — the water-filling solver's own documented fallback — and
    this composition can exceed it.

    Codex's round-2 counterexample, reproduced exactly.  Partition 1 holds
    ``{A: 1000, B: 9000}``; at a 25% cap that partition is infeasible
    (``2 * 0.25 <= 1``) so both identities should share influence equally,
    bound ``max(25%, 50%) = 50%``.  Partition 2 holds
    ``{a,b,c,d: 250 each, E: 9000}`` with bound ``max(25%, 20%) = 25%``.

    Current behaviour: partition 2's cap binds correctly and partition 1's
    does not — ``A`` reaches 75% against a 50% bound.  Before the re-basing
    change the violation sat in the other partition (``E`` reached 50% against
    a 25% bound), so BOTH forms are wrong here; re-basing moved the violation,
    it did not introduce it.

    A correct fix is a joint fixed point over one shared total (each group
    capped at ``c * T`` of the *final* weight rather than of its own
    partition), which is a real redesign of `capped_pair_weights` and is
    deliberately not attempted here.  This test goes red the moment the
    composition is fixed — that is the intended signal, not a failure.
    """
    observations = [
        (250, "A", "a"),
        (250, "A", "b"),
        (250, "A", "c"),
        (250, "A", "d"),
        (9_000, "B", "E"),
    ]
    first_shares, second_shares = _composed_shares(observations, 250_000)

    first_bound = max(Fraction(250_000, 1_000_000), Fraction(1, 2))
    second_bound = max(Fraction(250_000, 1_000_000), Fraction(1, 5))

    # Partition 2 is respected.
    assert all(share <= second_bound for share in second_shares.values())
    # Partition 1 is NOT — pinned so the defect cannot silently change.
    assert first_shares["A"] == Fraction(3, 4)
    assert first_shares["A"] > first_bound
    assert first_shares["B"] == Fraction(1, 4)


def test_single_identity_partition_does_not_erase_the_other_caps() -> None:
    """The half of the composition that re-basing genuinely fixed.

    When every observation shares one requester, that partition holds a single
    identity and carries no dampening information.  Before re-basing it
    returned a uniformly tiny `1 / total_volume` scale that won every `min()`
    and erased the pair/buyer/seller caps outright, letting a whale print the
    price.  Its scale is now 1 — "not dampened here".
    """
    scales = price_surface._capped_scales({("only", "only"): 12_030}, 250_000)

    assert scales == {("only", "only"): Fraction(1)}

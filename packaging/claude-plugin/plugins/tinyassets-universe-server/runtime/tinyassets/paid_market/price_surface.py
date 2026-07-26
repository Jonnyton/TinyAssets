"""Pure paid-observation joins, reference quotes, and field-fresh surfaces."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Protocol, Sequence

from tinyassets.paid_market.index import PPM, capped_pair_weights
from tinyassets.paid_market.scope import ScopeError, validate_scope_dimensions


class PriceSurfaceError(ValueError):
    """Settlement or price evidence is invalid or incomparable."""


@dataclass(frozen=True)
class SettlementBinding:
    tenant_id: str
    universe_id: str
    settlement_id: str
    accepted_result_id: str
    requester_id: str
    host_owner_id: str
    currency: str
    token: str
    chain: str
    gross_micros: int
    net_micros: int
    fee_micros: int


@dataclass(frozen=True)
class AccountingReceipt:
    binding: SettlementBinding
    transaction_id: str


@dataclass(frozen=True)
class DomainAcceptanceReceipt:
    binding: SettlementBinding
    evidence_digest: str
    accepted: bool
    disputed: bool


@dataclass(frozen=True)
class ChainReceipt:
    binding: SettlementBinding
    receipt_digest: str
    finality_status: str
    reorged: bool


@dataclass(frozen=True)
class PaidObservation:
    binding: SettlementBinding
    accounting_transaction_id: str
    acceptance_evidence_digest: str
    chain_receipt_digest: str
    market_class_id: str
    market_scope_revision: str
    public_scope: bytes
    unit_price_micros: int
    quantity: int
    observed_at: int
    buyer_principal_root: str | None
    seller_principal_root: str | None
    linked_party: bool
    index_eligible: bool

    @property
    def principal_pair(self) -> tuple[str, str] | None:
        if self.buyer_principal_root is None or self.seller_principal_root is None:
            return None
        return tuple(sorted((self.buyer_principal_root, self.seller_principal_root)))


@dataclass(frozen=True)
class ReferenceRequest:
    market_class_id: str
    currency: str
    region: str
    required_components: frozenset[str]
    terms_digest: str


@dataclass(frozen=True)
class ReferenceQuote:
    source_id: str
    market_class_id: str
    currency: str
    total_micros: int
    components: frozenset[str]
    observed_at: int
    valid_until: int
    adequate: bool
    currently_available: bool
    executable: bool
    caveats: tuple[str, ...]
    coverage: str = "unknown"
    missing_components: frozenset[str] = frozenset()


class ReferenceAdapter(Protocol):
    adapter_id: str

    def quote(self, request: ReferenceRequest) -> ReferenceQuote:
        """Return public price evidence; execution is intentionally absent."""


@dataclass(frozen=True)
class ReferenceBatch:
    quotes: tuple[ReferenceQuote, ...]
    failures: tuple[tuple[str, str], ...]
    top_line_reference: ReferenceQuote | None


@dataclass(frozen=True)
class NativeAsk:
    source_id: str
    market_class_id: str
    price_micros: int
    observed_at: int
    valid_until: int
    owner_principal_root: str
    executable: bool


@dataclass(frozen=True)
class PriceField:
    value_micros: int | None
    observed_at: int | None
    valid_until: int | None
    sample_count: int
    owner_count: int
    source_ids: tuple[str, ...]
    coverage: str
    confidence: str
    stale: bool
    executable: bool


@dataclass(frozen=True)
class PriceSurface:
    market_class_id: str
    market_scope_revision: str
    public_scope: bytes
    raw_vwap: PriceField
    native_ask: PriceField
    external_reference: PriceField
    composite_index: PriceField
    composite_clamped: bool
    references: ReferenceBatch


def join_paid_observation(
    accounting: AccountingReceipt,
    acceptance: DomainAcceptanceReceipt,
    chain: ChainReceipt,
    *,
    market_class_id: str,
    market_scope_revision: str,
    public_scope: bytes,
    unit_price_micros: int,
    quantity: int,
    observed_at: int,
    buyer_principal_root: str | None,
    seller_principal_root: str | None,
    linked_party: bool = False,
) -> PaidObservation:
    """Join existing authority receipts without creating settlement truth."""
    if accounting.binding != acceptance.binding or accounting.binding != chain.binding:
        raise PriceSurfaceError("receipt_binding_mismatch")
    binding = accounting.binding
    _validate_binding(binding)
    if not acceptance.accepted or acceptance.disputed:
        raise PriceSurfaceError("domain_not_accepted")
    if chain.finality_status != "final" or chain.reorged:
        raise PriceSurfaceError("chain_not_final")
    for value, label in (
        (accounting.transaction_id, "transaction_id"),
        (acceptance.evidence_digest, "evidence_digest"),
        (chain.receipt_digest, "receipt_digest"),
        (market_class_id, "market_class_id"),
        (market_scope_revision, "market_scope_revision"),
    ):
        if not value:
            raise PriceSurfaceError(f"{label} is required")
    public_scope = _canonical_scope(public_scope)
    _positive_int(unit_price_micros, "unit_price_micros")
    _positive_int(quantity, "quantity")
    _nonnegative_int(observed_at, "observed_at")

    return PaidObservation(
        binding=binding,
        accounting_transaction_id=accounting.transaction_id,
        acceptance_evidence_digest=acceptance.evidence_digest,
        chain_receipt_digest=chain.receipt_digest,
        market_class_id=market_class_id,
        market_scope_revision=market_scope_revision,
        public_scope=public_scope,
        unit_price_micros=unit_price_micros,
        quantity=quantity,
        observed_at=observed_at,
        buyer_principal_root=buyer_principal_root,
        seller_principal_root=seller_principal_root,
        linked_party=linked_party,
        index_eligible=_index_eligible(
            binding,
            buyer_principal_root=buyer_principal_root,
            seller_principal_root=seller_principal_root,
            linked_party=linked_party,
        ),
    )


def _index_eligible(
    binding: SettlementBinding,
    *,
    buyer_principal_root: str | None,
    seller_principal_root: str | None,
    linked_party: bool,
) -> bool:
    """Manipulation control: who may move trusted paid-market price evidence.

    Discovery consumes, never decides, the transaction owner's verified
    identities.  Exclusion here changes index eligibility only — it never
    creates a settlement-fee exemption (see :func:`_require_canonical_fee`).
    """
    same_owner = binding.requester_id == binding.host_owner_id
    known_roots = buyer_principal_root is not None and seller_principal_root is not None
    same_principal = known_roots and buyer_principal_root == seller_principal_root
    return known_roots and not same_owner and not same_principal and not linked_party


def collect_references(
    adapters: Sequence[ReferenceAdapter],
    request: ReferenceRequest,
    *,
    now: int,
) -> ReferenceBatch:
    _validate_reference_request(request)
    quotes: list[ReferenceQuote] = []
    failures: list[tuple[str, str]] = []
    for adapter in adapters:
        adapter_id = getattr(adapter, "adapter_id", "")
        if not isinstance(adapter_id, str) or not adapter_id:
            failures.append(("<unknown>", "adapter_id_missing"))
            continue
        try:
            quote = adapter.quote(request)
        except Exception:
            failures.append((adapter_id, "adapter_failure"))
            continue
        failure = _reference_failure(quote, request)
        if failure is not None:
            failures.append((adapter_id, failure))
            continue
        missing = request.required_components - quote.components
        quotes.append(
            replace(
                quote,
                coverage="complete" if not missing else "partial",
                missing_components=frozenset(missing),
            )
        )

    complete_current = [
        quote
        for quote in quotes
        if quote.coverage == "complete"
        and quote.adequate
        and quote.currently_available
        and quote.observed_at <= now < quote.valid_until
    ]
    top_line = min(
        complete_current,
        key=lambda quote: (quote.total_micros, quote.source_id),
        default=None,
    )
    return ReferenceBatch(tuple(quotes), tuple(failures), top_line)


def aggregate_price_surface(
    *,
    market_class_id: str,
    market_scope_revision: str,
    public_scope: bytes,
    now: int,
    observations: Sequence[PaidObservation],
    native_asks: Sequence[NativeAsk],
    references: ReferenceBatch,
    min_samples: int,
    settlement_ttl: int,
    principal_share_cap_ppm: int = 250_000,
) -> PriceSurface:
    if not market_class_id or not market_scope_revision:
        raise PriceSurfaceError("market_class_id and market_scope_revision are required")
    public_scope = _canonical_scope(public_scope)
    _positive_int(min_samples, "min_samples")
    _positive_int(settlement_ttl, "settlement_ttl")
    if not (0 < principal_share_cap_ppm <= PPM):
        raise PriceSurfaceError("principal_share_cap_ppm is invalid")

    current = [
        observation
        for observation in observations
        if observation.market_class_id == market_class_id
        and observation.market_scope_revision == market_scope_revision
        and observation.public_scope == public_scope
        and observation.index_eligible
        and observation.seller_principal_root is not None
        and observation.observed_at <= now
        and observation.observed_at + settlement_ttl > now
    ]
    raw = _raw_vwap_field(
        current,
        min_samples=min_samples,
        settlement_ttl=settlement_ttl,
        principal_share_cap_ppm=principal_share_cap_ppm,
    )
    native = _native_ask_field(native_asks, market_class_id=market_class_id, now=now)
    external = _external_field(references, now=now)
    composite, clamped = _composite_field(raw, references.top_line_reference)
    return PriceSurface(
        market_class_id=market_class_id,
        market_scope_revision=market_scope_revision,
        public_scope=public_scope,
        raw_vwap=raw,
        native_ask=native,
        external_reference=external,
        composite_index=composite,
        composite_clamped=clamped,
        references=references,
    )


def _canonical_scope(public_scope: object) -> bytes:
    """Scope authority is canonical object bytes, never an ordered tuple."""
    try:
        return validate_scope_dimensions(public_scope)
    except ScopeError as exc:
        raise PriceSurfaceError("public_scope_not_canonical") from exc


def _validate_binding(binding: SettlementBinding) -> None:
    for name in (
        "tenant_id",
        "universe_id",
        "settlement_id",
        "accepted_result_id",
        "requester_id",
        "host_owner_id",
        "currency",
        "token",
        "chain",
    ):
        if not getattr(binding, name):
            raise PriceSurfaceError(f"{name} is required")
    _positive_int(binding.gross_micros, "gross_micros")
    _nonnegative_int(binding.net_micros, "net_micros")
    _nonnegative_int(binding.fee_micros, "fee_micros")
    if binding.net_micros + binding.fee_micros != binding.gross_micros:
        raise PriceSurfaceError("settlement_conservation_mismatch")
    _require_canonical_fee(binding)


def _require_canonical_fee(binding: SettlementBinding) -> None:
    """Every positive-gross settlement retains the canonical fee.

    Same-owner, linked-party, connected, and external supply never create a
    fee exemption; only index eligibility differs.
    """
    if binding.fee_micros <= 0:
        raise PriceSurfaceError("canonical_fee_required")


def _validate_reference_request(request: ReferenceRequest) -> None:
    if (
        not request.market_class_id
        or not request.currency
        or not request.region
        or not request.terms_digest
        or not request.required_components
        or any(not component for component in request.required_components)
    ):
        raise PriceSurfaceError("invalid_reference_request")


def _reference_failure(
    quote: ReferenceQuote, request: ReferenceRequest
) -> str | None:
    if quote.market_class_id != request.market_class_id:
        return "market_class_mismatch"
    if quote.currency != request.currency:
        return "currency_mismatch"
    if quote.executable:
        return "executable_reference_forbidden"
    if (
        not isinstance(quote.total_micros, int)
        or isinstance(quote.total_micros, bool)
        or quote.total_micros <= 0
    ):
        return "invalid_reference_total"
    if (
        not quote.source_id
        or quote.observed_at < 0
        or quote.valid_until <= quote.observed_at
        or any(not component for component in quote.components)
    ):
        return "malformed_reference"
    return None


def _raw_vwap_field(
    observations: Sequence[PaidObservation],
    *,
    min_samples: int,
    settlement_ttl: int,
    principal_share_cap_ppm: int,
) -> PriceField:
    if len(observations) < min_samples:
        return _empty_field()
    pair_volumes: dict[tuple[str, str], int] = {}
    buyer_volumes: dict[tuple[str, str], int] = {}
    seller_volumes: dict[tuple[str, str], int] = {}
    for observation in observations:
        pair = observation.principal_pair
        buyer = observation.buyer_principal_root
        seller = observation.seller_principal_root
        assert pair is not None and buyer is not None and seller is not None
        pair_volumes[pair] = pair_volumes.get(pair, 0) + observation.quantity
        buyer_key = (buyer, buyer)
        seller_key = (seller, seller)
        buyer_volumes[buyer_key] = (
            buyer_volumes.get(buyer_key, 0) + observation.quantity
        )
        seller_volumes[seller_key] = (
            seller_volumes.get(seller_key, 0) + observation.quantity
        )
    pair_scales = _capped_scales(pair_volumes, principal_share_cap_ppm)
    buyer_scales = _capped_scales(buyer_volumes, principal_share_cap_ppm)
    seller_scales = _capped_scales(seller_volumes, principal_share_cap_ppm)
    numerator = Fraction(0)
    denominator = Fraction(0)
    for observation in observations:
        pair = observation.principal_pair
        buyer = observation.buyer_principal_root
        seller = observation.seller_principal_root
        assert pair is not None and buyer is not None and seller is not None
        # The strongest applicable dampening wins. Structurally infeasible
        # overlaps retain capped_pair_weights' volume-invariant equal weighting.
        weight = observation.quantity * min(
            pair_scales[pair],
            buyer_scales[(buyer, buyer)],
            seller_scales[(seller, seller)],
        )
        numerator += observation.unit_price_micros * weight
        denominator += weight
    value = int(numerator / denominator)
    latest = max(observation.observed_at for observation in observations)
    owner_count = min(len(buyer_volumes), len(seller_volumes))
    return PriceField(
        value_micros=value,
        observed_at=latest,
        valid_until=latest + settlement_ttl,
        sample_count=len(observations),
        owner_count=owner_count,
        source_ids=tuple(
            sorted(observation.binding.settlement_id for observation in observations)
        ),
        coverage="complete",
        confidence="normal" if owner_count >= 3 else "low",
        stale=False,
        executable=False,
    )


def _capped_scales(
    volumes: dict[tuple[str, str], int], principal_share_cap_ppm: int
) -> dict[tuple[str, str], Fraction]:
    weights = capped_pair_weights(volumes, principal_share_cap_ppm)
    return {key: weight / volumes[key] for key, weight in weights.items()}


def _native_ask_field(
    asks: Sequence[NativeAsk], *, market_class_id: str, now: int
) -> PriceField:
    matching: list[NativeAsk] = []
    for ask in asks:
        if ask.market_class_id != market_class_id:
            continue
        _positive_int(ask.price_micros, "native ask price")
        if (
            not ask.source_id
            or not ask.owner_principal_root
            or ask.valid_until <= ask.observed_at
            or ask.observed_at > now
        ):
            raise PriceSurfaceError("malformed_native_ask")
        matching.append(ask)
    fresh = [ask for ask in matching if ask.executable and now < ask.valid_until]
    candidates = fresh or matching
    if not candidates:
        return _empty_field(executable=True)
    best = min(candidates, key=lambda ask: (ask.price_micros, ask.source_id))
    return PriceField(
        value_micros=best.price_micros,
        observed_at=best.observed_at,
        valid_until=best.valid_until,
        sample_count=len(candidates),
        owner_count=len({ask.owner_principal_root for ask in candidates}),
        source_ids=tuple(sorted(ask.source_id for ask in candidates)),
        coverage="complete",
        confidence="normal" if len(candidates) >= 3 else "low",
        stale=now >= best.valid_until,
        executable=best.executable and now < best.valid_until,
    )


def _external_field(references: ReferenceBatch, *, now: int) -> PriceField:
    if not references.quotes:
        return _empty_field()
    fresh = [
        quote
        for quote in references.quotes
        if quote.observed_at <= now < quote.valid_until
    ]
    candidates = fresh or list(references.quotes)
    best = min(candidates, key=lambda quote: (quote.total_micros, quote.source_id))
    return PriceField(
        value_micros=best.total_micros,
        observed_at=best.observed_at,
        valid_until=best.valid_until,
        sample_count=len(candidates),
        owner_count=len({quote.source_id for quote in candidates}),
        source_ids=tuple(sorted(quote.source_id for quote in candidates)),
        coverage=best.coverage,
        confidence="reference",
        stale=now >= best.valid_until,
        executable=False,
    )


def _composite_field(
    raw: PriceField, ceiling: ReferenceQuote | None
) -> tuple[PriceField, bool]:
    if raw.value_micros is None:
        return _empty_field(), False
    if ceiling is None or ceiling.total_micros >= raw.value_micros:
        return raw, False
    assert raw.observed_at is not None
    assert raw.valid_until is not None
    return (
        replace(
            raw,
            value_micros=ceiling.total_micros,
            observed_at=max(raw.observed_at, ceiling.observed_at),
            valid_until=min(raw.valid_until, ceiling.valid_until),
            source_ids=tuple(sorted((*raw.source_ids, ceiling.source_id))),
            executable=False,
        ),
        True,
    )


def _empty_field(*, executable: bool = False) -> PriceField:
    return PriceField(
        value_micros=None,
        observed_at=None,
        valid_until=None,
        sample_count=0,
        owner_count=0,
        source_ids=(),
        coverage="missing",
        confidence="insufficient",
        stale=False,
        executable=executable,
    )


def _positive_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PriceSurfaceError(f"{name} must be a positive integer")


def _nonnegative_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PriceSurfaceError(f"{name} must be a non-negative integer")

"""Pure paid-observation joins, reference quotes, and field-fresh surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Protocol, Sequence

from tinyassets.paid_market.fee_schedule import FeeScheduleError, scheduled_fee_micros
from tinyassets.paid_market.index import PPM
from tinyassets.paid_market.quotes import ValidatedQuote
from tinyassets.paid_market.scope import ScopeError, validate_scope_dimensions

# The only signing domain whose bytes can stand behind a public observation.
_QUOTE_V2_DOMAIN = "tinyassets.paid-market.quote.v2"


class PriceSurfaceError(ValueError):
    """Settlement or price evidence is invalid or incomparable."""


@dataclass(frozen=True)
class SettlementBinding:
    """What all three settlement authorities must already agree on.

    Everything a price observation is allowed to assert about *money* and
    *parties* lives here, so no caller can supply it after the receipts agree.
    Unknown linkage is the fail-closed default: a settlement with no attested
    principal roots is never index-eligible.
    """

    tenant_id: str
    universe_id: str
    settlement_id: str
    accepted_result_id: str
    requester_id: str
    host_owner_id: str
    descriptor_id: str
    currency: str
    token: str
    chain: str
    gross_micros: int
    net_micros: int
    fee_micros: int
    fee_schedule_version: str
    # Delivery evidence, not a caller declaration: bounding `price * quantity`
    # against the gross does not bound the price unless the quantity is also
    # authoritative — otherwise one settled gross can be re-declared as any
    # (price, quantity) pair whose product matches.
    delivered_quantity: int = 0
    buyer_principal_root: str | None = None
    seller_principal_root: str | None = None
    linked_party: bool = False


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
    quote_id: str
    descriptor_id: str
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
    # Compatible supply headroom shares one demand class, and the aggregate
    # still retains each source's exact descriptor id as evidence.
    observation_descriptor_ids: tuple[str, ...]
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
    quote: ValidatedQuote,
    unit_price_micros: int,
    observed_at: int,
) -> PaidObservation:
    """Join existing authority receipts without creating settlement truth.

    Nothing price-bearing is accepted from the caller.  *Identity and scope*
    are derived from the signed v2 quote that the settlement already bound;
    *money, delivered quantity, and parties* come from the binding the three
    receipts agree on.  The declared unit price is the only surviving caller
    value, and it is admitted only when it exactly reconstructs the settled
    gross over the delivered quantity — both of which are settlement evidence,
    so the price is fully determined rather than merely constrained.
    """
    if accounting.binding != acceptance.binding or accounting.binding != chain.binding:
        raise PriceSurfaceError("receipt_binding_mismatch")
    binding = accounting.binding
    _validate_binding(binding)
    if not acceptance.accepted or acceptance.disputed:
        raise PriceSurfaceError("domain_not_accepted")
    if chain.finality_status != "final" or chain.reorged:
        raise PriceSurfaceError("chain_not_final")
    public_scope = _require_quote_binding(binding, quote)
    for value, label in (
        (accounting.transaction_id, "transaction_id"),
        (acceptance.evidence_digest, "evidence_digest"),
        (chain.receipt_digest, "receipt_digest"),
        (quote.quote_id, "quote_id"),
        (quote.market_class_id, "market_class_id"),
        (quote.market_scope_revision, "market_scope_revision"),
    ):
        if not value:
            raise PriceSurfaceError(f"{label} is required")
    quantity = binding.delivered_quantity
    _require_settlement_derived_price(binding, unit_price_micros)
    _nonnegative_int(observed_at, "observed_at")

    return PaidObservation(
        binding=binding,
        accounting_transaction_id=accounting.transaction_id,
        acceptance_evidence_digest=acceptance.evidence_digest,
        chain_receipt_digest=chain.receipt_digest,
        quote_id=quote.quote_id,
        descriptor_id=binding.descriptor_id,
        market_class_id=quote.market_class_id,
        market_scope_revision=str(quote.market_scope_revision),
        public_scope=public_scope,
        unit_price_micros=unit_price_micros,
        quantity=quantity,
        observed_at=observed_at,
        buyer_principal_root=binding.buyer_principal_root,
        seller_principal_root=binding.seller_principal_root,
        linked_party=binding.linked_party,
        index_eligible=_index_eligible(binding),
    )


def _require_quote_binding(
    binding: SettlementBinding, quote: ValidatedQuote
) -> bytes:
    """Manipulation control: the observation inherits one signed identity.

    A validated quote signs its exact descriptor, market class, scope revision,
    and scope dimensions under the v2 domain.  Requiring the settlement to
    match means an aggregator cannot pick a different class or scope bucket
    after seeing the price, and a v1 quote — whose signature never spanned a
    scope binding — can never stand behind a public observation.

    ``ValidatedQuote`` is an ordinary public dataclass, so *holding* one proves
    nothing: its attributes can be constructed or replaced while keeping the
    ``canonical_bytes`` of a genuinely signed quote.  The signed bytes are the
    authority and the attributes are only a view of them, so every identity
    field is re-read out of ``canonical_bytes`` here.
    """
    if (
        quote.schema_version != 2
        or quote.market_scope_revision is None
        or quote.public_scope_dimensions is None
    ):
        raise PriceSurfaceError("quote_scope_unsigned")
    public_scope = _canonical_scope(quote.public_scope_dimensions)
    _require_attributes_match_signed_bytes(quote, public_scope)
    if quote.descriptor_id != binding.descriptor_id:
        raise PriceSurfaceError("descriptor_binding_mismatch")
    if quote.settlement_currency != binding.currency:
        raise PriceSurfaceError("currency_binding_mismatch")
    if quote.fee_schedule_version != binding.fee_schedule_version:
        raise PriceSurfaceError("fee_version_binding_mismatch")
    return public_scope


def _require_attributes_match_signed_bytes(
    quote: ValidatedQuote, public_scope: bytes
) -> None:
    """Re-read every identity field from the bytes the issuer actually signed."""
    try:
        signed = json.loads(bytes(quote.canonical_bytes).decode("ascii"))
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise PriceSurfaceError("quote_bytes_unreadable") from exc
    if not isinstance(signed, dict):
        raise PriceSurfaceError("quote_bytes_unreadable")
    if signed.get("domain") != _QUOTE_V2_DOMAIN or signed.get("schema_version") != 2:
        raise PriceSurfaceError("quote_scope_unsigned")
    expected = (
        ("quote_id", quote.quote_id),
        ("descriptor_id", quote.descriptor_id),
        ("market_class_id", quote.market_class_id),
        ("market_scope_revision", quote.market_scope_revision),
        ("settlement_currency", quote.settlement_currency),
        ("fee_schedule_version", quote.fee_schedule_version),
        ("public_scope_dimensions", public_scope.decode("ascii")),
    )
    for name, attribute in expected:
        if signed.get(name) != attribute:
            raise PriceSurfaceError("quote_attributes_not_signed")


def _require_settlement_derived_price(
    binding: SettlementBinding, unit_price_micros: object
) -> None:
    """Manipulation control: the price is authoritative money, not a claim.

    A positive fixed weight times an unbounded caller-provided price is still
    unbounded, so the price is bounded here rather than downstream.  Both
    factors are settlement evidence — the gross the three authorities settled
    and the quantity they attested delivered — so the unit price is fully
    determined, not merely constrained: bounding the *product* alone would let
    one settled gross be re-declared as any (price, quantity) pair whose
    product matches.  Publishing a 10^18-micro print therefore costs
    10^18 * delivered_quantity micros of real money plus its canonical fee,
    and a gross that does not divide exactly by the delivered quantity fails
    loud instead of rounding into the index.  Integer micros only.
    """
    _positive_int(unit_price_micros, "unit_price_micros")
    if unit_price_micros * binding.delivered_quantity != binding.gross_micros:  # type: ignore[operator]
        raise PriceSurfaceError("unit_price_not_settlement_derived")


def _index_eligible(binding: SettlementBinding) -> bool:
    """Manipulation control: who may move trusted paid-market price evidence.

    Discovery consumes, never decides, the transaction owner's verified
    identities — all of which are settlement authority, so a caller cannot
    claim unrelated roots to escape these exclusions.  Exclusion here changes
    index eligibility only; it never creates a settlement-fee exemption (see
    :func:`_require_canonical_fee`).

    Unknown never reads as benign: an absent *or empty* root is unknown
    linkage, which is not eligible.  ``linked_party`` is validated as a real
    bool in :func:`_validate_binding`, so ``None`` can never arrive here
    meaning "not linked".
    """
    buyer_principal_root = binding.buyer_principal_root
    seller_principal_root = binding.seller_principal_root
    same_owner = binding.requester_id == binding.host_owner_id
    known_roots = bool(buyer_principal_root) and bool(seller_principal_root)
    same_principal = known_roots and buyer_principal_root == seller_principal_root
    return (
        known_roots
        and not same_owner
        and not same_principal
        and not binding.linked_party
    )


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
    if (
        not isinstance(principal_share_cap_ppm, int)
        or isinstance(principal_share_cap_ppm, bool)  # `True == 1` is not a 1-ppm cap
        or not (0 < principal_share_cap_ppm <= PPM)
    ):
        raise PriceSurfaceError("principal_share_cap_ppm is invalid")
    _require_unique_settlements(observations)

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
        observation_descriptor_ids=tuple(
            sorted({observation.descriptor_id for observation in current})
        ),
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
        "fee_schedule_version",
    ):
        if not getattr(binding, name):
            raise PriceSurfaceError(f"{name} is required")
    _positive_int(binding.gross_micros, "gross_micros")
    _nonnegative_int(binding.net_micros, "net_micros")
    _nonnegative_int(binding.fee_micros, "fee_micros")
    _positive_int(binding.delivered_quantity, "delivered_quantity")
    # `None` is not "unlinked" and `0`/`1`/`"false"` are not booleans: an
    # unstated relationship must fail closed, never default to arm's length.
    if not isinstance(binding.linked_party, bool):
        raise PriceSurfaceError("linked_party must be an explicit boolean")
    for root, name in (
        (binding.buyer_principal_root, "buyer_principal_root"),
        (binding.seller_principal_root, "seller_principal_root"),
    ):
        if root is not None and (not isinstance(root, str) or not root):
            raise PriceSurfaceError(f"{name} must be non-empty text or None")
    if binding.net_micros + binding.fee_micros != binding.gross_micros:
        raise PriceSurfaceError("settlement_conservation_mismatch")
    _require_canonical_fee(binding)


def _require_canonical_fee(binding: SettlementBinding) -> None:
    """Every positive-gross settlement retains the canonical fee.

    Same-owner, linked-party, connected, and external supply never create a
    fee exemption; only index eligibility differs.

    Positivity is not canonicality: the fee must equal the amount the
    settlement's *bound schedule version* derives from its gross, so a
    1-micro fee on a 1,000,000-micro gross is refused even though it conserves.
    """
    if binding.fee_micros <= 0:
        raise PriceSurfaceError("canonical_fee_required")
    if not _fee_matches_schedule(binding):
        raise PriceSurfaceError("canonical_fee_mismatch")


def _fee_matches_schedule(binding: SettlementBinding) -> bool:
    """Manipulation control: the fee is the *bound version's* derived amount."""
    try:
        expected = scheduled_fee_micros(
            binding.gross_micros, fee_schedule_version=binding.fee_schedule_version
        )
    except FeeScheduleError as exc:
        raise PriceSurfaceError("unknown_fee_schedule_version") from exc
    return binding.fee_micros == expected


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
    quantities: list[int] = []
    pairs: list[tuple[str, str]] = []
    buyers: list[str] = []
    sellers: list[str] = []
    requesters: list[str] = []
    hosts: list[str] = []
    for observation in observations:
        pair = observation.principal_pair
        buyer = observation.buyer_principal_root
        seller = observation.seller_principal_root
        assert pair is not None and buyer is not None and seller is not None
        quantities.append(observation.quantity)
        pairs.append(pair)
        buyers.append(buyer)
        sellers.append(seller)
        requesters.append(observation.binding.requester_id)
        hosts.append(observation.binding.host_owner_id)
    weights = _joint_capped_weights(
        quantities,
        (pairs, buyers, sellers, requesters, hosts),
        principal_share_cap_ppm,
    )
    numerator = Fraction(0)
    denominator = Fraction(0)
    for observation, weight in zip(observations, weights, strict=True):
        numerator += observation.unit_price_micros * weight
        denominator += weight
    value = int(numerator / denominator)
    latest = max(observation.observed_at for observation in observations)
    owner_count = min(len(set(buyers)), len(set(sellers)))
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


def _joint_capped_weights(
    quantities: Sequence[int],
    partitions: Sequence[Sequence[object]],
    principal_share_cap_ppm: int,
) -> tuple[Fraction, ...]:
    """Maximize retained settlement weight under every identity cap jointly.

    Every group constraint is expressed against the same final weight total.
    A partition with too few groups for the configured cap uses the existing
    volume-invariant fallback ``1 / n``.  If overlapping partitions make those
    bounds mutually inconsistent, no observation is silently discarded: the
    aggregate fails closed.
    """
    if not quantities:
        return ()
    if any(
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
        for quantity in quantities
    ):
        raise PriceSurfaceError("joint influence quantities must be positive integers")
    if any(len(partition) != len(quantities) for partition in partitions):
        raise PriceSurfaceError("joint influence partitions must align")

    count = len(quantities)
    total_index = count
    variable_count = count + 1
    constraints: list[list[Fraction]] = []
    limits: list[Fraction] = []

    def add_constraint(coefficients: dict[int, Fraction], limit: Fraction) -> None:
        row = [Fraction(0) for _ in range(variable_count)]
        for index, coefficient in coefficients.items():
            row[index] = coefficient
        constraints.append(row)
        limits.append(limit)

    # T == sum(weights), represented as two <= constraints.
    add_constraint(
        {**{index: Fraction(1) for index in range(count)}, total_index: Fraction(-1)},
        Fraction(0),
    )
    add_constraint(
        {**{index: Fraction(-1) for index in range(count)}, total_index: Fraction(1)},
        Fraction(0),
    )

    cap = Fraction(principal_share_cap_ppm, PPM)
    for partition in partitions:
        groups: dict[object, list[int]] = {}
        for index, identity in enumerate(partition):
            groups.setdefault(identity, []).append(index)
        if len(groups) <= 1:
            continue
        bound = max(cap, Fraction(1, len(groups)))
        for members in groups.values():
            coefficients = {index: Fraction(1) for index in members}
            coefficients[total_index] = -bound
            add_constraint(coefficients, Fraction(0))

    for index, quantity in enumerate(quantities):
        add_constraint({index: Fraction(1)}, Fraction(quantity))

    objective = [Fraction(1) for _ in range(count)] + [Fraction(0)]
    solution = _simplex_maximize(constraints, limits, objective)
    weights = tuple(solution[:count])
    total = sum(weights, Fraction(0))
    if total <= 0:
        raise PriceSurfaceError("joint_influence_cap_infeasible")

    for partition in partitions:
        groups: dict[object, Fraction] = {}
        for identity, weight in zip(partition, weights, strict=True):
            groups[identity] = groups.get(identity, Fraction(0)) + weight
        bound = max(cap, Fraction(1, len(groups)))
        if any(group_weight > bound * total for group_weight in groups.values()):
            raise PriceSurfaceError("joint_influence_cap_infeasible")
    return weights


def _simplex_maximize(
    constraints: Sequence[Sequence[Fraction]],
    limits: Sequence[Fraction],
    objective: Sequence[Fraction],
) -> list[Fraction]:
    """Exact Bland-rule simplex for ``A*x <= b, x >= 0`` with ``b >= 0``."""
    row_count = len(constraints)
    variable_count = len(objective)
    width = variable_count + row_count + 1
    tableau: list[list[Fraction]] = []
    basis: list[int] = []
    for row_index, (constraint, limit) in enumerate(
        zip(constraints, limits, strict=True)
    ):
        if limit < 0:
            raise PriceSurfaceError("joint influence solver received a negative limit")
        row = [Fraction(value) for value in constraint]
        row.extend(
            Fraction(1 if index == row_index else 0)
            for index in range(row_count)
        )
        row.append(Fraction(limit))
        tableau.append(row)
        basis.append(variable_count + row_index)
    tableau.append(
        [-Fraction(value) for value in objective]
        + [Fraction(0) for _ in range(row_count + 1)]
    )

    objective_row = row_count
    pivot_limit = max(1_000, row_count * width * 4)
    for _ in range(pivot_limit):
        entering = next(
            (
                column
                for column in range(width - 1)
                if tableau[objective_row][column] < 0
            ),
            None,
        )
        if entering is None:
            solution = [Fraction(0) for _ in range(variable_count)]
            for row_index, basic_variable in enumerate(basis):
                if basic_variable < variable_count:
                    solution[basic_variable] = tableau[row_index][-1]
            return solution

        candidates = [
            (
                tableau[row_index][-1] / tableau[row_index][entering],
                basis[row_index],
                row_index,
            )
            for row_index in range(row_count)
            if tableau[row_index][entering] > 0
        ]
        if not candidates:
            raise PriceSurfaceError("joint_influence_cap_unbounded")
        _, _, leaving = min(candidates)
        pivot = tableau[leaving][entering]
        tableau[leaving] = [value / pivot for value in tableau[leaving]]
        for row_index in range(row_count + 1):
            if row_index == leaving:
                continue
            factor = tableau[row_index][entering]
            if factor:
                tableau[row_index] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(
                        tableau[row_index], tableau[leaving], strict=True
                    )
                ]
        basis[leaving] = entering
    raise PriceSurfaceError("joint_influence_cap_solver_limit")


def _require_unique_settlements(observations: Sequence[PaidObservation]) -> None:
    """Manipulation control: one settlement is one observation, forever.

    Volume aggregates by settlement identity, never per call, so replaying the
    same settled trade into the window cannot multiply its weight.
    """
    seen: set[str] = set()
    for observation in observations:
        settlement_id = observation.binding.settlement_id
        if settlement_id in seen:
            raise PriceSurfaceError("duplicate_settlement_observation")
        seen.add(settlement_id)


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

"""Pure, advisory model ordering; never an inference grant or dispatch path.

Discovery adapters normalize evidence before entering here. Admission MUST refresh
authority, privacy, capabilities and pricing before every actual attempt. A saved
choice or an advisory candidate cannot authorize inference. No vendor names,
model-release list, credentials, storage, clock or network belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Freshness = Literal["fresh", "stale", "missing"]
SourceKind = Literal["subscription", "local", "http"]


@dataclass(frozen=True, slots=True)
class ModelRef:
    connection_id: str
    model_id: str  # Opaque; empty may represent the connection's native default.


@dataclass(frozen=True, slots=True)
class Charge:
    component: str  # Includes the unit, e.g. input_million_tokens_usd.
    amount_micros: int
    confirmed: bool = False

    def __post_init__(self) -> None:
        if type(self.amount_micros) is not int or self.amount_micros < 0:
            raise ValueError("charge must be an exact nonnegative integer")


@dataclass(frozen=True, slots=True)
class Pricing:
    freshness: Freshness = "missing"
    charges: tuple[Charge, ...] = ()
    unmetered: bool = False  # Confirmed non-metered inference, not unknown cost.

    def __post_init__(self) -> None:
        if len({charge.component for charge in self.charges}) != len(self.charges):
            raise ValueError("duplicate charge component")
        if self.unmetered and self.charges:
            raise ValueError("unmetered pricing cannot also declare metered charges")


@dataclass(frozen=True, slots=True)
class Scores:
    source: str
    freshness: Freshness
    agentic: int | None = None
    general: int | None = None

    def __post_init__(self) -> None:
        for score in (self.agentic, self.general):
            if score is not None and type(score) is not int:
                raise ValueError("score must be an exact integer or unknown")


@dataclass(frozen=True, slots=True)
class Model:
    model_id: str
    tools: bool | None
    modalities: frozenset[str]
    context_tokens: int | None = None
    pricing: Pricing = Pricing()
    scores: Scores | None = None


@dataclass(frozen=True, slots=True)
class ConnectionModels:
    connection_id: str
    provider_scope: str  # Trusted adapter scope, not remote model metadata.
    source_kind: SourceKind
    freshness: Freshness
    owner_filtered: bool
    executor_tools: bool
    models: tuple[Model, ...]
    default_model_id: str | None = None
    authenticated_account_id: str | None = None


@dataclass(frozen=True, slots=True)
class Catalog:
    owner_id: str
    universe_id: str
    connections: tuple[ConnectionModels, ...]


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    generation: int
    # Behaviour when neither current nor saved primary is present. A primary
    # always wins; clearing it is an explicit caller action, not a mode side effect.
    mode: Literal["automatic", "explicit"]
    fallbacks: tuple[ModelRef, ...]  # Required: an empty tuple is meaningful.
    current_selection: ModelRef | None = None
    saved_default: ModelRef | None = None
    ranking_source: str | None = None
    stable_preference: ModelRef | None = None
    # None is free-only. A cap must name every required charge component.
    cost_caps: tuple[Charge, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid policy generation")
        if self.mode not in ("automatic", "explicit"):
            raise ValueError("invalid selection mode")
        if self.cost_caps is not None:
            _charges(self.cost_caps)
        if (
            self.mode == "automatic"
            and self.current_selection is None
            and self.saved_default is None
            and self.fallbacks
        ):
            raise ValueError("accepted fallbacks require an explicit primary or explicit mode")


@dataclass(frozen=True, slots=True)
class Interaction:
    needs_tools: bool
    modalities: frozenset[str]
    charge_components: frozenset[str]
    min_context: int | None = None


@dataclass(frozen=True, slots=True)
class Exhaustion:
    scope: Literal["model", "account"]
    ref: ModelRef

    def __post_init__(self) -> None:
        if self.scope not in ("model", "account"):
            raise ValueError("invalid exhaustion scope")


@dataclass(frozen=True, slots=True)
class Candidate:
    ref: ModelRef
    basis: str
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Ineligible:
    ref: ModelRef
    reason: str
    component: str = ""


@dataclass(frozen=True, slots=True)
class AdvisoryOrder:
    generation: int
    candidates: tuple[Candidate, ...]
    ineligible: tuple[Ineligible, ...]
    kind: Literal["advisory_order"] = "advisory_order"


def _charges(charges: tuple[Charge, ...]) -> dict[str, Charge]:
    result = {charge.component: charge for charge in charges}
    if len(result) != len(charges):
        raise ValueError("duplicate charge component")
    return result


def _capacity_identity(connection: ConnectionModels) -> tuple[str, str, str]:
    if connection.authenticated_account_id:
        return (connection.provider_scope, "account", connection.authenticated_account_id)
    return (connection.provider_scope, "connection", connection.connection_id)


def _ineligibility(
    connection: ConnectionModels,
    model: Model,
    policy: ModelPolicy,
    interaction: Interaction,
    *,
    explicit: bool,
) -> tuple[str, str] | None:
    if not connection.owner_filtered:
        return "privacy_unverified", ""
    if interaction.needs_tools and not connection.executor_tools:
        return "executor_unsupported", ""
    if interaction.needs_tools and model.tools is not True:
        return ("capability_unknown" if model.tools is None else "capability_unsupported"), ""
    if not interaction.modalities <= model.modalities:
        return "capability_unsupported", ""
    if interaction.min_context is not None:
        if model.context_tokens is None:
            return "capability_unknown", ""
        if model.context_tokens < interaction.min_context:
            return "capability_unsupported", ""
    if not explicit and connection.freshness != "fresh":
        return "stale_capability", ""
    pricing = model.pricing
    if not explicit and pricing.freshness != "fresh":
        return "stale_price", ""
    if pricing.unmetered:
        return None
    if not interaction.charge_components:
        return "missing_price_component", "required_charge_components"
    charges = _charges(pricing.charges)
    caps = None if policy.cost_caps is None else _charges(policy.cost_caps)
    for component in sorted(interaction.charge_components):
        charge = charges.get(component)
        if charge is None or not charge.confirmed:
            return "missing_price_component", component
        if caps is None:
            if charge.amount_micros != 0:
                return "not_confirmed_free", component
        else:
            cap = caps.get(component)
            if cap is None or not cap.confirmed or charge.amount_micros > cap.amount_micros:
                return "exceeds_cost_cap", component
    return None


def order_models(
    catalog: Catalog,
    policy: ModelPolicy,
    interaction: Interaction,
    *,
    owner_id: str,
    universe_id: str,
    exhaustion: tuple[Exhaustion, ...] = (),
) -> AdvisoryOrder:
    """Return a finite advisory order from normalized, explicitly scoped evidence.

    Current choice overrides the saved primary, never the accepted fallback list.
    Unavailable references stay visible in `ineligible`; they do not turn into an
    automatic choice. Explicit stale evidence is labelled for required refresh.
    """
    if (
        not owner_id
        or not universe_id
        or (owner_id, universe_id)
        != (
            catalog.owner_id,
            catalog.universe_id,
        )
    ):
        raise ValueError("catalogue scope mismatch")
    connections = {c.connection_id: c for c in catalog.connections}
    if len(connections) != len(catalog.connections):
        raise ValueError("duplicate connection")
    entries: dict[ModelRef, tuple[ConnectionModels, Model]] = {}
    for connection in catalog.connections:
        if connection.source_kind not in ("subscription", "local", "http"):
            raise ValueError("invalid source kind")
        if not connection.connection_id or not connection.provider_scope:
            raise ValueError("missing connection identity")
        for model in connection.models:
            ref = ModelRef(connection.connection_id, model.model_id)
            if ref in entries:
                raise ValueError("duplicate model reference")
            entries[ref] = (connection, model)

    primary = policy.current_selection or policy.saved_default
    explicit = primary is not None or policy.mode == "explicit"
    rejected: list[Ineligible] = []
    if explicit:
        refs = ([] if primary is None else [primary]) + list(policy.fallbacks)
    else:
        # A subscription/local connection controls its own advertised default.
        # Other models remain visible in the catalogue for explicit selection.
        refs = []
        for connection in catalog.connections:
            if connection.source_kind == "http":
                refs.extend(
                    ModelRef(connection.connection_id, m.model_id) for m in connection.models
                )
            elif connection.default_model_id is None:
                rejected.append(
                    Ineligible(
                        ModelRef(connection.connection_id, ""),
                        "default_unavailable",
                    )
                )
            else:
                refs.append(ModelRef(connection.connection_id, connection.default_model_id))

    exhausted_models: set[tuple[tuple[str, str, str], str]] = set()
    model_failures: list[tuple[ConnectionModels, str]] = []
    exhausted_accounts: list[ConnectionModels] = []
    for failure in exhaustion:
        connection = connections.get(failure.ref.connection_id)
        if connection is None:
            # Unknown old evidence cannot prove any remaining source independent.
            raise ValueError("exhaustion connection absent from catalogue")
        if failure.scope == "account":
            exhausted_accounts.append(connection)
        else:
            exhausted_models.add((_capacity_identity(connection), failure.ref.model_id))
            model_failures.append((connection, failure.ref.model_id))

    eligible: list[Candidate] = []
    seen: set[tuple[tuple[str, str, str], str]] = set()
    for ref in refs:
        entry = entries.get(ref)
        if entry is None:
            rejected.append(Ineligible(ref, "absent_from_catalogue"))
            continue
        connection, model = entry
        identity = (_capacity_identity(connection), model.model_id)
        reason: tuple[str, str] | None = None
        for failed in exhausted_accounts:
            if failed.provider_scope != connection.provider_scope:
                continue
            if _capacity_identity(failed) == _capacity_identity(connection):
                reason = "account_exhausted", ""
            elif not failed.authenticated_account_id or not connection.authenticated_account_id:
                reason = "capacity_identity_unverified", ""
            if reason:
                break
        if reason is None and identity in exhausted_models:
            reason = "model_exhausted", ""
        if reason is None:
            for failed, failed_model in model_failures:
                if (
                    failed.provider_scope == connection.provider_scope
                    and failed_model == model.model_id
                    and (
                        not failed.authenticated_account_id
                        or not connection.authenticated_account_id
                    )
                ):
                    reason = "capacity_identity_unverified", ""
                    break
        if reason is None:
            reason = _ineligibility(connection, model, policy, interaction, explicit=explicit)
        if reason is None and identity in seen:
            reason = "duplicate", ""
        if reason is not None:
            rejected.append(Ineligible(ref, *reason))
            continue
        seen.add(identity)
        labels = tuple(
            label
            for stale, label in (
                (connection.freshness != "fresh", "refresh_capabilities"),
                (model.pricing.freshness != "fresh", "refresh_price"),
            )
            if stale
        )
        eligible.append(Candidate(ref, "explicit" if explicit else "automatic", labels))

    if not explicit:

        def ranking(candidate: Candidate) -> tuple[int, int, int, int, int]:
            connection, model = entries[candidate.ref]
            stable = int(candidate.ref != policy.stable_preference)
            if connection.source_kind in ("subscription", "local"):
                return (0, 0, 0, 0, stable)
            scores = model.scores
            if (
                scores is not None
                and policy.ranking_source is not None
                and scores.source == policy.ranking_source
                and scores.freshness == "fresh"
                and scores.agentic is not None
            ):
                # General score only breaks equal agentic scores. Unknown is not
                # zero (which could itself be a real benchmark score).
                return (
                    1,
                    -scores.agentic,
                    int(scores.general is None),
                    -(scores.general or 0),
                    stable,
                )
            return (2, 0, 0, 0, 0)  # Unranked: preserve discovery's stable order.

        eligible.sort(key=ranking)
    return AdvisoryOrder(policy.generation, tuple(eligible), tuple(rejected))

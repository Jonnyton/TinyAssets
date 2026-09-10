"""Build a conversation plan from current owned bindings, never caller facts.

Discovery happens outside assignment admission and database transactions. The
result is advisory: every actual launch still validates its exact member anew.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from tinyassets.custom_agents import get_binding
from tinyassets.exceptions import ProviderError
from tinyassets.provider_assignment import (
    _served_request_agent,
    load_provider_assignment_in_transaction,
    provider_assignment_admission,
)
from tinyassets.provider_serving_binding import (
    _PROVIDER_SERVICE,
    ServingProviderHeld,
    _current_selected_member_authority,
    _resolve_serving_source,
)
from tinyassets.providers.agent_model_plan import AgentModelPlan
from tinyassets.providers.discovery_snapshot import ModelDiscoveryUnavailable
from tinyassets.providers.model_policy import (
    Catalog,
    Charge,
    ConnectionModels,
    Ineligible,
    Interaction,
    Model,
    ModelPolicy,
    ModelRef,
    Pricing,
    order_models,
)
from tinyassets.providers.model_preferences import ModelPreferences, capture_preference_policy
from tinyassets.storage.current_home import check_current_home
from tinyassets.storage.model_preferences import ModelPreferenceStore
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore


@dataclass(frozen=True, slots=True)
class PreparedPlan:
    plan: AgentModelPlan
    catalog: Catalog  # Unfiltered choices for display, not execution permission.
    ineligible: tuple[Ineligible, ...]
    assignment: object
    chains: tuple
    agent: dict
    preferences: object
    snapshots: tuple
    display_only: bool = False

    def recheck(self, conn, *, store, base, universe, owner, agent, check_preferences=False):
        from tinyassets.providers.discovery_snapshot import assert_discovery_snapshot_current

        if self.display_only:
            raise ValueError("display catalogue cannot authorize activation")
        self.recheck_scope(conn, universe=universe, owner=owner, agent=agent,
                           check_preferences=check_preferences)
        for provider, expected in self.chains:
            actual = _current_selected_member_authority(
                conn, store=store, universe_dir=universe, base_path=base,
                owner_user_id=owner, universe_id=universe.name, agent=agent, provider=provider,
            )
            if actual != expected:
                raise PermissionError("model member changed during discovery")
        for snapshot in self.snapshots:
            assert_discovery_snapshot_current(snapshot)

    def recheck_scope(self, conn, *, universe, owner, agent, check_preferences=False):
        """A changed home/agent/assignment invalidates the entire display too."""
        from tinyassets.storage.model_preferences import _read

        check_current_home(conn, owner, universe.name)
        if agent != self.agent or load_provider_assignment_in_transaction(
            conn, universe_id=universe.name,
        ) != self.assignment:
            raise PermissionError("model assignment changed during discovery")
        if check_preferences and _read(conn, owner, universe.name) != self.preferences:
            raise PermissionError("model preferences changed during activation")
    def recheck_display(self, conn, *, store, base, universe, owner, agent):
        """Demote only failed sources; never let them hide independent choices."""
        from tinyassets.providers.discovery_snapshot import assert_discovery_snapshot_current

        self.recheck_scope(conn, universe=universe, owner=owner, agent=agent,
                           check_preferences=True)
        failed = {}
        for provider, expected in self.chains:
            try:
                actual = _current_selected_member_authority(
                    conn, store=store, universe_dir=universe, base_path=base,
                    owner_user_id=owner, universe_id=universe.name, agent=agent, provider=provider,
                )
                if actual != expected:
                    failed[provider] = "source_revoked"
            except PermissionError:
                failed[provider] = "source_revoked"
        for snapshot in self.snapshots:
            try:
                assert_discovery_snapshot_current(snapshot)
            except ModelDiscoveryUnavailable as exc:
                failed[snapshot.provider] = exc.reason
            except ProviderError:
                failed[snapshot.provider] = "discovery_unavailable"
        if not failed:
            return self

        def retained(catalog):
            return replace(catalog, connections=tuple(
                item for item in catalog.connections if item.connection_id not in failed
            ))

        return replace(
            self, catalog=retained(self.catalog),
            plan=replace(self.plan, catalog=retained(self.plan.catalog)),
            ineligible=self.ineligible + tuple(
                Ineligible(ModelRef(provider, ""), reason, scope="source")
                for provider, reason in failed.items()
            ),
            chains=tuple(item for item in self.chains if item[0] not in failed),
            snapshots=tuple(item for item in self.snapshots if item.provider not in failed),
        )


class ModelSourceUnavailable(PermissionError):
    """Non-executable source with a fixed reason, never upstream error prose."""

    def __init__(self, reason):
        if reason not in {
            "executor_unavailable", "protocol_mismatch", "price_components_unenforceable",
            "price_contract_incompatible",
            "model_access_optin_required",
        }:
            raise ValueError("invalid model source reason")
        super().__init__(reason)
        self.reason = reason


def _native_models(base, universe, owner, member):
    from tinyassets.providers.call import get_provider_router
    from tinyassets.providers.model_selection import _native_default

    _resolve_serving_source(base, universe.name, owner, member.provider, member.access)
    _native_default(member.provider, "", member.access)
    router = get_provider_router()
    provider = None if router is None else router._providers.get(member.provider)
    if provider is None or not provider.is_available():
        raise ModelSourceUnavailable("executor_unavailable")
    return ConnectionModels(
        member.provider, "native-subscription:" + member.provider, "subscription", "fresh",
        True, True,
        (Model("", True, frozenset({"text"}), pricing=Pricing("fresh", unmetered=True)),),
        default_model_id="",
    )


def _http_models(owner, uid, member, *, snapshot=None):
    from tinyassets.providers.definition import get_definition
    from tinyassets.providers.discovery_protocols import discovery_protocol
    from tinyassets.providers.discovery_snapshot import refresh_model_discovery

    if not member.provider.startswith("api_key_http:") or member.access.model_scope == "legacy":
        raise ModelSourceUnavailable("model_access_optin_required")
    if snapshot is None:
        snapshot = refresh_model_discovery(
            owner_user_id=owner, universe_id=uid,
            definition_id=member.provider.removeprefix("api_key_http:"),
        )
    contract = discovery_protocol(snapshot.models.provider_scope)
    definition = get_definition(uid, member.provider.removeprefix("api_key_http:"))
    if (definition is None or definition.owner_user_id != owner
            or definition.protocol != contract.inference_protocol):
        raise ModelSourceUnavailable("protocol_mismatch")
    caps = member.access.cost_caps
    if caps is None:
        caps = tuple((name, 0) for name in sorted(contract.price_components))
    if {name for name, _ in caps} != contract.price_components:
        raise ModelSourceUnavailable("price_components_unenforceable")
    interaction = replace(contract.text_interaction, needs_tools=True)
    order = order_models(
        Catalog(owner, uid, (snapshot.models,)),
        ModelPolicy(0, "automatic", (), cost_caps=tuple(Charge(k, v, True) for k, v in caps)),
        interaction, owner_id=owner, universe_id=uid,
    )
    eligible = {candidate.ref.model_id for candidate in order.candidates}
    rejected = list(order.ineligible)
    models = []
    for model in snapshot.models.models:
        ref = ModelRef(member.provider, model.model_id)
        if (member.access.model_scope == "explicit"
                and model.model_id not in member.access.model_ids):
            rejected.append(Ineligible(ref, "outside_accepted_model_scope"))
            continue
        if model.model_id not in eligible:
            continue
        try:
            contract.constrain_inference({"model": model.model_id, "messages": []}, caps)
        except ValueError:
            rejected.append(Ineligible(ref, "unsupported_model_indirection"))
            continue
        models.append(model)
    return snapshot, replace(snapshot.models, models=tuple(models)), interaction, caps, rejected


def prepare_owned_model_plan(
    *, base, universe, owner, agent, current=None, config=None, allow_empty=False,
):
    """Private composition for authenticated ingress and serving readiness.

    Caller must verify its principal and exact agent first. No principal is
    inferred from preferences. A manifest is the explicit opt-in to discovery;
    absent preferences on an existing legacy assignment leave its path unchanged.
    allow_empty permits advisory display, never invocation without a candidate.
    """
    base, universe = Path(base), Path(universe)
    store = SQLiteProviderWorkAuthorityStore(base)
    preferences = ModelPreferenceStore(base).get(owner, universe.name, require_current_home=True)
    captured = capture_preference_policy(
        saved=preferences.policy, observed_generation=preferences.generation, current=current,
    )
    with provider_assignment_admission().shared(universe):
        observed_agent = get_binding(
            base, universe_id=universe.name, binding_id=agent["agent_binding_id"],
        )
        if observed_agent != agent or agent["created_by"] != owner:
            raise PermissionError("agent binding changed")
        with store.connection() as conn:
            conn.execute("BEGIN")
            check_current_home(conn, owner, universe.name)
            assignment = load_provider_assignment_in_transaction(conn, universe_id=universe.name)
            if assignment is None or not assignment.manifest_digest:
                if captured is None or (
                    current is None and preferences.policy is not None
                    and preferences.policy.mode == "automatic"
                ):
                    # Saving an unpowered preference cannot brick an existing
                    # native binding. Without model-access opt-in, saved auto
                    # retains that provider's own default and grants nothing.
                    # Explicit saved/current choices still require a manifest.
                    return None
                raise PermissionError("model choice requires an accepted model assignment")
            if (assignment.owner_user_id != owner or assignment.universe_id != universe.name
                    or agent["configuration"].get("provider_ref") != assignment.binding_id):
                raise PermissionError("model assignment does not match the current owned agent")
            chains, rejected = [], []
            for member in assignment.candidates:
                try:
                    chain = _current_selected_member_authority(
                        conn, store=store, universe_dir=universe, base_path=base,
                        owner_user_id=owner, universe_id=universe.name,
                        agent=agent, provider=member.provider,
                    )
                except PermissionError:
                    rejected.append(Ineligible(ModelRef(member.provider, ""), "source_revoked",
                                               scope="source"))
                else:
                    chains.append((member.provider, chain))
    if captured is None:
        captured = ModelPolicy(0, "automatic", ()), "automatic"
    policy, source = captured
    all_models, admitted, snapshots, caps_union = [], [], [], {}
    interaction = None
    ranking_sources = set()
    allowed = None if config is None else config.allowed_providers
    for provider, chain in chains:
        member = next(m for m in chain[0].candidates if m.provider == provider)
        try:
            if provider in _PROVIDER_SERVICE:
                catalog = filtered = _native_models(base, universe, owner, member)
            else:
                from tinyassets.providers.discovery_snapshot import refresh_model_discovery

                snapshot = refresh_model_discovery(
                    owner_user_id=owner, universe_id=universe.name,
                    definition_id=provider.removeprefix("api_key_http:"),
                )
                # Discovery facts remain useful to a repair screen even when
                # authority, pricing or the agent's contract excludes execution.
                all_models.append(snapshot.models)
                snapshots.append(snapshot)
                snapshot, filtered, required, caps, denied = _http_models(
                    owner, universe.name, member, snapshot=snapshot,
                )
                from tinyassets.universe_intelligence import _engine_mcp_enabled

                if not _engine_mcp_enabled():
                    denied.extend(Ineligible(ModelRef(provider, model.model_id),
                                             "engine_tools_unavailable")
                                  for model in filtered.models)
                    filtered = replace(filtered, models=())
                catalog = snapshot.models
                rejected.extend(denied)
                common = replace(required, min_context=None)
                if interaction is not None and interaction != common:
                    raise ModelSourceUnavailable("price_contract_incompatible")
                interaction = common
                # Every HTTP member was prefiltered under its own exact caps.
                # The combined advisory ceiling cannot authorize an actual call.
                for name, amount in caps:
                    caps_union[name] = max(caps_union.get(name, 0), amount)
                from tinyassets.providers.discovery_protocols import discovery_protocol

                benchmark = discovery_protocol(catalog.provider_scope).ranking_source
                if benchmark is not None:
                    ranking_sources.add(benchmark)
        except (ModelDiscoveryUnavailable, ModelSourceUnavailable, ServingProviderHeld) as exc:
            rejected.append(Ineligible(ModelRef(provider, ""), exc.reason, scope="source"))
            continue
        except (PermissionError, ValueError, RuntimeError, OSError, ProviderError):
            rejected.append(Ineligible(ModelRef(provider, ""), "discovery_unavailable",
                                       scope="source"))
            continue
        if provider in _PROVIDER_SERVICE:
            all_models.append(catalog)
        if allowed is not None and provider not in allowed:
            rejected.extend(Ineligible(ModelRef(provider, m.model_id), "provider_not_allowed")
                            for m in catalog.models)
        else:
            admitted.append(filtered)
    if interaction is None:
        interaction = Interaction(True, frozenset({"text"}), frozenset())
    policy = replace(
        policy, cost_caps=tuple(Charge(k, v, True) for k, v in sorted(caps_union.items())),
        ranking_source=next(iter(ranking_sources)) if len(ranking_sources) == 1 else None,
    )
    plan = AgentModelPlan(
        Catalog(owner, universe.name, tuple(admitted)), policy, interaction, source,
    )
    if not allow_empty and plan.next_candidate(owner, universe.name) is None:
        raise PermissionError("no eligible model in the accepted assignment")
    result = PreparedPlan(
        plan, Catalog(owner, universe.name, tuple(all_models)), tuple(rejected),
        assignment, tuple(chains), agent, preferences, tuple(snapshots), display_only=allow_empty,
    )
    with provider_assignment_admission().shared(universe):
        current_agent = get_binding(
            base, universe_id=universe.name, binding_id=agent["agent_binding_id"],
        )
        with store.connection() as conn:
            conn.execute("BEGIN")
            if allow_empty:
                result = result.recheck_display(
                    conn, store=store, base=base, universe=universe,
                    owner=owner, agent=current_agent,
                )
            else:
                result.recheck(
                    conn, store=store, base=base, universe=universe,
                    owner=owner, agent=current_agent,
                )
    return result


def apply_served_model_preferences(context, *, model_choice=None):
    """Capture preferences only from a genuine current owned conversation."""
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.exceptions import ProviderAuthorityHeldError

    try:
        current = None if model_choice is None else ModelPreferences.from_document(model_choice)
        if context.provider_request is None:
            if current is not None:
                raise PermissionError("model choice requires an authenticated conversation")
            return context
        universe = context.universe_dir
        capability, agent = _served_request_agent(
            universe.parent, universe, context.provider_request, "writer", "converse",
        )
        if get_founder_home(universe.parent, capability.principal_id) != universe.name:
            if current is not None:
                raise PermissionError("model choice is not supported outside the current home")
            return context
        prepared = prepare_owned_model_plan(
            base=universe.parent, universe=universe, owner=capability.principal_id,
            agent=agent, current=current, config=context.config,
        )
        if prepared is None:
            return context
        return replace(
            context, agent_model_plan=prepared.plan,
            model_selection=prepared.plan.next_candidate(capability.principal_id, universe.name),
        )
    except (PermissionError, ValueError, RuntimeError, ProviderError) as exc:
        raise ProviderAuthorityHeldError(str(exc)) from exc

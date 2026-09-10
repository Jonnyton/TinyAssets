"""Per-attempt model validation, separate from advisory ordering and preferences.

Only the serving validator supplies these facts after checking a current accepted
member. A model reference or catalogue object from the caller is never a grant.
No release names or provider wire shapes belong in this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.providers.model_policy import (
    Catalog,
    Charge,
    ModelPolicy,
    ModelRef,
    order_models,
)


@dataclass(frozen=True, slots=True)
class SelectedModel:
    provider: str
    model_id: str
    discovery_protocol: str
    cost_caps: tuple[tuple[str, int], ...]
    source_digest: str
    context_tokens: int
    supports_tools: bool = False

    def cost_upper_bound(self, output_tokens: int) -> int:
        """Conservative USD micros for this text-only request at accepted caps.

        Use the whole model context as an input upper bound, not a tokenizer
        guess. The wire has no images or paid server plugins. Actual response
        cost remains unknown unless reported; this is reservation evidence.
        """
        caps = dict(self.cost_caps)
        input_cost = (self.context_tokens * caps["input_million_tokens_usd"] + 999999) // 1000000
        output_cost = (output_tokens * caps["output_million_tokens_usd"] + 999999) // 1000000
        return input_cost + output_cost + caps["request_usd"]

    def affordable_output(self, remaining_cost: int) -> int | None:
        available = remaining_cost - self.cost_upper_bound(0)
        if available < 0:
            return 0
        price = dict(self.cost_caps)["output_million_tokens_usd"]
        return None if price == 0 else available * 1000000 // price


def prepare_selected_model(
    *,
    base_path: Path,
    owner_user_id: str,
    universe_id: str,
    provider: str,
    model_id: str,
    access: ModelAccess,
    needs_tools: bool = False,
) -> tuple[SelectedModel, Callable[[], None]]:
    """Refresh an accepted HTTP source; return facts plus a pre-launch recheck.

    This is not an independent authority entrypoint. The caller must validate the
    exact current member before and after this IO, under assignment admission.
    Full HTTP agent tools remain gated in the executor until their runtime exists.
    """
    from tinyassets.providers.discovery_snapshot import refresh_model_discovery

    definition = _selection_definition(
        base_path, owner_user_id, universe_id, provider, model_id, access
    )
    snapshot = refresh_model_discovery(
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        definition_id=definition.id,
    )
    return _validate_snapshot(
        definition, snapshot, provider, model_id, access, needs_tools=needs_tools,
    )


async def prepare_selected_model_async(
    *, base_path: Path, owner_user_id: str, universe_id: str,
    provider: str, model_id: str, access: ModelAccess,
    needs_tools: bool = False,
) -> tuple[SelectedModel, Callable[[], None]]:
    """Refresh without blocking ingress; the caller re-fences authority afterward.

    No assignment lock or SQLite transaction may span this await. The snapshot
    is advisory data, not permission, and cancelled callers never reach launch.
    """
    from tinyassets.providers.discovery_snapshot import refresh_model_discovery_async

    definition = _selection_definition(
        base_path, owner_user_id, universe_id, provider, model_id, access
    )
    snapshot = await refresh_model_discovery_async(
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        definition_id=definition.id,
    )
    return _validate_snapshot(
        definition, snapshot, provider, model_id, access, needs_tools=needs_tools,
    )


def _selection_definition(base_path, owner_user_id, universe_id, provider, model_id, access):
    from tinyassets.providers.definition import get_definition
    from tinyassets.storage import data_dir

    if Path(base_path).resolve() != data_dir().resolve():
        raise PermissionError("model discovery requires the current storage root")
    if (
        not isinstance(model_id, str)
        or not model_id
        or len(model_id) > 200
        or not model_id.isprintable()
        or model_id != model_id.strip()
        or access.model_scope == "legacy"
        or (access.model_scope == "explicit" and model_id not in access.model_ids)
    ):
        raise PermissionError("model is outside the accepted selection scope")
    if not isinstance(provider, str) or not provider.startswith("api_key_http:"):
        raise PermissionError("dynamic selection is not supported by this executor yet")
    definition_id = provider.removeprefix("api_key_http:")
    definition = get_definition(universe_id, definition_id)
    if definition is None or definition.owner_user_id != owner_user_id:
        raise PermissionError("selected provider definition is unavailable")
    return definition


def _validate_snapshot(definition, snapshot, provider, model_id, access, *, needs_tools=False):
    from tinyassets.providers.discovery_protocols import discovery_protocol
    from tinyassets.providers.discovery_snapshot import assert_discovery_snapshot_current

    owner_user_id, universe_id = definition.owner_user_id, definition.universe_id
    if (
        snapshot.owner_id != owner_user_id or snapshot.universe_id != universe_id
        or snapshot.provider != provider
    ):
        raise PermissionError("discovery snapshot does not match selected provider")
    contract = discovery_protocol(snapshot.models.provider_scope)
    if definition.protocol != contract.inference_protocol:
        raise PermissionError("discovery and inference protocols do not match")
    components = contract.price_components
    caps = (
        tuple((name, 0) for name in sorted(components))
        if access.cost_caps is None
        else access.cost_caps
    )
    if {name for name, _ in caps} != components:
        raise PermissionError("selected executor cannot enforce the accepted price components")
    contract.constrain_inference({"model": model_id, "messages": []}, caps)
    ref = ModelRef(provider, model_id)
    # Automatic eligibility enforces fresh capability/privacy AND price evidence.
    # An explicit preference cannot use the advisory kernel's stale-list allowance.
    policy = ModelPolicy(
        generation=0,
        mode="automatic",
        fallbacks=(),
        cost_caps=tuple(Charge(name, amount, True) for name, amount in caps),
    )
    if type(needs_tools) is not bool:
        raise PermissionError("invalid required model capability")
    interaction = replace(contract.text_interaction, needs_tools=needs_tools)
    order = order_models(
        Catalog(owner_user_id, universe_id, (snapshot.models,)),
        policy,
        interaction,
        owner_id=owner_user_id,
        universe_id=universe_id,
    )
    if ref not in {candidate.ref for candidate in order.candidates}:
        raise PermissionError("selected model lacks fresh capability or permitted pricing")
    assert_discovery_snapshot_current(snapshot)
    model = next(model for model in snapshot.models.models if model.model_id == model_id)
    selected = SelectedModel(
        provider,
        model_id,
        snapshot.models.provider_scope,
        caps,
        snapshot.source_digest,
        model.context_tokens,
        needs_tools,
    )
    return selected, lambda: assert_discovery_snapshot_current(snapshot)

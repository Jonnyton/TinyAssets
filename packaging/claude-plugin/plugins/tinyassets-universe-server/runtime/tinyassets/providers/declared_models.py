"""Model facts a connection's owner declared, as an execution contract.

A connection's ``model`` use (``uses.model{wire, models, billing}``) names a
bundled wire dialect, a static model list and a billing class. This module
turns that declaration into the same contract shape discovery produces, so
selection, reservation and the executor run unchanged whether the models came
from a fetched catalogue or from the owner's own list.

No network, no storage, no credentials. The declaration is evidence of what the
owner said the source serves (``availability_basis="owner_configured_contract"``),
not an independent verification, and it grants nothing by itself: serving still
needs accepted model access. ``free`` and ``flat`` billing carry no prices, so
every model is ``unmetered`` and no spending ceiling can be raised through it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Callable

from tinyassets.providers.model_policy import (
    ConnectionModels,
    Interaction,
    Model,
    Pricing,
    Scores,
)

#: Declared sources share the legacy reservation arithmetic, whose caps name
#: these three components. With free-only access every cap is zero, and an
#: unmetered model costs zero at any cap.
_PRICE_COMPONENTS = frozenset(
    {"input_million_tokens_usd", "output_million_tokens_usd", "request_usd"}
)
#: The provider scope a declared source reports. It is a label for capacity
#: grouping and receipts, never a registry key.
DECLARED_SCOPE = "declared-http"


@dataclass(frozen=True, slots=True)
class DeclaredModelContract:
    """The contract attributes selection and the executor read, from a declaration."""

    declaration_json: str
    auth_scheme: str
    inference_protocol: str
    price_components: frozenset[str]
    text_interaction: Interaction
    account_filtered: bool = False
    catalogue_path: str = ""
    catalogue_query: str = ""
    benchmark_path: str = ""
    capacity_decoder: Callable | None = None
    usage_decoder: Callable | None = None
    ranking_source: str | None = None

    def descriptor(self) -> dict[str, Any]:
        """The declaration plus auth scheme; enough to rebuild this contract."""
        return {**json.loads(self.declaration_json), "auth_scheme": self.auth_scheme}

    def constrain_inference(self, body: dict[str, Any], caps: Any) -> dict[str, Any]:
        """Validate the body against the installed wire; free/flat has no caps to set."""
        from tinyassets.providers.protocol_encoders import PROTOCOLS

        validator = PROTOCOLS[self.inference_protocol].request_validator
        if validator is not None:
            validator(body)
        return body

    def model_decoder(self, _payload: Any, *, connection: ConnectionModels,
                      benchmarks: dict[str, Scores] | None = None) -> ConnectionModels:
        models = tuple(
            Model(
                model_id=entry["id"],
                tools=entry["tools"],
                modalities=frozenset({"text"}),
                context_tokens=entry["context"],
                pricing=Pricing("fresh", unmetered=True),
                availability_basis="owner_configured_contract",
            )
            for entry in json.loads(self.declaration_json)["models"]
        )
        return replace(connection, models=models)

    def benchmark_decoder(self, *_args: Any, **_kwargs: Any) -> dict[str, Scores]:
        return {}

    def validate_urls(self, catalogue_url: str, benchmark_url: str) -> None:
        if catalogue_url or benchmark_url:
            raise ValueError("a declared model list has no catalogue to fetch")


def declared_model_contract(
    descriptor: dict[str, Any], *, auth_scheme: str,
) -> DeclaredModelContract:
    """Build the contract for one validated ``model_use`` descriptor."""
    from tinyassets.providers.wire_dialects import canonical_dialect

    wire = canonical_dialect(descriptor["wire"])
    declaration = json.dumps(
        {"billing": descriptor["billing"], "models": descriptor["models"], "wire": wire},
        sort_keys=True, separators=(",", ":"),
    )
    return DeclaredModelContract(
        declaration_json=declaration,
        auth_scheme=auth_scheme,
        inference_protocol=wire,
        price_components=_PRICE_COMPONENTS,
        text_interaction=Interaction(
            needs_tools=False, modalities=frozenset({"text"}),
            charge_components=frozenset(), min_context=1,
        ),
    )


def contract_from_evidence(value: Any) -> DeclaredModelContract:
    """Rebuild a persisted declared contract, re-validating the declaration."""
    from tinyassets.storage.outbound_connections import _validate_model_use_capability

    if not isinstance(value, dict) or set(value) != {"wire", "models", "billing", "auth_scheme"}:
        raise ValueError("invalid declared model contract")
    capability = _validate_model_use_capability(
        "evidence", {key: value[key] for key in ("wire", "models", "billing")}
    )
    auth_scheme = value["auth_scheme"]
    if not isinstance(auth_scheme, str) or not auth_scheme:
        raise ValueError("invalid declared model contract")
    return declared_model_contract(capability.descriptor(), auth_scheme=auth_scheme)


def declared_connection_models(
    contract: DeclaredModelContract, *, provider: str,
) -> ConnectionModels:
    """The declared models, scoped to one provider source, freshly observed."""
    from tinyassets.providers.protocol_encoders import agent_codec_for

    return contract.model_decoder(None, connection=ConnectionModels(
        connection_id=provider,
        provider_scope=DECLARED_SCOPE,
        source_kind="http",
        freshness="fresh",
        owner_filtered=False,
        # Local executor capability, never the declaration's claim.
        executor_tools=agent_codec_for(contract.inference_protocol) is not None,
        models=(),
        authenticated_account_id=None,
        availability_basis="owner_configured_contract",
    ))


__all__ = [
    "DECLARED_SCOPE",
    "DeclaredModelContract",
    "contract_from_evidence",
    "declared_connection_models",
    "declared_model_contract",
]

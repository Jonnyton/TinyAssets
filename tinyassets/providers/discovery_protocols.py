"""Installed compatibility contracts compiled from data, never source callbacks.

New owner-authored connections use SourceContract. This preserves legacy stored
descriptors and trusted preset semantics without a parallel execution engine.
"""

from dataclasses import dataclass
from functools import partial
from typing import Callable
from urllib.parse import urlsplit

from tinyassets.providers.discovery_catalogue import BenchmarkShape, CatalogueShape, _fields
from tinyassets.providers.discovery_execution import CapacityShape, RequestCeilings, UsageShape
from tinyassets.providers.discovery_presets import bundled_discovery_documents
from tinyassets.providers.model_policy import ConnectionModels, Interaction, Scores
from tinyassets.providers.protocol_encoders import PROTOCOLS


@dataclass(frozen=True, slots=True)
class DiscoveryProtocol:
    catalogue_path: str
    catalogue_query: str
    benchmark_path: str
    auth_scheme: str
    account_filtered: bool
    model_decoder: Callable[..., ConnectionModels]
    benchmark_decoder: Callable[..., dict[str, Scores]]
    inference_protocol: str
    price_components: frozenset[str]
    constrain_inference: Callable[..., dict]
    text_interaction: Interaction
    capacity_decoder: Callable | None = None
    ranking_source: str | None = None
    usage_decoder: Callable[[str], int | None] | None = None

    @classmethod
    def from_bundled_document(cls, document):
        """Internal installed compatibility, not an owner metadata entrypoint.

        Trust/exclusions/legacy mode are inherited only from the shipped preset.
        No configured descriptor can call or select this compilation path.
        """
        _fields(document, {"compatibility_default", "transport", "catalogue", "prices",
                           "benchmark", "inference", "interaction", "capacity", "usage"})
        transport = document["transport"]
        _fields(transport, {"catalogue_path", "catalogue_query", "benchmark_path", "auth_scheme",
                            "account_filtered", "inference_protocol"})
        if type(transport["account_filtered"]) is not bool:
            raise ValueError("invalid installed discovery provenance")
        wire = PROTOCOLS[transport["inference_protocol"]]
        if wire.legacy_request_validator is None:
            raise ValueError("installed compatibility validator unavailable")
        catalogue = CatalogueShape.compile(document["catalogue"], document["prices"], legacy=True)
        benchmark = BenchmarkShape.compile(document["benchmark"], legacy=True)
        interaction = dict(document["interaction"])
        for key in ("modalities", "charge_components", "ceiling_components", "excluded_components"):
            interaction[key] = frozenset(interaction[key])
        for key in ("extra_price_bounds", "output_price_components"):
            interaction[key] = tuple(tuple(item) for item in interaction[key])
        interaction = Interaction(**interaction)
        request = RequestCeilings.compile(document["inference"],
                                          components=interaction.ceiling_components, legacy=True)
        if not request.allowed <= wire.request_fields:
            raise ValueError("installed source fields exceed wire capability")
        return cls(
            transport["catalogue_path"], transport["catalogue_query"], transport["benchmark_path"],
            transport["auth_scheme"], transport["account_filtered"],
            catalogue.decode, benchmark.decode, transport["inference_protocol"], request.components,
            partial(request.constrain, validate_body=wire.legacy_request_validator), interaction,
            CapacityShape.compile(document["capacity"]).decode, benchmark.source,
            UsageShape.compile(document["usage"], legacy=True).decode,
        )

    def validate_urls(self, catalogue_url: str, benchmark_url: str) -> None:
        catalogue = urlsplit(catalogue_url)
        if (catalogue.path, catalogue.query) != (self.catalogue_path, self.catalogue_query):
            raise ValueError("discovery catalogue URL does not match the protocol")
        if benchmark_url:
            benchmark = urlsplit(benchmark_url)
            if benchmark.path != self.benchmark_path or benchmark.query:
                raise ValueError("discovery benchmark URL does not match the protocol")


_PROTOCOLS = {name: DiscoveryProtocol.from_bundled_document(document)
              for name, document in bundled_discovery_documents().items()}


def discovery_protocol(protocol: str) -> DiscoveryProtocol:
    try:
        return _PROTOCOLS[protocol]
    except (KeyError, TypeError):
        raise ValueError("model discovery protocol is not supported") from None

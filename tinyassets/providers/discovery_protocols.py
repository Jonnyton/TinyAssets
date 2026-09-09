"""Protocol-boundary discovery contracts, never a model-release catalogue.

Owners choose the granted host. Each adapter defines which path/query actually
has its account-filtered semantics; schema similarity cannot substitute for it.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class DiscoveryProtocol:
    catalogue_path: str
    catalogue_query: str
    benchmark_path: str
    auth_scheme: str
    account_filtered: bool

    def validate_urls(self, catalogue_url: str, benchmark_url: str) -> None:
        catalogue = urlsplit(catalogue_url)
        if (catalogue.path, catalogue.query) != (self.catalogue_path, self.catalogue_query):
            raise ValueError("discovery catalogue URL does not match the protocol")
        if benchmark_url:
            benchmark = urlsplit(benchmark_url)
            if benchmark.path != self.benchmark_path or benchmark.query:
                raise ValueError("discovery benchmark URL does not match the protocol")


_PROTOCOLS = {
    "openrouter_user_models_v1": DiscoveryProtocol(
        "/api/v1/models/user", "output_modalities=all", "/api/v1/benchmarks", "bearer", True
    )
}


def discovery_protocol(protocol: str) -> DiscoveryProtocol:
    try:
        return _PROTOCOLS[protocol]
    except (KeyError, TypeError):
        raise ValueError("model discovery protocol is not supported") from None

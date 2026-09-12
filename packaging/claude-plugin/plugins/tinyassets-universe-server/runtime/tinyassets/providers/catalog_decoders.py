"""Legacy discovery names backed by the shared bounded data interpreter.

Installed data preserves existing endpoint semantics. New owner-authored sources
use the same catalogue compiler without acquiring bundled trust or legacy mode.
"""

from tinyassets.providers.discovery_catalogue import (
    BenchmarkShape,
    CatalogDecodeError,
    CatalogueShape,
)
from tinyassets.providers.discovery_presets import compatibility_document

_DOCUMENT = compatibility_document()
_CATALOGUE = CatalogueShape.compile(_DOCUMENT["catalogue"], _DOCUMENT["prices"], legacy=True)
_BENCHMARK = BenchmarkShape.compile(_DOCUMENT["benchmark"], legacy=True)


def decode_openrouter_models(payload, *, connection, benchmarks=None):
    """Compatibility wrapper; the common interpreter owns all decoding."""
    return _CATALOGUE.decode(payload, connection=connection, benchmarks=benchmarks)


def decode_openrouter_benchmarks(payload, *, now, max_age, source="artificial-analysis"):
    """Preserve the legacy source restriction and score/freshness rules."""
    if source != _BENCHMARK.source:
        raise CatalogDecodeError("unsupported comparable benchmark source")
    return _BENCHMARK.decode(payload, now=now, max_age=max_age)

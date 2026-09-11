"""Compose one finite source contract; configuration is not execution authority.

Private compiler, not yet a published connection descriptor. Installed wire
validators establish structure; source-declared effects/tariffs remain promises.
No credentials, grants, network, storage or source-specific callbacks live here.
"""

import hashlib
import json
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from tinyassets.providers.discovery_catalogue import (
    BenchmarkShape,
    CatalogueShape,
    Pointer,
    _document,
    _fields,
    _names,
    identifier,
)
from tinyassets.providers.discovery_execution import CapacityShape, RequestCeilings, UsageShape
from tinyassets.providers.discovery_quantities import QuantityModel
from tinyassets.providers.model_policy import Interaction
from tinyassets.providers.protocol_encoders import PROTOCOLS, WireProtocol

_DIMENSIONS = {
    "input_million_tokens_usd": "input_tokens",
    "output_million_tokens_usd": "output_tokens",
    "request_usd": "requests",
}


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_shape(value, depth=0):
    if depth > 16:
        raise ValueError("source contract nesting exceeds the limit")
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("source contract object keys must be strings")
        for nested in value.values():
            _json_shape(nested, depth + 1)
    elif type(value) is list:
        for nested in value:
            _json_shape(nested, depth + 1)
    elif type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("source contract requires JSON values")


@dataclass(frozen=True, slots=True)
class SourceContract:
    descriptor_json: str
    digest: str
    inference_protocol: str
    wire: WireProtocol
    auth_scheme: str
    catalogue_path: str
    catalogue_query: str
    benchmark_path: str
    catalogue: CatalogueShape
    benchmark: BenchmarkShape | None
    ranking_source: str | None
    request: RequestCeilings
    quantities: QuantityModel
    capacity: CapacityShape
    usage: UsageShape | None
    interaction: Interaction

    @classmethod
    def compile(cls, document):
        _document(document)
        _json_shape(document)
        _fields(document, {"version", "transport", "catalogue", "prices", "inference",
                           "quantity_model", "extension_quantities", "charge_bindings",
                           "capacity", "price_bound_basis"}, {"benchmark", "usage"})
        if type(document["version"]) is not int or document["version"] != 1:
            raise ValueError("unsupported source contract version")
        if document["price_bound_basis"] != "source_request_caps":
            raise ValueError("source price basis requires unsupported authority")
        transport = document["transport"]
        _fields(transport, {"protocol", "auth_scheme", "catalogue_path", "catalogue_query",
                            "benchmark_path"})
        protocol = transport["protocol"]
        if type(protocol) is not str:
            raise ValueError("invalid source wire protocol")
        wire = PROTOCOLS.get(protocol)
        if wire is None or wire.request_validator is None or not wire.request_fields:
            raise ValueError("installed constrained wire protocol unavailable")
        if transport["auth_scheme"] not in ("bearer", "header", "basic", "oauth1a", "none"):
            raise ValueError("unsupported source authentication shape")
        for key in ("catalogue_path", "benchmark_path"):
            value = transport[key]
            if (type(value) is not str or len(value) > 2048
                    or (value and (not value.startswith("/") or value.startswith("//")
                                   or urlsplit(value).path != value))):
                raise ValueError("invalid source endpoint path")
        query = transport["catalogue_query"]
        if type(query) is not str or len(query) > 2048 or "#" in query:
            raise ValueError("invalid source catalogue query")
        catalogue = CatalogueShape.compile(document["catalogue"], document["prices"])
        prices = catalogue.price_fields
        components = frozenset(item[1] for item in prices.fields)
        bindings = document["charge_bindings"]
        if type(bindings) is not dict or bindings != _DIMENSIONS or components != bindings.keys():
            raise ValueError("incomplete or dimensionally unsupported source charges")
        required = frozenset(component for name, component, _, _ in prices.fields
                             if name in prices.required)
        if not {"input_million_tokens_usd", "output_million_tokens_usd"} <= required:
            raise ValueError("source token prices must be required")
        request = RequestCeilings.compile(document["inference"])
        if not request.allowed <= wire.request_fields:
            raise ValueError("source accepts fields outside installed wire contract")
        paths = [pointer for _, pointer, _ in request.outputs]
        paths.extend(pointer for pointer, _, _ in request.constants)
        if any(pointer.tokens[0] in wire.request_fields for pointer in paths):
            raise ValueError("source extension overwrites installed wire field")
        quantities = QuantityModel.compile(document["quantity_model"])
        # An actual text dispatch has at least one input/output budget and request.
        # These floors do not prove remote semantics; they prevent declarations
        # from removing the locally known base operation from reservation.
        if (quantities.coefficients[0][0] < 1 or quantities.coefficients[1][1] < 1
                or quantities.coefficients[2][2] < 1):
            raise ValueError("source quantities omit the base dispatch")
        effects = document["extension_quantities"]
        if type(effects) is not dict or len(effects) != len(request.constants):
            raise ValueError("source extension quantities are incomplete")
        by_path = {Pointer.compile(path).tokens: value for path, value in effects.items()}
        if len(by_path) != len(effects) or by_path.keys() != {
            pointer.tokens for pointer, _, _ in request.constants
        }:
            raise ValueError("source extension quantities do not match constants")
        for pointer, _, charges in request.constants:
            effect = by_path[pointer.tokens]
            if effect == "quantity_neutral":
                continue
            refs = _names(effect)
            if not refs or not set(refs) <= {_DIMENSIONS[charge] for charge in charges}:
                raise ValueError("source extension effect lacks compatible charge binding")
        benchmark = None
        ranking_source = None
        if "benchmark" in document:
            if type(document["benchmark"]) is not dict:
                raise ValueError("invalid source benchmark shape")
            raw_benchmark = dict(document["benchmark"])
            schema = raw_benchmark.pop("score_schema", None)
            if not identifier(schema):
                raise ValueError("source benchmark schema identity required")
            benchmark = BenchmarkShape.compile(raw_benchmark)
            ranking_source = hashlib.sha256(_canonical({
                "source": benchmark.source, "schema": schema, "scale": benchmark.scale,
            }).encode()).hexdigest()
        if bool(transport["benchmark_path"]) != (benchmark is not None):
            raise ValueError("source benchmark endpoint and shape disagree")
        raw = _canonical(document)
        return cls(raw, hashlib.sha256(raw.encode()).hexdigest(), protocol, wire,
                   transport["auth_scheme"], transport["catalogue_path"], query,
                   transport["benchmark_path"], catalogue, benchmark, ranking_source,
                   request, quantities, CapacityShape.compile(document["capacity"]),
                   UsageShape.compile(document["usage"]) if "usage" in document else None,
                   Interaction(False, frozenset({"text"}), required, min_context=1,
                               ceiling_components=components))

    def validate_urls(self, catalogue_url, benchmark_url):
        catalogue = urlsplit(catalogue_url)
        if (catalogue.path, catalogue.query) != (self.catalogue_path, self.catalogue_query):
            raise ValueError("source catalogue URL differs from contract")
        if bool(benchmark_url) != (self.benchmark is not None):
            raise ValueError("source benchmark URL and contract disagree")
        if benchmark_url:
            benchmark = urlsplit(benchmark_url)
            if benchmark.path != self.benchmark_path or benchmark.query:
                raise ValueError("source benchmark URL differs from contract")
        # Exact allowed HTTPS hosts/grants are checked by the existing ledger and
        # broker. Matching these paths alone supplies no transport authority.

    def decode_models(self, payload, *, connection, benchmarks=None):
        return self.catalogue.decode(payload, connection=connection, benchmarks=benchmarks)

    def decode_benchmarks(self, payload, *, now, max_age):
        if self.benchmark is None:
            raise ValueError("source has no benchmark contract")
        return {key: replace(score, source=self.ranking_source) for key, score in
                self.benchmark.decode(payload, now=now, max_age=max_age).items()}

    def constrain_inference(self, body, caps):
        return self.request.constrain(body, caps, validate_body=self.wire.request_validator)

    def validate_envelope(self, body, envelope, caps):
        expected = self.constrain_inference(body, caps)
        # JSON bytes preserve types (True != 1 here) and reject extra/mutated fields.
        if _canonical(envelope) != _canonical(expected):
            raise ValueError("source final envelope differs from compiled contract")

    def cost_upper_bound(self, caps, input_bound, output_limit):
        return self.quantities.cost_upper_bound(caps, input_bound, output_limit)

    def affordable_output(self, caps, input_bound, output_limit, remaining_cost):
        return self.quantities.affordable_output(caps, input_bound, output_limit, remaining_cost)

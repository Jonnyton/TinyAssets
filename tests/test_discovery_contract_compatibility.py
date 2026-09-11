"""Freeze old decoding before compiling user-authored discovery contracts."""

import ast
import inspect
from copy import deepcopy
from datetime import timedelta

import pytest

from tests import _discovery_legacy_oracle as legacy
from tests.test_catalog_decoders import CONNECTION, NOW, row, score
from tinyassets.providers import catalog_decoders as current
from tinyassets.providers import discovery_catalogue as implementation


def _outcome(function, payload, **kwargs):
    try:
        return ("value", function(deepcopy(payload), **kwargs))
    except (ValueError, TypeError) as error:
        return ("error", type(error).__name__, str(error))


@pytest.mark.parametrize("identifier", [
    "new/source:v101", " padded", "padded ", "", None, 4, "a" * 201,
])
@pytest.mark.parametrize("pricing", [
    None, {}, {"prompt": "0", "completion": "0"},
    {"prompt": "0.000000001234", "completion": "0.000009"},
    {"prompt": "0.0000000000001", "completion": "0"},
    {"prompt": "-1", "completion": "0"},
    {"prompt": "NaN", "completion": "0"},
    {"prompt": True, "completion": 0},
    {"prompt": "0", "completion": "0", "new_charge": "0"},
    {"prompt": "0", "completion": "0", "overrides": [{"prompt": "0.01", "utc_days": [1]}]},
    {"prompt": "0", "completion": "0", "overrides": [{"prompt": "bad"}]},
    {"prompt": "0", "completion": "0", "overrides": [None]},
    {"prompt": "0", "completion": "0", "overrides": "invalid"},
])
def test_model_identity_and_price_interpretation_match_frozen_legacy(identifier, pricing):
    payload = {"data": [row(identifier, pricing=pricing)]}
    assert _outcome(current.decode_openrouter_models, payload, connection=CONNECTION) == _outcome(
        legacy.decode_openrouter_models, payload, connection=CONNECTION,
    )


@pytest.mark.parametrize("context", [None, True, -1, 0, 1, 64000, "100"])
@pytest.mark.parametrize("tools", [None, [], ["tools"], ["tools", "temperature"], [True], "tools"])
def test_capability_unknowns_and_context_minimum_match_legacy(context, tools):
    payload = {"data": [row(context_length=context, supported_parameters=tools)]}
    assert _outcome(current.decode_openrouter_models, payload, connection=CONNECTION) == _outcome(
        legacy.decode_openrouter_models, payload, connection=CONNECTION,
    )


@pytest.mark.parametrize("envelope", [
    None, [], {}, {"data": None}, {"data": [None]}, {"data": []},
    {"data": [row(), row()]}, {"data": [row()], "total_count": True},
    {"data": [row()], "total_count": 2}, {"data": [row()], "total_count": 1},
    {"data": [row()], "links": {"next": "https://untrusted.invalid/next"}},
    {"data": [row()], "links": {"next": ""}},
])
def test_envelope_completeness_match_legacy(envelope):
    assert _outcome(current.decode_openrouter_models, envelope, connection=CONNECTION) == _outcome(
        legacy.decode_openrouter_models, envelope, connection=CONNECTION,
    )


@pytest.mark.parametrize("as_of", [
    NOW.isoformat(), None, "", "malformed", "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
])
@pytest.mark.parametrize("rows", [
    [], [score()], [score(), score()], [score(source="unfamiliar-benchmark")],
    [score(agentic_index="0.0000001")], [score(agentic_index=True)],
    [score(model_permaslug=" padded")],
])
def test_benchmark_identity_exact_scaling_and_freshness_match_legacy(as_of, rows):
    payload = {"data": rows, "meta": {"as_of": as_of}}
    kwargs = {"now": NOW, "max_age": timedelta(days=1)}
    assert _outcome(current.decode_openrouter_benchmarks, payload, **kwargs) == _outcome(
        legacy.decode_openrouter_benchmarks, payload, **kwargs,
    )


def test_frozen_oracle_does_not_call_the_rewritten_decoder(monkeypatch):
    # Domain value types may remain shared; decoding behavior must not be.
    tree = ast.parse(inspect.getsource(legacy))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and "catalog_decoders" in name for name in imports)
    before = legacy.decode_openrouter_models({"data": [row()]}, connection=CONNECTION)

    def forbidden(*args, **kwargs):
        raise AssertionError("production helper reached by the frozen oracle")

    monkeypatch.setattr(implementation.PriceFields, "decode", forbidden)
    monkeypatch.setattr(implementation.Rows, "read", forbidden)
    monkeypatch.setattr(implementation, "exact_scaled", forbidden)
    assert legacy.decode_openrouter_models({"data": [row()]}, connection=CONNECTION) == before

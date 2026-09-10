"""Request-local answer observation; no provider calls or account authority."""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tinyassets.providers import call as calls
from tinyassets.providers.base import ProviderResponse
from tinyassets.providers.execution_receipt import WriterExecutionReceipt


def response(provider="owned", reported="actual"):
    return ProviderResponse(
        "reply", provider, "requested-alias", "family", 1.0, reported_model=reported
    )


@pytest.fixture
def router(monkeypatch):
    history = []

    def call_sync(role, prompt, system, **kwargs):
        history.append(prompt)
        return response(provider=prompt, reported=f"actual-{prompt}")

    router = SimpleNamespace(call_sync=call_sync)
    monkeypatch.setattr(calls, "_force_mock", False)
    monkeypatch.setattr(calls, "_real_router", router)
    monkeypatch.setattr(calls, "_register_open_providers_for", lambda _: None)
    return router, history


def test_alias_never_substitutes_for_reported_model():
    receipt = WriterExecutionReceipt()
    receipt.observe(response(reported=""))
    assert receipt.projection() == {"provider": "owned", "model": "", "model_status": "unknown"}
    assert ProviderResponse("a", "p", "legacy-model", "f", 1).reported_model == ""


@pytest.mark.parametrize("bad", [None, True, 123, "", " ", "bad\nlabel", "a" * 201])
def test_unusable_model_evidence_stays_unknown(bad):
    receipt = WriterExecutionReceipt()
    receipt.observe(response(reported=bad))
    assert receipt.projection()["model_status"] == "unknown"


def test_projection_is_detached_and_first_success_cannot_be_overwritten():
    receipt = WriterExecutionReceipt()
    assert receipt.projection() is None
    receipt.observe(response())
    receipt.projection()["provider"] = "tampered"
    receipt.observe(response("learning-provider", "learning-model"))
    assert receipt.projection() == {
        "provider": "owned",
        "model": "actual",
        "model_status": "reported",
    }


@pytest.mark.parametrize(
    "item",
    [
        None,
        {},
        response(""),
        response("bad\nprovider"),
        replace(response(), degraded=True),
        replace(response(), failure_class="provider_rate_limited"),
    ],
)
def test_non_success_is_not_an_answer_receipt(item):
    receipt = WriterExecutionReceipt()
    receipt.observe(item)
    assert receipt.projection() is None


def test_observer_failure_never_retries_or_discards_answer(router):
    def broken(_):
        raise RuntimeError("private callback detail must not be logged")

    assert calls.call_provider("writer", operation="converse", response_observer=broken) == "reply"
    assert router[1] == ["writer"]


def test_failed_call_cannot_reuse_prior_receipt(router):
    first, second = WriterExecutionReceipt(), WriterExecutionReceipt()
    calls.call_provider("writer", response_observer=first.observe)

    def fail(*args, **kwargs):
        raise RuntimeError("failed")

    router[0].call_sync = fail
    with pytest.raises(RuntimeError, match="failed"):
        calls.call_provider("second", operation="converse", response_observer=second.observe)
    assert second.projection() is None
    assert first.projection()["provider"] == "writer"


def test_mock_has_no_actual_provider_receipt(router, monkeypatch):
    monkeypatch.setattr(calls, "_force_mock", True)
    receipt = WriterExecutionReceipt()
    assert (
        calls.call_provider("test", fallback_response="mock", response_observer=receipt.observe)
        == "mock"
    )
    assert receipt.projection() is None
    assert router[1] == []


def test_interleaved_requests_capture_only_their_own_response(router):
    ready = threading.Barrier(2)

    def overlap(role, prompt, system, **kwargs):
        ready.wait(timeout=5)
        return response(provider=prompt, reported=f"actual-{prompt}")

    router[0].call_sync = overlap

    def invoke(identity):
        receipt = WriterExecutionReceipt()
        text = calls.call_provider(
            identity, operation="converse", response_observer=receipt.observe
        )
        return text, receipt.projection()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(invoke, ["owner-a", "owner-b"]))
    for identity, (text, receipt) in zip(["owner-a", "owner-b"], results):
        assert text == "reply"
        assert receipt["provider"] == identity
        assert receipt["model"] == f"actual-{identity}"

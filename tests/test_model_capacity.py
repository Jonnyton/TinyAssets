"""Boundary-decoded capacity is scoped evidence, never inferred from model names."""

from datetime import UTC, datetime

import pytest

from tinyassets.exceptions import ProviderUnavailableError, SelectedModelCapacityError
from tinyassets.providers.discovery_protocols import discovery_protocol
from tinyassets.providers.model_capacity import CapacitySignal, retry_after_seconds
from tinyassets.providers.model_policy import ModelRef


@pytest.mark.parametrize("status,scope", [(402, "account"), (429, "unknown"), (503, "model")])
def test_protocol_capacity_scope_and_shared_unknown_fold(status, scope):
    decode = discovery_protocol("openrouter_user_models_v1").capacity_decoder
    signal = decode(status, {"Retry-After": "60"})
    assert signal.scope == scope and signal.retry_after_s == 60
    exc = SelectedModelCapacityError(signal)
    assert isinstance(exc, ProviderUnavailableError)
    assert signal.exhaustion(ModelRef("future-connection", "opaque")).scope == (
        "model" if scope == "model" else "account"
    )


@pytest.mark.parametrize("status", [200, 400, 401, 403, 408, 500, 502, None, True, "503"])
def test_non_capacity_status_is_not_a_fallback_signal(status):
    assert discovery_protocol("openrouter_user_models_v1").capacity_decoder(status, {}) is None


@pytest.mark.parametrize("value", ["", "-1", "1.5", "nan", "inf", "9" * 30, "１", "garbage"])
def test_invalid_hint_remains_unknown(value):
    assert retry_after_seconds({"retry-after": value}) is None


def test_retry_hint_date_duplicate_headers_and_zero():
    now = datetime(2026, 9, 10, 6, 0, tzinfo=UTC)
    assert retry_after_seconds({"Retry-After": "Thu, 10 Sep 2026 06:01:00 GMT"}, now=now) == 60
    assert retry_after_seconds({"retry-after": "0"}) == 0
    assert retry_after_seconds({"Retry-After": "60", "retry-after": "10"}) is None
    assert retry_after_seconds({"retry-after": 60}) is None


@pytest.mark.parametrize("delay", [True, float("nan"), float("inf"), -1, 2**31])
def test_signal_rejects_invalid_delay(delay):
    with pytest.raises(ValueError):
        CapacitySignal("model", "provider_overloaded", delay)

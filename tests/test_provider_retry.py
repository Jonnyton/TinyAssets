"""Tests for exact-provider retry with no fallback widening."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers import call as _provider_stub


class TestProviderRetry:
    @pytest.fixture(autouse=True)
    def _force_mock_off(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_force_mock", False)

    def test_force_mock_bypasses_retry(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_force_mock", True)
        assert _provider_stub.call_provider(
            "test",
            fallback_response="mock",
        ) == "mock"

    def test_force_mock_default_response(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_force_mock", True)
        assert "[Mock response" in _provider_stub.call_provider("test")

    def test_retry_succeeds_on_second_exact_attempt(self, monkeypatch):
        mock_router = MagicMock()
        response = MagicMock(provider="assigned", text="success after retry")
        mock_router.call_sync.side_effect = [
            AllProvidersExhaustedError("assigned provider unavailable"),
            response,
        ]
        monkeypatch.setattr(_provider_stub, "_real_router", mock_router)

        assert _provider_stub.call_provider("test", role="writer") == response.text
        assert mock_router.call_sync.call_count == 2

    def test_retry_exhaustion_never_uses_fallback_response(self, monkeypatch):
        mock_router = MagicMock()
        mock_router.call_sync.side_effect = AllProvidersExhaustedError("exhausted")
        monkeypatch.setattr(_provider_stub, "_real_router", mock_router)

        with pytest.raises(AllProvidersExhaustedError, match="exhausted"):
            _provider_stub.call_provider(
                "test",
                role="writer",
                fallback_response="must-not-return",
            )
        assert mock_router.call_sync.call_count == 3

    def test_non_retryable_error_propagates_once(self, monkeypatch):
        mock_router = MagicMock()
        mock_router.call_sync.side_effect = RuntimeError("unexpected")
        monkeypatch.setattr(_provider_stub, "_real_router", mock_router)

        with pytest.raises(RuntimeError, match="unexpected"):
            _provider_stub.call_provider(
                "test",
                role="writer",
                fallback_response="must-not-return",
            )
        assert mock_router.call_sync.call_count == 1

    def test_no_router_holds_even_with_fallback_response(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_real_router", None)

        with pytest.raises(AllProvidersExhaustedError, match="explicitly installed"):
            _provider_stub.call_provider(
                "test",
                fallback_response="must-not-return",
            )

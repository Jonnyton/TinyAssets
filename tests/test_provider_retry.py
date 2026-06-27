"""Tests for provider retry with tenacity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers import call as _provider_stub


class TestProviderRetry:
    @pytest.fixture(autouse=True)
    def _force_mock_off(self, monkeypatch):
        # Exception-safe save+restore: monkeypatch tears down even if a test
        # errors mid-execution, unlike setup_method/teardown_method which
        # leaves _FORCE_MOCK=False permanent on a mid-setup crash and
        # contaminates downstream tests (notably test_writer_tools).
        monkeypatch.setattr(_provider_stub, "_force_mock", False)

    def test_force_mock_bypasses_retry(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_force_mock", True)
        result = _provider_stub.call_provider("test", fallback_response="mock")
        assert result == "mock"

    def test_force_mock_default_response(self, monkeypatch):
        monkeypatch.setattr(_provider_stub, "_force_mock", True)
        result = _provider_stub.call_provider("test")
        assert "[Mock response" in result

    def test_retry_succeeds_on_second_attempt(self):
        """Simulate transient exhaustion that clears on retry."""
        mock_router = MagicMock()
        mock_response = MagicMock()
        mock_response.provider = "test-provider"
        mock_response.text = "success after retry"

        # First call raises exhaustion, second succeeds
        mock_router.call_sync.side_effect = [
            AllProvidersExhaustedError("all exhausted"),
            mock_response,
        ]

        orig_router = _provider_stub._real_router
        _provider_stub._real_router = mock_router
        try:
            result = _provider_stub.call_provider("test prompt", role="writer")
            assert result == "success after retry"
            assert mock_router.call_sync.call_count == 2
        finally:
            _provider_stub._real_router = orig_router

    def test_retry_exhausted_falls_to_fallback(self):
        """After 3 retry attempts, falls back to fallback_response."""
        mock_router = MagicMock()
        mock_router.call_sync.side_effect = AllProvidersExhaustedError("exhausted")

        orig_router = _provider_stub._real_router
        _provider_stub._real_router = mock_router
        try:
            result = _provider_stub.call_provider(
                "test", role="writer", fallback_response="fallback text"
            )
            assert result == "fallback text"
            # Should have retried 3 times
            assert mock_router.call_sync.call_count == 3
        finally:
            _provider_stub._real_router = orig_router

    def test_retry_exhausted_no_fallback_raises(self):
        """After exhaustion with no fallback, raise the real provider error."""
        mock_router = MagicMock()
        mock_router.call_sync.side_effect = AllProvidersExhaustedError("exhausted")

        orig_router = _provider_stub._real_router
        _provider_stub._real_router = mock_router
        try:
            with pytest.raises(AllProvidersExhaustedError, match="exhausted"):
                _provider_stub.call_provider("test", role="writer")
            assert mock_router.call_sync.call_count == 3
        finally:
            _provider_stub._real_router = orig_router

    def test_no_router_without_fallback_raises(self):
        """No router and no fallback must fail loudly, not return empty text."""
        orig_router = _provider_stub._real_router
        _provider_stub._real_router = None
        try:
            with pytest.raises(AllProvidersExhaustedError, match="No provider router"):
                _provider_stub.call_provider("test", role="writer")
        finally:
            _provider_stub._real_router = orig_router

    def test_non_retryable_error_does_not_retry(self):
        """Non-AllProvidersExhaustedError should not trigger retry."""
        mock_router = MagicMock()
        mock_router.call_sync.side_effect = RuntimeError("unexpected")

        orig_router = _provider_stub._real_router
        _provider_stub._real_router = mock_router
        try:
            result = _provider_stub.call_provider(
                "test", role="writer", fallback_response="fb"
            )
            assert result == "fb"
            # Only called once — no retry on generic RuntimeError
            assert mock_router.call_sync.call_count == 1
        finally:
            _provider_stub._real_router = orig_router

    def test_no_router_uses_fallback(self):
        """When _real_router is None, goes straight to fallback."""
        orig_router = _provider_stub._real_router
        _provider_stub._real_router = None
        try:
            result = _provider_stub.call_provider(
                "test", fallback_response="no router fallback"
            )
            assert result == "no router fallback"
        finally:
            _provider_stub._real_router = orig_router

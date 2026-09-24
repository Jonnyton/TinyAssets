"""Provider stub registration tests.

Guards the boot-time registration block in
``domains/fantasy_daemon/phases/_provider_stub.py`` so Gemini + Groq
registration stays wired after future refactors.

Prod was previously effectively zero-deep on provider fallback because
Gemini + Groq were named in the router chain but never registered. This
test file locks in the registration call pattern.
"""
from __future__ import annotations

import importlib
import sys

import pytest

from tests.support.provider_import import isolated_provider_import


def _reload_stub():
    """Force a fresh import of the stub so module-level registration reruns."""
    mod_name = "tinyassets.providers.call"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.fixture
def reset_stub():
    with isolated_provider_import():
        yield


class TestGeminiGroqRegistration:
    def test_gemini_never_registered_from_a_host_key(
        self, monkeypatch, reset_stub
    ):
        """Hard Rule 15: a host key plus the retired switch registers nothing."""
        pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-gemini")
        monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "gemini-free" not in stub._real_router.available_providers

    def test_groq_never_registered_from_a_host_key(
        self, monkeypatch, reset_stub
    ):
        pytest.importorskip("groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-key-groq")
        monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "groq-free" not in stub._real_router.available_providers

    def test_gemini_skipped_without_key(self, monkeypatch, reset_stub):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "gemini-free" not in stub._real_router.available_providers

    def test_groq_skipped_without_key(self, monkeypatch, reset_stub):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "groq-free" not in stub._real_router.available_providers

    def test_stub_importable_even_when_all_providers_fail(
        self, monkeypatch, reset_stub
    ):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        stub = _reload_stub()

        assert stub is not None
        assert hasattr(stub, "call_provider")

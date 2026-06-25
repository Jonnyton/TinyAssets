"""Provider stub registration tests for GrokProvider (task #11).

Mirrors `tests/test_provider_stub_registration.py` shape but targets the
GrokProvider registration block. Locks in the registration call so a
future refactor doesn't silently drop Grok from the provider chain.

Prod effective provider depth pre-#11 = 2 (Gemini + Groq). After #11,
depth = 3 with Grok on the xAI family, broadening judge diversity.
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _reload_stub():
    mod_name = "workflow.providers.call"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.fixture
def reset_stub():
    mod_name = "workflow.providers.call"
    saved = sys.modules.pop(mod_name, None)
    yield
    sys.modules.pop(mod_name, None)
    if saved is not None:
        sys.modules[mod_name] = saved


class TestGrokRegistration:
    def test_grok_registered_when_key_and_sdk_present(
        self, monkeypatch, reset_stub
    ):
        pytest.importorskip("openai")
        monkeypatch.setenv("XAI_API_KEY", "test-key-grok")

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "grok-free" in stub._real_router.available_providers

    def test_grok_skipped_without_key(self, monkeypatch, reset_stub):
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "grok-free" not in stub._real_router.available_providers

    def test_grok_skipped_when_key_is_empty_string(
        self, monkeypatch, reset_stub
    ):
        monkeypatch.setenv("XAI_API_KEY", "")

        stub = _reload_stub()

        assert stub._real_router is not None
        assert "grok-free" not in stub._real_router.available_providers

    def test_stub_importable_even_when_grok_sdk_missing(
        self, monkeypatch, reset_stub
    ):
        """If openai SDK import fails, GrokProvider init raises
        ProviderUnavailableError — the stub must catch and continue."""
        monkeypatch.setenv("XAI_API_KEY", "test-key-grok")
        # Force the openai import to fail inside GrokProvider.__init__
        # by removing it from sys.modules so the `try: import openai`
        # block re-imports; then block the import.
        import builtins
        real_import = builtins.__import__

        def _blocked(name, *args, **kwargs):
            if name == "openai" or name.startswith("openai."):
                raise ImportError("openai not installed (test stub)")
            return real_import(name, *args, **kwargs)

        # Drop any cached openai module so the next import hits our block.
        for key in list(sys.modules):
            if key == "openai" or key.startswith("openai."):
                sys.modules.pop(key, None)
        monkeypatch.setattr(builtins, "__import__", _blocked)

        stub = _reload_stub()

        assert stub is not None
        assert hasattr(stub, "call_provider")
        assert stub._real_router is not None
        assert "grok-free" not in stub._real_router.available_providers

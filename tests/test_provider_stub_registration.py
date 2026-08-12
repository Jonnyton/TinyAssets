"""Ambient API keys must never construct a process-global provider router."""

from __future__ import annotations


def test_api_key_environment_never_materializes_ambient_router(monkeypatch):
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.setenv(name, f"host-{name.lower()}")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")

    import importlib

    call = importlib.import_module("tinyassets.providers.call")

    assert call._real_router is None
    assert callable(call.call_provider)

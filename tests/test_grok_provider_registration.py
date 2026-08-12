"""Grok host credentials do not become universe execution authority."""

from __future__ import annotations


def test_grok_host_key_never_registers_process_global_router(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "host-grok-key")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")

    import importlib

    call = importlib.import_module("tinyassets.providers.call")

    assert call._real_router is None

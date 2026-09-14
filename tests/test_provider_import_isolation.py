"""Registration probes must not change the bridge used by later workflows."""

import importlib
import sys
from types import ModuleType

import pytest

import tinyassets.providers as providers
from tests.support.provider_import import isolated_provider_import


@pytest.mark.parametrize("present", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_provider_boot_probe_restores_both_import_paths(monkeypatch, present, raises):
    name = "tinyassets.providers.call"
    original = ModuleType(name)
    original.force_mock = True
    if present:
        monkeypatch.setitem(sys.modules, name, original)
        monkeypatch.setattr(providers, "call", original)
    else:
        monkeypatch.delitem(sys.modules, name)
        monkeypatch.delattr(providers, "call")
    replacement = ModuleType(name)
    replacement.force_mock = False

    def probe():
        with isolated_provider_import():
            assert name not in sys.modules
            assert "call" not in vars(providers)
            sys.modules[name] = replacement
            providers.call = replacement
            if raises:
                raise RuntimeError("synthetic boot failure")

    if raises:
        with pytest.raises(RuntimeError, match="synthetic boot failure"):
            probe()
    else:
        probe()
    if present:
        from tinyassets.providers import call

        assert call is original
        assert importlib.import_module(name) is original
        assert call.force_mock is True
    else:
        assert name not in sys.modules
        assert "call" not in vars(providers)

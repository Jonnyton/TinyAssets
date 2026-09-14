"""Isolate provider bridge boot tests without splitting Python module identity."""

import sys
from contextlib import contextmanager

import tinyassets.providers as providers


@contextmanager
def isolated_provider_import():
    """Restore both import lookup paths, including on failed boot or test skip."""
    name = "tinyassets.providers.call"
    missing = object()
    saved_module = sys.modules.pop(name, missing)
    saved_attribute = vars(providers).pop("call", missing)
    try:
        yield
    finally:
        sys.modules.pop(name, None)
        vars(providers).pop("call", None)
        if saved_module is not missing:
            sys.modules[name] = saved_module
        if saved_attribute is not missing:
            providers.call = saved_attribute

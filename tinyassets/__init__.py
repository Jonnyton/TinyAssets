"""TinyAssets -- goal-agnostic daemon engine on LangGraph."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.2.0"

__all__ = [
    "Domain",
    "DomainConfig",
    "DomainRegistry",
    "auto_register",
    "default_registry",
    "discover_domains",
]

_LAZY_IMPORTS = {
    "Domain": ("tinyassets.protocols", "Domain"),
    "DomainConfig": ("tinyassets.protocols", "DomainConfig"),
    "DomainRegistry": ("tinyassets.registry", "DomainRegistry"),
    "auto_register": ("tinyassets.discovery", "auto_register"),
    "default_registry": ("tinyassets.registry", "default_registry"),
    "discover_domains": ("tinyassets.discovery", "discover_domains"),
}


def __getattr__(name: str) -> Any:
    """Load the public convenience API only when a caller requests it.

    Keeping package initialization side-effect free lets operational modules
    such as ``tinyassets.storage.rotation`` run from the deliberately small
    host-uptime bundle without importing the full application graph.
    """
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'tinyassets' has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_IMPORTS))

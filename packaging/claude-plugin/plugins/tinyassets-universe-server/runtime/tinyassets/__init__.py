"""TinyAssets -- goal-agnostic daemon engine on LangGraph."""

__version__ = "0.2.0"

from tinyassets.discovery import auto_register, discover_domains
from tinyassets.protocols import Domain, DomainConfig
from tinyassets.registry import DomainRegistry, default_registry

__all__ = [
    "Domain",
    "DomainConfig",
    "DomainRegistry",
    "auto_register",
    "default_registry",
    "discover_domains",
]

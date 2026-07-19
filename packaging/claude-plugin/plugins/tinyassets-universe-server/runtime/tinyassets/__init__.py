"""TinyAssets -- goal-agnostic daemon engine on LangGraph."""

from tinyassets.control_plane import scrub_control_plane_provider_credentials

# Package import is the earliest shared bootstrap for every TinyAssets app and
# daemon entrypoint.  On a control-plane host, quarantine provider credentials
# before importing any module that could launch a child process.
scrub_control_plane_provider_credentials()

__version__ = "0.2.0"

from tinyassets.discovery import auto_register, discover_domains  # noqa: E402
from tinyassets.protocols import Domain, DomainConfig  # noqa: E402
from tinyassets.registry import DomainRegistry, default_registry  # noqa: E402

__all__ = [
    "Domain",
    "DomainConfig",
    "DomainRegistry",
    "auto_register",
    "default_registry",
    "discover_domains",
]

"""Domain auto-discovery for the TinyAssets engine.

Two discovery sources, unioned and deduplicated:

1. ``importlib.metadata.entry_points(group="tinyassets.domains")`` —
   the primary path. Any package declaring
   ``[project.entry-points."tinyassets.domains"] name = "mod.path:Class"``
   in its ``pyproject.toml`` is discoverable when pip-installed. This
   is how third-party domains reach the registry without needing to
   sit inside the repo tree.
2. Filesystem scan of ``domains/<name>/skill.py`` next to the
   ``tinyassets/`` package — the editable-dev-install fallback. Same
   shape discovery had before entry points landed (Task #22 /
   modularity audit §3.2); kept so an editable checkout without
   ``pip install -e .`` still finds domains.

Both sources coexist; the union is deduped by domain name. Canonical
names win — the entry-point table keys the registry when both report
the same skill.

Usage
-----
from tinyassets.discovery import discover_domains, auto_register
from tinyassets.registry import default_registry

domains = discover_domains()
auto_register(default_registry)

# Now all found domains are registered in default_registry
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "tinyassets.domains"


def _discover_entry_point_domains() -> dict[str, str]:
    """Read ``tinyassets.domains`` entry points from installed packages.

    Returns a mapping of domain-name -> ``"module:attr"`` import path.
    Empty mapping on any failure (never raises); the filesystem
    fallback keeps discovery working for editable-dev checkouts.
    """
    found: dict[str, str] = {}
    try:
        # ``entry_points(group=...)`` is the Python 3.10+ shape.
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # noqa: BLE001 - broad: metadata errors vary
        logger.debug(
            "entry_points(group=%r) lookup failed", ENTRY_POINT_GROUP,
            exc_info=True,
        )
        return found

    for ep in eps:
        name = (ep.name or "").strip()
        value = getattr(ep, "value", "") or ""
        if not name or not value:
            continue
        if name in found:
            logger.debug(
                "Duplicate entry-point for %r in %s; keeping first",
                name, ENTRY_POINT_GROUP,
            )
            continue
        found[name] = value
        logger.debug("Discovered entry-point domain: %s -> %s", name, value)
    return found


def _discover_filesystem_domains() -> list[str]:
    """Scan ``domains/<name>/skill.py`` next to the ``tinyassets/`` package.

    Editable-dev-install fallback. Returns sorted domain-name list.
    """
    workflow_dir = Path(__file__).parent.parent
    domains_dir = workflow_dir / "domains"

    if not domains_dir.exists():
        logger.debug("domains/ directory not found at %s", domains_dir)
        return []

    names: list[str] = []
    for domain_path in sorted(domains_dir.iterdir()):
        if not domain_path.is_dir():
            continue
        if (domain_path / "skill.py").exists():
            names.append(domain_path.name)
            logger.debug("Discovered filesystem domain: %s", domain_path.name)
    return names


def discover_domains() -> list[str]:
    """Return the union of entry-point and filesystem-discovered domains.

    Entry points are the primary source (pip-installed packages). The
    filesystem scan stays as fallback for editable checkouts that
    haven't run ``pip install -e .``. Results are sorted and
    deduplicated.
    """
    ep_domains = set(_discover_entry_point_domains().keys())
    fs_domains = set(_discover_filesystem_domains())
    return sorted(ep_domains | fs_domains)


def _load_domain_class(
    domain_name: str, ep_target: str | None,
) -> type | None:
    """Resolve a Domain class for ``domain_name`` via entry point or heuristic.

    If ``ep_target`` is an entry-point target string (``"module:attr"``),
    it's the authoritative path. Otherwise falls back to importing
    ``domains.<name>.skill`` and scanning for a ``*Domain`` class —
    the pre-entry-point heuristic kept for editable dev installs.
    """
    # 1. Entry-point target wins when present.
    if ep_target:
        module_path, _, attr = ep_target.partition(":")
        if not module_path or not attr:
            logger.warning(
                "Entry-point target %r for %r is not 'module:attr'",
                ep_target, domain_name,
            )
            return None
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.warning(
                "Failed to import entry-point module %s for %s: %s",
                module_path, domain_name, e,
            )
            return None
        cls = getattr(module, attr, None)
        if not isinstance(cls, type):
            logger.warning(
                "Entry-point %r did not resolve to a class (got %r)",
                ep_target, type(cls).__name__,
            )
            return None
        return cls

    # 2. Filesystem fallback — import ``domains.<name>.skill`` and pick
    #    the first ``*Domain`` class. Matches pre-entry-point behavior.
    module_path = f"domains.{domain_name}.skill"
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        logger.warning("Failed to import domain %s: %s", domain_name, e)
        return None

    class_name: str | None = None
    if hasattr(module, "FantasyAuthorDomain") and domain_name == "fantasy_author":
        class_name = "FantasyAuthorDomain"
    elif hasattr(module, "ResearchProbeDomain") and domain_name == "research_probe":
        class_name = "ResearchProbeDomain"
    else:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and attr_name.endswith("Domain")
                and attr_name != "Domain"
            ):
                class_name = attr_name
                break

    if class_name is None:
        logger.warning(
            "No domain class found in %s (expected %sDomain or Domain export)",
            module_path,
            "".join(word.capitalize() for word in domain_name.split("_")),
        )
        return None

    return getattr(module, class_name)


def auto_register(registry: Any) -> None:
    """Discover and auto-register all domains in the registry.

    Per-domain resolution order:
      1. If ``tinyassets.domains`` entry-point table names the domain,
         import its ``"module:attr"`` target directly.
      2. Otherwise fall back to scanning ``domains.<name>.skill`` for a
         ``*Domain`` class (pre-entry-point heuristic). Keeps editable
         dev checkouts working without a pip install.

    If a domain fails to import or register, a warning is logged and
    the process continues with the next domain.
    """
    ep_targets = _discover_entry_point_domains()
    discovered = discover_domains()

    if not discovered:
        logger.debug("No domains discovered")
        return

    for domain_name in discovered:
        try:
            domain_class = _load_domain_class(
                domain_name, ep_targets.get(domain_name),
            )
            if domain_class is None:
                continue
            registry.register(domain_class())
            logger.info(
                "Registered domain %s via %s",
                domain_name,
                "entry-point" if domain_name in ep_targets else "filesystem",
            )
        except Exception as e:  # noqa: BLE001 - isolate per-domain failure
            logger.warning("Failed to register domain %s: %s", domain_name, e)


__all__ = ["discover_domains", "auto_register", "ENTRY_POINT_GROUP"]

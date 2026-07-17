"""Domain-trusted opaque node registry (Phase D).

Engine-side storage for opaque node callables owned by domains. The
engine (`tinyassets/graph_compiler.py`) resolves registered callables at
compile time; domains (e.g. `fantasy_author/branch_registrations.py`)
populate the registry at import time.

The engine never imports any specific domain — domains are plugins that
call ``register_domain_callable`` from their own package-level modules.
Matches PLAN.md's "engine is infrastructure, not topology" principle.

Registration is idempotent: re-registering the same
``(domain_id, node_id)`` overwrites silently with a debug log. Tests
and re-import scenarios (e.g. ``importlib.reload``) thus stay
side-effect-free. A double-register that ships different callables
would indicate an actual bug in the domain layer; the debug log is
the footprint for investigation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


_DomainCallable = Callable[[dict[str, Any]], dict[str, Any]]

# Codex S3 r13 #2: the CLOSED capability vocabulary. A registration whose declared
# capability is outside this set is a typo / mistake (e.g. ``repo_raed``) and is
# treated as UNCLASSIFIED PERMANENTLY (stored as None → fails closed), never
# silently accepted. Mirrors the community-callable classes in
# ``tinyassets.sandbox_policy`` (kept as literals here to avoid an import cycle).
VALID_CAPABILITIES: frozenset[str] = frozenset({
    "text", "repo_read", "repo_exec", "coding", "source_exec",
})

_REGISTRY: dict[tuple[str, str], _DomainCallable] = {}
# Codex S3 r12 #1: an opaque callable's SANDBOX CAPABILITY (what it actually
# does — read/exec a repo, run commands, or pure text transform) is invisible to
# the node-field classifier in ``sandbox_policy.node_capability``. Bind it to the
# registered adapter here so the graph choke-point + validate + enqueue can
# classify an opaque node by its adapter type. A callable registered WITHOUT a
# declared capability (or with an unknown one) is UNCLASSIFIED and fails closed
# (never defaults to text).
_CAPABILITY_REGISTRY: dict[tuple[str, str], str | None] = {}
# Codex S3 r13 #1: the HOST-ONLY vs COMMUNITY-CALLABLE trust boundary. A HOST-ONLY
# callable is daemon-internal (e.g. ``universe_cycle_wrapper``, which runs the
# full daemon graph and reaches filesystem / SQLite / provider ops). A user-
# authored branch may NOT select / compile / queue / execute it — only a TRUSTED
# (daemon) compile may. A COMMUNITY-CALLABLE adapter (host_only=False) may be
# selected by a user branch, with its capability enforced by the classifier.
_HOST_ONLY_REGISTRY: dict[tuple[str, str], bool] = {}
_DOMAIN_BRANCH_SLUGS: dict[str, set[str]] = {}


@dataclass(frozen=True, slots=True)
class EpisodicCoordinateShape:
    """Domain-owned coordinate fields for episodic memory rows."""

    domain_id: str
    coordinate_fields: tuple[str, ...]
    sequence_field: str | None = None


_EPISODIC_COORDINATE_SHAPES: dict[str, EpisodicCoordinateShape] = {}


def register_domain_callable(
    domain_id: str,
    node_id: str,
    fn: _DomainCallable,
    *,
    capability: str | None = None,
    host_only: bool = False,
) -> None:
    """Register a domain-trusted opaque node callable.

    ``fn`` must accept the current state dict and return a dict of
    updates. Called from `_build_opaque_node` inside the compiler;
    must be safe under LangGraph's execution model (no hidden
    globals, no blocking I/O beyond domain contract).

    ``capability`` declares the adapter's SANDBOX CLASS — one of
    :data:`VALID_CAPABILITIES` (``text`` / ``repo_read`` / ``repo_exec`` /
    ``coding`` / ``source_exec``; Codex S3 r12 #1). A repo-touching adapter fails
    closed until the per-job sandbox runner exists; a ``text`` adapter runs. An
    adapter registered with ``capability=None`` — OR an UNKNOWN capability string
    (a typo like ``repo_raed``; Codex S3 r13 #2) — is UNCLASSIFIED and the graph
    choke-point refuses it (fail closed); an unknown value is treated as
    unclassified PERMANENTLY, never accepted.

    ``host_only`` marks a DAEMON-INTERNAL callable (Codex S3 r13 #1): a
    user-authored branch may NOT select / compile / queue / execute it — only a
    trusted (daemon) compile may. Community-callable adapters (the default) may be
    selected by user branches, with capability enforced by the classifier.
    """
    key = (domain_id, node_id)
    if key in _REGISTRY and _REGISTRY[key] is not fn:
        logger.debug(
            "Domain callable re-registered for %s; replacing previous entry.",
            key,
        )
    _REGISTRY[key] = fn
    normalized_cap = str(capability).strip().lower() if capability else None
    if normalized_cap is not None and normalized_cap not in VALID_CAPABILITIES:
        # Codex S3 r13 #2: an unknown capability is a typo/mistake — do NOT accept
        # it (it would slip past the reject-unknown node-side gate and execute
        # when a runner appears). Treat as unclassified permanently (fail closed).
        logger.warning(
            "Domain callable %s registered with UNKNOWN capability %r; "
            "treating as UNCLASSIFIED (fail closed). Valid: %s",
            key, capability, sorted(VALID_CAPABILITIES),
        )
        normalized_cap = None
    _CAPABILITY_REGISTRY[key] = normalized_cap
    _HOST_ONLY_REGISTRY[key] = bool(host_only)


def resolve_domain_callable(
    domain_id: str,
    node_id: str,
) -> _DomainCallable | None:
    """Return the registered callable, or None if unregistered."""
    return _REGISTRY.get((domain_id, node_id))


def resolve_domain_capability(
    domain_id: str,
    node_id: str,
) -> str | None:
    """Return the registered opaque adapter's declared sandbox capability.

    ``None`` means either (a) not a registered opaque adapter, or (b) registered
    with no declared capability OR an unknown/typo'd one (UNCLASSIFIED). Callers
    distinguish (a) from (b) via :func:`resolve_domain_callable` (non-None ⇒ it is
    an opaque adapter), and an opaque adapter whose capability is ``None`` MUST
    fail closed.
    """
    return _CAPABILITY_REGISTRY.get((domain_id, node_id))


def resolve_domain_host_only(
    domain_id: str,
    node_id: str,
) -> bool:
    """Return True when the registered opaque adapter is HOST-ONLY (daemon-
    internal). A user-authored branch may not select/compile/queue/execute it."""
    return bool(_HOST_ONLY_REGISTRY.get((domain_id, node_id), False))


def clear_registry() -> None:
    """Testing-only helper; drops all registrations."""
    _REGISTRY.clear()
    _CAPABILITY_REGISTRY.clear()
    _HOST_ONLY_REGISTRY.clear()
    _EPISODIC_COORDINATE_SHAPES.clear()
    _DOMAIN_BRANCH_SLUGS.clear()


def register_domain_branch_slug(domain_id: str, branch_slug: str) -> None:
    """Register a Branch slug owned by a domain.

    Goal-pool subscribers use this to discover always-available domain
    branches without core producer code naming any one domain.
    """
    clean_domain = domain_id.strip()
    clean_slug = branch_slug.strip()
    if not clean_domain or not clean_slug:
        return
    _DOMAIN_BRANCH_SLUGS.setdefault(clean_domain, set()).add(clean_slug)


def registered_domain_branch_slugs(domain_id: str = "") -> tuple[str, ...]:
    """Return registered Branch slugs, optionally limited to one domain."""
    clean_domain = domain_id.strip()
    if clean_domain:
        return tuple(sorted(_DOMAIN_BRANCH_SLUGS.get(clean_domain, set())))
    slugs: set[str] = set()
    for domain_slugs in _DOMAIN_BRANCH_SLUGS.values():
        slugs.update(domain_slugs)
    return tuple(sorted(slugs))


def clear_domain_branch_slugs() -> None:
    """Testing-only helper; drops registered domain Branch slugs."""
    _DOMAIN_BRANCH_SLUGS.clear()


def register_episodic_coordinate_shape(
    domain_id: str,
    coordinate_fields: tuple[str, ...] | list[str],
    *,
    sequence_field: str | None = None,
) -> None:
    """Register the domain-owned coordinate fields for episodic rows.

    The shared episodic tables stay domain-neutral; this registry names
    which optional payload fields a domain uses to interpret row order and
    identity.
    """
    _EPISODIC_COORDINATE_SHAPES[domain_id] = EpisodicCoordinateShape(
        domain_id=domain_id,
        coordinate_fields=tuple(coordinate_fields),
        sequence_field=sequence_field,
    )


def resolve_episodic_coordinate_shape(
    domain_id: str,
) -> EpisodicCoordinateShape | None:
    """Return a registered episodic coordinate shape, if any."""
    return _EPISODIC_COORDINATE_SHAPES.get(domain_id)

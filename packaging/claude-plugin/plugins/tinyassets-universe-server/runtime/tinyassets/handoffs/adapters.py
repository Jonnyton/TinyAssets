"""The handoff adapter seam — one registry, no second network or credential path.

Task 5.4 of ``openspec/changes/complete-independent-full-platform-targets``
(capability ``real-world-handoffs-and-outcomes``).

A handoff never opens a socket. It resolves a *registered adapter* by the name
its declaration carries and hands it a :class:`HandoffRequest`; the adapter is a
canonical ``tinyassets/effectors/`` entry point that already owns its own
capability/credential resolution. That is what makes "reuse the canonical
external-effect adapter and receipt boundary rather than create a second
network/credential path" structurally true rather than a claim: there is no
transport code in this package to bypass the boundary with.

**The registry starts empty, and that is deliberate.** No adapter is registered
at import time, so a deployment that has not explicitly bound one gets
``adapter_not_registered`` and executes nothing. A default stub registered "for
convenience" would be exactly the mock-that-looks-like-real-output this project
forbids.

**Credential blindness.** :class:`HandoffRequest` refuses to be constructed with
credential material anywhere in its payload, recursively. The adapter resolves
its own secret from the capability boundary; the handoff layer never sees, logs,
or journals one.

**Uncertainty is a first-class reply.** An adapter that cannot prove whether the
destination received the payload raises
:class:`~tinyassets.effectors.outbound_boundary.AmbiguousEffectOutcome` — the
same exception the landed outbound boundary already reconciles — so the receipt
stays uncertain instead of being retried under a fresh key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tinyassets.handoffs.models import (
    HandoffValidationError,
    reject_credential_material,
)

#: Provider-proven states an adapter may claim. ``submitted`` means the payload
#: was transported; only ``accepted`` may be claimed when the provider response
#: contract proves destination acceptance, and neither implies any later
#: real-world impact.
ADAPTER_STATES: frozenset[str] = frozenset({"submitted", "accepted", "rejected"})


@dataclass(frozen=True)
class HandoffRequest:
    """The bounded, credential-free effect request handed to an adapter."""

    effect_key: str
    adapter: str
    adapter_action: str
    destination: str
    branch_version_id: str
    content_hash: str
    run_id: str
    output_field: str
    output_sha256: str
    payload: Any = None
    evidence_contract: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reject_credential_material(self.payload, where="handoff payload")
        reject_credential_material(
            self.evidence_contract, where="handoff evidence contract"
        )

    def redacted(self) -> dict[str, Any]:
        """A display form that names the payload without reproducing it.

        Used by the dry-run path and by journalled evidence: a receipt row is
        durable and readable, so it records the payload's shape and digest, not
        its bytes.
        """
        return {
            "effect_key": self.effect_key,
            "adapter": self.adapter,
            "adapter_action": self.adapter_action,
            "destination": self.destination,
            "branch_version_id": self.branch_version_id,
            "content_hash": self.content_hash,
            "run_id": self.run_id,
            "output_field": self.output_field,
            "output_sha256": self.output_sha256,
            "payload_type": type(self.payload).__name__,
            "evidence_contract": dict(self.evidence_contract),
        }


@dataclass(frozen=True)
class HandoffResult:
    """What an adapter proved. ``state`` is the provider's claim, not ours."""

    state: str
    external_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in ADAPTER_STATES:
            raise HandoffValidationError(
                f"adapter state must be one of {sorted(ADAPTER_STATES)}, "
                f"got {self.state!r}"
            )
        if self.state == "accepted" and not (self.external_id or "").strip():
            # "Accepted" without a stable external identifier is unverifiable
            # later, which would let a transport success masquerade as a durable
            # destination acceptance.
            raise HandoffValidationError(
                "an accepted handoff must carry the provider's stable external id"
            )


HandoffAdapter = Callable[[HandoffRequest], HandoffResult]

_REGISTRY: dict[str, HandoffAdapter] = {}


def register_adapter(name: str, adapter: HandoffAdapter) -> None:
    """Bind a declared adapter name to a canonical effector entry point."""
    key = (name or "").strip()
    if not key:
        raise HandoffValidationError("adapter name must be non-empty")
    if not callable(adapter):
        raise HandoffValidationError(f"adapter {key!r} must be callable")
    _REGISTRY[key] = adapter


def unregister_adapter(name: str) -> None:
    _REGISTRY.pop((name or "").strip(), None)


def registered_adapters() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def resolve_adapter(name: str) -> HandoffAdapter:
    """Resolve a declared adapter, failing closed when none is bound."""
    key = (name or "").strip()
    adapter = _REGISTRY.get(key)
    if adapter is None:
        raise HandoffValidationError(
            f"adapter {key!r} is not registered; a handoff cannot execute "
            "without a canonical effector bound to its declared adapter"
        )
    return adapter


__all__ = [
    "ADAPTER_STATES",
    "HandoffAdapter",
    "HandoffRequest",
    "HandoffResult",
    "register_adapter",
    "registered_adapters",
    "resolve_adapter",
    "unregister_adapter",
]

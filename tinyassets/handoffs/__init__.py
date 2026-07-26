"""Real-world handoffs — declared external-effect outputs and their outcomes.

Capability ``real-world-handoffs-and-outcomes`` of
``openspec/changes/complete-independent-full-platform-targets`` (tasks 5.1, 5.2,
5.4).

Module map:

``models``
    Pure vocabulary, declarations, records, the closed transition graph, and the
    system-derived effect identity. No I/O.
``store``
    Owner-scoped persistence in ``.runs.db``, colocated with — and extending —
    the existing ``outcome_event`` registry rather than replacing it.
``authority``
    Authority resolved only from authenticated request subjects and persisted
    run/version records; destination consent from the canonical grant store.
``adapters``
    The single seam out. Starts empty and fails closed; the registered adapter is
    a canonical ``tinyassets/effectors/`` entry point that owns its own
    credential.
``service``
    Behavior plus the ``extensions`` dispatch table. No new advertised MCP handle.

Not here, on purpose: inbound webhook transport and provider polling (task 5.3).
That work needs a host decision on the inbound receiver it would share with the
outbound-boundary inbox URLs, so this lane left it unbuilt rather than shipping a
receiver that cannot be reached.
"""

from tinyassets.handoffs.models import (
    EVIDENCE_LEVELS,
    HANDOFF_STATES,
    LEGAL_TRANSITIONS,
    HandoffAccessError,
    HandoffAuthorityError,
    HandoffConfirmationRequired,
    HandoffConflictError,
    HandoffDeclaration,
    HandoffError,
    HandoffRecord,
    HandoffValidationError,
)
from tinyassets.handoffs.store import HandoffStore

__all__ = [
    "EVIDENCE_LEVELS",
    "HANDOFF_STATES",
    "LEGAL_TRANSITIONS",
    "HandoffAccessError",
    "HandoffAuthorityError",
    "HandoffConfirmationRequired",
    "HandoffConflictError",
    "HandoffDeclaration",
    "HandoffError",
    "HandoffRecord",
    "HandoffStore",
    "HandoffValidationError",
]

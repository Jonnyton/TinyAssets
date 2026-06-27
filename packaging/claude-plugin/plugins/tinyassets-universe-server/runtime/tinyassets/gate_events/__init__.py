"""tinyassets.gate_events — Real-world outcome attestation primitives.

Schema (schema.py): gate_event + gate_event_cite DDL, GateEvent/GateEventCite dataclasses.
Store (store.py): attest, verify, dispute, retract, get, list storage functions.

Attribution language invariant (load-bearing for all callers):
  Always say "this branch's output was cited in this gate event",
  never "this branch caused the outcome."
"""

from __future__ import annotations

from tinyassets.gate_events.schema import (
    GATE_EVENT_SCHEMA,
    VERIFICATION_STATUSES,
    GateEvent,
    GateEventCite,
    VerificationStatus,
    migrate_gate_event_schema,
)
from tinyassets.gate_events.store import (
    attest_gate_event,
    dispute_gate_event,
    get_gate_event,
    leaderboard_by_gate_events,
    list_gate_events,
    retract_gate_event,
    verify_gate_event,
)

__all__ = [
    "GATE_EVENT_SCHEMA",
    "VERIFICATION_STATUSES",
    "GateEvent",
    "GateEventCite",
    "VerificationStatus",
    "attest_gate_event",
    "dispute_gate_event",
    "get_gate_event",
    "leaderboard_by_gate_events",
    "list_gate_events",
    "migrate_gate_event_schema",
    "retract_gate_event",
    "verify_gate_event",
]

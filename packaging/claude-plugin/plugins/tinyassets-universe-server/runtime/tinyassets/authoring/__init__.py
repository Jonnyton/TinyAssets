"""Node and evaluator authoring — owner-scoped draft sessions.

Capability owner for ``node-authoring-and-autoresearch`` §§ sessions, inspection,
edits, typed file I/O, sandboxed test runs, and explicit publication (tasks
4.1-4.3 of
``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets``).

Module map:

- :mod:`tinyassets.authoring.models` — records, the edit grammar, pure validation
- :mod:`tinyassets.authoring.store` — owner-scoped SQLite persistence (CAS)
- :mod:`tinyassets.authoring.io` — typed manifests and execution-scoped handles
- :mod:`tinyassets.authoring.sandbox` — budget / network / effect primitives
- :mod:`tinyassets.authoring.service` — session behavior + ``extensions`` actions

Not owned here: bounded autoresearch/optimization (task 4.4,
``tinyassets/autoresearch/``), the external-effect adapters and receipts
(``tinyassets/effectors/``, ``tinyassets/storage/external_write_receipts.py``),
and graph execution (``tinyassets/graph_compiler.py``).
"""

from __future__ import annotations

from tinyassets.authoring.models import (
    ARTIFACT_KINDS,
    ArtifactVersion,
    AuthoringAccessError,
    AuthoringConflictError,
    AuthoringError,
    AuthoringEvent,
    AuthoringSession,
    AuthoringValidationError,
    BudgetExceeded,
    ConfirmationRequired,
    ManifestViolation,
    SandboxDenied,
    ValidationIssue,
)

__all__ = [
    "ARTIFACT_KINDS",
    "ArtifactVersion",
    "AuthoringAccessError",
    "AuthoringConflictError",
    "AuthoringError",
    "AuthoringEvent",
    "AuthoringSession",
    "AuthoringValidationError",
    "BudgetExceeded",
    "ConfirmationRequired",
    "ManifestViolation",
    "SandboxDenied",
    "ValidationIssue",
]

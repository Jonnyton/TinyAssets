"""Handoff authority — resolved from persisted, authenticated records only.

Task 5.2 of ``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets``
(capability ``real-world-handoffs-and-outcomes``).

Every fact this module returns is read from something durable:

- the **subject** is the credential-validated request actor
  (``tinyassets.api.permissions.current_request_actor_id``), never
  ``UNIVERSE_SERVER_USER`` and never a caller-supplied ``author``/``actor``
  string. This is the same rule ``tinyassets/api/branches.py``'s
  ``_request_branch_actor`` established, for the same reason: a handoff moves a
  real-world effect, so an env fallback here would let an ambient process act as
  a user;
- the **source artifact** is the persisted run row plus its immutable branch
  version — the run's recorded owner is what confers authority, not the request;
- the **declaration** is parsed off the version snapshot, so destination and
  effect class are properties of the published artifact rather than the request;
- the **destination consent** is the canonical per-destination grant in
  ``tinyassets/storage/effector_consents.py``. No second consent surface.

Nothing here vends a credential. The adapter resolves its own from the
capability boundary; the handoff layer stays credential-blind.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tinyassets.handoffs.models import (
    HandoffAuthorityError,
    HandoffDeclaration,
    HandoffValidationError,
    find_declaration,
    output_digest,
)

#: Run states from which a handoff may be constructed. A handoff carries a real
#: output to the outside world, so an in-flight or failed run is refused: its
#: output is not final and re-running would change what was sent.
_ELIGIBLE_RUN_STATUSES: frozenset[str] = frozenset({"completed", "succeeded"})


def request_subject() -> str:
    """Return the credential-validated request subject.

    Raises rather than returning a synthetic subject: every caller of this module is
    about to touch external-effect authority, and a sentinel string that reads
    like an actor is exactly how an unauthenticated path acquires one.
    """
    from tinyassets.api.permissions import current_request_actor_id
    from tinyassets.principals import named_principal

    subject = named_principal(current_request_actor_id())
    if not subject:
        raise HandoffAuthorityError(
            "an authenticated account is required to initiate a handoff"
        )
    return subject


@dataclass(frozen=True)
class HandoffSource:
    """The persisted, authority-bearing source of one handoff."""

    subject: str
    run_id: str
    branch_def_id: str
    branch_version_id: str
    content_hash: str
    output_field: str
    output_value: Any
    output_sha256: str
    declaration: HandoffDeclaration

    def effect_summary(self) -> str:
        return self.declaration.effect_summary()


def _run_owner(run: dict[str, Any]) -> str:
    """The account that owns a run.

    ``owner_user_id`` is the authenticated binding and wins when present;
    ``actor`` is the legacy column and is only consulted when the run predates
    owner binding. An empty result means the run has no provable owner, which
    fails closed at the call site rather than matching any subject.
    """
    owner = str(run.get("owner_user_id") or "").strip()
    if owner:
        return owner
    from tinyassets.principals import named_principal

    return named_principal(run.get("actor"))


def resolve_source(
    *,
    subject: str,
    base_path: str | Path,
    run_id: str,
    branch_version_id: str,
    output_field: str,
    destination: str = "",
) -> HandoffSource:
    """Resolve and authorize the exact immutable version/run/output triple.

    Order matters: ownership of the run is proven before the version snapshot is
    read, and the declaration is resolved before any consent or credential path
    is reachable. A caller naming an undeclared output or a substituted
    destination fails here — task 5.2's "handoff initiation fails before
    credential vending or adapter execution".
    """
    from tinyassets.branch_versions import get_branch_version
    from tinyassets.runs import get_run

    run_id = (run_id or "").strip()
    branch_version_id = (branch_version_id or "").strip()
    if not run_id:
        raise HandoffValidationError("run_id is required")
    if not branch_version_id:
        raise HandoffValidationError("branch_version_id is required")

    run = get_run(base_path, run_id)
    if run is None:
        # Indistinguishable from "not yours" on purpose — see the store's
        # owner-scoping note.
        raise HandoffAuthorityError(f"run {run_id!r} is not available to this account")
    owner = _run_owner(run)
    if not owner or owner != subject:
        raise HandoffAuthorityError(f"run {run_id!r} is not available to this account")
    if str(run.get("status") or "") not in _ELIGIBLE_RUN_STATUSES:
        raise HandoffValidationError(
            f"run {run_id!r} is {run.get('status')!r}; a handoff requires a "
            "completed run whose output is final"
        )

    version = get_branch_version(base_path, branch_version_id)
    if version is None:
        raise HandoffAuthorityError(
            f"branch version {branch_version_id!r} is not available to this account"
        )
    if version.branch_def_id != run.get("branch_def_id"):
        raise HandoffValidationError(
            f"run {run_id!r} did not come from branch version {branch_version_id!r}"
        )

    declaration = find_declaration(
        version.snapshot,
        output_field,
        destination=destination,
    )

    outputs = run.get("output") or {}
    if not isinstance(outputs, dict) or declaration.output_field not in outputs:
        raise HandoffValidationError(
            f"run {run_id!r} produced no {declaration.output_field!r} output; "
            "a handoff may only carry the exact declared output"
        )
    value = outputs[declaration.output_field]

    return HandoffSource(
        subject=subject,
        run_id=run_id,
        branch_def_id=version.branch_def_id,
        branch_version_id=branch_version_id,
        content_hash=version.content_hash,
        output_field=declaration.output_field,
        output_value=value,
        output_sha256=output_digest(value),
        declaration=declaration,
    )


def require_destination_consent(
    universe_dir: str | Path,
    *,
    sink: str,
    destination: str,
) -> None:
    """Require the canonical per-destination consent grant for this effect.

    Delegates to ``tinyassets/storage/effector_consents.py`` — exact-match,
    case-sensitive, wildcard-free — so a handoff cannot reach a destination the
    universe's owner never granted, and so there is exactly one consent surface
    to revoke.
    """
    from tinyassets.storage.effector_consents import is_consent_active

    if not is_consent_active(universe_dir, sink=sink, destination=destination):
        raise HandoffAuthorityError(
            f"no active consent grant for {sink}:{destination}; grant it with "
            "grant_effector_consent before this handoff can execute"
        )


__all__ = [
    "HandoffSource",
    "request_subject",
    "require_destination_consent",
    "resolve_source",
]

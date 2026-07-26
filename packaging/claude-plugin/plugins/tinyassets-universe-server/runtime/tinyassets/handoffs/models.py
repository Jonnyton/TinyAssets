"""Handoff-effect lifecycle models — declarations, records, transitions, and the
pure validation/identity helpers the store and service share.

Task 5.1 of ``openspec/changes/complete-independent-full-platform-targets``
(capability ``real-world-handoffs-and-outcomes``).

This module is **pure**: no I/O, no clock reads beyond what a caller passes in,
no credential access. Everything here is either a dataclass, a frozen table of
legal values, or a deterministic function. That is what lets the store and the
service share one definition of "is this legal" without either one being able to
drift from the other.

Invariants this module owns
---------------------------

- **A declaration is read from an immutable version snapshot, never from the
  caller.** :func:`parse_declarations` takes a published ``BranchVersion``
  snapshot. A caller who names an undeclared output field, or redirects the
  destination, cannot produce a :class:`HandoffDeclaration` — the mismatch is a
  :class:`HandoffValidationError` before any credential or adapter is reachable.
- **The effect identity is system-derived.** :func:`derive_handoff_effect_key`
  delegates to the landed outbound-boundary identity
  (:func:`tinyassets.idempotency.derive_effect_key`) so there is exactly one
  ``effect:v1:`` key space and one hashing implementation across the platform.
  A caller-supplied ``idempotency_hint`` is never consulted here.
- **Lifecycle transitions are a closed graph.** :data:`LEGAL_TRANSITIONS` is the
  single source of truth; the store asserts against it inside the same
  transaction that writes the row, so an illegal advance cannot be persisted.
- **Evidence level is separate from lifecycle state.** A handoff reaching
  ``accepted`` proves destination acceptance only; it never implies peer review,
  publication, citation, sales, production use, or regulatory approval. Those
  are later :data:`EVIDENCE_LEVELS` transitions with their own evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from tinyassets.outcomes.schema import OUTCOME_EVIDENCE_LEVELS

# ── Vocabularies ──────────────────────────────────────────────────────────────

#: Lifecycle states of one real handoff. ``reserved`` means the receipt slot is
#: held and nothing has left the machine yet.
HANDOFF_STATES: frozenset[str] = frozenset({
    "reserved",
    "submitted",
    "accepted",
    "verified",
    "rejected",
    "uncertain",
    "orphaned",
    "cancelled",
})

#: Terminal states — no further transition is legal from these.
TERMINAL_STATES: frozenset[str] = frozenset({
    "rejected",
    "orphaned",
    "cancelled",
})

#: The closed transition graph. A successful adapter transport proves only
#: ``submitted``; ``accepted`` requires the provider response contract to prove
#: destination acceptance, and ``verified`` requires a separate later evidence
#: transition. ``uncertain`` is reachable from ``reserved``/``submitted`` and is
#: NOT terminal — reconciliation resolves it, elapsed time never does.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "reserved": frozenset({"submitted", "accepted", "rejected", "uncertain", "cancelled"}),
    "submitted": frozenset({"accepted", "rejected", "uncertain", "orphaned"}),
    "accepted": frozenset({"verified", "orphaned", "uncertain"}),
    "verified": frozenset({"orphaned"}),
    "uncertain": frozenset({"submitted", "accepted", "rejected", "orphaned"}),
    "rejected": frozenset(),
    "orphaned": frozenset(),
    "cancelled": frozenset(),
}

#: Evidence levels that may be persisted on an ``outcome_event`` extension row.
#: Imported from the registry owner rather than restated, so this module's
#: guards and the extension table's SQL CHECK cannot drift apart — a Python
#: value that passed validation and then violated the CHECK would surface as an
#: opaque IntegrityError at write time.
PERSISTABLE_EVIDENCE_LEVELS: frozenset[str] = OUTCOME_EVIDENCE_LEVELS

#: Evidence strength of an outcome claim. Deliberately NOT a single success
#: count — consumers receive these distinctly (spec: "Outcome consumers preserve
#: evidence level"). ``simulated`` exists only for dry-run reporting and is
#: never persisted as an outcome claim, which is why it is added here rather
#: than living in the registry's vocabulary.
EVIDENCE_LEVELS: frozenset[str] = PERSISTABLE_EVIDENCE_LEVELS | {"simulated"}

#: Legal evidence-level advances. Append-only: a transition adds a row, it never
#: rewrites the original attestation.
LEGAL_EVIDENCE_TRANSITIONS: dict[str, frozenset[str]] = {
    "user_attested": frozenset({
        "submitted", "accepted", "externally_verified", "disputed",
        "rejected", "orphaned", "retracted",
    }),
    "submitted": frozenset({
        "accepted", "externally_verified", "disputed", "rejected",
        "orphaned", "retracted",
    }),
    "accepted": frozenset({
        "externally_verified", "disputed", "rejected", "orphaned", "retracted",
    }),
    "externally_verified": frozenset({
        "disputed", "rejected", "orphaned", "retracted",
    }),
    "disputed": frozenset({
        "user_attested", "accepted", "externally_verified", "rejected",
        "orphaned", "retracted",
    }),
    "rejected": frozenset(),
    "orphaned": frozenset({"accepted", "externally_verified", "retracted"}),
    "retracted": frozenset(),
}

EFFECT_CLASSES: frozenset[str] = frozenset({"reversible", "irreversible"})

#: The base ``outcome_event`` table constrains ``outcome_type`` to five values
#: (``tinyassets/outcomes/schema.py``). A handoff's richer ``outcome_kind`` maps
#: onto that CHECK; anything unmapped becomes ``custom`` and the exact kind is
#: preserved on the extension row, so the registry stays one table with no DDL
#: change to its owner.
OUTCOME_KIND_TO_EVENT_TYPE: dict[str, str] = {
    "published_paper": "published_paper",
    "preprint_submission": "published_paper",
    "journal_acceptance": "published_paper",
    "merged_pr": "merged_pr",
    "deployed_app": "deployed_app",
    "won_competition": "won_competition",
}

_ID_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,190}$")
_WHITESPACE = re.compile(r"\s+")

#: Declaration keys whose value could carry credential material. A declaration
#: naming one of these is refused rather than sanitized — the adapter resolves
#: its own credential from the capability boundary (credential blindness), so a
#: handoff never has a reason to carry one.
_CREDENTIAL_KEYS: frozenset[str] = frozenset({
    "token", "secret", "password", "passwd", "api_key", "apikey", "key",
    "credential", "credentials", "authorization", "auth", "bearer",
    "private_key", "client_secret", "access_token", "refresh_token", "pat",
})


# ── Errors ────────────────────────────────────────────────────────────────────

class HandoffError(Exception):
    """Base class for every handoff failure. Carries a machine-readable code."""

    code = "handoff_error"


class HandoffValidationError(HandoffError):
    """A declaration, request, or transition is structurally illegal."""

    code = "handoff_invalid"


class HandoffAccessError(HandoffError):
    """The request subject may not read or act on this handoff.

    Deliberately indistinguishable from "does not exist" at the store layer so a
    probe cannot enumerate other accounts' handoffs.
    """

    code = "handoff_access_denied"


class HandoffAuthorityError(HandoffError):
    """Authority is missing — no authenticated subject, no destination consent,
    or the subject does not control the source artifact."""

    code = "handoff_authority_required"


class HandoffConfirmationRequired(HandoffError):
    """An irreversible handoff reached its adapter without a fresh, matching
    confirmation. Carries what the user must confirm."""

    code = "handoff_confirmation_required"

    def __init__(self, message: str, *, requirement: dict[str, Any]) -> None:
        super().__init__(message)
        self.requirement = requirement


class HandoffConflictError(HandoffError):
    """A concurrent writer already owns this handoff identity or state."""

    code = "handoff_conflict"


# ── Canonicalization + digests ────────────────────────────────────────────────

def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def output_digest(value: Any) -> str:
    """Content hash of one run output value.

    Hashing the canonical form (not ``repr``) means a semantically identical
    output produces the same digest across processes, which is what makes the
    derived effect key stable for a replay of the same run output.
    """
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def derive_handoff_effect_key(
    *,
    branch_version_id: str,
    content_hash: str,
    run_id: str,
    output_field: str,
    output_sha256: str,
    adapter_action: str,
    destination: str,
) -> str:
    """Derive the system-owned exactly-once identity for one handoff.

    Consumes the landed outbound-boundary identity function rather than adding a
    second dedup mechanism: :func:`tinyassets.idempotency.derive_effect_key` owns
    the ``effect:v1:<sha256>`` key space and its canonicalization, and the
    identity-alias/parity machinery in
    ``tinyassets/storage/external_write_receipts.py`` therefore applies to
    handoff receipts unchanged.

    The mapping onto that function's three durable slots:

    ``goal_id``
        the immutable source artifact — version id plus its content hash, so a
        republished version is a different effect identity.
    ``schedule_period``
        the occurrence — the exact run that produced the output.
    ``item_fingerprint``
        the content — output field, output digest, adapter action, destination.

    No caller-supplied hint participates. Two authorized requests naming the same
    source output and destination therefore collide on one receipt row by
    construction, which is what makes the duplicate-submission race safe.
    """
    from tinyassets.idempotency import derive_effect_key

    for label, value in (
        ("branch_version_id", branch_version_id),
        ("content_hash", content_hash),
        ("run_id", run_id),
        ("output_field", output_field),
        ("output_sha256", output_sha256),
        ("adapter_action", adapter_action),
        ("destination", destination),
    ):
        if not (value or "").strip():
            raise HandoffValidationError(f"{label} must be non-empty to derive an effect identity")

    fingerprint = hashlib.sha256(
        canonical_json({
            "output_field": output_field.strip(),
            "output_sha256": output_sha256.strip(),
            "adapter_action": adapter_action.strip(),
            "destination": destination.strip(),
        }).encode("utf-8")
    ).hexdigest()
    return derive_effect_key(
        goal_id=f"handoff:{branch_version_id.strip()}:{content_hash.strip()}",
        schedule_period=f"run:{run_id.strip()}",
        item_fingerprint=fingerprint,
    )


def confirmation_fingerprint(
    *,
    effect_key: str,
    effect_summary: str,
    destination: str,
    branch_version_id: str,
    content_hash: str,
    adapter_action: str,
) -> str:
    """Bind a confirmation to exactly what the user reviewed.

    Includes the source version AND its content hash, so a confirmation issued
    against version N cannot authorize an effect initiated from a later version
    — the stale-confirmation scenario in the capability spec.
    """
    return hashlib.sha256(
        canonical_json({
            "effect_key": effect_key,
            "effect_summary": effect_summary,
            "destination": destination,
            "branch_version_id": branch_version_id,
            "content_hash": content_hash,
            "adapter_action": adapter_action,
        }).encode("utf-8")
    ).hexdigest()


def normalize_external_ref(outcome_kind: str, external_id: str) -> str:
    """Normalize ``(kind, external id)`` into one artifact reference.

    Two sources that contributed to the same external artifact normalize to the
    same reference, which is how the artifact is counted once while both source
    attributions survive. URL-ish identifiers lose scheme, ``www.``, and any
    trailing slash so ``https://doi.org/10.1/x`` and ``doi.org/10.1/x/`` are one
    artifact rather than two.
    """
    kind = (outcome_kind or "").strip().lower()
    raw = _WHITESPACE.sub(" ", (external_id or "").strip()).lower()
    if not kind or not raw:
        return ""
    raw = re.sub(r"^[a-z][a-z0-9+.-]*://", "", raw)
    if raw.startswith("www."):
        raw = raw[4:]
    raw = raw.rstrip("/")
    return f"{kind}:{raw}"


def reject_credential_material(payload: Any, *, where: str) -> None:
    """Refuse a declaration/payload carrying credential material, recursively.

    Recursive because a nested ``{"headers": {"authorization": ...}}`` is the
    same leak as a top-level one; a shallow check reads as protection while
    letting the real shape through.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).strip().lower() in _CREDENTIAL_KEYS:
                raise HandoffValidationError(
                    f"{where} must not carry credential material "
                    f"(found {key!r}); the adapter resolves its own credential"
                )
            reject_credential_material(value, where=where)
    elif isinstance(payload, list):
        for item in payload:
            reject_credential_material(item, where=where)


# ── Declaration ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HandoffDeclaration:
    """One typed external-effect output declared by an immutable node version."""

    output_field: str
    adapter: str
    adapter_action: str
    destination: str
    effect_class: str
    outcome_kind: str
    node_id: str = ""
    credential_class: str = ""
    evidence_contract: dict[str, Any] = field(default_factory=dict)

    @property
    def irreversible(self) -> bool:
        return self.effect_class == "irreversible"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_field": self.output_field,
            "adapter": self.adapter,
            "adapter_action": self.adapter_action,
            "destination": self.destination,
            "effect_class": self.effect_class,
            "outcome_kind": self.outcome_kind,
            "node_id": self.node_id,
            "credential_class": self.credential_class,
            "evidence_contract": dict(self.evidence_contract),
        }

    def effect_summary(self) -> str:
        """The one-line human summary a confirmation is bound to."""
        return (
            f"{self.adapter}.{self.adapter_action} -> {self.destination} "
            f"({self.effect_class}, from output {self.output_field!r})"
        )


def _require_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HandoffValidationError(f"handoff declaration requires {label}")
    if not _ID_SAFE.match(text):
        raise HandoffValidationError(
            f"handoff declaration {label} {text!r} is not a legal identifier"
        )
    return text


def parse_declaration(raw: Any, *, node_id: str = "") -> HandoffDeclaration:
    """Validate one declaration mapping. Raises rather than dropping fields."""
    if not isinstance(raw, dict):
        raise HandoffValidationError("each handoff declaration must be a mapping")
    reject_credential_material(raw, where="handoff declaration")

    effect_class = str(raw.get("effect_class") or "").strip().lower()
    if effect_class not in EFFECT_CLASSES:
        raise HandoffValidationError(
            f"effect_class must be one of {sorted(EFFECT_CLASSES)}, got {effect_class!r}"
        )
    evidence_contract = raw.get("evidence_contract") or {}
    if not isinstance(evidence_contract, dict):
        raise HandoffValidationError("evidence_contract must be a mapping")

    return HandoffDeclaration(
        output_field=_require_id(raw.get("output_field"), "output_field"),
        adapter=_require_id(raw.get("adapter"), "adapter"),
        adapter_action=_require_id(raw.get("adapter_action"), "adapter_action"),
        destination=_require_id(raw.get("destination"), "destination"),
        effect_class=effect_class,
        outcome_kind=_require_id(raw.get("outcome_kind"), "outcome_kind"),
        node_id=str(node_id or raw.get("node_id") or "").strip(),
        credential_class=str(raw.get("credential_class") or "").strip(),
        evidence_contract=dict(evidence_contract),
    )


def parse_declarations(snapshot: dict[str, Any]) -> list[HandoffDeclaration]:
    """Read every handoff declaration off an immutable branch-version snapshot.

    Declarations live on the *node definitions* inside the snapshot
    (``node_defs[].handoffs``), which is what makes them immutable for that
    published version: ``branch_versions._canonical_snapshot`` carries
    ``node_defs`` verbatim, so a declaration cannot be edited after publication
    without producing a different version and content hash.

    A version whose nodes declare nothing declares none — that is legal and is
    the common shape. A malformed declaration raises: silently returning ``[]``
    for a typo'd entry would present "this version declares no external
    effects", which is the dangerous direction to be wrong in.
    """
    node_defs = (snapshot or {}).get("node_defs") or []
    if not isinstance(node_defs, list):
        raise HandoffValidationError("snapshot 'node_defs' must be a list")

    declarations: list[HandoffDeclaration] = []
    for node in node_defs:
        if not isinstance(node, dict):
            continue
        raw = node.get("handoffs")
        if raw in (None, []):
            continue
        if not isinstance(raw, list):
            raise HandoffValidationError(
                f"node {node.get('node_id')!r} 'handoffs' must be a list of declarations"
            )
        node_id = str(node.get("node_id") or "").strip()
        declarations.extend(parse_declaration(item, node_id=node_id) for item in raw)

    seen: set[str] = set()
    for declaration in declarations:
        if declaration.output_field in seen:
            # Two nodes claiming the same output field would make "which
            # declaration authorized this effect?" ambiguous, and ambiguity here
            # resolves into an unintended destination.
            raise HandoffValidationError(
                f"output {declaration.output_field!r} is declared as a handoff twice"
            )
        seen.add(declaration.output_field)
    return declarations


def find_declaration(
    snapshot: dict[str, Any],
    output_field: str,
    *,
    destination: str = "",
) -> HandoffDeclaration:
    """Resolve the declaration for ``output_field``, refusing substitution.

    ``destination`` is optional and is only ever a *check*: when a caller
    supplies one it must equal the declared destination. The declared value is
    what the effect uses, so a caller can never redirect a handoff — it can only
    fail to match and be refused here, before credential vending or adapter
    execution.
    """
    wanted = (output_field or "").strip()
    if not wanted:
        raise HandoffValidationError("output_field is required")
    for declaration in parse_declarations(snapshot):
        if declaration.output_field == wanted:
            supplied = (destination or "").strip()
            if supplied and supplied != declaration.destination:
                raise HandoffValidationError(
                    f"destination {supplied!r} is not the declared destination "
                    f"{declaration.destination!r} for output {wanted!r}"
                )
            return declaration
    raise HandoffValidationError(
        f"output {wanted!r} is not declared as a handoff on this version"
    )


# ── Records ───────────────────────────────────────────────────────────────────

@dataclass
class HandoffRecord:
    """One real handoff's durable row. ``state`` advances only through
    :func:`assert_transition`."""

    handoff_id: str
    owner_id: str
    effect_key: str
    sink: str
    adapter_action: str
    destination: str
    branch_def_id: str
    branch_version_id: str
    content_hash: str
    run_id: str
    output_field: str
    output_sha256: str
    effect_class: str
    outcome_kind: str
    state: str
    created_at: str
    updated_at: str
    credential_class: str = ""
    external_id: str = ""
    declaration: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in HANDOFF_STATES:
            raise HandoffValidationError(
                f"state must be one of {sorted(HANDOFF_STATES)}, got {self.state!r}"
            )
        if self.effect_class not in EFFECT_CLASSES:
            raise HandoffValidationError(
                f"effect_class must be one of {sorted(EFFECT_CLASSES)}, "
                f"got {self.effect_class!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "owner_id": self.owner_id,
            "effect_key": self.effect_key,
            "sink": self.sink,
            "adapter_action": self.adapter_action,
            "destination": self.destination,
            "branch_def_id": self.branch_def_id,
            "branch_version_id": self.branch_version_id,
            "content_hash": self.content_hash,
            "run_id": self.run_id,
            "output_field": self.output_field,
            "output_sha256": self.output_sha256,
            "effect_class": self.effect_class,
            "outcome_kind": self.outcome_kind,
            "credential_class": self.credential_class,
            "state": self.state,
            "external_id": self.external_id,
            "declaration": dict(self.declaration),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class HandoffTransition:
    """One append-only lifecycle observation."""

    transition_id: str
    handoff_id: str
    seq: int
    from_state: str
    to_state: str
    evidence_source: str
    evidence: dict[str, Any]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "handoff_id": self.handoff_id,
            "seq": self.seq,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "evidence_source": self.evidence_source,
            "evidence": dict(self.evidence),
            "recorded_at": self.recorded_at,
        }


def assert_transition(from_state: str, to_state: str) -> None:
    """Raise unless ``from_state -> to_state`` is in the closed graph."""
    if from_state not in HANDOFF_STATES:
        raise HandoffValidationError(f"unknown handoff state {from_state!r}")
    if to_state not in HANDOFF_STATES:
        raise HandoffValidationError(f"unknown handoff state {to_state!r}")
    if to_state not in LEGAL_TRANSITIONS[from_state]:
        raise HandoffValidationError(
            f"{from_state!r} -> {to_state!r} is not a legal handoff transition"
        )


def assert_evidence_transition(from_level: str, to_level: str) -> None:
    """Raise unless the evidence-level advance is legal.

    Notably there is no path back to ``user_attested`` from
    ``externally_verified``: verification is additive evidence, and a downgrade
    goes through ``disputed`` so the reason stays on the record.
    """
    if from_level not in PERSISTABLE_EVIDENCE_LEVELS:
        raise HandoffValidationError(f"unknown evidence level {from_level!r}")
    if to_level not in PERSISTABLE_EVIDENCE_LEVELS:
        raise HandoffValidationError(f"unknown evidence level {to_level!r}")
    if to_level not in LEGAL_EVIDENCE_TRANSITIONS[from_level]:
        raise HandoffValidationError(
            f"{from_level!r} -> {to_level!r} is not a legal evidence transition"
        )


def event_type_for(outcome_kind: str) -> str:
    """Map a handoff ``outcome_kind`` onto the base registry's ``outcome_type``."""
    return OUTCOME_KIND_TO_EVENT_TYPE.get((outcome_kind or "").strip(), "custom")


__all__ = [
    "EFFECT_CLASSES",
    "EVIDENCE_LEVELS",
    "HANDOFF_STATES",
    "LEGAL_EVIDENCE_TRANSITIONS",
    "LEGAL_TRANSITIONS",
    "OUTCOME_KIND_TO_EVENT_TYPE",
    "PERSISTABLE_EVIDENCE_LEVELS",
    "TERMINAL_STATES",
    "HandoffAccessError",
    "HandoffAuthorityError",
    "HandoffConfirmationRequired",
    "HandoffConflictError",
    "HandoffDeclaration",
    "HandoffError",
    "HandoffRecord",
    "HandoffTransition",
    "HandoffValidationError",
    "assert_evidence_transition",
    "assert_transition",
    "canonical_json",
    "confirmation_fingerprint",
    "derive_handoff_effect_key",
    "event_type_for",
    "find_declaration",
    "normalize_external_ref",
    "output_digest",
    "parse_declaration",
    "parse_declarations",
    "reject_credential_material",
]

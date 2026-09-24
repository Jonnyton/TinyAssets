"""Codec + storage for a run's admission envelope.

Design source: ``openspec/changes/consolidate-platform-resource-policy/
design-amendment-resume-exact-definition.md`` (root-approved shape, 2026-09-23;
round-2 corrections C.1-C.5 applied).

A run's *admission envelope* is the durable record of what was actually
admitted: the frozen ``BranchDefinition`` handed to the worker plus the
effective execution choices resolved at admission time. It lives in one
nullable **private** ``runs.admission_envelope_json`` column and is deliberately
absent from ``_row_to_run`` / the MCP run projection -- it is read only by
:func:`resolve_admitted_execution`, after the caller has already passed the
run's ownership gate.

Why a private envelope rather than reusing ``runs.branch_version_id``:
``branch_version_id`` means "the user asked to run this published version" and
feeds contribution attribution, branch-delete dependency counting and market
canonicality. Overloading it with platform-minted pins would silently
reclassify every def-based run's attribution. It stays untouched here.

Why not the canonical ``branch_versions`` snapshot: ``_canonical_snapshot``
carries behaviour only -- it omits ``name``, ``domain_id`` and ``version``, and
it cannot carry per-run execution choices at all. A resume driven from it loses
the authored branch name and the admitted recursion/concurrency budget.

**There is no legacy reconstruction.** A run admitted before this column
existed has no complete durable evidence of its execution choices, and the
absence of override parameters on the old resume path proves only that the old
path *dropped* them -- it is the bug, never evidence about the admission. Such
a run refuses ``admission_not_reconstructable``. Nothing here guesses a
default, and nothing infers admission truth from a function signature.

Nothing here publishes, grants, or mutates shared definition/market state.
Run inputs are already persisted on the run row and carried by the LangGraph
checkpoint, so the envelope does not duplicate them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Bumped when the stored shape changes incompatibly. A row carrying an
#: unknown version is *not* guessed at -- it refuses like a corrupt row.
ENVELOPE_SCHEMA_VERSION = 1

#: Private run column. Not in ``_row_to_run``; not in any public projection.
ENVELOPE_COLUMN = "admission_envelope_json"

#: Typed refusal reason, surfaced through ``runs.ResumeError.reason``.
REASON_NOT_RECONSTRUCTABLE = "admission_not_reconstructable"

#: Every key a well-formed envelope carries. An envelope with an unknown key,
#: or missing any of these, refuses -- it was not written by a build that
#: agrees with this one about what was admitted.
_PAYLOAD_KEYS = frozenset({
    "envelope_schema", "branch", "branch_def_id", "execution",
    "run_name", "branch_version_id",
})
_EXECUTION_KEYS = frozenset({
    "recursion_limit", "concurrency_budget_override", "effective_concurrency_budget",
})


class AdmissionEnvelopeError(Exception):
    """The envelope could not be durably captured, so dispatch must not happen.

    Carries ``run_id`` so the admission path can terminalize the reserved run
    instead of leaving a queued row whose graph nobody will ever run. An
    *encoding* failure is raised before any run is reserved and carries no
    ``run_id``: there is nothing to terminalize, and it propagates.
    """

    def __init__(self, message: str, *, run_id: str = "") -> None:
        super().__init__(message)
        self.run_id = run_id


class AdmissionEnvelopeConflict(AdmissionEnvelopeError):
    """A second preparation tried to replace an already-captured envelope.

    The original admitted payload is immutable once written. A durable-intent
    seam that re-prepares a run may re-supply the *same* envelope (idempotent),
    never a different one.
    """


class AdmissionNotReconstructable(Exception):
    """No honest record of what this run was admitted with.

    Raised for a missing envelope (any pre-envelope run, with or without a
    ``branch_version_id``), for a corrupt or unknown-schema envelope, for one
    whose fields are malformed or mutually inconsistent, and for one whose
    branch/version bindings disagree with the persisted run row. Never falls
    back to the *current* mutable definition, and never substitutes guessed
    execution defaults.
    """

    def __init__(self, message: str, *, reason: str = REASON_NOT_RECONSTRUCTABLE) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class AdmittedExecution:
    """What a run was admitted with, reconstructed from durable storage."""

    branch: Any  # BranchDefinition -- untyped here to keep this module import-light
    recursion_limit: int
    concurrency_budget_override: int | None
    effective_concurrency_budget: int | None
    run_name: str
    #: The *user-selected* published version, if the run was version-based.
    #: Attribution semantics are unchanged: this mirrors ``runs.branch_version_id``.
    branch_version_id: str | None
    #: How this record was obtained. Only ``"envelope"`` exists -- kept so a
    #: caller can assert provenance rather than assume it.
    source: str


def encode_admission_envelope(
    branch: Any,
    *,
    recursion_limit: int,
    concurrency_budget_override: int | None,
    run_name: str,
    branch_version_id: str | None,
) -> str:
    """Serialize the frozen definition + effective execution choices.

    ``branch`` must already be the detached freeze that the worker closes over,
    so the envelope and the executing graph are the same object graph.

    Raises :class:`AdmissionEnvelopeError` (no ``run_id``) if the caller hands
    values this module would later refuse to decode -- caught at admission,
    before a run is reserved, rather than at resume time.
    """
    try:
        branch_dict = branch.to_dict()
    except Exception as exc:  # noqa: BLE001 - any failure here is fail-closed
        raise AdmissionEnvelopeError(
            f"admitted definition could not be serialized: {exc}"
        ) from exc
    if not isinstance(branch_dict, dict):
        raise AdmissionEnvelopeError("admitted definition did not serialize to an object")
    limit = _require_int(
        recursion_limit, field="recursion_limit", minimum=1,
        err=AdmissionEnvelopeError,
    )
    override = (
        None if concurrency_budget_override is None
        else _require_int(
            concurrency_budget_override,
            field="concurrency_budget_override",
            # 0 is executable: the compiler builds a tracker with no semaphore.
            minimum=0,
            err=AdmissionEnvelopeError,
        )
    )
    branch_wide = _branch_concurrency_budget(branch, AdmissionEnvelopeError)
    payload = {
        "envelope_schema": ENVELOPE_SCHEMA_VERSION,
        # Full frozen definition: name, domain_id, version, node_defs,
        # graph_nodes, edges, conditional_edges, state_schema, skills,
        # io_manifest, policies -- everything to_dict() carries.
        "branch": branch_dict,
        # Denormalized for the binding check at resume: an envelope must prove
        # it belongs to the run row that stores it.
        "branch_def_id": str(getattr(branch, "branch_def_id", "") or ""),
        "execution": {
            "recursion_limit": limit,
            "concurrency_budget_override": override,
            "effective_concurrency_budget": (
                override if override is not None else branch_wide
            ),
        },
        "run_name": str(run_name or ""),
        "branch_version_id": str(branch_version_id) if branch_version_id else None,
    }
    try:
        return json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise AdmissionEnvelopeError(
            f"admitted definition is not JSON-serializable: {exc}"
        ) from exc


def _require_int(
    value: Any, *, field: str, minimum: int, err: Callable[[str], BaseException],
) -> int:
    """A strict int at or above ``minimum``. ``bool`` is never an int here.

    There is deliberately **no upper bound**. Admission imposes none: the MCP
    surface range-checks ``recursion_limit_override`` to 10..1000
    (``tinyassets/api/runs.py``) but every internal caller passes an arbitrary
    positive int. Since #3940, ``BranchDefinition.validate()`` does constrain
    ``concurrency_budget`` at *authoring* time -- ``validate_concurrency_budget``
    requires ``type(...) is int`` and ``> 0``, below ``SQLITE_MAX_INT64`` -- but
    that is an authoring-time field validator, not an admission ceiling, and it
    does not describe rows already admitted. This decoder therefore stays
    deliberately wider than it: ``0`` is still accepted verbatim (a branch
    authored before that validator can carry it, and ``0`` means *tracked but
    unbounded* to ``ConcurrencyTracker``), and no ceiling is imposed. A ceiling
    invented here would refuse a run that admission genuinely accepted, which is
    the failure this module exists to prevent.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise err(f"{field} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise err(f"{field} must be >= {minimum}, got {value!r}")
    return value


def _branch_concurrency_budget(branch: Any, err: Callable[[str], BaseException]) -> int | None:
    """The branch-wide budget **verbatim**, exactly as the compiler reads it.

    ``compile_branch`` uses ``branch.concurrency_budget`` unchanged when no
    override is given, and ``ConcurrencyTracker`` treats ``0`` as "tracked but
    unbounded" (``Semaphore(budget) if budget else None``) -- which is NOT the
    same as ``None``, where no tracker is built at all. So this normalizes
    nothing: ``0`` stays ``0`` and a large value stays large.

    A malformed budget (a bool, a string, a negative) is a value
    ``ConcurrencyTracker`` cannot construct from. It raises rather than
    degrading to ``None``, because degrading would hand the resumed run
    unbounded concurrency while claiming it was admitted that way.
    """
    raw = getattr(branch, "concurrency_budget", None)
    if raw is None:
        return None
    return _require_int(raw, field="branch concurrency_budget", minimum=0, err=err)


def capture_admission_envelope(
    conn: sqlite3.Connection, *, run_id: str, envelope: str,
) -> None:
    """Write the envelope once, on the caller's connection. Never replaces one.

    The UPDATE is guarded on ``IS NULL``, so a second preparation of the same
    run cannot overwrite the original admitted payload. Re-supplying the
    byte-identical envelope is accepted (idempotent re-preparation); supplying
    a different one raises :class:`AdmissionEnvelopeConflict`.

    Any storage fault -- a failing write, a locked or read-only database, a
    missing column -- is wrapped as :class:`AdmissionEnvelopeError` carrying
    ``run_id``, because the run is already reserved at this point and the
    caller must terminalize it rather than dispatch it.
    """
    if not envelope:
        raise AdmissionEnvelopeError("refusing to capture an empty envelope", run_id=run_id)
    try:
        conn.execute(
            f"UPDATE runs SET {ENVELOPE_COLUMN} = ? "
            f"WHERE run_id = ? AND {ENVELOPE_COLUMN} IS NULL",
            (envelope, run_id),
        )
        row = conn.execute(
            f"SELECT {ENVELOPE_COLUMN} AS env FROM runs WHERE run_id = ?", (run_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise AdmissionEnvelopeError(
            f"admission envelope for run {run_id!r} could not be written: {exc}",
            run_id=run_id,
        ) from exc
    if row is None:
        raise AdmissionEnvelopeError(
            f"run {run_id!r} vanished before its admission envelope was captured",
            run_id=run_id,
        )
    stored = row["env"] if isinstance(row, sqlite3.Row) else row[0]
    if not stored:
        raise AdmissionEnvelopeError(
            f"admission envelope for run {run_id!r} did not persist", run_id=run_id,
        )
    if stored != envelope:
        raise AdmissionEnvelopeConflict(
            f"run {run_id!r} already carries a different admission envelope; "
            "the admitted payload is immutable",
            run_id=run_id,
        )


def read_raw_envelope(base_path: str | Path, run_id: str) -> str | None:
    """Private read of the stored envelope text. Ownership is the caller's job.

    Returns ``None`` for a row that stores no envelope, and for a genuinely
    pre-migration table that lacks the column. **Every other database fault
    propagates** -- a locked, corrupt or malformed DB must not be laundered
    into "this run is legacy", which would then read as a plain refusal.
    """
    from tinyassets.runs import _connect

    with _connect(base_path) as conn:
        try:
            row = conn.execute(
                f"SELECT {ENVELOPE_COLUMN} AS env FROM runs WHERE run_id = ?", (run_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_missing_envelope_column(exc):
                raise
            return None  # pre-migration table
    if row is None:
        return None
    return row["env"] if isinstance(row, sqlite3.Row) else row[0]


def _is_missing_envelope_column(exc: sqlite3.OperationalError) -> bool:
    """Only SQLite's 'no such column: <our column>' counts as pre-migration."""
    text = str(exc).lower()
    return "no such column" in text and ENVELOPE_COLUMN.lower() in text


def resolve_admitted_execution(
    base_path: str | Path, run: dict[str, Any],
) -> AdmittedExecution:
    """Reconstruct exactly what ``run`` was admitted with, or refuse.

    Call only after the run's ownership/authorization gate has passed. This is
    a definition *source*, never an authorization input: resolving an envelope
    does not make a run resumable.
    """
    from tinyassets.branches import BranchDefinition

    run_id = str(run.get("run_id") or "")
    raw = read_raw_envelope(base_path, run_id)
    if not raw:
        raise AdmissionNotReconstructable(
            f"Run {run_id!r} predates admission-envelope capture and records no "
            "durable evidence of the definition or execution choices it was "
            "admitted with. Resuming it would run a definition nobody can "
            "prove was the admitted one. Start a new run instead."
        )
    return _decode(
        raw, run=run, run_id=run_id, branch_from_dict=BranchDefinition.from_dict,
    )


def _refuse(run_id: str, detail: str) -> AdmissionNotReconstructable:
    return AdmissionNotReconstructable(
        f"admission envelope for run {run_id!r} {detail}"
    )


def _decode(
    raw: str, *, run: dict[str, Any], run_id: str, branch_from_dict,
) -> AdmittedExecution:
    """Strictly decode a stored envelope. Anything unexpected refuses.

    No field silently defaults and no malformed value degrades to ``None``: a
    corrupt envelope is indistinguishable from a forged one, and both must
    refuse before the caller reaches provider admission or dispatch.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise _refuse(run_id, f"is corrupt: {exc}") from exc
    if not isinstance(payload, dict):
        raise _refuse(run_id, "is not an object")
    # ``True == 1`` in Python, so a boolean schema version would slip past a
    # bare ``!=`` comparison against version 1. A bool was never written by
    # this codec; it refuses like any other unknown schema.
    if type(payload.get("envelope_schema")) is not int or (
        payload.get("envelope_schema") != ENVELOPE_SCHEMA_VERSION
    ):
        raise _refuse(
            run_id,
            f"has schema {payload.get('envelope_schema')!r}; "
            f"this build reads {ENVELOPE_SCHEMA_VERSION}",
        )
    keys = set(payload)
    if keys != _PAYLOAD_KEYS:
        raise _refuse(
            run_id,
            f"has unexpected shape (missing {sorted(_PAYLOAD_KEYS - keys)}, "
            f"unknown {sorted(keys - _PAYLOAD_KEYS)})",
        )

    branch_dict = payload["branch"]
    if not isinstance(branch_dict, dict) or not branch_dict:
        raise _refuse(run_id, "carries no definition")
    execution = payload["execution"]
    if not isinstance(execution, dict) or set(execution) != _EXECUTION_KEYS:
        got = sorted(execution) if isinstance(execution, dict) else type(execution).__name__
        raise _refuse(run_id, f"carries no well-formed execution choices (got {got})")

    run_name = payload["run_name"]
    if not isinstance(run_name, str):
        raise _refuse(run_id, f"has a non-string run_name ({type(run_name).__name__})")
    version_id = payload["branch_version_id"]
    if version_id is not None and not isinstance(version_id, str):
        raise _refuse(
            run_id, f"has a non-string branch_version_id ({type(version_id).__name__})",
        )
    envelope_def_id = payload["branch_def_id"]
    if not isinstance(envelope_def_id, str):
        raise _refuse(
            run_id, f"has a non-string branch_def_id ({type(envelope_def_id).__name__})",
        )

    # Strict execution typing. A value that is not an int of the right sign is
    # a refusal, never a fallback to the branch-wide or platform default.
    invalid = lambda m: _refuse(run_id, f"is invalid: {m}")  # noqa: E731
    recursion_limit = _require_int(
        execution["recursion_limit"], field="recursion_limit", minimum=1, err=invalid,
    )
    override = execution["concurrency_budget_override"]
    if override is not None:
        override = _require_int(
            override, field="concurrency_budget_override", minimum=0, err=invalid,
        )
    effective = execution["effective_concurrency_budget"]
    if effective is not None:
        effective = _require_int(
            effective, field="effective_concurrency_budget", minimum=0, err=invalid,
        )
    # Internal consistency: an explicit override IS the effective budget. A
    # payload where they disagree was not produced by this codec.
    if override is not None and effective != override:
        raise _refuse(
            run_id,
            f"is inconsistent: override {override!r} but effective {effective!r}",
        )

    try:
        branch = branch_from_dict(branch_dict)
    except Exception as exc:  # noqa: BLE001 - any decode failure is a refusal
        raise _refuse(run_id, f"cannot be reconstructed: {exc}") from exc

    # With no override, the compiler's effective budget IS the branch-wide one
    # (``graph_compiler.compile_branch``). Check it against the FROZEN branch
    # this envelope carries -- never against the current stored definition,
    # which is the mutable lookup this whole module exists to avoid. A stored
    # effective value that disagrees with the definition it ships with was not
    # written by this codec, so it refuses rather than executing under a budget
    # nobody admitted.
    if override is None:
        frozen_budget = _branch_concurrency_budget(branch, invalid)
        if effective != frozen_budget:
            raise _refuse(
                run_id,
                f"records effective concurrency {effective!r} but its own frozen "
                f"definition declares {frozen_budget!r}",
            )

    # Bindings. The run_id binding is the storage key itself -- the envelope is
    # a column on this run's own row, written guarded IS NULL in the same
    # transaction that claimed the thread_id. Branch and version are checked
    # against the persisted row so an envelope that describes some other
    # subject refuses instead of executing.
    row_def_id = str(run.get("branch_def_id") or "")
    decoded_def_id = str(getattr(branch, "branch_def_id", "") or "")
    if envelope_def_id != decoded_def_id:
        raise _refuse(
            run_id,
            f"names branch {envelope_def_id!r} but its definition is "
            f"{decoded_def_id!r}",
        )
    if row_def_id and envelope_def_id != row_def_id:
        raise _refuse(
            run_id,
            f"describes branch {envelope_def_id!r} but the run row records "
            f"{row_def_id!r}",
        )
    row_version_id = run.get("branch_version_id") or None
    if (version_id or None) != (str(row_version_id) if row_version_id else None):
        raise _refuse(
            run_id,
            f"records branch_version {version_id!r} but the run row records "
            f"{row_version_id!r}",
        )

    return AdmittedExecution(
        branch=branch,
        recursion_limit=recursion_limit,
        concurrency_budget_override=override,
        effective_concurrency_budget=effective,
        run_name=run_name,
        branch_version_id=version_id or None,
        source="envelope",
    )

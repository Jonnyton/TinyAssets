"""Requester-local provider assignment state and admission.

Assignments are server-owned routing authority.  Configuration preferences are
only a projection; served turns re-read this SQLite state under the shared
admission lock before any credential or provider access.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from tinyassets.storage import db_path

_WINDOWS_LOCK_RETRY_ATTEMPTS = 100
_WINDOWS_LOCK_RETRY_SECONDS = 0.01
_SERVED_REQUEST_MAX_INVOCATIONS = 2


@dataclass(frozen=True, slots=True)
class ProviderAssignment:
    universe_id: str
    owner_user_id: str
    state: str
    generation: int
    provider: str
    binding_id: str
    binding_generation: int
    binding_digest: str
    credential_reference_id: str
    credential_reference_generation: int
    credential_reference_digest: str
    assignment_digest: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ServedProviderAuthority:
    """Fresh, server-validated provider facts for one exact served call."""

    provider: str
    max_invocations: int
    request_max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    owner_user_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    binding_id: str
    binding_generation: int
    binding_digest: str
    credential_reference_id: str
    credential_reference_generation: int
    credential_reference_digest: str
    credential_service: str
    credential_snapshot_dir: Path = field(repr=False, compare=False)
    request_capability: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ServedProviderBudgetReservation:
    reservation_id: str
    binding_id: str
    binding_generation: int
    output_tokens: int
    reserved_total_tokens: int
    reserved_cost_microunits: int


_SERVED_COST_MICROUNITS_PER_TOKEN = 100


def _ensure_served_budget_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS served_provider_budget_reservations (
            reservation_id TEXT PRIMARY KEY,
            binding_id TEXT NOT NULL,
            binding_generation INTEGER NOT NULL,
            state TEXT NOT NULL CHECK (
                state IN ('reserved', 'succeeded', 'indeterminate', 'exceeded')
            ),
            reserved_total_tokens INTEGER NOT NULL CHECK (reserved_total_tokens >= 1),
            reserved_cost_microunits INTEGER NOT NULL
                CHECK (reserved_cost_microunits >= 1),
            actual_total_tokens INTEGER,
            actual_cost_microunits INTEGER
        )
        """
    )


def reserve_served_provider_budget(
    base_path: str | Path,
    *,
    universe_dir: str | Path,
    authority: ServedProviderAuthority,
    requested_output_tokens: int,
    estimated_input_tokens: int,
) -> ServedProviderBudgetReservation:
    """Atomically reserve remaining durable binding budget before launch."""

    from tinyassets.credential_vault import current_llm_subscription_custody
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    held = "Provider authority budget is exhausted; reconnect or rebind your provider."
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (requested_output_tokens, estimated_input_tokens)
    ):
        raise ProviderAuthorityHeldError(held)
    store = SQLiteProviderWorkAuthorityStore(base_path)
    with store.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        assignment = load_provider_assignment_in_transaction(
            conn, universe_id=authority.universe_id,
        )
        binding = store.get_binding_in_transaction(conn, binding_id=authority.binding_id)
        custody = current_llm_subscription_custody(
            conn,
            universe_dir=universe_dir,
            owner_user_id=authority.owner_user_id,
            universe_id=authority.universe_id,
            service=authority.credential_service,
        )
        if (
            assignment is None
            or assignment.state != "ready"
            or assignment.binding_id != authority.binding_id
            or assignment.binding_generation != authority.binding_generation
            or assignment.binding_digest != authority.binding_digest
            or binding is None
            or not store.validate_in_transaction(
                conn,
                binding_id=authority.binding_id,
                binding_generation=authority.binding_generation,
                binding_digest=authority.binding_digest,
                owner_user_id=authority.owner_user_id,
                universe_id=authority.universe_id,
                provider=authority.provider,
                operation="converse",
                role="writer",
            )
            or custody is None
            or custody.reference_id != authority.credential_reference_id
            or custody.generation != authority.credential_reference_generation
            or custody.reference_digest != authority.credential_reference_digest
        ):
            conn.rollback()
            raise ProviderAuthorityHeldError(held)
        _ensure_served_budget_schema(conn)
        rows = conn.execute(
            """
            SELECT state, reserved_total_tokens, reserved_cost_microunits,
                   actual_total_tokens, actual_cost_microunits
              FROM served_provider_budget_reservations
             WHERE binding_id = ? AND binding_generation = ?
            """,
            (authority.binding_id, authority.binding_generation),
        ).fetchall()
        # The budget bounds IN-FLIGHT (unsettled) reserved spend — a concurrency
        # + per-turn runaway guard — NOT a cumulative lifetime ceiling.
        #
        # Long-term fix shape (2026-08-19): a SETTLED reservation ('succeeded' or
        # 'exceeded') already spent on the founder's OWN deposited subscription,
        # which Anthropic itself metered and rate-limits. Counting settled rows
        # against a fixed per-generation ceiling made the binding permanently
        # BRICK after ~max_tokens of lifetime serving and demand a manual
        # re-bind — the opposite of "24/7 on the resources the user gave it," and
        # the reason this cap kept being raised as a band-aid. Only UNSETTLED
        # holds ('reserved'/'indeterminate') consume budget now, so each settled
        # turn RELEASES and the binding serves indefinitely, bounded per-turn by
        # ``max_tokens`` (a single turn cannot reserve more) and overall by the
        # user's real subscription limits. The per-reservation cap + release-on-
        # no-output fix still bound a single call and reclaim a failed one.
        # FOLLOW-UP for full 24/7 robustness: expire stale 'reserved' rows left
        # by a crashed turn, and reconcile long-lived 'indeterminate' rows, so
        # neither can slowly re-accumulate a hold.
        _IN_FLIGHT_STATES = ("reserved", "indeterminate")
        in_flight = [row for row in rows if row[0] in _IN_FLIGHT_STATES]
        if len(in_flight) >= authority.max_invocations:
            conn.rollback()
            raise ProviderAuthorityHeldError(held)
        used_tokens = sum(int(row[1]) for row in in_flight)
        used_cost = sum(int(row[2]) for row in in_flight)
        remaining_tokens = authority.max_tokens - used_tokens
        remaining_cost = authority.max_cost_microunits - used_cost
        affordable_total_tokens = remaining_cost // _SERVED_COST_MICROUNITS_PER_TOKEN
        output_tokens = min(
            requested_output_tokens,
            remaining_tokens - estimated_input_tokens,
            affordable_total_tokens - estimated_input_tokens,
        )
        if output_tokens < 1:
            conn.rollback()
            raise ProviderAuthorityHeldError(held)
        reserved_total = estimated_input_tokens + output_tokens
        reserved_cost = reserved_total * _SERVED_COST_MICROUNITS_PER_TOKEN
        reservation = ServedProviderBudgetReservation(
            reservation_id=f"served_budget_{secrets.token_hex(16)}",
            binding_id=authority.binding_id,
            binding_generation=authority.binding_generation,
            output_tokens=output_tokens,
            reserved_total_tokens=reserved_total,
            reserved_cost_microunits=reserved_cost,
        )
        conn.execute(
            """
            INSERT INTO served_provider_budget_reservations (
                reservation_id, binding_id, binding_generation, state,
                reserved_total_tokens, reserved_cost_microunits
            ) VALUES (?, ?, ?, 'reserved', ?, ?)
            """,
            (
                reservation.reservation_id,
                reservation.binding_id,
                reservation.binding_generation,
                reservation.reserved_total_tokens,
                reservation.reserved_cost_microunits,
            ),
        )
        conn.commit()
        return reservation


def finalize_served_provider_budget(
    base_path: str | Path,
    *,
    authority: ServedProviderAuthority,
    reservation: ServedProviderBudgetReservation,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_microunits: int | None,
    fallback_output: str = "",
) -> None:
    """Persist actual usage and hold when one call crossed its reservation."""

    from tinyassets.exceptions import ProviderAuthorityHeldError

    measured_input = (
        input_tokens
        if isinstance(input_tokens, int) and not isinstance(input_tokens, bool)
        and input_tokens >= 0
        else max(1, reservation.reserved_total_tokens - reservation.output_tokens)
    )
    measured_output = (
        output_tokens
        if isinstance(output_tokens, int) and not isinstance(output_tokens, bool)
        and output_tokens >= 0
        else len(fallback_output.encode("utf-8"))
    )
    actual_total = measured_input + measured_output
    measured_cost = (
        cost_microunits
        if isinstance(cost_microunits, int) and not isinstance(cost_microunits, bool)
        and cost_microunits >= 0
        else actual_total * _SERVED_COST_MICROUNITS_PER_TOKEN
    )
    exceeded = (
        actual_total > reservation.reserved_total_tokens
        or measured_cost > reservation.reserved_cost_microunits
        or actual_total > authority.max_tokens
        or measured_cost > authority.max_cost_microunits
    )
    conn = sqlite3.connect(db_path(base_path), isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_served_budget_schema(conn)
        cursor = conn.execute(
            """
            UPDATE served_provider_budget_reservations
               SET state = ?, actual_total_tokens = ?, actual_cost_microunits = ?
             WHERE reservation_id = ? AND binding_id = ?
               AND binding_generation = ? AND state = 'reserved'
            """,
            (
                "exceeded" if exceeded else "succeeded",
                actual_total,
                measured_cost,
                reservation.reservation_id,
                authority.binding_id,
                authority.binding_generation,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            raise ProviderAuthorityHeldError("Provider authority budget accounting failed.")
        conn.commit()
    finally:
        conn.close()
    if exceeded:
        raise ProviderAuthorityHeldError(
            "Provider authority budget was exceeded; the provider result was withheld."
        )


def abandon_served_provider_budget(
    base_path: str | Path,
    reservation: ServedProviderBudgetReservation,
) -> None:
    """Conservatively consume a reservation when provider usage is unknown.

    Use ONLY when the provider call began and could have spent tokens before
    dying. A call that never reached the provider (:class:`ProviderUnavailableError`)
    consumed nothing and must be RELEASED instead — see
    :func:`release_served_provider_budget` — or a flaky provider permanently
    exhausts its own budget one failed turn at a time.
    """

    conn = sqlite3.connect(db_path(base_path), isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_served_budget_schema(conn)
        conn.execute(
            """
            UPDATE served_provider_budget_reservations SET state = 'indeterminate'
             WHERE reservation_id = ? AND state = 'reserved'
            """,
            (reservation.reservation_id,),
        )
        conn.commit()
    finally:
        conn.close()


def release_served_provider_budget(
    base_path: str | Path,
    reservation: ServedProviderBudgetReservation,
) -> None:
    """Release a reservation for a call that provably produced no output.

    A provider that never became available spent nothing, so its reservation
    must not count against the binding's budget at all. Deleting the still-
    ``reserved`` row (never a ``succeeded``/``exceeded``/``indeterminate`` one,
    which record real or possible usage) is the difference between a flaky
    provider that recovers and one that reads as permanently "budget exhausted".
    """

    conn = sqlite3.connect(db_path(base_path), isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_served_budget_schema(conn)
        conn.execute(
            """
            DELETE FROM served_provider_budget_reservations
             WHERE reservation_id = ? AND state = 'reserved'
            """,
            (reservation.reservation_id,),
        )
        conn.commit()
    finally:
        conn.close()


class _AdmissionState:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.readers = 0
        self.writer: int | None = None
        self.waiting_writers = 0
        self.reader_threads: set[int] = set()


def _acquire_windows_file_lock(
    handle: object,
    *,
    locking=None,
    sleep=time.sleep,
    max_attempts: int = _WINDOWS_LOCK_RETRY_ATTEMPTS,
) -> None:
    """Acquire the Windows byte lock with a bounded fail-closed retry."""

    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts < 1
    ):
        raise ValueError("max_attempts must be a positive integer")
    if locking is None:
        import msvcrt

        locking = msvcrt.locking
        nonblocking_mode = msvcrt.LK_NBLCK
    else:
        nonblocking_mode = 1
    last_error: OSError | None = None
    for attempt in range(max_attempts):
        try:
            handle.seek(0)
            locking(handle.fileno(), nonblocking_mode, 1)
            return
        except OSError as exc:
            last_error = exc
            if attempt + 1 < max_attempts:
                sleep(_WINDOWS_LOCK_RETRY_SECONDS)
    raise TimeoutError(
        "provider assignment admission lock remained unavailable"
    ) from last_error


class ProviderAssignmentAdmission:
    """Cross-process shared-reader/exclusive-writer admission by universe path."""

    def __init__(self) -> None:
        self._states_lock = threading.Lock()
        self._states: dict[str, _AdmissionState] = {}

    @staticmethod
    def _key(universe_dir: str | Path) -> str:
        return str(Path(universe_dir).resolve(strict=False))

    def _state(self, universe_dir: str | Path) -> _AdmissionState:
        key = self._key(universe_dir)
        with self._states_lock:
            return self._states.setdefault(key, _AdmissionState())

    @staticmethod
    @contextmanager
    def _file_lock(universe_dir: str | Path, *, exclusive: bool) -> Iterator[None]:
        universe = Path(universe_dir).resolve(strict=False)
        universe.mkdir(parents=True, exist_ok=True)
        handle = (universe / ".provider-assignment-admission.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                # Windows exposes only exclusive byte-range locks here. That
                # serializes readers conservatively while still excluding
                # credential/assignment writers across processes.
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                _acquire_windows_file_lock(handle)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(handle.fileno(), mode)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    @contextmanager
    def shared(self, universe_dir: str | Path) -> Iterator[None]:
        state = self._state(universe_dir)
        thread_id = threading.get_ident()
        with state.condition:
            if state.writer == thread_id or thread_id in state.reader_threads:
                raise RuntimeError("provider assignment admission is not reentrant")
            while state.writer is not None or state.waiting_writers:
                state.condition.wait()
            state.readers += 1
            state.reader_threads.add(thread_id)
        try:
            with self._file_lock(universe_dir, exclusive=False):
                yield
        finally:
            with state.condition:
                state.readers -= 1
                state.reader_threads.remove(thread_id)
                state.condition.notify_all()

    @contextmanager
    def exclusive(self, universe_dir: str | Path) -> Iterator[None]:
        state = self._state(universe_dir)
        thread_id = threading.get_ident()
        with state.condition:
            if state.writer == thread_id or thread_id in state.reader_threads:
                raise RuntimeError("provider assignment admission is not reentrant")
            state.waiting_writers += 1
            try:
                while state.writer is not None or state.readers:
                    state.condition.wait()
                state.writer = thread_id
            finally:
                state.waiting_writers -= 1
        try:
            with self._file_lock(universe_dir, exclusive=True):
                yield
        finally:
            with state.condition:
                state.writer = None
                state.condition.notify_all()


_ADMISSION = ProviderAssignmentAdmission()


def provider_assignment_admission() -> ProviderAssignmentAdmission:
    return _ADMISSION


def ensure_provider_assignment_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_assignments (
            universe_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('pending', 'ready', 'failed', 'unassigned')),
            generation INTEGER NOT NULL CHECK (generation >= 1),
            provider TEXT NOT NULL,
            binding_id TEXT NOT NULL,
            binding_generation INTEGER NOT NULL CHECK (binding_generation >= 1),
            binding_digest TEXT NOT NULL,
            credential_reference_id TEXT NOT NULL,
            credential_reference_generation INTEGER NOT NULL
                CHECK (credential_reference_generation >= 1),
            credential_reference_digest TEXT NOT NULL,
            assignment_digest TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_assignment_owner
        ON provider_assignments(owner_user_id, universe_id, state)
        """
    )


def provider_assignment_digest(
    *,
    owner_user_id: str,
    universe_id: str,
    provider: str,
    generation: int,
    binding_id: str,
    credential_reference_id: str,
    credential_reference_generation: int,
    credential_reference_digest: str,
) -> str:
    payload = {
        "binding_id": binding_id,
        "credential_reference_digest": credential_reference_digest,
        "credential_reference_generation": credential_reference_generation,
        "credential_reference_id": credential_reference_id,
        "generation": generation,
        "owner_user_id": owner_user_id,
        "provider": provider,
        "schema_version": 1,
        "universe_id": universe_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assignment_from_row(row: sqlite3.Row | tuple[object, ...]) -> ProviderAssignment:
    values = list(row)
    assignment = ProviderAssignment(
        universe_id=str(values[0]),
        owner_user_id=str(values[1]),
        state=str(values[2]),
        generation=int(values[3]),
        provider=str(values[4]),
        binding_id=str(values[5]),
        binding_generation=int(values[6]),
        binding_digest=str(values[7]),
        credential_reference_id=str(values[8]),
        credential_reference_generation=int(values[9]),
        credential_reference_digest=str(values[10]),
        assignment_digest=str(values[11]),
        updated_at=str(values[12]),
    )
    expected = provider_assignment_digest(
        owner_user_id=assignment.owner_user_id,
        universe_id=assignment.universe_id,
        provider=assignment.provider,
        generation=assignment.generation,
        binding_id=assignment.binding_id,
        credential_reference_id=assignment.credential_reference_id,
        credential_reference_generation=assignment.credential_reference_generation,
        credential_reference_digest=assignment.credential_reference_digest,
    )
    if assignment.assignment_digest != expected:
        raise RuntimeError("provider assignment digest is invalid")
    return assignment


def load_provider_assignment_in_transaction(
    conn: sqlite3.Connection,
    *,
    universe_id: str,
) -> ProviderAssignment | None:
    ensure_provider_assignment_schema(conn)
    row = conn.execute(
        """
        SELECT universe_id, owner_user_id, state, generation, provider,
               binding_id, binding_generation, binding_digest,
               credential_reference_id, credential_reference_generation,
               credential_reference_digest, assignment_digest, updated_at
          FROM provider_assignments WHERE universe_id = ?
        """,
        (universe_id.strip(),),
    ).fetchone()
    return _assignment_from_row(row) if row is not None else None


def store_provider_assignment_in_transaction(
    conn: sqlite3.Connection,
    assignment: ProviderAssignment,
) -> None:
    if not conn.in_transaction:
        raise ValueError("provider assignment write requires an active transaction")
    expected = provider_assignment_digest(
        owner_user_id=assignment.owner_user_id,
        universe_id=assignment.universe_id,
        provider=assignment.provider,
        generation=assignment.generation,
        binding_id=assignment.binding_id,
        credential_reference_id=assignment.credential_reference_id,
        credential_reference_generation=assignment.credential_reference_generation,
        credential_reference_digest=assignment.credential_reference_digest,
    )
    if assignment.assignment_digest != expected:
        raise ValueError("provider assignment digest is invalid")
    ensure_provider_assignment_schema(conn)
    conn.execute(
        """
        INSERT INTO provider_assignments (
            universe_id, owner_user_id, state, generation, provider,
            binding_id, binding_generation, binding_digest,
            credential_reference_id, credential_reference_generation,
            credential_reference_digest, assignment_digest, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(universe_id) DO UPDATE SET
            owner_user_id = excluded.owner_user_id,
            state = excluded.state,
            generation = excluded.generation,
            provider = excluded.provider,
            binding_id = excluded.binding_id,
            binding_generation = excluded.binding_generation,
            binding_digest = excluded.binding_digest,
            credential_reference_id = excluded.credential_reference_id,
            credential_reference_generation = excluded.credential_reference_generation,
            credential_reference_digest = excluded.credential_reference_digest,
            assignment_digest = excluded.assignment_digest,
            updated_at = excluded.updated_at
        """,
        (
            assignment.universe_id,
            assignment.owner_user_id,
            assignment.state,
            assignment.generation,
            assignment.provider,
            assignment.binding_id,
            assignment.binding_generation,
            assignment.binding_digest,
            assignment.credential_reference_id,
            assignment.credential_reference_generation,
            assignment.credential_reference_digest,
            assignment.assignment_digest,
            assignment.updated_at,
        ),
    )


def load_provider_assignment(
    base_path: str | Path,
    *,
    universe_id: str,
) -> ProviderAssignment | None:
    conn = sqlite3.connect(db_path(base_path))
    try:
        ensure_provider_assignment_schema(conn)
        row = conn.execute(
            """
            SELECT universe_id, owner_user_id, state, generation, provider,
                   binding_id, binding_generation, binding_digest,
                   credential_reference_id, credential_reference_generation,
                   credential_reference_digest, assignment_digest, updated_at
              FROM provider_assignments WHERE universe_id = ?
            """,
            (universe_id.strip(),),
        ).fetchone()
    finally:
        conn.close()
    return _assignment_from_row(row) if row is not None else None


@contextmanager
def authorize_served_provider_call(
    base_path: str | Path,
    *,
    universe_dir: str | Path,
    request_carrier: object,
    role: str,
    operation: str,
) -> Iterator[ServedProviderAuthority]:
    """Fence selection + request + binding + custody immediately before launch."""

    from tinyassets.auth.middleware import validate_provider_request_carrier
    from tinyassets.credential_vault import (
        cleanup_llm_credential_snapshot,
        current_llm_subscription_custody,
        snapshot_llm_subscription_credential,
    )
    from tinyassets.custom_agents import get_binding
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    held = (
        "Connect your provider before running this universe. TinyAssets will not "
        "borrow platform credentials or start a metered trial."
    )
    universe = Path(universe_dir)
    uid = universe.name
    carrier_uid = str(getattr(request_carrier, "universe_id", ""))
    carrier_binding_id = str(getattr(request_carrier, "agent_binding_id", ""))
    carrier_revision = getattr(request_carrier, "binding_revision", 0)
    if carrier_uid != uid or not carrier_binding_id:
        raise ProviderAuthorityHeldError(held)

    with provider_assignment_admission().shared(universe):
        authority: ServedProviderAuthority | None = None
        credential_snapshot = None
        try:
            capability = validate_provider_request_carrier(
                request_carrier,
                universe_id=uid,
                agent_binding_id=carrier_binding_id,
                binding_revision=carrier_revision,
                operation=operation,
            )
            accepted_request_sources = {
                (
                    "tinyassets.authenticated-request.v1",
                    "tinyassets.auth.middleware",
                    "converse",
                ),
                (
                    "tinyassets.authenticated-app-event.v1",
                    "tinyassets.app_ingress_http",
                    "slack_event",
                ),
            }
            if (
                capability.mechanism,
                capability.issuer,
                capability.tool_name,
            ) not in accepted_request_sources:
                raise PermissionError("provider request source is not trusted")
            if role != "writer" or operation != "converse":
                raise PermissionError("served authority is converse/writer only")
            agent = get_binding(
                base_path,
                universe_id=uid,
                binding_id=carrier_binding_id,
            )
            if agent is None:
                raise PermissionError("agent binding is missing")
            exact_agent = (
                agent["status"] == "serving",
                agent["created_by"] == capability.principal_id,
                int(agent["revision"]) == carrier_revision,
            )
            if not all(exact_agent):
                raise PermissionError("agent binding is not current serving authority")

            store = SQLiteProviderWorkAuthorityStore(base_path)
            with store.connection() as conn:
                conn.execute("BEGIN")
                assignment = load_provider_assignment_in_transaction(
                    conn,
                    universe_id=uid,
                )
                provider_ref = agent["configuration"].get("provider_ref")
                if (
                    assignment is None
                    or assignment.state != "ready"
                    or assignment.owner_user_id != capability.principal_id
                    or provider_ref != assignment.binding_id
                ):
                    raise PermissionError("provider assignment is not current")
                provider_binding = store.get_binding_in_transaction(
                    conn,
                    binding_id=assignment.binding_id,
                )
                if provider_binding is None or not store.validate_in_transaction(
                    conn,
                    binding_id=assignment.binding_id,
                    binding_generation=assignment.binding_generation,
                    binding_digest=assignment.binding_digest,
                    owner_user_id=capability.principal_id,
                    universe_id=uid,
                    provider=assignment.provider,
                    operation=operation,
                    role=role,
                ):
                    raise PermissionError("provider binding is not current")
                service = {"codex": "codex", "claude-code": "claude"}.get(
                    assignment.provider
                )
                if service is None:
                    raise PermissionError("provider is not supported for serving")
                custody = current_llm_subscription_custody(
                    conn,
                    universe_dir=universe,
                    owner_user_id=capability.principal_id,
                    universe_id=uid,
                    service=service,
                )
                exact_custody = (
                    custody is not None,
                    custody is not None
                    and custody.reference_id == assignment.credential_reference_id,
                    custody is not None
                    and custody.generation == assignment.credential_reference_generation,
                    custody is not None
                    and custody.reference_digest
                    == assignment.credential_reference_digest,
                    provider_binding.assignment_generation == assignment.generation,
                    provider_binding.assignment_digest == assignment.assignment_digest,
                    provider_binding.credential_reference_digest
                    == assignment.credential_reference_digest,
                )
                if not all(exact_custody):
                    raise PermissionError("credential custody is not current")
                credential_snapshot = snapshot_llm_subscription_credential(
                    universe_dir=universe,
                    custody=custody,
                )
                authority = ServedProviderAuthority(
                    provider=assignment.provider,
                    max_invocations=provider_binding.max_invocations,
                    request_max_invocations=_SERVED_REQUEST_MAX_INVOCATIONS,
                    max_tokens=provider_binding.max_tokens,
                    max_cost_microunits=provider_binding.max_cost_microunits,
                    owner_user_id=capability.principal_id,
                    universe_id=uid,
                    agent_binding_id=carrier_binding_id,
                    binding_revision=carrier_revision,
                    binding_id=provider_binding.binding_id,
                    binding_generation=provider_binding.generation,
                    binding_digest=provider_binding.binding_digest,
                    credential_reference_id=custody.reference_id,
                    credential_reference_generation=credential_snapshot.generation,
                    credential_reference_digest=credential_snapshot.reference_digest,
                    credential_service=service,
                    credential_snapshot_dir=credential_snapshot.directory,
                    request_capability=capability,
                )
                conn.rollback()
            yield authority
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            # Exceptions from the provider body are raised back through the
            # context-manager yield. They are not authority failures and must
            # retain their original type/diagnostics.
            if authority is not None:
                raise
            raise ProviderAuthorityHeldError(held) from exc
        finally:
            cleanup_llm_credential_snapshot(credential_snapshot)


__all__ = [
    "ProviderAssignment",
    "ProviderAssignmentAdmission",
    "ServedProviderAuthority",
    "ServedProviderBudgetReservation",
    "abandon_served_provider_budget",
    "release_served_provider_budget",
    "authorize_served_provider_call",
    "ensure_provider_assignment_schema",
    "load_provider_assignment",
    "load_provider_assignment_in_transaction",
    "provider_assignment_admission",
    "provider_assignment_digest",
    "reserve_served_provider_budget",
    "finalize_served_provider_budget",
    "store_provider_assignment_in_transaction",
]

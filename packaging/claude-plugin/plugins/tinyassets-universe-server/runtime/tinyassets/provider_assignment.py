"""Requester-local provider assignment state and admission.

Assignments are server-owned routing authority.  Configuration preferences are
only a projection; served turns re-read this SQLite state under the shared
admission lock before any credential or provider access.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from tinyassets.storage import db_path


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
    max_tokens: int
    max_cost_microunits: int
    owner_user_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    request_capability: object = field(repr=False, compare=False)


class _AdmissionState:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.readers = 0
        self.writer: int | None = None
        self.waiting_writers = 0
        self.reader_threads: set[int] = set()


class ProviderAssignmentAdmission:
    """Process-local shared-reader/exclusive-writer admission by universe path."""

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
    from tinyassets.credential_vault import current_llm_subscription_custody
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
                authority = ServedProviderAuthority(
                    provider=assignment.provider,
                    max_invocations=provider_binding.max_invocations,
                    max_tokens=provider_binding.max_tokens,
                    max_cost_microunits=provider_binding.max_cost_microunits,
                    owner_user_id=capability.principal_id,
                    universe_id=uid,
                    agent_binding_id=carrier_binding_id,
                    binding_revision=carrier_revision,
                    request_capability=capability,
                )
                try:
                    yield authority
                finally:
                    conn.rollback()
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            # Exceptions from the provider body are raised back through the
            # context-manager yield. They are not authority failures and must
            # retain their original type/diagnostics.
            if authority is not None:
                raise
            raise ProviderAuthorityHeldError(held) from exc


__all__ = [
    "ProviderAssignment",
    "ProviderAssignmentAdmission",
    "ServedProviderAuthority",
    "authorize_served_provider_call",
    "ensure_provider_assignment_schema",
    "load_provider_assignment",
    "load_provider_assignment_in_transaction",
    "provider_assignment_admission",
    "provider_assignment_digest",
    "store_provider_assignment_in_transaction",
]

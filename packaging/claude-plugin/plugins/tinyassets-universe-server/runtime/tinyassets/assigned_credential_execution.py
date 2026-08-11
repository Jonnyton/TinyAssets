"""Resolve one universe serving binding into launch-scoped credential authority."""

from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from tinyassets.credential_vault import (
    cleanup_llm_credential_snapshot,
    snapshot_llm_subscription_credential,
)
from tinyassets.provider_assignment import load_provider_assignment
from tinyassets.provider_serving_binding import (
    _current_serving_authority as current_serving_authority,
)
from tinyassets.provider_serving_binding import (
    resolve_serving_agent_binding,
)
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)

NO_REQUESTER_OWNED_EXECUTOR = "no_requester_owned_executor"
_DAEMON_BOOT_ID = uuid.uuid4().hex
_DAEMON_DESCRIPTOR_TTL_SECONDS = 90


class NoRequesterOwnedExecutor(PermissionError):
    """The universe has no current usable assigned serving credential."""

    reason = NO_REQUESTER_OWNED_EXECUTOR

    def __init__(self) -> None:
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class AssignedCredentialAuthority:
    """Secret-free identity plus one launch's private credential snapshot."""

    universe_id: str
    owner_user_id: str
    agent_binding_id: str
    binding_revision: int
    provider: str
    credential_snapshot_dir: Path = field(repr=False, compare=False)
    allowed_operations: tuple[str, ...] = ("run_graph",)
    allowed_roles: tuple[str, ...] = ("writer", "judge", "extract")


@dataclass(frozen=True, slots=True)
class AssignedCredentialAvailability:
    """Secret-free proof that the exact assigned credential is usable."""

    universe_id: str
    owner_user_id: str
    agent_binding_id: str
    binding_revision: int
    provider: str
    allowed_operations: tuple[str, ...]
    allowed_roles: tuple[str, ...]


def _assigned_credential_state(
    base_path: str | Path,
    universe_dir: str | Path,
) -> tuple[AssignedCredentialAvailability, Any]:
    base = Path(base_path).resolve(strict=False)
    universe = Path(universe_dir).resolve(strict=False)
    if universe.parent != base or not universe.name:
        raise NoRequesterOwnedExecutor()

    assignment = load_provider_assignment(base, universe_id=universe.name)
    if assignment is None or assignment.state != "ready":
        raise NoRequesterOwnedExecutor()
    agent = resolve_serving_agent_binding(
        base,
        universe_id=universe.name,
        owner_user_id=assignment.owner_user_id,
    )
    store = SQLiteProviderWorkAuthorityStore(base)
    with store.connection() as conn:
        conn.execute("BEGIN")
        current, binding, custody = current_serving_authority(
            conn,
            store=store,
            universe_dir=universe,
            owner_user_id=assignment.owner_user_id,
            universe_id=universe.name,
            agent=agent,
            operation="run_graph",
            role="writer",
        )
        conn.rollback()
    if (
        current.provider != assignment.provider
        or current.binding_id != assignment.binding_id
        or current.credential_reference_id != assignment.credential_reference_id
    ):
        raise NoRequesterOwnedExecutor()
    return (
        AssignedCredentialAvailability(
            universe_id=universe.name,
            owner_user_id=assignment.owner_user_id,
            agent_binding_id=str(agent["agent_binding_id"]),
            binding_revision=int(agent["revision"]),
            provider=assignment.provider,
            allowed_operations=tuple(binding.allowed_operations),
            allowed_roles=tuple(binding.allowed_roles),
        ),
        custody,
    )


def assigned_credential_availability(
    base_path: str | Path,
    universe_dir: str | Path,
) -> AssignedCredentialAvailability:
    """Resolve current credential identity without materializing its secret."""

    try:
        availability, _custody = _assigned_credential_state(base_path, universe_dir)
        return availability
    except NoRequesterOwnedExecutor:
        raise
    except (KeyError, LookupError, OSError, PermissionError, RuntimeError, ValueError) as exc:
        raise NoRequesterOwnedExecutor() from exc


@contextmanager
def resolve_assigned_credential(
    base_path: str | Path,
    universe_dir: str | Path,
) -> Iterator[AssignedCredentialAuthority]:
    """Yield the exact current serving credential, or a typed fail-closed hold."""

    universe = Path(universe_dir).resolve(strict=False)
    snapshot = None
    try:
        availability, custody = _assigned_credential_state(base_path, universe)
        snapshot = snapshot_llm_subscription_credential(
            universe_dir=universe,
            custody=custody,
        )
    except NoRequesterOwnedExecutor:
        raise
    except (KeyError, LookupError, OSError, PermissionError, RuntimeError, ValueError) as exc:
        raise NoRequesterOwnedExecutor() from exc

    authority = AssignedCredentialAuthority(
        universe_id=availability.universe_id,
        owner_user_id=availability.owner_user_id,
        agent_binding_id=availability.agent_binding_id,
        binding_revision=availability.binding_revision,
        provider=availability.provider,
        allowed_operations=availability.allowed_operations,
        allowed_roles=availability.allowed_roles,
        credential_snapshot_dir=snapshot.directory,
    )
    try:
        yield authority
    finally:
        cleanup_llm_credential_snapshot(snapshot)


def refresh_pending_credential_holds(
    base_path: str | Path,
    universe_dir: str | Path,
) -> bool:
    """Refresh pending task hold evidence; return credential availability."""

    from tinyassets.branch_tasks import read_queue, set_task_hold_reason

    universe = Path(universe_dir)
    try:
        assigned_credential_availability(base_path, universe)
        reason = ""
    except NoRequesterOwnedExecutor:
        reason = NO_REQUESTER_OWNED_EXECUTOR
    for task in read_queue(universe):
        if task.status != "pending" or task.hold_reason == reason:
            continue
        set_task_hold_reason(universe, task.branch_task_id, reason)
    return not reason


def ensure_assigned_daemon_claim_context(
    base_path: str | Path,
    universe_dir: str | Path,
    *,
    daemon_id: str,
) -> Any:
    """Publish short-lived queue authority for this credential-driven daemon."""

    from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
    from tinyassets.daemon_registry import (
        ensure_daemon_runtime,
        set_worker_queue_descriptor,
    )

    base = Path(base_path).resolve(strict=False)
    universe = Path(universe_dir).resolve(strict=False)
    clean_daemon_id = str(daemon_id or "").strip()
    if not clean_daemon_id:
        raise NoRequesterOwnedExecutor()
    authority = assigned_credential_availability(base, universe)
    executor_id = "worker_" + hashlib.sha256(
        f"{universe.name}:{clean_daemon_id}".encode()
    ).hexdigest()[:20]
    runtime = ensure_daemon_runtime(
        base,
        daemon_id=clean_daemon_id,
        universe_id=universe.name,
        provider_name=authority.provider,
        model_name=authority.provider,
        created_by=authority.owner_user_id,
        worker_id=executor_id,
        metadata={
            "runtime_registration": "assigned_credential_daemon",
            "automation_executor_class": "cloud",
            "agent_binding_id": authority.agent_binding_id,
            "binding_revision": authority.binding_revision,
        },
    )
    runtime_id = str(runtime["runtime_instance_id"])
    build_sha = (
        os.environ.get("TINYASSETS_BUILD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "development"
    )
    config_hash = hashlib.sha256(
        (
            f"{universe.name}:{clean_daemon_id}:{authority.provider}:"
            f"{authority.agent_binding_id}:{authority.binding_revision}"
        ).encode()
    ).hexdigest()
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(seconds=_DAEMON_DESCRIPTOR_TTL_SECONDS)
    ).isoformat().replace("+00:00", "Z")
    set_worker_queue_descriptor(
        base,
        runtime_instance_id=runtime_id,
        descriptor={
            "queue_protocol_version": 2,
            "capabilities": ["operator_request_v1"],
            "worker_id": executor_id,
            "runtime_instance_id": runtime_id,
            "boot_id": _DAEMON_BOOT_ID,
            "build_sha": build_sha,
            "config_hash": config_hash,
            "universe_id": universe.name,
            "expires_at": expires_at,
        },
        expected_worker_id=executor_id,
    )
    context = Epoch2BranchTaskAdapter(base).worker_claim_context(
        worker_id=executor_id,
        runtime_instance_id=runtime_id,
        universe_id=universe.name,
    )
    if context is None or context.daemon_id != clean_daemon_id:
        raise NoRequesterOwnedExecutor()
    return context


@contextmanager
def bind_assigned_provider_call(
    base_path: str | Path,
    universe_dir: str | Path,
    provider_call: Any,
) -> Iterator[Any]:
    """Bind one Branch run's provider calls to its assigned credential."""

    from tinyassets.config import load_universe_config
    from tinyassets.providers.base import UniverseContext
    from tinyassets.providers.call import bind_universe_provider_call

    universe = Path(universe_dir).resolve(strict=False)
    with resolve_assigned_credential(base_path, universe) as authority:
        context = UniverseContext(
            universe_dir=universe,
            config=load_universe_config(universe),
            assigned_credential=authority,
        )
        yield bind_universe_provider_call(
            provider_call,
            context,
            operation="run_graph",
        )


__all__ = [
    "AssignedCredentialAvailability",
    "AssignedCredentialAuthority",
    "NO_REQUESTER_OWNED_EXECUTOR",
    "NoRequesterOwnedExecutor",
    "assigned_credential_availability",
    "bind_assigned_provider_call",
    "ensure_assigned_daemon_claim_context",
    "refresh_pending_credential_holds",
    "resolve_assigned_credential",
]

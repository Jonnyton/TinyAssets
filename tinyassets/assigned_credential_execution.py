"""Resolve one universe serving binding into launch-scoped credential authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
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


@contextmanager
def resolve_assigned_credential(
    base_path: str | Path,
    universe_dir: str | Path,
) -> Iterator[AssignedCredentialAuthority]:
    """Yield the exact current serving credential, or a typed fail-closed hold."""

    base = Path(base_path).resolve(strict=False)
    universe = Path(universe_dir).resolve(strict=False)
    if universe.parent != base or not universe.name:
        raise NoRequesterOwnedExecutor()

    snapshot = None
    try:
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
            current, _binding, custody = current_serving_authority(
                conn,
                store=store,
                universe_dir=universe,
                owner_user_id=assignment.owner_user_id,
                universe_id=universe.name,
                agent=agent,
            )
            conn.rollback()
        if (
            current.provider != assignment.provider
            or current.binding_id != assignment.binding_id
            or current.credential_reference_id
            != assignment.credential_reference_id
        ):
            raise NoRequesterOwnedExecutor()
        snapshot = snapshot_llm_subscription_credential(
            universe_dir=universe,
            custody=custody,
        )
        yield AssignedCredentialAuthority(
            universe_id=universe.name,
            owner_user_id=assignment.owner_user_id,
            agent_binding_id=str(agent["agent_binding_id"]),
            binding_revision=int(agent["revision"]),
            provider=assignment.provider,
            credential_snapshot_dir=snapshot.directory,
        )
    except NoRequesterOwnedExecutor:
        raise
    except (KeyError, LookupError, OSError, PermissionError, RuntimeError, ValueError) as exc:
        raise NoRequesterOwnedExecutor() from exc
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
        with resolve_assigned_credential(base_path, universe):
            reason = ""
    except NoRequesterOwnedExecutor:
        reason = NO_REQUESTER_OWNED_EXECUTOR
    for task in read_queue(universe):
        if task.status != "pending" or task.hold_reason == reason:
            continue
        set_task_hold_reason(universe, task.branch_task_id, reason)
    return not reason


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
    "AssignedCredentialAuthority",
    "NO_REQUESTER_OWNED_EXECUTOR",
    "NoRequesterOwnedExecutor",
    "bind_assigned_provider_call",
    "refresh_pending_credential_holds",
    "resolve_assigned_credential",
]

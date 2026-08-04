"""Trusted activation composition for immutable custom-agent manifests.

The caller selects only a private manifest. Authentication, current grants,
execution identity, executor class, lease identity, and activation state are
all resolved or minted by this server-owned boundary under one SQLite fence.
This module intentionally exposes no public route and performs no execution.
"""

from __future__ import annotations

import math
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from tinyassets.agent_runtime_grants import (
    AgentRuntimeGrantError,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)
from tinyassets.storage.agent_runtime import (
    AgentRuntimeManifestIntegrityError,
    AgentRuntimeManifestStore,
)
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)


class AgentRuntimeActivationBlockerCode(str, Enum):
    OWNER_UNAVAILABLE = "owner_unavailable"
    MANIFEST_NOT_CURRENT = "manifest_not_current"
    GRANTS_NOT_CURRENT = "grants_not_current"
    ACTIVATION_CONFLICT = "activation_conflict"
    ACTIVATION_UNAVAILABLE = "activation_unavailable"


class AgentRuntimeActivationBlocked(PermissionError):
    """A typed, bounded refusal from the trusted activation boundary."""

    def __init__(
        self,
        code: AgentRuntimeActivationBlockerCode,
        message: str,
    ) -> None:
        if not isinstance(code, AgentRuntimeActivationBlockerCode):
            raise ValueError("code must be typed")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        self.code = code
        super().__init__(message)


def _blocked(
    code: AgentRuntimeActivationBlockerCode,
    message: str,
) -> AgentRuntimeActivationBlocked:
    return AgentRuntimeActivationBlocked(code, message)


class AgentRuntimeActivationService:
    """Activate one authenticated owner's current immutable manifest."""

    __slots__ = (
        "_activation_store",
        "_authenticate_owner",
        "_clock",
        "_executor_class",
        "_grant_resolver",
        "_lease_factory",
        "_manifest_store",
    )

    def __init__(
        self,
        base_path: str | Path,
        *,
        authenticate_owner: Callable[[], str],
        grant_resolver: AgentRuntimeGrantResolver,
        executor_class: AutomationActivationExecutor,
        lease_factory: Callable[[], str],
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not callable(authenticate_owner):
            raise ValueError("authenticate_owner must be server-owned")
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        if not isinstance(executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        if not callable(lease_factory):
            raise ValueError("lease_factory must be server-owned")
        if not callable(clock):
            raise ValueError("clock must be server-owned")
        self._authenticate_owner = authenticate_owner
        self._grant_resolver = grant_resolver
        self._executor_class = executor_class
        self._lease_factory = lease_factory
        self._clock = clock
        self._manifest_store = AgentRuntimeManifestStore(base_path)
        self._activation_store = AutomationActivationStore(
            base_path,
            clock=lambda: datetime.fromtimestamp(
                self._server_time(),
                tz=timezone.utc,
            ),
        )

    def activate(self, manifest_id: str) -> AutomationActivation:
        """Activate caller intent without accepting any authority fields."""

        owner_user_id = self._owner()
        identifier = self._manifest_identifier(manifest_id)
        try:
            selected = self._manifest_store.get(
                owner_user_id=owner_user_id,
                manifest_id=identifier,
            )
        except (AgentRuntimeManifestIntegrityError, ValueError):
            selected = None
        except sqlite3.Error:
            raise _blocked(
                AgentRuntimeActivationBlockerCode.ACTIVATION_UNAVAILABLE,
                "agent activation is unavailable",
            ) from None
        if selected is None:
            raise _blocked(
                AgentRuntimeActivationBlockerCode.MANIFEST_NOT_CURRENT,
                "agent manifest is not current",
            )

        with self._activation_store.connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = AgentRuntimeManifestStore.resolve_current_in_transaction(
                    connection,
                    owner_user_id=owner_user_id,
                    manifest_id=selected.manifest_id,
                    manifest_digest=selected.manifest_digest,
                )
                if current is None:
                    raise _blocked(
                        AgentRuntimeActivationBlockerCode.MANIFEST_NOT_CURRENT,
                        "agent manifest is not current",
                    )
                evaluated_at = self._server_time()
                try:
                    grants = self._grant_resolver.resolve_in_transaction(
                        current,
                        connection,
                        evaluated_at=evaluated_at,
                    )
                except AgentRuntimeGrantError:
                    raise _blocked(
                        AgentRuntimeActivationBlockerCode.GRANTS_NOT_CURRENT,
                        "agent grants are not current",
                    ) from None
                if grants.blockers:
                    raise _blocked(
                        AgentRuntimeActivationBlockerCode.GRANTS_NOT_CURRENT,
                        "agent grants are not current",
                    )

                content = current.manifest_input.to_dict()
                subject = ExecutionSubject(
                    kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
                    ref=current.manifest_id,
                    digest=current.manifest_digest,
                )
                universe_id = str(content["universe_id"])
                agent_binding_id = str(content["agent_binding_id"])
                automation_id = agent_binding_automation_id(agent_binding_id)
                activation = self._activation_store.get_in_transaction(
                    connection,
                    universe_id=universe_id,
                    automation_id=automation_id,
                )
                if activation is None:
                    activation = (
                        self._activation_store.create_stopped_for_agent_binding_in_transaction(
                            connection,
                            universe_id=universe_id,
                            agent_binding_id=agent_binding_id,
                        )
                    )
                if activation.state is AutomationActivationState.ACTIVE:
                    if (
                        activation.executor_class is self._executor_class
                        and activation.subject == subject
                    ):
                        connection.commit()
                        return activation
                    raise _blocked(
                        AgentRuntimeActivationBlockerCode.ACTIVATION_CONFLICT,
                        "another agent activation is current",
                    )

                lease_id = self._lease()
                activated = self._activation_store.activate_in_transaction(
                    connection,
                    expected=activation,
                    executor_class=self._executor_class,
                    subject=subject,
                    lease_id=lease_id,
                )
                if activated is None:
                    raise _blocked(
                        AgentRuntimeActivationBlockerCode.ACTIVATION_CONFLICT,
                        "agent activation changed concurrently",
                    )
                connection.commit()
                return activated
            except AgentRuntimeActivationBlocked:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise _blocked(
                    AgentRuntimeActivationBlockerCode.ACTIVATION_UNAVAILABLE,
                    "agent activation is unavailable",
                ) from None

    def _owner(self) -> str:
        try:
            owner = self._authenticate_owner()
        except Exception:
            owner = None
        if not isinstance(owner, str) or not owner.strip():
            raise _blocked(
                AgentRuntimeActivationBlockerCode.OWNER_UNAVAILABLE,
                "authenticated owner is unavailable",
            )
        return owner

    @staticmethod
    def _manifest_identifier(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise _blocked(
                AgentRuntimeActivationBlockerCode.MANIFEST_NOT_CURRENT,
                "agent manifest is not current",
            )
        return value

    def _server_time(self) -> float:
        try:
            value = self._clock()
        except Exception:
            value = None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise _blocked(
                AgentRuntimeActivationBlockerCode.ACTIVATION_UNAVAILABLE,
                "agent activation is unavailable",
            )
        return float(value)

    def _lease(self) -> str:
        try:
            lease_id = self._lease_factory()
        except Exception:
            lease_id = None
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise _blocked(
                AgentRuntimeActivationBlockerCode.ACTIVATION_UNAVAILABLE,
                "agent activation is unavailable",
            )
        return lease_id


__all__ = [
    "AgentRuntimeActivationBlocked",
    "AgentRuntimeActivationBlockerCode",
    "AgentRuntimeActivationService",
]

"""Dark, fail-closed mapping from authenticated app principals to founder bindings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tinyassets.app_event_ingress import (
    AuthenticatedAppEvent,
    is_authenticated_app_event,
)
from tinyassets.custom_agents import get_binding
from tinyassets.daemon_server import get_founder_home, list_universe_acl
from tinyassets.storage.app_principal_mappings import (
    AppPrincipalMappingConflict,
    AppPrincipalMappingGenerationConflict,
    AppPrincipalMappingNotFound,
    AppPrincipalMappingRecord,
    AppPrincipalMappingStore,
    StoredAppPrincipalMapping,
)


class AppPrincipalMappingError(PermissionError):
    """The external principal cannot be used as current TinyAssets authority."""


class AppPrincipalEvidenceError(AppPrincipalMappingError):
    """The event or trusted setup target is missing or malformed."""


class AppPrincipalStaleError(AppPrincipalMappingError):
    """The mapping no longer matches current server-owned authority."""


@dataclass(frozen=True, slots=True)
class ExternalAppPrincipalKey:
    """The only event data exposed to a trusted setup resolver."""

    provider: str
    installation_id: str
    workspace_id: str
    external_sender_id: str


@dataclass(frozen=True, slots=True)
class AppPrincipalTarget:
    """Candidate founder-owned target returned by trusted setup state."""

    subject_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int


@dataclass(frozen=True, slots=True)
class CurrentFounderBinding:
    subject_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    membership_generation: str


class AppPrincipalMappingService:
    """Compose sealed provider evidence with current founder-owned state."""

    def __init__(self, base_path: str | Path, *, store: AppPrincipalMappingStore | None = None):
        self.base_path = Path(base_path)
        self.store = store or AppPrincipalMappingStore(self.base_path)

    def provision(
        self,
        event: AuthenticatedAppEvent,
        *,
        resolve_target: Callable[[ExternalAppPrincipalKey], AppPrincipalTarget | None],
    ) -> StoredAppPrincipalMapping:
        key = _external_key(event)
        if not callable(resolve_target):
            raise TypeError("resolve_target must be callable trusted setup state")
        target = resolve_target(key)
        if target is None:
            raise AppPrincipalEvidenceError("no unique trusted target exists")
        _validate_target(target)
        current = self._current_founder_binding(target)
        if current is None:
            raise AppPrincipalStaleError("trusted target is not a current founder binding")
        return self.store.create(
            provider=key.provider,
            installation_id=key.installation_id,
            workspace_id=key.workspace_id,
            external_sender_id=key.external_sender_id,
            subject_id=current.subject_id,
            universe_id=current.universe_id,
            agent_binding_id=current.agent_binding_id,
            binding_revision=current.binding_revision,
            membership_generation=current.membership_generation,
        )

    def resolve(self, event: AuthenticatedAppEvent) -> AppPrincipalMappingRecord:
        key = _external_key(event)
        record = self.store.get_active(
            provider=key.provider,
            installation_id=key.installation_id,
            workspace_id=key.workspace_id,
            external_sender_id=key.external_sender_id,
        )
        if record is None:
            raise AppPrincipalStaleError("no active mapping exists for this principal")
        current = self._current_founder_binding(
            AppPrincipalTarget(
                subject_id=record.subject_id,
                universe_id=record.universe_id,
                agent_binding_id=record.agent_binding_id,
                binding_revision=record.binding_revision,
            )
        )
        if current is None or not _same_current(record, current):
            raise AppPrincipalStaleError("external principal mapping is stale")
        return record

    def revoke(
        self,
        event: AuthenticatedAppEvent,
        *,
        expected_generation: int,
    ) -> AppPrincipalMappingRecord:
        key = _external_key(event)
        try:
            return self.store.revoke(
                provider=key.provider,
                installation_id=key.installation_id,
                workspace_id=key.workspace_id,
                external_sender_id=key.external_sender_id,
                expected_generation=expected_generation,
            )
        except (
            AppPrincipalMappingNotFound,
            AppPrincipalMappingGenerationConflict,
        ) as exc:
            raise AppPrincipalStaleError(str(exc)) from exc

    def _current_founder_binding(
        self,
        target: AppPrincipalTarget,
    ) -> CurrentFounderBinding | None:
        try:
            if get_founder_home(self.base_path, target.subject_id) != target.universe_id:
                return None
            acl_rows = [
                row
                for row in list_universe_acl(
                    self.base_path,
                    universe_id=target.universe_id,
                )
                if row.get("actor_id") == target.subject_id
                and row.get("permission") == "admin"
            ]
            if len(acl_rows) != 1:
                return None
            binding = get_binding(
                self.base_path,
                universe_id=target.universe_id,
                binding_id=target.agent_binding_id,
            )
            if (
                binding is None
                or binding.get("created_by") != target.subject_id
                or binding.get("status") != "configured"
                or int(binding.get("revision", 0)) != target.binding_revision
            ):
                return None
            return CurrentFounderBinding(
                subject_id=target.subject_id,
                universe_id=target.universe_id,
                agent_binding_id=target.agent_binding_id,
                binding_revision=target.binding_revision,
                membership_generation=_membership_generation(acl_rows[0]),
            )
        except (KeyError, TypeError, ValueError, OSError, sqlite3.Error):
            return None


def _external_key(event: object) -> ExternalAppPrincipalKey:
    if not is_authenticated_app_event(event):
        raise AppPrincipalEvidenceError("mapping requires fresh verifier evidence")
    assert isinstance(event, AuthenticatedAppEvent)
    if event.provider != "slack" or not event.external_sender_id:
        raise AppPrincipalEvidenceError("event has no admissible Slack sender")
    expected_installation = f"{event.api_app_id}:{event.team_id}"
    if event.installation_id != expected_installation:
        raise AppPrincipalEvidenceError("event installation identity is inconsistent")
    return ExternalAppPrincipalKey(
        provider=event.provider,
        installation_id=event.installation_id,
        workspace_id=event.team_id,
        external_sender_id=event.external_sender_id,
    )


def _validate_target(target: object) -> None:
    if not isinstance(target, AppPrincipalTarget):
        raise AppPrincipalEvidenceError("trusted target has an invalid type")
    for name in ("subject_id", "universe_id", "agent_binding_id"):
        value = getattr(target, name)
        if not isinstance(value, str) or not value or value != value.strip():
            raise AppPrincipalEvidenceError(f"trusted target {name} is invalid")
    if (
        not isinstance(target.binding_revision, int)
        or isinstance(target.binding_revision, bool)
        or target.binding_revision < 1
    ):
        raise AppPrincipalEvidenceError("trusted target binding revision is invalid")


def _membership_generation(row: dict[str, object]) -> str:
    fields = {
        "actor_id": str(row.get("actor_id") or ""),
        "granted_at": row.get("granted_at"),
        "granted_by": str(row.get("granted_by") or ""),
        "permission": str(row.get("permission") or ""),
        "universe_id": str(row.get("universe_id") or ""),
    }
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "acl:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _same_current(
    record: AppPrincipalMappingRecord,
    current: CurrentFounderBinding,
) -> bool:
    return (
        record.subject_id == current.subject_id
        and record.universe_id == current.universe_id
        and record.agent_binding_id == current.agent_binding_id
        and record.binding_revision == current.binding_revision
        and record.membership_generation == current.membership_generation
    )


__all__ = [
    "AppPrincipalEvidenceError",
    "AppPrincipalMappingConflict",
    "AppPrincipalMappingError",
    "AppPrincipalMappingService",
    "AppPrincipalStaleError",
    "AppPrincipalTarget",
    "ExternalAppPrincipalKey",
]

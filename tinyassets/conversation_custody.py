"""Dark private-conversation custody contracts.

This module has no production constructor, app ingress, provider call, effect,
or MCP surface.  A future authenticated app owner must mint the opaque grants
consumed here.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import stat
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PRIVATE_UNIVERSE_MODE = "private_universe"

_ACTIONS = frozenset(
    {"create_thread", "append_message", "read_thread", "export_thread", "delete_thread"}
)
_MUTATIONS = frozenset({"create_thread", "append_message", "delete_thread"})
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


class ConversationCustodyValidationError(ValueError):
    """A custody contract value is malformed or unsupported."""


class ConversationCustodyAuthorizationError(PermissionError):
    """A custody operation lacks current exact authority."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _required_ref(value: object, name: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise ConversationCustodyValidationError(f"{name} is not a canonical internal ref")
    return value


def _required_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ConversationCustodyValidationError(f"{name} is not a canonical sha256 digest")
    return value


def _parsed_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise ConversationCustodyValidationError(f"{name} must use YYYY-MM-DDTHH:MM:SS.ffffffZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ConversationCustodyValidationError(f"{name} is not a valid UTC time") from exc
    if parsed.second >= 60:
        raise ConversationCustodyValidationError(f"{name} cannot contain a leap second")
    return parsed


@dataclass(frozen=True, slots=True)
class ConversationCustodyGrantEvidence:
    """Detached evidence returned by a future authority's live grant check."""

    action: str
    request_digest: str
    idempotency_key_digest: str | None
    owner_user_id: str
    universe_id: str
    agent_binding_id: str
    custody_mode: str
    selection_generation: int
    registered_universe_path: str
    platform_data_root: str
    issued_at: str
    expires_at: str

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ConversationCustodyValidationError("action is unsupported")
        _required_digest(self.request_digest, "request_digest")
        if self.action in _MUTATIONS:
            _required_digest(self.idempotency_key_digest, "idempotency_key_digest")
        elif self.idempotency_key_digest is not None:
            raise ConversationCustodyValidationError(
                "read/export grant idempotency_key_digest must be null"
            )
        _required_ref(self.owner_user_id, "owner_user_id")
        _required_ref(self.universe_id, "universe_id")
        _required_ref(self.agent_binding_id, "agent_binding_id")
        if self.custody_mode != PRIVATE_UNIVERSE_MODE:
            raise ConversationCustodyValidationError("custody_mode is unsupported")
        if (
            isinstance(self.selection_generation, bool)
            or not isinstance(self.selection_generation, int)
            or self.selection_generation < 1
        ):
            raise ConversationCustodyValidationError("selection_generation must be an integer >= 1")
        for value, name in (
            (self.registered_universe_path, "registered_universe_path"),
            (self.platform_data_root, "platform_data_root"),
        ):
            if not isinstance(value, str) or not value or not Path(value).is_absolute():
                raise ConversationCustodyValidationError(f"{name} must be absolute")
        issued = _parsed_timestamp(self.issued_at, "issued_at")
        expires = _parsed_timestamp(self.expires_at, "expires_at")
        if expires <= issued:
            raise ConversationCustodyValidationError("expires_at must be after issued_at")


@dataclass(frozen=True, slots=True)
class StorageFileIdentity:
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class ConversationCustodyStorageLocation:
    universe_path: Path
    database_path: Path
    primary_identity: StorageFileIdentity | None


def _is_reparse(metadata: os.stat_result) -> bool:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & reparse)


def _lstat_no_alias(path: Path, *, expect_directory: bool) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ConversationCustodyAuthorizationError(
            "storage_location_invalid", "registered custody path is unavailable"
        ) from exc
    valid_kind = (
        stat.S_ISDIR(metadata.st_mode) if expect_directory else stat.S_ISREG(metadata.st_mode)
    )
    if (
        not valid_kind
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or (not expect_directory and metadata.st_nlink != 1)
    ):
        raise ConversationCustodyAuthorizationError(
            "storage_location_invalid", "registered custody path is aliased or invalid"
        )
    return metadata


def _existing_ancestors(path: Path) -> tuple[Path, ...]:
    return tuple(reversed((path, *path.parents)))


def validate_private_universe_location(
    evidence: ConversationCustodyGrantEvidence,
    *,
    expected_primary_identity: StorageFileIdentity | None = None,
) -> ConversationCustodyStorageLocation:
    """Validate the registered directory and every present SQLite file."""

    universe = Path(evidence.registered_universe_path)
    platform_root = Path(evidence.platform_data_root)
    try:
        universe_resolved = universe.resolve(strict=True)
        platform_resolved = platform_root.resolve(strict=True)
    except OSError as exc:
        raise ConversationCustodyAuthorizationError(
            "storage_location_invalid", "registered custody directory is unavailable"
        ) from exc
    if universe_resolved != universe or universe_resolved == platform_resolved:
        raise ConversationCustodyAuthorizationError(
            "storage_location_invalid", "registered custody directory is not exact"
        )
    for component in _existing_ancestors(universe):
        _lstat_no_alias(component, expect_directory=True)

    database = universe / ".tinyassets.db"
    identity = None
    for candidate in (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
    ):
        if not os.path.lexists(candidate):
            continue
        metadata = _lstat_no_alias(candidate, expect_directory=False)
        if candidate == database:
            identity = StorageFileIdentity(metadata.st_dev, metadata.st_ino)
    if expected_primary_identity is not None and identity != expected_primary_identity:
        raise ConversationCustodyAuthorizationError(
            "storage_location_invalid", "custody database identity changed across open"
        )
    return ConversationCustodyStorageLocation(universe_resolved, database, identity)


class ConversationCustodyOperationGrant:
    __slots__ = ("_grant_id", "_seal", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("conversation custody grants are authority-issued")


@dataclass(frozen=True, slots=True)
class _GrantPayload:
    evidence: ConversationCustodyGrantEvidence
    live_check: Callable[[ConversationCustodyGrantEvidence], bool]


_CAPABILITY_KEY = secrets.token_bytes(32)
_GRANT_LOCK = threading.Lock()
_GRANTS: dict[
    str,
    tuple[weakref.ReferenceType[ConversationCustodyOperationGrant], _GrantPayload],
] = {}


def _seal(identifier: str) -> bytes:
    return hmac.digest(_CAPABILITY_KEY, f"conversation-custody\0{identifier}".encode(), "sha256")


def _discard_grant(identifier: str) -> None:
    with _GRANT_LOCK:
        _GRANTS.pop(identifier, None)


def _issue_operation_grant(
    evidence: ConversationCustodyGrantEvidence,
    *,
    live_check: Callable[[ConversationCustodyGrantEvidence], bool],
) -> ConversationCustodyOperationGrant:
    """Test/integration seam; no production caller is wired by this change."""

    if type(evidence) is not ConversationCustodyGrantEvidence or not callable(live_check):
        raise ConversationCustodyValidationError("grant evidence and live_check are required")
    identifier = secrets.token_hex(32)
    grant = object.__new__(ConversationCustodyOperationGrant)
    object.__setattr__(grant, "_grant_id", identifier)
    object.__setattr__(grant, "_seal", _seal(identifier))
    with _GRANT_LOCK:
        _GRANTS[identifier] = (weakref.ref(grant), _GrantPayload(evidence, live_check))
    weakref.finalize(grant, _discard_grant, identifier)
    return grant


def consume_operation_grant(
    grant: ConversationCustodyOperationGrant,
    *,
    expected_action: str,
    expected_request_digest: str,
    expected_idempotency_key_digest: str | None,
    now: str,
) -> ConversationCustodyGrantEvidence:
    """Consume one exact grant after request, freshness, live, and path checks."""

    try:
        exact = type(grant) is ConversationCustodyOperationGrant and hmac.compare_digest(
            grant._seal, _seal(grant._grant_id)
        )
    except (AttributeError, TypeError):
        exact = False
    if not exact:
        raise ConversationCustodyAuthorizationError(
            "grant_invalid", "conversation custody requires an authority-issued grant"
        )
    with _GRANT_LOCK:
        entry = _GRANTS.get(grant._grant_id)
        if entry is not None and entry[0]() is grant:
            _GRANTS.pop(grant._grant_id, None)
        else:
            entry = None
    if entry is None:
        raise ConversationCustodyAuthorizationError(
            "grant_consumed", "conversation custody grant was already consumed"
        )

    evidence = entry[1].evidence
    expected = (expected_action, expected_request_digest, expected_idempotency_key_digest)
    actual = (evidence.action, evidence.request_digest, evidence.idempotency_key_digest)
    if actual != expected:
        raise ConversationCustodyAuthorizationError(
            "grant_mismatch", "conversation custody grant does not match the request"
        )
    observed_at = _parsed_timestamp(now, "now")
    if observed_at >= _parsed_timestamp(evidence.expires_at, "expires_at"):
        raise ConversationCustodyAuthorizationError("grant_expired", "custody grant expired")
    try:
        current = entry[1].live_check(evidence)
    except Exception:
        current = False
    if current is not True:
        raise ConversationCustodyAuthorizationError(
            "grant_revoked", "custody selection or binding is not current"
        )
    validate_private_universe_location(evidence)
    return evidence


__all__ = [
    "PRIVATE_UNIVERSE_MODE",
    "ConversationCustodyAuthorizationError",
    "ConversationCustodyGrantEvidence",
    "ConversationCustodyOperationGrant",
    "ConversationCustodyStorageLocation",
    "ConversationCustodyValidationError",
    "StorageFileIdentity",
    "consume_operation_grant",
    "validate_private_universe_location",
]

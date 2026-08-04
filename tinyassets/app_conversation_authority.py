"""Founder-mapped, dark authority for issuing private conversation grants."""

from __future__ import annotations

import base64
import binascii
import os
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tinyassets.app_event_ingress import AuthenticatedAppEvent
from tinyassets.app_principal_mapping import AppPrincipalMappingService
from tinyassets.conversation_custody import (
    ConversationCustodyAuthorizationError,
    ConversationCustodyGrantEvidence,
    canonical_json_bytes,
    validate_private_universe_location,
)
from tinyassets.storage.app_principal_mappings import AppPrincipalMappingRecord

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$\Z")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_ACTIONS = frozenset(
    {"create_thread", "append_message", "read_thread", "export_thread", "delete_thread"}
)
_MUTATIONS = frozenset({"create_thread", "append_message", "delete_thread"})
_MAX_TTL_SECONDS = 300


class AppConversationAuthorityError(PermissionError):
    """The app principal cannot mint current private custody authority."""


@dataclass(frozen=True, slots=True)
class AppConversationGrant:
    """Signed handoff evidence awaiting the custody domain's opaque mint."""

    evidence: ConversationCustodyGrantEvidence
    signature: str


class AppConversationAuthority:
    """Issue an opaque grant only after current founder state is revalidated."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        mapping: AppPrincipalMappingService | None = None,
        storage_resolver: Callable[[AppPrincipalMappingRecord], tuple[str | Path, str | Path]],
        signing_key: Ed25519PrivateKey | None = None,
        authority_key_id: str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not callable(storage_resolver):
            raise TypeError("storage_resolver must be callable server-owned state")
        self.base_path = Path(base_path)
        self.mapping = mapping or AppPrincipalMappingService(self.base_path)
        self.storage_resolver = storage_resolver
        self.signing_key = signing_key or _load_signing_key()
        self.authority_key_id = authority_key_id or os.environ.get(
            "TINYASSETS_CUSTODY_AUTHORITY_KEY_ID"
        )
        if not isinstance(self.authority_key_id, str) or not _REF.fullmatch(self.authority_key_id):
            raise AppConversationAuthorityError("custody authority key identity is unavailable")
        self.clock = clock or time.time

    def issue(
        self,
        event: AuthenticatedAppEvent,
        *,
        action: str,
        request_digest: str,
        idempotency_key_digest: str | None = None,
        ttl_seconds: int = 60,
    ) -> AppConversationGrant:
        _validate_request(action, request_digest, idempotency_key_digest, ttl_seconds)
        try:
            record = self.mapping.resolve(event)
            registered_path, platform_root = self.storage_resolver(record)
            issued_at = _timestamp(self.clock())
            expires_at = _timestamp(self.clock() + ttl_seconds)
            evidence = ConversationCustodyGrantEvidence(
                action=action,
                authority_key_id=self.authority_key_id,
                grant_id=_new_grant_id(),
                request_digest=request_digest,
                idempotency_key_digest=idempotency_key_digest,
                owner_user_id=record.subject_id,
                universe_id=record.universe_id,
                agent_binding_id=record.agent_binding_id,
                custody_mode="private_universe",
                selection_generation=record.mapping_generation,
                registered_universe_path=str(registered_path),
                platform_data_root=str(platform_root),
                issued_at=issued_at,
                expires_at=expires_at,
            )
            validate_private_universe_location(evidence)
            signature = base64.urlsafe_b64encode(
                self.signing_key.sign(_grant_signing_bytes(evidence))
            ).decode("ascii").rstrip("=")
            return AppConversationGrant(evidence=evidence, signature=signature)
        except AppConversationAuthorityError:
            raise
        except (ConversationCustodyAuthorizationError, OSError, TypeError, ValueError) as exc:
            raise AppConversationAuthorityError("custody grant issuance failed closed") from exc


def _validate_request(
    action: str,
    request_digest: str,
    idempotency_key_digest: str | None,
    ttl_seconds: int,
) -> None:
    if action not in _ACTIONS:
        raise AppConversationAuthorityError("custody action is not allowed")
    if not isinstance(request_digest, str) or not _DIGEST.fullmatch(request_digest):
        raise AppConversationAuthorityError("request digest is invalid")
    if action in _MUTATIONS:
        if not isinstance(idempotency_key_digest, str) or not _DIGEST.fullmatch(
            idempotency_key_digest
        ):
            raise AppConversationAuthorityError("mutation idempotency digest is required")
    elif idempotency_key_digest is not None:
        raise AppConversationAuthorityError("read grant cannot carry an idempotency digest")
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS
    ):
        raise AppConversationAuthorityError("custody grant TTL is invalid")


def _timestamp(value: float) -> str:
    if not isinstance(value, (int, float)) or not value == value:
        raise AppConversationAuthorityError("custody authority clock is invalid")
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _new_grant_id() -> str:
    return "cg_" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _grant_signing_bytes(evidence: ConversationCustodyGrantEvidence) -> bytes:
    return b"conversation-custody/operation-grant/v1\0" + canonical_json_bytes(
        {
            "action": evidence.action,
            "agent_binding_id": evidence.agent_binding_id,
            "authority_key_id": evidence.authority_key_id,
            "custody_mode": evidence.custody_mode,
            "expires_at": evidence.expires_at,
            "grant_id": evidence.grant_id,
            "idempotency_key_digest": evidence.idempotency_key_digest,
            "issued_at": evidence.issued_at,
            "owner_user_id": evidence.owner_user_id,
            "platform_data_root": evidence.platform_data_root,
            "registered_universe_path": evidence.registered_universe_path,
            "request_digest": evidence.request_digest,
            "selection_generation": evidence.selection_generation,
            "universe_id": evidence.universe_id,
        }
    )


def _load_signing_key() -> Ed25519PrivateKey:
    wire = os.environ.get("TINYASSETS_CUSTODY_AUTHORITY_PRIVATE_KEY_B64U")
    if not isinstance(wire, str) or len(wire) != 43:
        raise AppConversationAuthorityError("custody authority signing key is unavailable")
    try:
        raw = base64.urlsafe_b64decode(wire + "=")
    except (binascii.Error, ValueError) as exc:
        raise AppConversationAuthorityError("custody authority signing key is invalid") from exc
    if len(raw) != 32:
        raise AppConversationAuthorityError("custody authority signing key is invalid")
    return Ed25519PrivateKey.from_private_bytes(raw)


__all__ = ["AppConversationAuthority", "AppConversationAuthorityError", "AppConversationGrant"]

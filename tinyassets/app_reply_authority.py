"""Dark, content-free authority gate for founder-mapped app replies."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tinyassets.app_conversation_authority import (
    AppConversationGrant,
    _grant_signing_bytes,
)
from tinyassets.app_event_ingress import AuthenticatedAppEvent, is_authenticated_app_event
from tinyassets.app_principal_mapping import AppPrincipalMappingService
from tinyassets.conversation_custody import canonical_json_bytes
from tinyassets.storage.app_principal_mappings import AppPrincipalMappingRecord

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_SUPPORTED_PROVIDERS = frozenset({"slack"})


class AppReplyAuthorityError(PermissionError):
    """The app reply cannot be authorized under current server state."""


@dataclass(frozen=True, slots=True)
class ReplyDestination:
    provider: str
    connection_id: str
    address: str

    def __post_init__(self) -> None:
        if self.provider not in _SUPPORTED_PROVIDERS:
            raise AppReplyAuthorityError("reply destination provider is unsupported")
        for value, name in (
            (self.connection_id, "connection_id"),
            (self.address, "address"),
        ):
            if not isinstance(value, str) or not _REF.fullmatch(value):
                raise AppReplyAuthorityError(f"reply destination {name} is invalid")


@dataclass(frozen=True, slots=True)
class AppReplyAuthorization:
    owner_user_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    mapping_generation: int
    destination: ReplyDestination
    response_digest: str
    authorization_digest: str


class AppReplyAuthority:
    """Verify a signed custody handoff and authorize one future adapter call."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        destination_resolver: Callable[[AppPrincipalMappingRecord], ReplyDestination],
        mapping: AppPrincipalMappingService | None = None,
        public_key: Ed25519PublicKey | None = None,
        authority_key_id: str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not callable(destination_resolver):
            raise TypeError("destination_resolver must be callable server-owned state")
        self.base_path = Path(base_path)
        self.destination_resolver = destination_resolver
        self.mapping = mapping or AppPrincipalMappingService(self.base_path)
        self.public_key = public_key or _load_public_key()
        self.authority_key_id = authority_key_id or os.environ.get(
            "TINYASSETS_CUSTODY_AUTHORITY_KEY_ID"
        )
        if not isinstance(self.authority_key_id, str) or not _REF.fullmatch(self.authority_key_id):
            raise AppReplyAuthorityError("reply authority key identity is unavailable")
        self.clock = clock or time.time

    def authorize(
        self,
        event: AuthenticatedAppEvent,
        handoff: AppConversationGrant,
        *,
        response_digest: str,
    ) -> AppReplyAuthorization:
        # Same reasoning as the issuing side: this authorises a reply against a
        # signed custody handoff, so it requires the request-signature evidence
        # that handoff was minted from. `mapping.resolve` alone would admit the
        # weaker Socket Mode evidence.
        if not is_authenticated_app_event(event):
            raise AppReplyAuthorityError(
                "reply authorisation requires verified request-signature evidence"
            )
        if type(handoff) is not AppConversationGrant:
            raise AppReplyAuthorityError("reply requires an authority-issued custody handoff")
        if not isinstance(response_digest, str) or not _DIGEST.fullmatch(response_digest):
            raise AppReplyAuthorityError("response digest is invalid")
        evidence = handoff.evidence
        if (
            evidence.action != "append_message"
            or evidence.authority_key_id != self.authority_key_id
        ):
            raise AppReplyAuthorityError("custody handoff is not a reply authority")
        try:
            signature = _decode_signature(handoff.signature)
            self.public_key.verify(signature, _grant_signing_bytes(evidence))
            now = self.clock()
            issued = _parse_timestamp(evidence.issued_at)
            expires = _parse_timestamp(evidence.expires_at)
            if now < issued.timestamp() or now > expires.timestamp():
                raise AppReplyAuthorityError("custody handoff is outside its validity window")
            record = self.mapping.resolve(event)
            if (
                record.subject_id != evidence.owner_user_id
                or record.universe_id != evidence.universe_id
                or record.agent_binding_id != evidence.agent_binding_id
                or record.mapping_generation != evidence.selection_generation
            ):
                raise AppReplyAuthorityError("custody handoff does not match current mapping")
            destination = self.destination_resolver(record)
            if type(destination) is not ReplyDestination:
                raise AppReplyAuthorityError("destination resolver returned invalid authority")
            authorization_digest = "sha256:" + hashlib.sha256(
                canonical_json_bytes(
                    {
                        "agent_binding_id": record.agent_binding_id,
                        "address": destination.address,
                        "connection_id": destination.connection_id,
                        "destination_provider": destination.provider,
                        "mapping_generation": record.mapping_generation,
                        "owner_user_id": record.subject_id,
                        "response_digest": response_digest,
                        "universe_id": record.universe_id,
                    }
                )
            ).hexdigest()
            return AppReplyAuthorization(
                owner_user_id=record.subject_id,
                universe_id=record.universe_id,
                agent_binding_id=record.agent_binding_id,
                binding_revision=record.binding_revision,
                mapping_generation=record.mapping_generation,
                destination=destination,
                response_digest=response_digest,
                authorization_digest=authorization_digest,
            )
        except AppReplyAuthorityError:
            raise
        except Exception as exc:
            raise AppReplyAuthorityError("reply authority failed closed") from exc


def _decode_signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) != 86:
        raise AppReplyAuthorityError("custody signature is invalid")
    try:
        decoded = base64.urlsafe_b64decode(value + "==")
    except (binascii.Error, ValueError) as exc:
        raise AppReplyAuthorityError("custody signature is invalid") from exc
    if len(decoded) != 64:
        raise AppReplyAuthorityError("custody signature is invalid")
    return decoded


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AppReplyAuthorityError("custody timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise AppReplyAuthorityError("custody timestamp is invalid")
    return parsed.astimezone(timezone.utc)


def _load_public_key() -> Ed25519PublicKey:
    wire = os.environ.get("TINYASSETS_CUSTODY_AUTHORITY_PUBLIC_KEY_B64U")
    if not isinstance(wire, str) or len(wire) != 43:
        raise AppReplyAuthorityError("reply authority public key is unavailable")
    try:
        raw = base64.urlsafe_b64decode(wire + "=")
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise AppReplyAuthorityError("reply authority public key is invalid") from exc


__all__ = [
    "AppReplyAuthorization",
    "AppReplyAuthority",
    "AppReplyAuthorityError",
    "ReplyDestination",
]

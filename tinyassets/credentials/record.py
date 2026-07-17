"""Authoritative record: the full descriptor sealed inside the AEAD payload.

Both backends serialize this record into the encrypted payload and, on read,
take EVERY authorization decision (identity match, custody, expiry, state) from
the decrypted copy — never from the plaintext DB/sidecar columns, which are
non-authoritative index hints only.
"""

from __future__ import annotations

import time
from typing import Any

from .errors import CredentialUnavailable, VaultErrorCode
from .types import DescriptorState, SecretKind, SecretScope, VaultStore


def build_record(
    *,
    ref: str,
    kind: SecretKind,
    scope: SecretScope,
    store: VaultStore,
    version: int,
    state: DescriptorState,
    created_at: float,
    updated_at: float,
    expires_at: float | None,
) -> dict[str, Any]:
    """Construct the authoritative record dict embedded in the sealed payload."""
    return {
        "ref": ref,
        "kind": kind.value,
        "scope": scope.as_dict(),
        "store_id": store.store_id,
        "custody": store.custody.value,
        "daemon_id": store.daemon_id,
        "version": int(version),
        "state": state.value,
        "created_at": created_at,
        "updated_at": updated_at,
        "expires_at": expires_at,
    }


def verify_record_identity(
    record: dict[str, Any],
    *,
    ref: str,
    kind: SecretKind,
    scope: SecretScope,
    store: VaultStore,
    version: int,
) -> None:
    """Assert the decrypted record's immutable identity matches the request.

    A decrypt can only succeed if the AAD (which also binds this identity)
    matched, so this is defense-in-depth; it also catches an internal
    serialization bug. Any mismatch is a tampered/forged record → fail closed.
    """
    expected = {
        "ref": ref,
        "kind": kind.value,
        "store_id": store.store_id,
        "custody": store.custody.value,
        "daemon_id": store.daemon_id,
        "version": int(version),
    }
    for key, want in expected.items():
        if record.get(key) != want:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
    if record.get("scope") != scope.as_dict():
        raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, ref)


def check_lifecycle(record: dict[str, Any], ref: str, *, now: float | None = None) -> None:
    """Enforce state + expiry from the AUTHORITATIVE (decrypted) record."""
    state = record.get("state")
    if state == DescriptorState.DISABLED.value:
        raise CredentialUnavailable(VaultErrorCode.DISABLED, ref)
    if state == DescriptorState.REVOCATION_PENDING.value:
        raise CredentialUnavailable(VaultErrorCode.REVOKED, ref)
    if state != DescriptorState.ACTIVE.value:
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
    expires_at = record.get("expires_at")
    if expires_at is not None and float(expires_at) <= (now if now is not None else time.time()):
        raise CredentialUnavailable(VaultErrorCode.EXPIRED, ref)

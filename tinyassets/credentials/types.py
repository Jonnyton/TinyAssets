"""Schemas for the provider-generic credential vault.

Mirrors the Schemas section of
``docs/design-notes/2026-07-16-provider-generic-credential-vault.md``. These are
all NON-secret control-plane shapes: an opaque :data:`SecretRef`, custody
metadata, and descriptors. The secret VALUE never appears in any of these types
— it lives only inside :class:`~tinyassets.credentials.secret_bytes.SecretBytes`
/ :class:`~tinyassets.credentials.secret_bytes.SecretLease`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Opaque reference
# ---------------------------------------------------------------------------

SECRET_REF_PREFIX = "secret:v1:"
_SECRET_REF_RANDOM_BYTES = 32  # 256 bits


def new_secret_ref() -> str:
    """Mint a fresh opaque ``secret:v1:<64 hex chars>`` reference.

    Carries no provider, path, account, custody, or scope information — it is a
    pure random handle. 256 bits of entropy makes it unguessable.
    """
    return SECRET_REF_PREFIX + secrets.token_hex(_SECRET_REF_RANDOM_BYTES)


def is_secret_ref(value: object) -> bool:
    """Return True for a syntactically valid opaque secret reference."""
    if not isinstance(value, str) or not value.startswith(SECRET_REF_PREFIX):
        return False
    body = value[len(SECRET_REF_PREFIX) :]
    if len(body) != _SECRET_REF_RANDOM_BYTES * 2:
        return False
    try:
        int(body, 16)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SecretKind(str, Enum):
    """What a stored value *is* — drives adapter codec selection, never storage."""

    GITHUB_APP_PRIVATE_KEY = "github_app_private_key"
    GITHUB_APP_USER_TOKEN = "github_app_user_token"
    GITHUB_PAT = "github_pat"
    OAUTH2_GENERIC = "oauth2_generic"
    API_KEY = "api_key"
    WEBHOOK_SECRET = "webhook_secret"


class Custody(str, Enum):
    """Which backend physically holds the ciphertext."""

    PLATFORM_ENCRYPTED = "platform_encrypted"
    DAEMON_LOCAL = "daemon_local"


class DescriptorState(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOCATION_PENDING = "revocation_pending"


# ---------------------------------------------------------------------------
# Scope + store + binding + descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretScope:
    """The exact-match authorization key for a secret.

    ``destination`` and ``purpose`` are exact-match policy keys — a lease minted
    for one destination/purpose cannot be reused for another.
    """

    founder_id: str
    universe_id: str
    provider: str
    destination: str
    purpose: str

    def as_dict(self) -> dict[str, str]:
        return {
            "founder_id": self.founder_id,
            "universe_id": self.universe_id,
            "provider": self.provider,
            "destination": self.destination,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class VaultStore:
    """Discriminated custody selector.

    The binding's ``store`` selects exactly one backend. Cross-store lookup is
    forbidden — the backend re-derives store identity from protected contents.
    """

    custody: Custody
    store_id: str
    daemon_id: str | None = None  # required only for DAEMON_LOCAL

    def __post_init__(self) -> None:
        if self.custody == Custody.DAEMON_LOCAL and not self.daemon_id:
            raise ValueError("daemon_local store requires a daemon_id")


@dataclass(frozen=True)
class SecretBinding:
    """Non-secret control-plane binding: opaque ref + custody metadata.

    This is the ONLY thing that may live in universe/branch control-plane rows.
    It contains no value and no refresh material.
    """

    ref: str
    kind: SecretKind
    scope: SecretScope
    store: VaultStore


@dataclass(frozen=True)
class SecretDescriptor:
    """Non-secret lifecycle metadata for one stored secret version."""

    binding: SecretBinding
    version: int
    created_at: float
    updated_at: float
    state: DescriptorState = DescriptorState.ACTIVE
    expires_at: float | None = None

    def public_projection(self) -> dict[str, object]:
        """The explicit allowlist safe to surface in status/list/receipts.

        Design allowlist = ref / kind / scope / timestamps ONLY. Internal
        lifecycle counters (``version``, ``state``) and all custody internals,
        backend paths/ids, ciphertext, wrapped DEKs, key ids, and the value are
        deliberately excluded.
        """
        return {
            "ref": self.binding.ref,
            "kind": self.binding.kind.value,
            "scope": self.binding.scope.as_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


# ---------------------------------------------------------------------------
# Persisted envelopes (backend-internal; never a public projection)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EncryptedRow:
    """Platform backend persisted shape (SQLite row).

    ``ciphertext`` is the AEAD-sealed framed payload; ``wrapped_dek`` is the DEK
    sealed under the active KEK. ``key_id`` identifies the KEK for rotation.
    No plaintext value is present.
    """

    descriptor: SecretDescriptor
    algorithm: str
    key_id: str
    wrap_nonce: bytes
    wrapped_dek: bytes
    data_nonce: bytes
    ciphertext: bytes


@dataclass(frozen=True)
class DpapiBlob:
    """Local (Windows) backend persisted shape.

    ``blob_path`` points at the immutable per-ref DPAPI blob;
    ``protection`` is always ``dpapi-current-user`` (never LOCAL_MACHINE).
    """

    descriptor: SecretDescriptor
    blob_path: str
    protection: str = "dpapi-current-user"
    blob_version: int = 1


# Algorithm tag persisted with every platform row.
XCHACHA20POLY1305_IETF = "xchacha20poly1305-ietf"

# Reserved scope used by the attestation self-test. Never a real credential.
PROBE_SCOPE = SecretScope(
    founder_id="platform:tinyassets",
    universe_id="platform",
    provider="__vault_probe__",
    destination="__attestation__",
    purpose="self_test",
)

__all__ = [
    "SECRET_REF_PREFIX",
    "new_secret_ref",
    "is_secret_ref",
    "SecretKind",
    "Custody",
    "DescriptorState",
    "SecretScope",
    "VaultStore",
    "SecretBinding",
    "SecretDescriptor",
    "EncryptedRow",
    "DpapiBlob",
    "XCHACHA20POLY1305_IETF",
    "PROBE_SCOPE",
]

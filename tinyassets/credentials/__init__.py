"""Provider-generic credential vault (CORE).

One :class:`VaultBroker` seam over two custody backends:

* :class:`PlatformVaultBackend` — XChaCha20-Poly1305-IETF envelope encryption in
  SQLite (WAL) for chatbot-only / 24×7 users.
* :class:`DpapiVaultBackend` — Windows current-user DPAPI for users who run a
  daemon.

Values never enter universe files, branch state, prompts, the commons, or MCP
responses. A connection stores only an opaque :data:`SecretRef` plus custody
metadata; the value is reachable only through a short-lived
:class:`SecretLease`. Every abnormal path raises
:class:`CredentialUnavailable` — never ``""``, ``None``, env, or ambient
fallback.

Design: ``docs/design-notes/2026-07-16-provider-generic-credential-vault.md``.
Review: ``docs/audits/2026-07-16-provider-generic-credential-vault-claude-review.md``.

This is the CORE module. It deliberately does NOT wire into the legacy
``tinyassets.credential_vault`` callers — that is the S5 integration seam,
sequenced separately.
"""

from __future__ import annotations

from .attestation import (
    BOOT_ID,
    AttestationResult,
    attest_store,
    byo_execution_enabled,
    operator_opt_in,
)
from .broker import VaultBroker
from .crypto import (
    FileKeyProvider,
    InMemoryKeyProvider,
    KeyProvider,
    canonical_aad,
)
from .errors import CredentialUnavailable, VaultErrorCode
from .local_backend import DpapiVaultBackend
from .platform_backend import PlatformVaultBackend
from .secret_bytes import SecretBytes, SecretLease
from .types import (
    PROBE_SCOPE,
    SECRET_REF_PREFIX,
    XCHACHA20POLY1305_IETF,
    Custody,
    DescriptorState,
    DpapiBlob,
    EncryptedRow,
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
    is_secret_ref,
    new_secret_ref,
)

__all__ = [
    # errors
    "CredentialUnavailable",
    "VaultErrorCode",
    # secret containers
    "SecretBytes",
    "SecretLease",
    # types
    "SecretKind",
    "Custody",
    "DescriptorState",
    "SecretScope",
    "VaultStore",
    "SecretBinding",
    "SecretDescriptor",
    "EncryptedRow",
    "DpapiBlob",
    "SecretRef",
    "SECRET_REF_PREFIX",
    "XCHACHA20POLY1305_IETF",
    "PROBE_SCOPE",
    "new_secret_ref",
    "is_secret_ref",
    # broker + backends
    "VaultBroker",
    "PlatformVaultBackend",
    "DpapiVaultBackend",
    # crypto
    "KeyProvider",
    "InMemoryKeyProvider",
    "FileKeyProvider",
    "canonical_aad",
    # attestation
    "AttestationResult",
    "attest_store",
    "byo_execution_enabled",
    "operator_opt_in",
    "BOOT_ID",
]

# SecretRef is a semantic alias for the opaque string reference type.
SecretRef = str

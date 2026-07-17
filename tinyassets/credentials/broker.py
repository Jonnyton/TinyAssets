"""The :class:`VaultBroker` protocol.

One provider-generic seam over the two custody backends. The seam is
deliberately HashiCorp-Vault-Transit-shaped ("encryption as a service"; the
caller never holds the KEK) so swapping the local-envelope platform backend for
Vault/KMS later is a backend change, not a rewrite (review adaptation #2). The
overall connector shape is the open-source Nango model, sized down.

Contract highlights:
  * ``put`` with ``replace=`` + ``expected_version=`` is atomic compare-and-swap.
  * ``get`` returns a :class:`SecretLease` — never raw bytes upward.
  * every failure is :class:`CredentialUnavailable`; ``""``/``None``/ambient
    fallbacks are forbidden.
  * the binding's discriminated ``store`` selects exactly ONE backend; the
    backend re-derives/verifies ref/kind/scope from protected contents.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .secret_bytes import SecretBytes, SecretLease
from .types import (
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
)


@runtime_checkable
class VaultBroker(Protocol):
    """Provider-generic credential custody seam."""

    def put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        *,
        replace: str | None = None,
        expected_version: int | None = None,
        expires_at: float | None = None,
    ) -> SecretDescriptor:
        """Store (or CAS-replace) a secret. Returns its non-secret descriptor."""

    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        """Return a short-lived lease over the stored value, scope-checked."""

    def delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        """Tombstone the binding and remove protected bytes. Absence is NOT_FOUND."""

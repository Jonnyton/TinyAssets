"""The :class:`VaultBroker` protocol.

One provider-generic seam over the two custody backends. The seam is
deliberately HashiCorp-Vault-Transit-shaped ("encryption as a service"; the
caller never holds the KEK) so swapping the local-envelope platform backend for
Vault/KMS later is a backend change, not a rewrite (review adaptation #2). The
overall connector shape is the open-source Nango model, sized down.

Contract highlights:
  * ``put`` with ``replace=`` + ``expected_version=`` is atomic compare-and-swap
    (both must be supplied together; a bare ``replace`` is rejected).
  * ``get`` returns a :class:`SecretLease` — never raw bytes upward.
  * **refresh is a first-class broker operation**: ``begin_refresh`` +
    ``complete_refresh`` are the sanctioned consume-before-mint pair. Integrations
    (S4/S5) MUST refresh one-time tokens through them — a plain CAS cannot advance
    a refresh without the durable ticket, so bypass is structurally prevented.
  * every failure is :class:`CredentialUnavailable`; ``""``/``None``/ambient
    fallbacks are forbidden.
  * the binding's discriminated ``store`` selects exactly ONE backend; the
    backend re-derives/verifies ref/kind/scope from protected contents.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .leases import RefreshTicket
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

    def begin_refresh(
        self, binding: SecretBinding, expected: SecretScope, holder: str, at_version: int
    ) -> RefreshTicket | None:
        """Atomically claim the exclusive right to redeem the current token.

        Returns a :class:`RefreshTicket` to the sole winner (who alone may call
        the provider), else ``None``. The claimed version is the authenticated
        current version, so a non-existent version cannot be permanently blocked.
        """

    def complete_refresh(
        self,
        binding: SecretBinding,
        expected: SecretScope,
        ticket: RefreshTicket,
        value: SecretBytes,
        *,
        expires_at: float | None = None,
    ) -> SecretDescriptor:
        """Store the refreshed secret, bound to ``ticket``'s durable claim."""

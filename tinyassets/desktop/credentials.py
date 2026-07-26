"""Fail-closed storage for packaged-tray account credentials.

Reusable desktop credentials are delegated to ``keyring`` so supported
platforms use Windows Credential Manager, macOS Keychain, or Linux Secret
Service. This module never offers a file or environment-variable fallback.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

_SERVICE = "io.tinyassets.desktop"
_REFERENCE_PREFIX = "tinyassets-desktop"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
_NATIVE_BACKENDS = {
    ("keyring.backends.Windows", "WinVaultKeyring"),
    ("keyring.backends.macOS", "Keyring"),
    ("keyring.backends.SecretService", "Keyring"),
}


class SecretStoreUnavailable(RuntimeError):
    """Raised when no supported operating-system secret store is usable."""


class SecretStore(Protocol):
    def set(self, reference: str, secret: str) -> None: ...

    def get(self, reference: str) -> str | None: ...

    def delete(self, reference: str) -> None: ...


class NativeCredentialStore:
    """Small adapter around the platform-native backend selected by keyring."""

    def __init__(self, *, keyring_module: Any | None = None) -> None:
        if keyring_module is None:
            try:
                import keyring as keyring_module
            except ImportError as exc:
                raise SecretStoreUnavailable(
                    "native operating-system secret store is unavailable; "
                    "install TinyAssets with the desktop dependencies"
                ) from exc
        self._keyring = keyring_module

    def _require_backend(self) -> None:
        try:
            backend = self._keyring.get_keyring()
            priority = float(backend.priority)
        except Exception as exc:
            raise SecretStoreUnavailable(
                "native operating-system secret store is unavailable; "
                "configure Windows Credential Manager, macOS Keychain, or "
                "Linux Secret Service before enabling persistent hosting"
            ) from exc
        identity = (type(backend).__module__, type(backend).__name__)
        if priority <= 0 or identity not in _NATIVE_BACKENDS:
            raise SecretStoreUnavailable(
                "native operating-system secret store is unavailable; "
                "configure Windows Credential Manager, macOS Keychain, or "
                "Linux Secret Service before enabling persistent hosting"
            )

    def set(self, reference: str, secret: str) -> None:
        self._require_backend()
        try:
            self._keyring.set_password(_SERVICE, reference, secret)
        except Exception as exc:
            raise SecretStoreUnavailable(
                "native operating-system secret store is unavailable"
            ) from exc

    def get(self, reference: str) -> str | None:
        self._require_backend()
        try:
            return self._keyring.get_password(_SERVICE, reference)
        except Exception as exc:
            raise SecretStoreUnavailable(
                "native operating-system secret store is unavailable"
            ) from exc

    def delete(self, reference: str) -> None:
        self._require_backend()
        try:
            if self._keyring.get_password(_SERVICE, reference) is not None:
                self._keyring.delete_password(_SERVICE, reference)
        except Exception as exc:
            raise SecretStoreUnavailable(
                "native operating-system secret store is unavailable"
            ) from exc


def _checked_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{label} must contain only letters, digits, '.', '_', or '-'")
    return normalized


class DesktopCredentialManager:
    """Store refresh tokens by opaque non-secret account/host reference."""

    def __init__(self, store: SecretStore | None = None) -> None:
        self._store = store or NativeCredentialStore()

    def save_refresh_token(
        self,
        *,
        account_id: str,
        host_id: str,
        refresh_token: str,
    ) -> str:
        if not refresh_token:
            raise ValueError("refresh token must not be empty")
        account = _checked_identifier(account_id, "account_id")
        host = _checked_identifier(host_id, "host_id")
        reference = f"{_REFERENCE_PREFIX}:{account}:{host}"
        self._store.set(reference, refresh_token)
        return reference

    def load_refresh_token(self, reference: str) -> str | None:
        self._validate_reference(reference)
        return self._store.get(reference)

    def delete(self, reference: str) -> None:
        self._validate_reference(reference)
        self._store.delete(reference)

    @staticmethod
    def _validate_reference(reference: str) -> None:
        parts = reference.split(":")
        if (
            len(parts) != 3
            or parts[0] != _REFERENCE_PREFIX
            or not _IDENTIFIER.fullmatch(parts[1])
            or not _IDENTIFIER.fullmatch(parts[2])
        ):
            raise ValueError("invalid desktop credential reference")


__all__ = [
    "DesktopCredentialManager",
    "NativeCredentialStore",
    "SecretStore",
    "SecretStoreUnavailable",
]

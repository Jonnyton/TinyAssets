"""Typed, fail-closed errors for the credential vault.

The single failure mode a broker or backend may surface to a caller is
:class:`CredentialUnavailable`. It NEVER carries a secret value, a backend
path/id, ciphertext, a wrapped DEK, or an OAuth flow body — only the machine
error ``code`` and the opaque ``ref`` (which encodes no provider/path/account).

Forbidden fallbacks (Hard Rule 8 — fail loudly, never silently): ``""``,
``None``, process env, shared auth homes, and any global/ambient credential are
never returned in place of a real value. Absence, corruption, scope mismatch,
version conflict, revocation, expiry, or failed attestation all raise here.
"""

from __future__ import annotations


class VaultErrorCode:
    """Canonical machine codes for :class:`CredentialUnavailable`.

    These are safe to log, surface in ``get_status``, and place in receipts:
    they name the error class, not the secret.
    """

    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    KIND_MISMATCH = "KIND_MISMATCH"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    CORRUPT_RECORD = "CORRUPT_RECORD"
    ATTESTATION_FAILED = "ATTESTATION_FAILED"
    CROSS_STORE_FORBIDDEN = "CROSS_STORE_FORBIDDEN"
    LEASE_TIMEOUT = "LEASE_TIMEOUT"
    LEASE_LOST = "LEASE_LOST"
    KEY_UNAVAILABLE = "KEY_UNAVAILABLE"
    KEK_INSECURE = "KEK_INSECURE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"
    # A refresh was claimed but never completed (crash/wedge): the provider may
    # or may not have rotated the one-use token, so the state is UNKNOWN — the
    # user must re-authorize. Retrying is unsafe; a silent None is dishonest.
    REAUTHORIZATION_REQUIRED = "REAUTHORIZATION_REQUIRED"

    _ALL = frozenset(
        {
            BACKEND_UNAVAILABLE,
            NOT_FOUND,
            SCOPE_MISMATCH,
            KIND_MISMATCH,
            VERSION_CONFLICT,
            CORRUPT_RECORD,
            ATTESTATION_FAILED,
            CROSS_STORE_FORBIDDEN,
            LEASE_TIMEOUT,
            LEASE_LOST,
            KEY_UNAVAILABLE,
            KEK_INSECURE,
            REVOKED,
            EXPIRED,
            DISABLED,
            REAUTHORIZATION_REQUIRED,
        }
    )


class CredentialUnavailable(Exception):
    """Raised whenever a credential cannot be safely resolved.

    Parameters
    ----------
    code:
        One of :class:`VaultErrorCode`. Unknown codes are rejected loudly so a
        typo can never masquerade as a recognized failure mode.
    ref:
        The opaque :data:`SecretRef` (``secret:v1:<hex>``) or ``None`` when no
        ref exists yet (e.g. backend unavailable at boot). Never a path, token,
        account, or provider-identifying value.

    The string form is deliberately minimal — ``code`` + ``ref`` only — so that
    logging the exception can never leak a secret value.
    """

    __slots__ = ("code", "ref")

    def __init__(self, code: str, ref: str | None = None) -> None:
        if code not in VaultErrorCode._ALL:
            raise ValueError(f"unknown vault error code: {code!r}")
        self.code = code
        self.ref = ref
        message = f"credential unavailable [{code}]"
        if ref:
            message += f" ref={ref}"
        super().__init__(message)

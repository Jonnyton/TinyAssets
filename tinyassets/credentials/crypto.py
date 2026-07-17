"""Envelope encryption for the platform backend.

Primitive (review adaptation #1): **libsodium XChaCha20-Poly1305-IETF AEAD**
(via PyNaCl). Chosen over AES-256-GCM and over libsodium secretbox because the
AEAD variant lets us bind canonical scope/ref/version metadata as *additional
authenticated data* on BOTH envelope layers, so swapping a ciphertext or a
wrapped DEK between records fails authentication.

Envelope shape (per record):
  * a fresh random 32-byte **DEK** encrypts the framed payload;
  * the active **KEK** wraps that DEK;
  * the SAME canonical AAD (scope/ref/kind/version/algorithm) authenticates both
    layers.

Rotation rewraps the DEK under a new KEK (AAD unchanged) and leaves the payload
ciphertext untouched — see :meth:`PlatformVaultBackend.rotate_kek`.

The KEK source is injected via :class:`KeyProvider` so production reads a
root-only key file while tests supply an in-memory key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from nacl import bindings as _sodium

from .errors import CredentialUnavailable, VaultErrorCode
from .types import XCHACHA20POLY1305_IETF, SecretScope

KEK_BYTES = _sodium.crypto_aead_xchacha20poly1305_ietf_KEYBYTES  # 32
DEK_BYTES = _sodium.crypto_aead_xchacha20poly1305_ietf_KEYBYTES  # 32
NONCE_BYTES = _sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES  # 24


# ---------------------------------------------------------------------------
# KEK source (injectable)
# ---------------------------------------------------------------------------


@runtime_checkable
class KeyProvider(Protocol):
    """Supplies KEKs by id and names the active KEK.

    Implementations must hold *both* the old and new KEK during a rotation so
    every live record can be unwrapped-then-rewrapped.
    """

    def active_key_id(self) -> str: ...

    def get_key(self, key_id: str) -> bytes: ...


class InMemoryKeyProvider:
    """Test / ephemeral KEK provider. Never used in production custody."""

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        for kid, key in keys.items():
            if len(key) != KEK_BYTES:
                raise ValueError(f"KEK {kid!r} must be {KEK_BYTES} bytes")
        if active_key_id not in keys:
            raise ValueError("active_key_id must be present in keys")
        self._keys = dict(keys)
        self._active = active_key_id

    def active_key_id(self) -> str:
        return self._active

    def get_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None


class FileKeyProvider:
    """Reads 32-byte KEK files from a root-only directory OUTSIDE ``/data``.

    Layout::

        <keys_dir>/<key_id>.bin      # 32 random bytes, mode 0400, root-owned
        <keys_dir>/active            # text file naming the active key_id

    The active key id may be overridden by ``TINYASSETS_VAULT_ACTIVE_KEY_ID`` or
    the constructor. Keys are cached in-process after first read; the custody
    boundary is the host file mount, not this class.
    """

    _ACTIVE_FILE = "active"

    def __init__(self, keys_dir: str | Path, active_key_id: str | None = None) -> None:
        self._dir = Path(keys_dir)
        self._cache: dict[str, bytes] = {}
        self._active_override = active_key_id

    def active_key_id(self) -> str:
        if self._active_override:
            return self._active_override
        env = os.environ.get("TINYASSETS_VAULT_ACTIVE_KEY_ID", "").strip()
        if env:
            return env
        marker = self._dir / self._ACTIVE_FILE
        try:
            value = marker.read_text(encoding="utf-8").strip()
        except OSError:
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None
        if not value or "/" in value or "\\" in value or value.startswith("."):
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        return value

    def get_key(self, key_id: str) -> bytes:
        if not key_id or "/" in key_id or "\\" in key_id or key_id.startswith("."):
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        cached = self._cache.get(key_id)
        if cached is not None:
            return cached
        path = self._dir / f"{key_id}.bin"
        try:
            raw = path.read_bytes()
        except OSError:
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None
        if len(raw) != KEK_BYTES:
            # A wrong-sized key is corruption, not a usable KEK — fail loud.
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        self._cache[key_id] = raw
        return raw


# ---------------------------------------------------------------------------
# Canonical AAD + framing
# ---------------------------------------------------------------------------


def canonical_aad(scope: SecretScope, ref: str, kind: str, version: int) -> bytes:
    """Deterministic additional-authenticated-data for both envelope layers.

    Binds the ciphertext to (algorithm, kind, ref, scope, version). Any tamper
    of these fields — including a cross-record swap — changes the AAD and fails
    the Poly1305 tag on decrypt. ``key_id`` is deliberately NOT part of the AAD
    so a KEK rotation can rewrap without touching the payload ciphertext.
    """
    payload = {
        "algorithm": XCHACHA20POLY1305_IETF,
        "kind": kind,
        "ref": ref,
        "scope": scope.as_dict(),
        "version": int(version),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def frame_payload(scope: SecretScope, ref: str, kind: str, version: int, value: bytes) -> bytes:
    """Prefix the secret value with an embedded identity header.

    The header repeats the canonical identity INSIDE the sealed payload so a
    backend can verify-after-decrypt (belt-and-suspenders alongside the AAD, and
    the sole binding for DPAPI which lacks AAD). Length-prefixed so the raw value
    is never text-encoded.
    """
    header = canonical_aad(scope, ref, kind, version)
    return len(header).to_bytes(4, "big") + header + value


def unframe_payload(blob: bytes) -> tuple[bytes, bytes]:
    """Split a framed payload into (identity_header, value). Raises on truncation."""
    if len(blob) < 4:
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    n = int.from_bytes(blob[:4], "big")
    if n < 0 or 4 + n > len(blob):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    return blob[4 : 4 + n], blob[4 + n :]


# ---------------------------------------------------------------------------
# Two-layer AEAD envelope
# ---------------------------------------------------------------------------


class Envelope:
    """Fields produced/consumed by the envelope, minus persistence concerns."""

    __slots__ = ("key_id", "wrap_nonce", "wrapped_dek", "data_nonce", "ciphertext")

    def __init__(
        self,
        key_id: str,
        wrap_nonce: bytes,
        wrapped_dek: bytes,
        data_nonce: bytes,
        ciphertext: bytes,
    ) -> None:
        self.key_id = key_id
        self.wrap_nonce = wrap_nonce
        self.wrapped_dek = wrapped_dek
        self.data_nonce = data_nonce
        self.ciphertext = ciphertext


def seal(
    key_provider: KeyProvider,
    scope: SecretScope,
    ref: str,
    kind: str,
    version: int,
    value: bytes,
) -> Envelope:
    """Encrypt ``value`` under a fresh DEK; wrap the DEK under the active KEK."""
    aad = canonical_aad(scope, ref, kind, version)
    key_id = key_provider.active_key_id()
    kek = key_provider.get_key(key_id)

    dek = _sodium.randombytes(DEK_BYTES)
    data_nonce = _sodium.randombytes(NONCE_BYTES)
    wrap_nonce = _sodium.randombytes(NONCE_BYTES)

    payload = frame_payload(scope, ref, kind, version, value)
    ciphertext = _sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        payload, aad, data_nonce, dek
    )
    wrapped_dek = _sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        dek, aad, wrap_nonce, kek
    )
    return Envelope(key_id, wrap_nonce, wrapped_dek, data_nonce, ciphertext)


def open_envelope(
    key_provider: KeyProvider,
    envelope: Envelope,
    scope: SecretScope,
    ref: str,
    kind: str,
    version: int,
) -> bytes:
    """Unwrap the DEK and decrypt the payload, verifying AAD + embedded identity.

    Any authentication failure, or a mismatch between the embedded identity and
    the expected (scope/ref/kind/version), raises ``CORRUPT_RECORD`` — never a
    partial or plaintext leak.
    """
    aad = canonical_aad(scope, ref, kind, version)
    try:
        kek = key_provider.get_key(envelope.key_id)
    except CredentialUnavailable:
        raise
    try:
        dek = _sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            envelope.wrapped_dek, aad, envelope.wrap_nonce, kek
        )
        payload = _sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            envelope.ciphertext, aad, envelope.data_nonce, dek
        )
    except Exception:  # noqa: BLE001 — libsodium raises CryptoError on tag fail
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None

    header, value = unframe_payload(payload)
    if header != aad:
        # Embedded identity disagrees with the expected identity → tampered row.
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
    return value


def rewrap_dek(
    key_provider: KeyProvider,
    envelope: Envelope,
    scope: SecretScope,
    ref: str,
    kind: str,
    version: int,
    new_key_id: str,
) -> Envelope:
    """Unwrap the DEK with its current KEK and rewrap under ``new_key_id``.

    The payload ciphertext and data nonce are unchanged — only the wrap layer and
    ``key_id`` change. Used by KEK rotation.
    """
    aad = canonical_aad(scope, ref, kind, version)
    old_kek = key_provider.get_key(envelope.key_id)
    try:
        dek = _sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            envelope.wrapped_dek, aad, envelope.wrap_nonce, old_kek
        )
    except Exception:  # noqa: BLE001
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None

    new_kek = key_provider.get_key(new_key_id)
    new_wrap_nonce = _sodium.randombytes(NONCE_BYTES)
    new_wrapped_dek = _sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        dek, aad, new_wrap_nonce, new_kek
    )
    return Envelope(
        new_key_id,
        new_wrap_nonce,
        new_wrapped_dek,
        envelope.data_nonce,
        envelope.ciphertext,
    )

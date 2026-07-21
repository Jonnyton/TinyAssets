"""Envelope encryption for the platform backend.

Primitive: **libsodium XChaCha20-Poly1305-IETF AEAD** (via PyNaCl). The reason to
prefer it here is operational, not a claim of a stronger authenticator: its
192-bit nonce makes independent RANDOM per-record nonces collision-safe with no
counter/nonce-management state (AES-256-GCM's 96-bit nonce would require careful
nonce management to reach the same margin). AES-GCM also authenticates AAD; the
choice is about safe random nonces, not AAD support.

Envelope shape (per record):
  * a fresh random 32-byte **DEK** encrypts the framed payload;
  * the active **KEK** wraps that DEK;
  * the SAME canonical AAD authenticates both layers.

The AAD binds the record's **immutable identity** — scope, ref, kind, version,
and the immutable store identity (store_id, custody, daemon_id). Binding store
identity into the AAD means a cross-store decrypt fails authentication outright.
``key_id`` is deliberately excluded so KEK rotation can rewrap without touching
payload ciphertext.

The full **authoritative record** (identity PLUS mutable lifecycle: state,
expiry, timestamps) lives INSIDE the sealed payload. Plaintext DB/sidecar columns
are non-authoritative index hints; every authorization decision on read is taken
from the decrypted record. This is why tampering a plaintext ``expires_at`` or
``store_id`` column has zero effect.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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

    Library-layer custody gates (fail loud on violation):
      * the KEK file must NOT be a symlink (symlink-swap defense, all platforms);
      * on POSIX, mode must be ``0400``/``0600`` (no group/other bits) and owned
        by ``expected_uid`` (default ``0`` = root).

    On Windows these POSIX bits are not meaningful; ACLs are the equivalent
    control and are enforced by the installer, not this library. The active key
    id may be overridden by ``TINYASSETS_VAULT_ACTIVE_KEY_ID`` or the constructor.
    """

    _ACTIVE_FILE = "active"

    def __init__(
        self,
        keys_dir: str | Path,
        active_key_id: str | None = None,
        *,
        enforce_permissions: bool = True,
        expected_uid: int | None = 0,
    ) -> None:
        self._dir = Path(keys_dir)
        self._cache: dict[str, bytes] = {}
        self._active_override = active_key_id
        self._enforce_permissions = enforce_permissions
        self._expected_uid = expected_uid

    def active_key_id(self) -> str:
        if self._active_override:
            return self._active_override
        env = os.environ.get("TINYASSETS_VAULT_ACTIVE_KEY_ID", "").strip()
        if env:
            return env
        self._verify_dir_not_symlink()
        # Read the active-marker with the same no-follow discipline as a key file.
        value = self._read_secure(self._dir / self._ACTIVE_FILE).decode("utf-8").strip()
        if not value or "/" in value or "\\" in value or value.startswith("."):
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        return value

    def _verify_dir_not_symlink(self) -> None:
        try:
            if stat.S_ISLNK(os.lstat(self._dir).st_mode):
                raise CredentialUnavailable(VaultErrorCode.KEK_INSECURE)
        except OSError:
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None

    def _read_secure(self, path: Path) -> bytes:
        """Open with O_NOFOLLOW, fstat the DESCRIPTOR, validate, then read.

        Closes the lstat→read TOCTOU: the descriptor we validate is the same one
        we read (a symlink swapped in between cannot redirect us). On POSIX we
        also enforce mode/owner on the fd. On Windows ``O_NOFOLLOW`` is absent;
        symlink creation there already needs privilege and ACLs govern.
        """
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            # ELOOP (symlink with O_NOFOLLOW) or missing → fail closed.
            import errno

            if getattr(exc, "errno", None) == errno.ELOOP:
                raise CredentialUnavailable(VaultErrorCode.KEK_INSECURE) from None
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None
        try:
            st = os.fstat(fd)
            if stat.S_ISLNK(st.st_mode):  # belt-and-suspenders
                raise CredentialUnavailable(VaultErrorCode.KEK_INSECURE)
            if self._enforce_permissions and os.name == "posix":
                if stat.S_IMODE(st.st_mode) & 0o077:
                    raise CredentialUnavailable(VaultErrorCode.KEK_INSECURE)
                if self._expected_uid is not None and st.st_uid != self._expected_uid:
                    raise CredentialUnavailable(VaultErrorCode.KEK_INSECURE)
            return os.read(fd, st.st_size if st.st_size > 0 else 4096)
        finally:
            os.close(fd)

    def get_key(self, key_id: str) -> bytes:
        if not key_id or "/" in key_id or "\\" in key_id or key_id.startswith("."):
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        cached = self._cache.get(key_id)
        if cached is not None:
            return cached
        self._verify_dir_not_symlink()
        raw = self._read_secure(self._dir / f"{key_id}.bin")
        if len(raw) != KEK_BYTES:
            # A wrong-sized key is corruption, not a usable KEK — fail loud.
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
        self._cache[key_id] = raw
        return raw


# ---------------------------------------------------------------------------
# Canonical AAD (immutable identity) + authoritative-record codec + framing
# ---------------------------------------------------------------------------


def identity_aad(
    scope: SecretScope,
    ref: str,
    kind: str,
    version: int,
    store_id: str,
    custody: str,
    daemon_id: str | None,
) -> bytes:
    """Additional-authenticated-data binding the record's IMMUTABLE identity.

    Includes scope/ref/kind/version AND the immutable store identity
    (store_id/custody/daemon_id). Any tamper — including a cross-record or
    cross-store swap — changes the AAD and fails the Poly1305 tag on decrypt.
    ``key_id`` is excluded so KEK rotation can rewrap without a payload rewrite.
    """
    payload = {
        "algorithm": XCHACHA20POLY1305_IETF,
        "custody": custody,
        "daemon_id": daemon_id,
        "kind": kind,
        "ref": ref,
        "scope": scope.as_dict(),
        "store_id": store_id,
        "version": int(version),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _reject_nan(_token: str) -> float:
    # json.loads calls parse_constant for NaN / Infinity / -Infinity.
    raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)


def encode_record(record: dict[str, Any]) -> bytes:
    """Canonical JSON for the authoritative record embedded in the payload.

    ``allow_nan=False`` refuses to serialize a ``NaN``/``Infinity`` — non-finite
    metadata must never be persisted.
    """
    try:
        return json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except ValueError as exc:  # non-finite float
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from exc


def decode_record(raw: bytes) -> dict[str, Any]:
    try:
        # parse_constant rejects NaN/Infinity that a tampered payload might carry.
        obj = json.loads(raw.decode("utf-8"), parse_constant=_reject_nan)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from exc
    if not isinstance(obj, dict):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    return obj


def frame_record(record_json: bytes, value: bytes) -> bytes:
    """Length-prefix the authoritative record ahead of the raw value bytes."""
    return len(record_json).to_bytes(4, "big") + record_json + value


def unframe_record(blob: bytes) -> tuple[bytes, bytes]:
    """Split a framed payload into (record_json, value). Raises on truncation."""
    if len(blob) < 4:
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    n = int.from_bytes(blob[:4], "big")
    if n < 0 or 4 + n > len(blob):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    return blob[4 : 4 + n], blob[4 + n :]


# ---------------------------------------------------------------------------
# Two-layer AEAD envelope (generic over payload/AAD)
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


def seal(key_provider: KeyProvider, aad: bytes, payload: bytes) -> Envelope:
    """Encrypt ``payload`` under a fresh DEK; wrap the DEK under the active KEK.

    ``aad`` authenticates both the payload ciphertext and the wrapped DEK.
    """
    key_id = key_provider.active_key_id()
    kek = key_provider.get_key(key_id)

    dek = _sodium.randombytes(DEK_BYTES)
    data_nonce = _sodium.randombytes(NONCE_BYTES)
    wrap_nonce = _sodium.randombytes(NONCE_BYTES)

    ciphertext = _sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        payload, aad, data_nonce, dek
    )
    wrapped_dek = _sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        dek, aad, wrap_nonce, kek
    )
    return Envelope(key_id, wrap_nonce, wrapped_dek, data_nonce, ciphertext)


def open_envelope(
    key_provider: KeyProvider, envelope: Envelope, aad: bytes, ref: str | None = None
) -> bytes:
    """Unwrap the DEK and decrypt the payload, verifying the AAD on both layers.

    Any authentication failure raises ``CORRUPT_RECORD`` — never a partial or
    plaintext leak. Returns the framed payload bytes.
    """
    kek = key_provider.get_key(envelope.key_id)  # may raise KEY_UNAVAILABLE
    try:
        dek = _sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            envelope.wrapped_dek, aad, envelope.wrap_nonce, kek
        )
        payload = _sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            envelope.ciphertext, aad, envelope.data_nonce, dek
        )
    except Exception:  # noqa: BLE001 — libsodium raises CryptoError on tag fail
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None
    return payload


def rewrap_dek(
    key_provider: KeyProvider, envelope: Envelope, aad: bytes, new_key_id: str,
    ref: str | None = None,
) -> Envelope:
    """Unwrap the DEK with its current KEK and rewrap under ``new_key_id``.

    The payload ciphertext and data nonce are unchanged — only the wrap layer and
    ``key_id`` change. Used by KEK rotation.
    """
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

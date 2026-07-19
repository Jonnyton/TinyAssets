"""Daemon device keys and signed-request authentication.

Production key material is held behind an OS-keystore operation interface.  The
Windows implementation uses Credential Manager; it never writes plaintext key
files and never exposes private-key bytes through the public API.  Windows
Credential Manager is software-backed, so it is reported honestly as not
hardware-non-exportable.  Unsupported platforms fail closed instead of falling
back to a file.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import platform
import secrets
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Protocol

from nacl.bindings import crypto_scalarmult
from nacl.public import PrivateKey
from nacl.signing import SigningKey

MAX_ACCESS_TOKEN_LIFETIME_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 60
_REQUEST_DOMAIN = b"tinyassets.daemon-request.v1\0"
_CHALLENGE_DOMAIN = b"tinyassets.daemon-challenge.v1\0"
_THUMBPRINT_DOMAIN = b"tinyassets.daemon-ed25519.v1\0"
_TOKEN_REFRESH_LEEWAY_SECONDS = 30


class KeystoreUnavailableError(RuntimeError):
    """Raised when no supported secure OS key store is available."""


class DeviceKeyStore(Protocol):
    """Non-exporting key-operation boundary used by ``DaemonSigner``."""

    backend_name: str
    hardware_non_exportable: bool

    def load_or_create(self, installation_id: str) -> DevicePublicIdentity: ...

    def sign(self, installation_id: str, message: bytes) -> bytes: ...

    def exchange(self, installation_id: str, peer_public_key: bytes) -> bytes: ...


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("base64url value must be a non-empty string")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url value") from exc


def device_key_thumbprint(ed25519_public_key: bytes) -> str:
    if len(ed25519_public_key) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    return _b64encode(hashlib.sha256(_THUMBPRINT_DOMAIN + ed25519_public_key).digest())


@dataclass(frozen=True)
class DevicePublicIdentity:
    installation_id: str
    ed25519_public_key: bytes
    x25519_public_key: bytes
    installation_nonce: bytes
    key_backend: str
    hardware_non_exportable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.installation_id, str) or not self.installation_id.strip():
            raise ValueError("installation_id is required")
        if len(self.ed25519_public_key) != 32:
            raise ValueError("Ed25519 public key must be 32 bytes")
        if len(self.x25519_public_key) != 32:
            raise ValueError("X25519 public key must be 32 bytes")
        if len(self.installation_nonce) < 32:
            raise ValueError("installation nonce must be at least 32 bytes")

    @property
    def key_thumbprint(self) -> str:
        return device_key_thumbprint(self.ed25519_public_key)

    def as_enrollment_payload(self) -> dict[str, str]:
        return {
            "installation_id": self.installation_id,
            "ed25519_public_key": _b64encode(self.ed25519_public_key),
            "x25519_public_key": _b64encode(self.x25519_public_key),
            "installation_nonce": _b64encode(self.installation_nonce),
        }


@dataclass(frozen=True)
class SignedRequest:
    method: str
    path: str
    body_hash: str
    timestamp: int
    nonce: str
    signature: str

    def as_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "X-TinyAssets-Body-SHA256": self.body_hash,
            "X-TinyAssets-Timestamp": str(self.timestamp),
            "X-TinyAssets-Nonce": self.nonce,
            "X-TinyAssets-Signature": self.signature,
        }


@dataclass(frozen=True)
class AccessToken:
    value: str
    daemon_id: str
    key_thumbprint: str
    credential_epoch: int
    expires_at: float


def request_body_hash(body: bytes | None) -> str:
    return hashlib.sha256(body or b"").hexdigest()


def canonical_request(
    method: str,
    path: str,
    body_hash: str,
    timestamp: int,
    nonce: str,
) -> bytes:
    if not method or not path.startswith("/"):
        raise ValueError("signed request requires a method and absolute path")
    if len(body_hash) != 64 or any(char not in "0123456789abcdef" for char in body_hash):
        raise ValueError("body_hash must be a lowercase SHA-256 hex digest")
    if not nonce or len(nonce) > 256:
        raise ValueError("request nonce must contain 1 to 256 characters")
    payload = {
        "body_sha256": body_hash,
        "method": method.upper(),
        "nonce": nonce,
        "path": path,
        "timestamp": int(timestamp),
    }
    return _REQUEST_DOMAIN + json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def canonical_challenge(daemon_id: str, challenge: str) -> bytes:
    if not daemon_id or not challenge:
        raise ValueError("daemon_id and challenge are required")
    payload = {"challenge": challenge, "daemon_id": daemon_id}
    return _CHALLENGE_DOMAIN + json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


class DaemonSigner:
    """Uses an OS-keystore identity without exposing its private keys."""

    def __init__(
        self,
        installation_id: str,
        *,
        key_store: DeviceKeyStore | None = None,
    ) -> None:
        self._key_store = key_store or default_device_keystore()
        self.identity = self._key_store.load_or_create(installation_id)

    def sign(self, message: bytes) -> bytes:
        return self._key_store.sign(self.identity.installation_id, message)

    def sign_challenge(self, daemon_id: str, challenge: str) -> str:
        return _b64encode(self.sign(canonical_challenge(daemon_id, challenge)))

    def exchange(self, peer_public_key: bytes) -> bytes:
        return self._key_store.exchange(self.identity.installation_id, peer_public_key)


class DaemonAuthSession:
    """Produces bearer plus proof-of-possession headers for every request."""

    def __init__(
        self,
        signer: DaemonSigner,
        *,
        token_supplier: Callable[[], AccessToken],
    ) -> None:
        self._signer = signer
        self._token_supplier = token_supplier
        self._token: AccessToken | None = None
        self._token_lock = threading.RLock()

    def _access_token(self) -> AccessToken:
        with self._token_lock:
            now = time.time()
            if (
                self._token is None
                or self._token.expires_at <= now + _TOKEN_REFRESH_LEEWAY_SECONDS
            ):
                supplied = self._token_supplier()
                if supplied.expires_at <= now:
                    raise ValueError("token supplier returned an expired access token")
                if supplied.key_thumbprint != self._signer.identity.key_thumbprint:
                    raise ValueError("access token is bound to a different device key")
                self._token = supplied
            return self._token

    def sign_request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> SignedRequest:
        token = self._access_token()
        return self._sign_request(
            token,
            method,
            path,
            body,
            timestamp=timestamp,
            nonce=nonce,
        )

    def _sign_request(
        self,
        token: AccessToken,
        method: str,
        path: str,
        body: bytes | None,
        *,
        timestamp: int | None,
        nonce: str | None,
    ) -> SignedRequest:
        if token.key_thumbprint != self._signer.identity.key_thumbprint:
            raise ValueError("access token is bound to a different device key")
        request_timestamp = int(time.time()) if timestamp is None else int(timestamp)
        request_nonce = nonce or secrets.token_urlsafe(24)
        body_hash = request_body_hash(body)
        message = canonical_request(method, path, body_hash, request_timestamp, request_nonce)
        return SignedRequest(
            method=method.upper(),
            path=path,
            body_hash=body_hash,
            timestamp=request_timestamp,
            nonce=request_nonce,
            signature=_b64encode(self._signer.sign(message)),
        )

    def sign_headers(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        token = self._access_token()
        signed = self._sign_request(
            token,
            method,
            path,
            body,
            timestamp=timestamp,
            nonce=nonce,
        )
        return signed.as_headers(token.value)


class _CredentialApi(Protocol):
    def read(self, target: str) -> bytes | None: ...

    def write(self, target: str, secret: bytes) -> None: ...


class _WindowsCredentialApi:
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168

    class _Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise KeystoreUnavailableError("Windows Credential Manager is unsupported here")
        self._advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        credential_pointer = ctypes.POINTER(self._Credential)
        self._advapi.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(credential_pointer),
        ]
        self._advapi.CredReadW.restype = wintypes.BOOL
        self._advapi.CredWriteW.argtypes = [ctypes.POINTER(self._Credential), wintypes.DWORD]
        self._advapi.CredWriteW.restype = wintypes.BOOL
        self._advapi.CredFree.argtypes = [wintypes.LPVOID]
        self._advapi.CredFree.restype = None

    def read(self, target: str) -> bytes | None:
        pointer = ctypes.POINTER(self._Credential)()
        if not self._advapi.CredReadW(target, self._CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == self._ERROR_NOT_FOUND:
                return None
            raise KeystoreUnavailableError(f"Windows Credential Manager read failed: {error}")
        try:
            return ctypes.string_at(
                pointer.contents.CredentialBlob,
                pointer.contents.CredentialBlobSize,
            )
        finally:
            self._advapi.CredFree(pointer)

    def write(self, target: str, secret: bytes) -> None:
        if not secret or len(secret) > 2560:
            raise ValueError("credential secret must contain 1 to 2560 bytes")
        blob = (ctypes.c_ubyte * len(secret)).from_buffer_copy(secret)
        credential = self._Credential()
        credential.Type = self._CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(secret)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "TinyAssets daemon"
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            error = ctypes.get_last_error()
            raise KeystoreUnavailableError(f"Windows Credential Manager write failed: {error}")


class WindowsCredentialKeyStore:
    """Ed25519/X25519 custody backed by Windows Credential Manager.

    Credential Manager protects the stored blob with the current Windows user
    boundary.  It is not a hardware KSP and is therefore not represented as
    hardware-non-exportable.  The class exposes only signing and key-agreement
    operations, never a private-key export operation.
    """

    backend_name = "windows-credential-manager"
    hardware_non_exportable = False

    def __init__(self, *, credential_api: _CredentialApi | None = None) -> None:
        self._credential_api = credential_api or _WindowsCredentialApi()
        self._lock = threading.RLock()

    @staticmethod
    def _target(installation_id: str) -> str:
        if not installation_id.strip():
            raise ValueError("installation_id is required")
        digest = hashlib.sha256(installation_id.encode("utf-8")).hexdigest()
        return f"TinyAssets/daemon-auth/v1/{digest}"

    def _load_material(self, installation_id: str) -> tuple[SigningKey, PrivateKey, bytes]:
        raw = self._credential_api.read(self._target(installation_id))
        if raw is None:
            raise KeystoreUnavailableError(
                "device identity is missing from Windows Credential Manager"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
            if payload.get("version") != 1:
                raise ValueError("unsupported key record version")
            signing_key = SigningKey(b64decode(payload["ed25519_seed"]))
            transfer_key = PrivateKey(b64decode(payload["x25519_private_key"]))
            nonce = b64decode(payload["installation_nonce"])
            if len(nonce) < 32:
                raise ValueError("installation nonce is too short")
            return signing_key, transfer_key, nonce
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise KeystoreUnavailableError("Windows device key record is corrupt") from exc

    def load_or_create(self, installation_id: str) -> DevicePublicIdentity:
        with self._lock:
            target = self._target(installation_id)
            if self._credential_api.read(target) is None:
                signing_key = SigningKey.generate()
                transfer_key = PrivateKey.generate()
                nonce = secrets.token_bytes(32)
                record = json.dumps(
                    {
                        "version": 1,
                        "ed25519_seed": _b64encode(signing_key.encode()),
                        "x25519_private_key": _b64encode(transfer_key.encode()),
                        "installation_nonce": _b64encode(nonce),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._credential_api.write(target, record)
            signing_key, transfer_key, nonce = self._load_material(installation_id)
        return DevicePublicIdentity(
            installation_id=installation_id,
            ed25519_public_key=signing_key.verify_key.encode(),
            x25519_public_key=transfer_key.public_key.encode(),
            installation_nonce=nonce,
            key_backend=self.backend_name,
            hardware_non_exportable=self.hardware_non_exportable,
        )

    def sign(self, installation_id: str, message: bytes) -> bytes:
        with self._lock:
            signing_key, _, _ = self._load_material(installation_id)
        return signing_key.sign(message).signature

    def exchange(self, installation_id: str, peer_public_key: bytes) -> bytes:
        if len(peer_public_key) != 32:
            raise ValueError("X25519 peer public key must be 32 bytes")
        with self._lock:
            _, transfer_key, _ = self._load_material(installation_id)
        return crypto_scalarmult(transfer_key.encode(), peer_public_key)


def default_device_keystore(*, platform_name: str | None = None) -> DeviceKeyStore:
    selected_platform = platform_name or platform.system()
    if selected_platform.casefold() == "windows":
        return WindowsCredentialKeyStore()
    raise KeystoreUnavailableError(
        f"secure daemon key storage is unsupported on {selected_platform}; "
        "no plaintext fallback is permitted"
    )


__all__ = [
    "AccessToken",
    "DaemonAuthSession",
    "DaemonSigner",
    "DeviceKeyStore",
    "DevicePublicIdentity",
    "KeystoreUnavailableError",
    "MAX_ACCESS_TOKEN_LIFETIME_SECONDS",
    "MAX_CLOCK_SKEW_SECONDS",
    "SignedRequest",
    "WindowsCredentialKeyStore",
    "b64decode",
    "canonical_challenge",
    "canonical_request",
    "default_device_keystore",
    "device_key_thumbprint",
    "request_body_hash",
]

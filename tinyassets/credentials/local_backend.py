"""Local custody backend: Windows current-user DPAPI.

For users who run a daemon. One immutable per-ref blob under
``%LOCALAPPDATA%\\TinyAssets\\credential-store\\v1``, outside any repository or
universe directory. Protection is ALWAYS current-user DPAPI with
``CRYPTPROTECT_UI_FORBIDDEN`` — NEVER ``CRYPTPROTECT_LOCAL_MACHINE`` (which any
local principal could decrypt).

The canonical scope/ref/kind/version identity is passed as DPAPI *entropy* (the
AAD-equivalent, since DPAPI has no AAD) AND embedded inside the sealed payload
for verify-after-decrypt. The DACL should be narrowed to the daemon SID + SYSTEM
by the installer; this module writes the blob and relies on the LOCALAPPDATA
per-user ACL for baseline isolation.

The module imports cross-platform; instantiating/using it off Windows raises
``CredentialUnavailable(BACKEND_UNAVAILABLE)`` so callers fail loud. DPAPI tests
skip on non-Windows.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import json
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .crypto import canonical_aad, frame_payload, unframe_payload
from .errors import CredentialUnavailable, VaultErrorCode
from .paths import local_store_dir
from .secret_bytes import SecretBytes, SecretLease
from .types import (
    Custody,
    DescriptorState,
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
    new_secret_ref,
)

IS_WINDOWS = sys.platform == "win32"
_PROTECTION = "dpapi-current-user"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


# ---------------------------------------------------------------------------
# DPAPI ctypes layer (Windows only)
# ---------------------------------------------------------------------------
if IS_WINDOWS:  # pragma: no cover - platform-gated
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    def _configure() -> tuple[Any, Any]:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
        ]
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        return crypt32, kernel32

    _CRYPT32, _KERNEL32 = _configure()

    def _to_blob(data: bytes) -> tuple[_DATA_BLOB, Any]:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        return blob, buf

    def _from_blob(blob: "_DATA_BLOB") -> bytes:
        return ctypes.string_at(blob.pbData, int(blob.cbData))

    def dpapi_protect(data: bytes, entropy: bytes) -> bytes:
        in_blob, _in_buf = _to_blob(data)
        ent_blob, _ent_buf = _to_blob(entropy)
        out_blob = _DATA_BLOB()
        ok = _CRYPT32.CryptProtectData(
            ctypes.byref(in_blob), "tinyassets-credential-vault",
            ctypes.byref(ent_blob), None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob),
        )
        if not ok:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)
        try:
            return _from_blob(out_blob)
        finally:
            _KERNEL32.LocalFree(out_blob.pbData)

    def dpapi_unprotect(blob_bytes: bytes, entropy: bytes) -> bytes:
        in_blob, _in_buf = _to_blob(blob_bytes)
        ent_blob, _ent_buf = _to_blob(entropy)
        out_blob = _DATA_BLOB()
        ok = _CRYPT32.CryptUnprotectData(
            ctypes.byref(in_blob), None, ctypes.byref(ent_blob), None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob),
        )
        if not ok:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
        try:
            return _from_blob(out_blob)
        finally:
            _KERNEL32.LocalFree(out_blob.pbData)
else:  # non-Windows: keep imports working, fail loud on use

    def dpapi_protect(data: bytes, entropy: bytes) -> bytes:  # noqa: ARG001
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    def dpapi_unprotect(blob_bytes: bytes, entropy: bytes) -> bytes:  # noqa: ARG001
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)


def _ref_filename(ref: str) -> str:
    # ref = "secret:v1:<hex>"; the hex tail is filename-safe and unique.
    tail = ref.rsplit(":", 1)[-1]
    if not tail.isalnum():
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
    return f"{tail}.json"


def _chmod_best_effort(path: Path, mode: int) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


class DpapiVaultBackend:
    """Windows current-user DPAPI store behind the :class:`VaultBroker` seam."""

    def __init__(
        self,
        *,
        daemon_id: str,
        store_id: str = "daemon:default",
        base: str | Path | None = None,
    ) -> None:
        self._daemon_id = daemon_id
        self._store_id = store_id
        self._dir = local_store_dir(base)
        self._attested: bool | None = None

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def custody(self) -> Custody:
        return Custody.DAEMON_LOCAL

    def _require_available(self) -> None:
        if not IS_WINDOWS:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    def _require_local_store(self, store: VaultStore) -> None:
        if store.custody != Custody.DAEMON_LOCAL:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)
        if store.store_id != self._store_id or store.daemon_id != self._daemon_id:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)

    def _blob_path(self, ref: str) -> Path:
        return self._dir / _ref_filename(ref)

    # ------------------------------------------------------------------
    # attestation gate
    # ------------------------------------------------------------------
    def _ensure_attested(self) -> None:
        if self._attested is True:
            return
        if self._attested is False:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)
        from .attestation import attest_store

        result = attest_store(self)
        self._attested = result.ok
        if not result.ok:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    def attest(self) -> Any:
        from .attestation import attest_store

        result = attest_store(self)
        self._attested = result.ok
        return result

    # ------------------------------------------------------------------
    # VaultBroker surface (attestation-gated)
    # ------------------------------------------------------------------
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
        self._require_available()
        self._require_local_store(store)
        self._ensure_attested()
        return self._put(store, scope, kind, value, replace, expected_version, expires_at)

    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        self._require_available()
        self._require_local_store(binding.store)
        self._ensure_attested()
        return self._get(binding, expected)

    def delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._require_available()
        self._require_local_store(binding.store)
        self._ensure_attested()
        self._delete(binding, expected)

    # ------------------------------------------------------------------
    # Internal (ungated) operations
    # ------------------------------------------------------------------
    def _probe_store(self) -> VaultStore:
        return VaultStore(
            custody=Custody.DAEMON_LOCAL,
            store_id=self._store_id,
            daemon_id=self._daemon_id,
        )

    def _read_sidecar(self, ref: str) -> dict[str, Any] | None:
        path = self._blob_path(ref)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from exc

    def _write_sidecar(self, ref: str, record: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self._dir, 0o700)
        path = self._blob_path(ref)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        _chmod_best_effort(tmp, 0o600)
        os.replace(tmp, path)  # atomic same-directory replace
        _chmod_best_effort(path, 0o600)

    def _seal_record(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        ref: str,
        version: int,
        value: bytes,
        created_at: float,
        updated_at: float,
        expires_at: float | None,
    ) -> dict[str, Any]:
        entropy = canonical_aad(scope, ref, kind.value, version)
        payload = frame_payload(scope, ref, kind.value, version, value)
        blob = dpapi_protect(payload, entropy)
        return {
            "protection": _PROTECTION,
            "blob_version": 1,
            "descriptor": {
                "ref": ref,
                "store_id": store.store_id,
                "custody": store.custody.value,
                "daemon_id": store.daemon_id,
                "kind": kind.value,
                "scope": scope.as_dict(),
                "version": version,
                "state": DescriptorState.ACTIVE.value,
                "created_at": created_at,
                "updated_at": updated_at,
                "expires_at": expires_at,
            },
            "dpapi_blob_b64": base64.b64encode(blob).decode("ascii"),
        }

    def _put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        replace: str | None,
        expected_version: int | None,
        expires_at: float | None,
    ) -> SecretDescriptor:
        now = time.time()
        if replace is None:
            ref = new_secret_ref()
            version = 1
            created = now
        else:
            ref = replace
            existing = self._read_sidecar(ref)
            if existing is None:
                raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
            desc = existing["descriptor"]
            if desc["scope"] != scope.as_dict():
                raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, ref)
            if desc["kind"] != kind.value:
                raise CredentialUnavailable(VaultErrorCode.KIND_MISMATCH, ref)
            if desc["store_id"] != store.store_id or desc.get("daemon_id") != store.daemon_id:
                raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN, ref)
            if expected_version is not None and int(desc["version"]) != expected_version:
                raise CredentialUnavailable(VaultErrorCode.VERSION_CONFLICT, ref)
            version = int(desc["version"]) + 1
            created = float(desc["created_at"])

        record = self._seal_record(
            store, scope, kind, ref, version, value.reveal(), created, now, expires_at
        )
        self._write_sidecar(ref, record)

        binding = SecretBinding(ref=ref, kind=kind, scope=scope, store=store)
        return SecretDescriptor(
            binding=binding,
            version=version,
            created_at=created,
            updated_at=now,
            state=DescriptorState.ACTIVE,
            expires_at=expires_at,
        )

    def _get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        record = self._read_sidecar(binding.ref)
        if record is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        desc = record["descriptor"]
        if desc["kind"] != binding.kind.value:
            raise CredentialUnavailable(VaultErrorCode.KIND_MISMATCH, binding.ref)
        if (
            desc["store_id"] != binding.store.store_id
            or desc.get("daemon_id") != binding.store.daemon_id
        ):
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN, binding.ref)
        self._check_state(desc, binding.ref)

        version = int(desc["version"])
        entropy = canonical_aad(expected, binding.ref, binding.kind.value, version)
        blob = base64.b64decode(record["dpapi_blob_b64"])
        payload = dpapi_unprotect(blob, entropy)
        header, secret_value = unframe_payload(payload)
        if header != entropy:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, binding.ref)
        return SecretLease(
            SecretBytes(secret_value),
            ref=binding.ref,
            kind=binding.kind.value,
            scope=expected,
            version=version,
        )

    @staticmethod
    def _check_state(desc: dict[str, Any], ref: str) -> None:
        state = desc.get("state")
        if state == DescriptorState.DISABLED.value:
            raise CredentialUnavailable(VaultErrorCode.DISABLED, ref)
        if state == DescriptorState.REVOCATION_PENDING.value:
            raise CredentialUnavailable(VaultErrorCode.REVOKED, ref)
        expires_at = desc.get("expires_at")
        if expires_at is not None and float(expires_at) <= time.time():
            raise CredentialUnavailable(VaultErrorCode.EXPIRED, ref)

    def _delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        record = self._read_sidecar(binding.ref)
        if record is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        if record["descriptor"]["scope"] != expected.as_dict():
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        path = self._blob_path(binding.ref)
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)

    # ------------------------------------------------------------------
    # Exclusive per-ref refresh lease (file O_EXCL lock)
    # ------------------------------------------------------------------
    @contextlib.contextmanager
    def refresh_lease(
        self,
        ref: str,
        holder: str,
        *,
        ttl: float = 30.0,
        wait: float = 30.0,
        poll: float = 0.02,
    ) -> Iterator[None]:
        self._dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._dir / (_ref_filename(ref) + ".lock")
        deadline = time.monotonic() + wait
        fd = None
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, holder.encode("utf-8"))
                break
            except FileExistsError:
                # Steal a stale lock past its ttl.
                with contextlib.suppress(OSError):
                    if time.time() - os.path.getmtime(lock_path) > ttl:
                        os.remove(lock_path)
                        continue
                if time.monotonic() >= deadline:
                    raise CredentialUnavailable(VaultErrorCode.LEASE_TIMEOUT, ref) from None
                time.sleep(poll)
        try:
            yield
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                os.remove(lock_path)

    # ------------------------------------------------------------------
    # Attestation-support hooks
    # ------------------------------------------------------------------
    def _probe_put(self, scope: SecretScope, value: bytes) -> SecretDescriptor:
        return self._put(
            self._probe_store(), scope, SecretKind.API_KEY, SecretBytes(value),
            None, None, None,
        )

    def _probe_get(self, binding: SecretBinding, expected: SecretScope) -> bytes:
        with self._get(binding, expected) as lease:
            return lease.reveal()

    def _probe_delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._delete(binding, expected)

    def inspect_persisted(self, ref: str, probe_value: bytes) -> dict[str, object]:
        record = self._read_sidecar(ref)
        if record is None:
            return {"present": False}
        raw_file = self._blob_path(ref).read_bytes()
        desc = record["descriptor"]
        # Attempt a real current-user unprotect to prove custody binding.
        current_user_bound = False
        try:
            entropy = canonical_aad(
                SecretScope(**desc["scope"]), ref, desc["kind"], int(desc["version"])
            )
            blob = base64.b64decode(record["dpapi_blob_b64"])
            payload = dpapi_unprotect(blob, entropy)
            _header, value = unframe_payload(payload)
            current_user_bound = value == probe_value
        except Exception:  # noqa: BLE001
            current_user_bound = False
        return {
            "present": True,
            "has_blob": len(record.get("dpapi_blob_b64", "")) > 0,
            "protection_current_user": record.get("protection") == _PROTECTION,
            "current_user_bound": current_user_bound,
            "plaintext_absent": probe_value not in raw_file,
        }

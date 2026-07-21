"""Local custody backend: Windows current-user DPAPI.

For users who run a daemon. One immutable per-ref blob under
``%LOCALAPPDATA%\\TinyAssets\\credential-store\\v1``, outside any repository or
universe directory. Protection is ALWAYS current-user DPAPI with
``CRYPTPROTECT_UI_FORBIDDEN`` — NEVER ``CRYPTPROTECT_LOCAL_MACHINE``.

Trust model mirrors the platform backend: the plaintext sidecar ``hint`` block is
non-authoritative. The authoritative record lives INSIDE the DPAPI blob, and the
canonical immutable identity (scope/ref/kind/version + store identity) is passed
as DPAPI *entropy* (the AAD-equivalent, since DPAPI has no AAD). On read the
entropy is rebuilt from the caller's binding, so a forged/cross-store/wrong-kind
binding produces the wrong entropy and the unprotect fails closed; the decrypted
record is then verified field-by-field.

Concurrency: an exclusive control-DB mutation lock makes the file-backed CAS
atomic, and a fenced refresh lease (shared with the platform backend) gives
exactly-one-winner refresh semantics.

Scope: this is the LIBRARY custody layer. Threat boundary = DPAPI current-user +
the LOCALAPPDATA per-user ACL protecting OFFLINE copies and other Windows users;
it does NOT isolate from code already running as the daemon principal. A narrowed
DACL (daemon SID + SYSTEM), a dedicated least-privilege service account, and the
design's separate-broker-process boundary are PRODUCTION DEPLOYMENT integration,
named follow-ups — not claimed by this library.

The module imports cross-platform; instantiating/using it off Windows raises
``CredentialUnavailable(BACKEND_UNAVAILABLE)``. DPAPI tests skip on non-Windows.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import json
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import crypto, leases, record
from .crypto import identity_aad
from .errors import CredentialUnavailable, VaultErrorCode
from .leases import RefreshLease, RefreshLeaseManager, RefreshTicket
from .paths import local_store_dir
from .rollback import (
    EpochGuard,
    GuardMismatch,
    GuardUnavailable,
    require_current,
    store_guard_identity,
)
from .secret_bytes import SecretBytes, SecretLease, require_nonempty_bounded
from .types import (
    ROTATING_TOKEN_KINDS,
    Custody,
    DescriptorState,
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
    is_secret_ref,
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


_SYSTEM_SID_STR = "S-1-5-18"


def _current_user_sid() -> Any:
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    return win32security.GetTokenInformation(token, win32security.TokenUser)[0]


def set_restrictive_dacl(path: Path) -> None:
    """Set the file's DACL to current-user + SYSTEM ONLY, inheritance disabled.

    FAILS HARD: raises ``CredentialUnavailable`` if the restrictive DACL cannot be
    applied AND verified — a credential blob must never be left world-readable on
    a reported-success write. No-op off Windows (the backend is Windows-gated).
    """
    if not IS_WINDOWS:
        return
    try:
        import ntsecuritycon
        import win32security

        user_sid = _current_user_sid()
        system_sid = win32security.ConvertStringSidToSid(_SYSTEM_SID_STR)
        dacl = win32security.ACL()
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, user_sid
        )
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, system_sid
        )
        # PROTECTED_DACL removes inherited ACEs so ONLY these two remain.
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
    except Exception:  # noqa: BLE001
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    # Verify the DACL actually took — never trust the set call alone.
    if not dacl_is_current_user_and_system_only(path):
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)


def _fsync_dir(directory: Path) -> None:
    """fsync a directory so a rename is durable (POSIX)."""
    dfd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _durable_replace(tmp: Path, path: Path) -> None:
    """Atomic, disk-flushed replace of ``path`` by ``tmp``.

    Windows: ``MoveFileExW`` with ``MOVEFILE_WRITE_THROUGH`` (documented
    disk-flushed move). POSIX: ``os.replace`` + ``fsync`` of the directory. Either
    way a reported-success deposit is durable across power loss.
    """
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        move_file_replace_existing = 0x1
        move_file_write_through = 0x8
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.MoveFileExW.restype = wintypes.BOOL
        k32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        if not k32.MoveFileExW(
            str(tmp), str(path), move_file_replace_existing | move_file_write_through
        ):
            raise OSError(ctypes.get_last_error(), "MoveFileEx WRITE_THROUGH failed")
    else:
        os.replace(tmp, path)
        _fsync_dir(path.parent)


def dacl_is_current_user_and_system_only(path: Path) -> bool:
    """True iff the file's DACL grants ONLY the current user + SYSTEM (Windows).

    This is the HONEST local-custody isolation proof — DPAPI proves current-user
    encryption, this proves the file is not readable by Everyone/Users/Admins.
    Returns False off Windows or on any inspection failure (fail closed).
    """
    if not IS_WINDOWS:
        return False
    try:
        import win32security

        sd = win32security.GetFileSecurity(
            str(path), win32security.DACL_SECURITY_INFORMATION
        )
        dacl = sd.GetSecurityDescriptorDacl()
        if dacl is None:  # a NULL DACL grants everyone — never acceptable
            return False
        allowed = {
            win32security.ConvertSidToStringSid(_current_user_sid()),
            _SYSTEM_SID_STR,
        }
        count = dacl.GetAceCount()
        if count == 0:
            return False
        for i in range(count):
            ace = dacl.GetAce(i)
            sid = ace[-1]
            if win32security.ConvertSidToStringSid(sid) not in allowed:
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


def _ref_tail(ref: str) -> str:
    if not is_secret_ref(ref):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
    # ref = "secret:v1:<64 hex>"; the hex tail is filename-safe + unique (256-bit).
    return ref.rsplit(":", 1)[-1]


def _ref_filename(ref: str, version: int) -> str:
    # Per-version sidecar: which version is LIVE is decided by the control-DB
    # pointer, not the filesystem — a versioned file is inert until committed.
    return f"{_ref_tail(ref)}.v{int(version)}.json"


def _chmod_best_effort(path: Path, mode: int) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


def _entropy(
    scope: SecretScope, ref: str, kind: SecretKind, version: int, store: VaultStore
) -> bytes:
    return identity_aad(
        scope, ref, kind.value, version, store.store_id, store.custody.value, store.daemon_id
    )


class DpapiVaultBackend:
    """Windows current-user DPAPI store behind the :class:`VaultBroker` seam."""

    def __init__(
        self,
        *,
        daemon_id: str,
        store_id: str = "daemon:default",
        base: str | Path | None = None,
        guard_dir: str | Path | None = None,
    ) -> None:
        self._daemon_id = daemon_id
        self._store_id = store_id
        self._dir = local_store_dir(base)
        self._attested: bool | None = None
        self._control_db = self._dir / "_control.db"
        self._leases = RefreshLeaseManager(self._control_connect)
        # Anti-rollback epoch guard in an INDEPENDENT recovery domain OUTSIDE the
        # store directory (so a full-directory restore does not carry it).
        self._epoch = EpochGuard(
            store_guard_identity(
                custody=Custody.DAEMON_LOCAL.value,
                store_id=store_id,
                daemon_id=daemon_id,
                recovery_domain=self._control_db,
            ),
            guard_dir=guard_dir,
        )

    def _all_version_paths(self, ref: str) -> list[Path]:
        """Every on-disk versioned sidecar for a ref (for durable GC)."""
        try:
            return sorted(self._dir.glob(f"{_ref_tail(ref)}.v*.json"))
        except OSError:
            return []

    def _versions_on_disk(self, ref: str) -> list[int]:
        tail = _ref_tail(ref)
        versions: list[int] = []
        for path in self._all_version_paths(ref):
            try:
                versions.append(int(path.name[len(tail) + 2 : -5]))  # <tail>.v<N>.json
            except ValueError:
                continue
        return versions

    def _sweep_pending_gc(self) -> None:
        """Retry durable pending GC: remove any recorded leftover version file and
        clear its row. Called on every operation so a locked file left by a prior
        delete is eventually removed (the read path DOES invoke GC now)."""
        self._leases.ensure_schema()
        conn = self._control_connect()
        try:
            pending = leases.list_pending_gc(conn)
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            return
        for ref, version in pending:
            removed = False
            try:
                os.remove(self._blob_path(ref, version))
                removed = True
            except FileNotFoundError:
                removed = True  # already gone
            except OSError:
                removed = False  # still locked — leave the row for the next sweep
            if removed:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("BEGIN IMMEDIATE")
                    leases.clear_pending_gc(conn, ref, version)
                    conn.execute("COMMIT")
        with contextlib.suppress(sqlite3.Error):
            conn.close()

    def _record_pending_gc(self, ref: str, versions: list[int]) -> None:
        """Durably record leftover version files as pending GC (fail-closed).

        Recording is durable BEFORE the file removal is attempted, so a crash or
        lock between recording and removal still leaves a row the next sweep acts
        on — no encrypted blob can silently survive a delete/rotation.
        """
        if not versions:
            return
        self._leases.ensure_schema()
        conn = self._control_connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for version in versions:
                leases.add_pending_gc(conn, ref, version)
            conn.execute("COMMIT")
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref) from None
        finally:
            with contextlib.suppress(sqlite3.Error):
                conn.close()

    def _require_no_rollback(self, conn: sqlite3.Connection | None = None) -> None:
        if conn is not None:
            self._check_no_rollback_locked(conn)
            return
        self._leases.ensure_schema()
        c = self._control_connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            self._check_no_rollback_locked(c)
            c.execute("COMMIT")
        except CredentialUnavailable:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        finally:
            with contextlib.suppress(sqlite3.Error):
                c.close()

    def _check_no_rollback_locked(self, conn: sqlite3.Connection) -> None:
        try:
            require_current(self._epoch, lambda: leases.read_epoch(conn))
        except GuardMismatch:
            raise CredentialUnavailable(VaultErrorCode.REAUTHORIZATION_REQUIRED) from None
        except GuardUnavailable:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None

    def _reserve_epoch(self, conn: sqlite3.Connection) -> int:
        try:
            db_epoch = require_current(self._epoch, lambda: leases.read_epoch(conn))
            reserved = self._epoch.reserve(db_epoch)
        except GuardMismatch:
            raise CredentialUnavailable(VaultErrorCode.REAUTHORIZATION_REQUIRED) from None
        except GuardUnavailable:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        leases.set_epoch(conn, reserved)
        return reserved

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def custody(self) -> Custody:
        return Custody.DAEMON_LOCAL

    # ------------------------------------------------------------------
    # control DB (mutation lock + fenced leases)
    # ------------------------------------------------------------------
    def _control_connect(self) -> sqlite3.Connection:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._control_db), timeout=30.0, isolation_level=None)
        except (OSError, sqlite3.Error):
            # sqlite3.connect() raises sqlite3.OperationalError, not OSError.
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        try:
            conn.row_factory = sqlite3.Row
            # DELETE rollback-journal + EXTRA — same version-independent
            # power-loss durability rationale as the platform backend (EXTRA's
            # extra fsync is a DELETE-mode guarantee; TRUNCATE is not durable).
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA synchronous = EXTRA")
        except sqlite3.DatabaseError:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
        return conn

    def _require_available(self) -> None:
        if not IS_WINDOWS:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    def _require_local_store(self, store: VaultStore) -> None:
        if store.custody != Custody.DAEMON_LOCAL:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)
        if store.store_id != self._store_id or store.daemon_id != self._daemon_id:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)

    def _blob_path(self, ref: str, version: int) -> Path:
        return self._dir / _ref_filename(ref, version)

    def _live_and_deleted(self, ref: str) -> tuple[int | None, bool]:
        """Read the AUTHORITATIVE live version + deletion tombstone (control DB)."""
        self._leases.ensure_schema()
        conn = self._control_connect()
        try:
            return leases.get_live_version(conn, ref), leases.is_deleted(conn, ref)
        except sqlite3.Error:
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None
        finally:
            with contextlib.suppress(sqlite3.Error):
                conn.close()

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
        fence: RefreshLease | None = None,
    ) -> SecretDescriptor:
        self._require_available()
        self._require_local_store(store)
        require_nonempty_bounded(value)  # reject empty/oversized before any write
        leases.require_cas_pairing(replace, expected_version)
        self._ensure_attested()
        self._require_no_rollback()  # EVERY mutation checks rollback FIRST
        self._sweep_pending_gc()  # retry any pending durable GC before mutating
        return self._put(store, scope, kind, value, replace, expected_version, expires_at, fence)

    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        self._require_available()
        self._require_local_store(binding.store)
        self._ensure_attested()
        self._require_no_rollback()  # restored (rolled-back) store → forced reauth
        self._sweep_pending_gc()  # read path retries any pending durable GC
        return self._get(binding, expected)

    def delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._require_available()
        self._require_local_store(binding.store)
        self._ensure_attested()
        self._require_no_rollback()  # EVERY mutation checks rollback FIRST
        self._sweep_pending_gc()  # retry any pending durable GC before mutating
        self._delete(binding, expected)

    # ------------------------------------------------------------------
    # Internal (ungated) operations
    # ------------------------------------------------------------------
    def _probe_store(self) -> VaultStore:
        return VaultStore(
            custody=Custody.DAEMON_LOCAL, store_id=self._store_id, daemon_id=self._daemon_id
        )

    def _read_sidecar(self, ref: str, version: int) -> dict[str, Any] | None:
        path = self._blob_path(ref, version)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None
        except OSError:
            # I/O fault — never leak the backend path via a chained cause.
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref) from None
        # Schema-validate BEFORE any use: a valid-JSON non-object (e.g. `[]`) must
        # not leak a raw AttributeError downstream.
        if not isinstance(raw, dict) or not isinstance(raw.get("hint"), dict):
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
        if not isinstance(raw.get("dpapi_blob_b64"), str):
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref)
        return raw

    def _write_sidecar(self, ref: str, version: int, record_dict: dict[str, Any]) -> None:
        """Durably write the per-version sidecar. It is INERT until the control-DB
        live-version pointer commits to it, so this write is never "live" on its
        own — a subsequent commit failure just leaves an orphaned versioned file.

        write temp -> fsync -> verify size -> apply+VERIFY the DACL on the temp ->
        durable disk-flushed replace into the versioned name.
        """
        path = self._blob_path(ref, version)
        tmp = path.with_name(path.name + ".tmp")
        data = json.dumps(record_dict, sort_keys=True).encode("utf-8")
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            _chmod_best_effort(self._dir, 0o700)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                # os.write() may write FEWER bytes than requested — loop until all
                # are written, or a truncated temp would replace the file.
                view = memoryview(data)
                written = 0
                while written < len(data):
                    n = os.write(fd, view[written:])
                    if n <= 0:
                        raise OSError("short write: os.write made no progress")
                    written += n
                os.fsync(fd)
            finally:
                os.close(fd)
            if os.path.getsize(tmp) != len(data):
                raise OSError("temp file size mismatch after write")
            _chmod_best_effort(tmp, 0o600)
            set_restrictive_dacl(tmp)  # apply + verify BEFORE replace; raises on fail
            _durable_replace(tmp, path)  # disk-flushed atomic replace
        except (OSError, CredentialUnavailable):
            with contextlib.suppress(OSError):
                os.remove(tmp)
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref) from None

    def _seal_sidecar(
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
        entropy = _entropy(scope, ref, kind, version, store)
        rec = record.build_record(
            ref=ref, kind=kind, scope=scope, store=store, version=version,
            state=DescriptorState.ACTIVE, created_at=created_at, updated_at=updated_at,
            expires_at=expires_at,
        )
        payload = crypto.frame_record(crypto.encode_record(rec), value)
        blob = dpapi_protect(payload, entropy)
        return {
            "protection": _PROTECTION,
            "blob_version": 1,
            # Non-authoritative index hints (authoritative copy is inside the blob).
            "hint": {
                "ref": ref, "store_id": store.store_id, "custody": store.custody.value,
                "daemon_id": store.daemon_id, "kind": kind.value,
                "scope": scope.as_dict(), "version": version,
            },
            "dpapi_blob_b64": base64.b64encode(blob).decode("ascii"),
        }

    def _decrypt_sidecar(
        self,
        sidecar: dict[str, Any],
        *,
        ref: str,
        kind: SecretKind,
        scope: SecretScope,
        store: VaultStore,
    ) -> tuple[dict[str, Any], bytes]:
        """Unprotect + authenticate. Returns (authoritative_record, value)."""
        hint = sidecar.get("hint") or {}
        try:
            version = int(hint["version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from exc
        entropy = _entropy(scope, ref, kind, version, store)
        try:
            blob = base64.b64decode(sidecar["dpapi_blob_b64"])
        except Exception as exc:  # noqa: BLE001
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from exc
        payload = dpapi_unprotect(blob, entropy)
        record_json, secret_value = crypto.unframe_record(payload)
        rec = crypto.decode_record(record_json)
        record.verify_record_identity(
            rec, ref=ref, kind=kind, scope=scope, store=store, version=version
        )
        return rec, secret_value

    def _put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        replace: str | None,
        expected_version: int | None,
        expires_at: float | None,
        fence: RefreshLease | None = None,
        ticket: RefreshTicket | None = None,
        bump: bool = True,
    ) -> SecretDescriptor:
        try:
            # Whole mutation under an exclusive control-DB lock. The versioned
            # sidecar write is SUBORDINATE; the control-DB commit (which advances
            # the live-version pointer) is the single atomic commit point. A
            # commit failure leaves the OLD version live.
            with self._leases.mutation_lock() as conn:
                now = time.time()
                if replace is None:
                    ref = new_secret_ref()
                    version = 1
                    created = now
                else:
                    ref = replace
                    if not is_secret_ref(ref):
                        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
                    if leases.is_deleted(conn, ref):
                        raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
                    live = leases.get_live_version(conn, ref)
                    if live is None:
                        raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
                    existing_sidecar = self._read_sidecar(ref, live)
                    if existing_sidecar is None:
                        raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
                    existing, _val = self._decrypt_sidecar(
                        existing_sidecar, ref=ref, kind=kind, scope=scope, store=store
                    )
                    if (
                        expected_version is not None
                        and int(existing["version"]) != expected_version
                    ):
                        raise CredentialUnavailable(VaultErrorCode.VERSION_CONFLICT, ref)
                    if fence is not None:
                        self._require_fence(conn, ref, fence, now)
                    if kind in ROTATING_TOKEN_KINDS and ticket is None:
                        raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)
                    if ticket is not None and not (
                        ticket.ref == ref
                        and ticket.version == int(existing["version"])
                        and leases.capability_valid(
                            conn, ref, ticket.version, ticket.holder,
                            ticket._reveal_capability(),
                        )
                    ):
                        raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)
                    version = int(existing["version"]) + 1
                    created = float(existing["created_at"])

                sidecar = self._seal_sidecar(
                    store, scope, kind, ref, version, value.reveal(), created, now, expires_at
                )
                self._write_sidecar(ref, version, sidecar)  # inert until commit
                leases.set_live_version(conn, ref, version)  # atomic commit point
                if bump:
                    self._reserve_epoch(conn)  # reserve externally before control-DB commit
        except CredentialUnavailable:
            raise
        except sqlite3.Error:
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None

        # Commit succeeded — the new version is authoritative.
        # Durable GC: record EVERY non-live versioned sidecar as pending FIRST
        # (durable), then sweep. A locked/leftover old blob is retried on a later
        # op's sweep instead of silently surviving the rotation.
        stale = [v for v in self._versions_on_disk(ref) if v != version]
        self._record_pending_gc(ref, stale)
        self._sweep_pending_gc()

        binding = SecretBinding(ref=ref, kind=kind, scope=scope, store=store)
        return SecretDescriptor(
            binding=binding, version=version, created_at=created, updated_at=now,
            state=DescriptorState.ACTIVE, expires_at=expires_at,
        )

    @staticmethod
    def _require_fence(
        conn: sqlite3.Connection, ref: str, fence: RefreshLease, now: float
    ) -> None:
        if fence.ref != ref or not leases.verify_fence(
            conn, ref, fence.holder, fence.fence, now
        ):
            raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)

    def _require_record_dacl(self, ref: str, version: int) -> None:
        """Verify THIS record's live sidecar DACL at access time (not a cached probe).

        A DACL broadened after the boot probe must fail the access closed — never
        return the secret from a world-readable blob.
        """
        if not dacl_is_current_user_and_system_only(self._blob_path(ref, version)):
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref)

    def _get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        if not is_secret_ref(binding.ref):
            # Validate before use; never echo a malformed ref (injection defense).
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        # The AUTHORITATIVE live version comes from the control DB, NOT the
        # filesystem — a restored/orphaned sidecar is never live.
        live, deleted = self._live_and_deleted(binding.ref)
        if deleted or live is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        sidecar = self._read_sidecar(binding.ref, live)
        if sidecar is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        self._require_record_dacl(binding.ref, live)  # per-record ACL isolation now
        rec, secret_value = self._decrypt_sidecar(
            sidecar, ref=binding.ref, kind=binding.kind, scope=expected, store=binding.store
        )
        record.check_lifecycle(rec, binding.ref)
        return SecretLease(
            SecretBytes(secret_value), ref=binding.ref, kind=binding.kind.value,
            scope=expected, version=int(rec["version"]),
        )

    def _delete(
        self, binding: SecretBinding, expected: SecretScope, *, tombstone: bool = True
    ) -> None:
        if not is_secret_ref(binding.ref):
            # Validate before use; never echo a malformed ref (injection defense).
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        # Order matters: commit the DURABLE control-DB state (clear the live
        # pointer + optional tombstone) FIRST, then remove the sidecar files. A
        # crash between leaves the ref not-live (control DB authoritative) and,
        # with the tombstone, never re-claimable.
        did_delete = False
        try:
            with self._leases.mutation_lock() as conn:
                live = leases.get_live_version(conn, binding.ref)
                if live is None or leases.is_deleted(conn, binding.ref):
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
                sidecar = self._read_sidecar(binding.ref, live)
                if sidecar is None:
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
                # Authenticate the COMPLETE record before removing — a forged/
                # mismatched binding produces wrong entropy and fails here.
                rec, _v = self._decrypt_sidecar(
                    sidecar, ref=binding.ref, kind=binding.kind, scope=expected,
                    store=binding.store,
                )
                if tombstone:
                    leases.tombstone_ref(conn, binding.ref, int(rec["version"]), time.time())
                    self._reserve_epoch(conn)
                leases.clear_live_version(conn, binding.ref)
                # Record EVERY on-disk version as DURABLE pending GC in the SAME
                # committed transaction as the tombstone — so a crash/lock after
                # commit cannot leave an untracked encrypted blob on disk.
                for version in self._versions_on_disk(binding.ref):
                    leases.add_pending_gc(conn, binding.ref, version)
                did_delete = True
        except CredentialUnavailable:
            raise
        except sqlite3.Error:
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        # control-DB state committed durably — now GC EVERY versioned sidecar for
        # the ref (durable, not just the live one), so no old encrypted blob stays.
        if did_delete:
            self._sweep_pending_gc()  # remove the just-recorded pending blobs
            if self._versions_on_disk(binding.ref):
                # The credential is already UNREADABLE (tombstone committed), but a
                # locked sidecar could not be removed. Never claim a full delete
                # while bytes remain — surface a typed pending failure; the durable
                # pending rows guarantee removal on a later op's sweep.
                raise CredentialUnavailable(VaultErrorCode.DELETE_PENDING, binding.ref)

    # ------------------------------------------------------------------
    # Fenced exclusive per-ref refresh lease
    # ------------------------------------------------------------------
    def refresh_lease(
        self,
        ref: str,
        holder: str,
        *,
        ttl: float = 30.0,
        wait: float = 30.0,
        poll: float = 0.02,
    ) -> Iterator[RefreshLease]:
        return self._leases.acquire(ref, holder, ttl=ttl, wait=wait, poll=poll)

    def begin_refresh(
        self,
        binding: SecretBinding,
        expected: SecretScope,
        holder: str,
        at_version: int,
        *,
        wedge_timeout: float = leases.REFRESH_WEDGE_TIMEOUT,
    ) -> RefreshTicket | None:
        """Atomic consume-before-mint gate for a local refresh (see platform docs).

        Under the exclusive mutation lock: authenticate the current record,
        enforce active/unexpired, confirm the version equals ``at_version``, then
        claim its redemption right. Winner gets a :class:`RefreshTicket`; ``None``
        otherwise. A non-existent version claims nothing (no permanent block); a
        wedged (crashed-mid-refresh) version past ``wedge_timeout`` raises
        ``REAUTHORIZATION_REQUIRED``.
        """
        self._require_available()
        self._require_local_store(binding.store)
        self._ensure_attested()
        self._sweep_pending_gc()  # retry any pending durable GC before mutating
        if not is_secret_ref(binding.ref):
            # Validate before use; never echo a malformed ref (injection defense).
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        try:
            at_version = int(at_version)
        except (TypeError, ValueError):
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, binding.ref) from None
        try:
            with self._leases.mutation_lock() as conn:
                self._require_no_rollback(conn)  # restored store → forced reauth
                if leases.is_deleted(conn, binding.ref):
                    # deleted ref — a restored sidecar cannot be refreshed
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
                live = leases.get_live_version(conn, binding.ref)
                if live is None:
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
                sidecar = self._read_sidecar(binding.ref, live)
                if sidecar is None:
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
                self._require_record_dacl(binding.ref, live)  # ACL isolation at access
                rec, _v = self._decrypt_sidecar(
                    sidecar, ref=binding.ref, kind=binding.kind, scope=expected,
                    store=binding.store,
                )
                record.check_lifecycle(rec, binding.ref)
                version = int(rec["version"])
                if version != at_version:
                    return None
                # A refresh already claimed at the CURRENT version but not yet
                # completed (crashed/in-flight past the timeout) is UNKNOWN — the
                # provider may have rotated the token. Surface reauthorization
                # rather than a silent-None wedge or an unsafe retry.
                leases.reauth_if_wedged(
                    conn, binding.ref, version, time.time(), wedge_timeout
                )
                secret = leases.mint_capability()
                won = leases.claim_refresh(
                    conn, binding.ref, version, holder, time.time(),
                    leases.capability_hash(secret),
                )
                if won:
                    self._reserve_epoch(conn)
        except CredentialUnavailable:
            raise
        except sqlite3.Error:
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        if not won:
            return None
        return RefreshTicket(
            ref=binding.ref, version=version, holder=holder, secret=secret
        )

    def complete_refresh(
        self,
        binding: SecretBinding,
        expected: SecretScope,
        ticket: RefreshTicket,
        value: SecretBytes,
        *,
        expires_at: float | None = None,
    ) -> SecretDescriptor:
        """Store the refreshed secret, bound to the ticket's durable claim."""
        self._require_available()
        self._require_local_store(binding.store)
        require_nonempty_bounded(value)  # reject empty/oversized before any write
        self._ensure_attested()
        self._require_no_rollback()  # EVERY mutation checks rollback FIRST
        self._sweep_pending_gc()  # retry any pending durable GC before mutating
        if not is_secret_ref(binding.ref):
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        if not isinstance(ticket, RefreshTicket):
            raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT, binding.ref)
        if ticket.ref != binding.ref:
            raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, binding.ref)
        return self._put(
            binding.store, expected, binding.kind, value,
            binding.ref, ticket.version, expires_at, None, ticket,
        )

    # ------------------------------------------------------------------
    # Attestation-support hooks
    # ------------------------------------------------------------------
    def _probe_put(self, scope: SecretScope, value: bytes) -> SecretDescriptor:
        return self._put(
            self._probe_store(), scope, SecretKind.API_KEY, SecretBytes(value),
            None, None, None, bump=False,  # ephemeral probe must not advance the epoch
        )

    def _probe_get(self, binding: SecretBinding, expected: SecretScope) -> bytes:
        with self._get(binding, expected) as lease:
            return lease.reveal()

    def _probe_delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._delete(binding, expected, tombstone=False)  # no permanent tombstone

    def inspect_persisted(self, ref: str, probe_value: bytes) -> dict[str, object]:
        """Evidence for attestation.

        Proves BOTH (a) current-user DPAPI encryption + integrity (the blob
        unprotects under the current user, carries the probe value, no plaintext
        on disk) AND (b) the file DACL is narrowed to current-user + SYSTEM only
        (verified via the Windows security API, not an icacls heuristic). Both are
        required for a passing local attestation.
        """
        live, _deleted = self._live_and_deleted(ref)
        if live is None:
            return {"present": False}
        sidecar = self._read_sidecar(ref, live)
        if sidecar is None:
            return {"present": False}
        blob_path = self._blob_path(ref, live)
        try:
            raw_file = blob_path.read_bytes()
        except OSError:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref) from None
        hint = sidecar.get("hint") or {}
        current_user_bound = False
        try:
            store = VaultStore(
                custody=Custody(hint["custody"]), store_id=hint["store_id"],
                daemon_id=hint.get("daemon_id"),
            )
            entropy = _entropy(
                SecretScope(**hint["scope"]), ref, SecretKind(hint["kind"]),
                int(hint["version"]), store,
            )
            blob = base64.b64decode(sidecar["dpapi_blob_b64"])
            payload = dpapi_unprotect(blob, entropy)
            _rec_json, value = crypto.unframe_record(payload)
            current_user_bound = value == probe_value
        except Exception:  # noqa: BLE001
            current_user_bound = False
        return {
            "present": True,
            "has_blob": len(sidecar.get("dpapi_blob_b64", "")) > 0,
            "protection_current_user": sidecar.get("protection") == _PROTECTION,
            "current_user_bound": current_user_bound,
            "dacl_current_user_only": dacl_is_current_user_and_system_only(blob_path),
            "plaintext_absent": probe_value not in raw_file,
        }

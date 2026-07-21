"""Owner- and job-bound content-addressed blob storage.

The filesystem is an internal single-writer implementation detail.  Callers
receive only opaque upload IDs and ``blob:sha256:...`` references, never paths.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import threading
import uuid
from collections.abc import Iterator
<<<<<<< HEAD
from dataclasses import dataclass, field
=======
from dataclasses import dataclass
>>>>>>> feat/lease-store-append-only
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, TypedDict, cast

from tinyassets.runtime.execution_capsule import (
    CapsulePolicyError,
    CapsuleSchemaError,
    reject_host_path_material,
)

DEFAULT_MAX_BLOB_BYTES = 25 * 1024 * 1024
DEFAULT_OWNER_BLOB_QUOTA_BYTES = 512 * 1024 * 1024
DEFAULT_DAEMON_BLOB_QUOTA_BYTES = 256 * 1024 * 1024
DEFAULT_UNREFERENCED_TTL_SECONDS = 24 * 60 * 60
_JSON_SAFE_INTEGER_MAX = 2**53 - 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOB_REF_RE = re.compile(r"^blob:sha256:(?P<sha256>[0-9a-f]{64})$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)
<<<<<<< HEAD
PhysicalRootIdentity = tuple[str, int, int | bytes]
_ROOT_COORDINATORS_GUARD = threading.Lock()
_ROOT_COORDINATORS: dict[PhysicalRootIdentity, BlobRootCoordinator] = {}
=======
_ROOT_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[str, threading.RLock] = {}


def _canonical_root_identity(root: Path) -> str:
    """Return one lock key for ordinary and extended Windows path aliases."""
    resolved = str(root.resolve())
    folded = resolved.casefold()
    if folded.startswith("\\\\?\\unc\\"):
        resolved = "\\\\" + resolved[8:]
    elif folded.startswith("\\\\?\\"):
        resolved = resolved[4:]
    return os.path.normcase(os.path.normpath(resolved))


def _shared_root_lock(root: Path) -> threading.RLock:
    key = _canonical_root_identity(root)
    with _ROOT_LOCKS_GUARD:
        lock = _ROOT_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _ROOT_LOCKS[key] = lock
        return lock
>>>>>>> feat/lease-store-append-only


class BlobDeclarationV1(TypedDict):
    sha256: str
    size_bytes: int
    media_type: str
    confidentiality: Literal["public", "owner_private", "host_visible_private"]
    job_id: str
    lease_id: str
    fence: int


@dataclass(frozen=True)
class BlobUpload:
    upload_id: str
    blob_ref: str


@dataclass(frozen=True)
class BlobReference:
    ref: str
    sha256: str
    size_bytes: int
    media_type: str
    confidentiality: str
    owner_controlled: bool


class BlobError(ValueError):
    """Base class for explicit blob protocol rejection."""


class BlobSchemaError(BlobError):
    """Raised when blob declaration or reference syntax is malformed."""


class BlobPolicyError(BlobError):
    """Raised for forbidden path material or confidentiality misuse."""


class BlobQuotaError(BlobError):
    """Raised before storage when a blob, owner, or daemon quota is exceeded."""


class BlobSizeMismatchError(BlobError):
    """Raised when uploaded bytes do not equal the committed declaration size."""


class BlobHashMismatchError(BlobError):
    """Raised when uploaded bytes do not equal the committed content digest."""


class BlobBindingError(BlobError):
    """Raised when a blob ref crosses owner, job, lease, or fence boundaries."""


class BlobStateError(BlobError):
    """Raised when durable blob state is missing, corrupt, or contradictory."""


class BlobProofError(BlobError):
    """Raised when owner-controlled storage possession cannot be verified."""


PossessionVerifier = Callable[[BlobDeclarationV1, str, bytes], bool]


<<<<<<< HEAD
@dataclass
class BlobRootCoordinator:
    """One in-process serialization authority for a physical blob directory."""

    identity: PhysicalRootIdentity
    root: Path
    lock: Any = field(default_factory=threading.RLock, repr=False)
    _thread_state: threading.local = field(
        default_factory=threading.local,
        init=False,
        repr=False,
    )

    @contextlib.contextmanager
    def serialized(self) -> Iterator[None]:
        with self.lock:
            depth = getattr(self._thread_state, "depth", 0)
            self._thread_state.depth = depth + 1
            try:
                yield
            finally:
                self._thread_state.depth = depth

    def assert_held(self) -> None:
        if getattr(self._thread_state, "depth", 0) <= 0:
            raise AssertionError("blob root coordinator lock is not held")


def _windows_root_identity(root: Path) -> PhysicalRootIdentity:
    import ctypes
    from ctypes import wintypes

    class FileId128(ctypes.Structure):
        _fields_ = [("identifier", ctypes.c_ubyte * 16)]

    class FileIdInfo(ctypes.Structure):
        _fields_ = [
            ("volume_serial_number", ctypes.c_ulonglong),
            ("file_id", FileId128),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(root),
        0,
        0x1 | 0x2 | 0x4,
        None,
        3,
        0x02000000,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        information = FileIdInfo()
        if not get_information(
            handle,
            18,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return (
            "windows",
            int(information.volume_serial_number),
            bytes(information.file_id.identifier),
        )
    finally:
        close_handle(handle)


def _physical_root_identity(root: Path) -> PhysicalRootIdentity:
    """Identify a directory by its filesystem object, never its path spelling."""
    if os.name == "nt":
        return _windows_root_identity(root)
    stat = root.stat()
    return ("posix", stat.st_dev, stat.st_ino)


def _shared_root_coordinator(root: Path) -> BlobRootCoordinator:
    root.mkdir(parents=True, exist_ok=True)
    try:
        identity = _physical_root_identity(root)
    except OSError as exc:
        raise BlobStateError("blob root physical identity is unavailable") from exc
    operational_root = root.resolve(strict=True)
    with _ROOT_COORDINATORS_GUARD:
        coordinator = _ROOT_COORDINATORS.get(identity)
        if coordinator is None:
            coordinator = BlobRootCoordinator(identity, operational_root)
            _ROOT_COORDINATORS[identity] = coordinator
        return coordinator


=======
>>>>>>> feat/lease-store-append-only
def _utc_text(value: datetime | None = None) -> str:
    stamp = datetime.now(UTC) if value is None else value
    if stamp.tzinfo is None:
        raise BlobSchemaError("timestamp must be timezone-aware")
    return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, path: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise BlobStateError(f"{path} must be an RFC 3339 UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BlobStateError(f"{path} is not a real timestamp") from exc


def _opaque_id(value: Any, path: str) -> str:
    if type(value) is not str or not _OPAQUE_ID_RE.fullmatch(value):
        raise BlobSchemaError(f"{path} must be an ASCII opaque identifier")
    return value


def _canonical_uuid(value: Any, path: str) -> str:
    if type(value) is not str:
        raise BlobSchemaError(f"{path} must be a canonical RFC 4122 UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise BlobSchemaError(f"{path} must be a canonical RFC 4122 UUID") from exc
    if str(parsed) != value or parsed.variant != uuid.RFC_4122:
        raise BlobSchemaError(f"{path} must be a canonical RFC 4122 UUID")
    return value


def _nonnegative_integer(value: Any, path: str) -> int:
    if type(value) is not int or not 0 <= value <= _JSON_SAFE_INTEGER_MAX:
        raise BlobSchemaError(f"{path} must be a non-negative safe integer")
    return value


def _parse_declaration(value: BlobDeclarationV1 | Mapping[str, Any]) -> BlobDeclarationV1:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise BlobSchemaError("blob declaration must be a JSON object")
    declaration = dict(value)
    try:
        reject_host_path_material(declaration, "blob_declaration")
    except CapsulePolicyError as exc:
        raise BlobPolicyError(str(exc)) from exc
    except CapsuleSchemaError as exc:
        raise BlobSchemaError(str(exc)) from exc
    expected = frozenset(BlobDeclarationV1.__required_keys__)
    actual = frozenset(declaration)
    if expected - actual:
        raise BlobSchemaError(f"blob declaration missing fields {sorted(expected - actual)}")
    if actual - expected:
        raise BlobSchemaError(f"blob declaration has unknown fields {sorted(actual - expected)}")
    digest = declaration["sha256"]
    if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
        raise BlobSchemaError("blob declaration sha256 must be lowercase hex")
    _nonnegative_integer(declaration["size_bytes"], "blob_declaration.size_bytes")
    media_type = declaration["media_type"]
    if type(media_type) is not str or not media_type.strip():
        raise BlobSchemaError("blob_declaration.media_type must be non-empty")
    if declaration["confidentiality"] not in {
        "public",
        "owner_private",
        "host_visible_private",
    }:
        raise BlobSchemaError("blob_declaration.confidentiality is unsupported")
    _canonical_uuid(declaration["job_id"], "blob_declaration.job_id")
    _canonical_uuid(declaration["lease_id"], "blob_declaration.lease_id")
    _nonnegative_integer(declaration["fence"], "blob_declaration.fence")
    return cast(BlobDeclarationV1, declaration)


def _binding_key(*, owner_user_id: str, job_id: str, lease_id: str, fence: int, sha256: str) -> str:
    return json.dumps([owner_user_id, job_id, lease_id, fence, sha256], separators=(",", ":"))


class BlobStore:
    """Durable single-writer CAS with logical owner/device quota reservations."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES,
        owner_quota_bytes: int = DEFAULT_OWNER_BLOB_QUOTA_BYTES,
        daemon_quota_bytes: int = DEFAULT_DAEMON_BLOB_QUOTA_BYTES,
        unreferenced_ttl_seconds: int = DEFAULT_UNREFERENCED_TTL_SECONDS,
    ) -> None:
<<<<<<< HEAD
        self._coordinator = _shared_root_coordinator(Path(root))
        self._root = self._coordinator.root
        self._objects = self._root / "objects"
        self._uploads = self._root / "uploads"
        self._index_path = self._root / "index.json"
=======
        self._root = Path(root).resolve()
        self._objects = self._root / "objects"
        self._uploads = self._root / "uploads"
        self._index_path = self._root / "index.json"
        self._lock = _shared_root_lock(self._root)
>>>>>>> feat/lease-store-append-only
        for value, name in (
            (max_blob_bytes, "max_blob_bytes"),
            (owner_quota_bytes, "owner_quota_bytes"),
            (daemon_quota_bytes, "daemon_quota_bytes"),
            (unreferenced_ttl_seconds, "unreferenced_ttl_seconds"),
        ):
            if type(value) is not int or value <= 0:
                raise BlobSchemaError(f"{name} must be a positive integer")
        self._max_blob_bytes = max_blob_bytes
        self._owner_quota_bytes = owner_quota_bytes
        self._daemon_quota_bytes = daemon_quota_bytes
        self._ttl = timedelta(seconds=unreferenced_ttl_seconds)
<<<<<<< HEAD
        with self.serialization_guard():
            self._objects.mkdir(parents=True, exist_ok=True)
            self._uploads.mkdir(parents=True, exist_ok=True)
            self._load_index()

    @contextlib.contextmanager
    def serialization_guard(self) -> Iterator[None]:
        """Serialize work against every alias of this physical blob root."""
        with self._coordinator.serialized():
            yield

    @contextlib.contextmanager
    def _locked_index(self) -> Iterator[dict[str, Any]]:
        """Yield an operation-local index under physical-root serialization."""
        with self.serialization_guard():
            yield self._load_index()

    @contextlib.contextmanager
    def completion_validation_guard(self) -> Iterator[None]:
        """Hold blob bindings stable through a caller's terminal commit."""
        with self.serialization_guard():
=======
        with self._lock:
            self._objects.mkdir(parents=True, exist_ok=True)
            self._uploads.mkdir(parents=True, exist_ok=True)
            self._index = self._load_index()

    @contextlib.contextmanager
    def _locked_index(self) -> Iterator[None]:
        """Reload the shared index before reading or mutating it."""
        with self._lock:
            self._index = self._load_index()
            yield

    @contextlib.contextmanager
    def completion_validation_guard(self) -> Iterator[None]:
        """Hold blob bindings stable through a caller's terminal commit."""
        with self._locked_index():
>>>>>>> feat/lease-store-append-only
            yield

    def _load_index(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {"version": 1, "blobs": {}, "bindings": {}, "uploads": {}}
        try:
            value = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise BlobStateError("blob index is unreadable or invalid") from exc
        if type(value) is not dict or value.get("version") != 1:
            raise BlobStateError("blob index version is unsupported")
        for key in ("blobs", "bindings", "uploads"):
            if type(value.get(key)) is not dict:
                raise BlobStateError(f"blob index {key} must be an object")
        return value

<<<<<<< HEAD
    def _persist(self, index: dict[str, Any]) -> None:
        self._coordinator.assert_held()
        encoded = json.dumps(
            index, sort_keys=True, separators=(",", ":"), ensure_ascii=False
=======
    def _persist(self) -> None:
        encoded = json.dumps(
            self._index, sort_keys=True, separators=(",", ":"), ensure_ascii=False
>>>>>>> feat/lease-store-append-only
        ).encode("utf-8")
        temporary = self._root / f".index-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._index_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _object_path(self, sha256: str) -> Path:
        if not _SHA256_RE.fullmatch(sha256):
            raise BlobStateError("blob index contains an invalid content hash")
        return self._objects / sha256[:2] / sha256

    def _verify_platform_object(self, sha256: str, size_bytes: int) -> None:
        object_path = self._object_path(sha256)
        if not object_path.is_file() or object_path.stat().st_size != size_bytes:
            raise BlobSizeMismatchError("committed CAS object size does not match metadata")
        digest = hashlib.sha256()
        with object_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), sha256):
            raise BlobHashMismatchError("committed CAS object hash does not match metadata")

    def _reference_from_binding(self, binding: dict[str, Any]) -> BlobReference:
        return BlobReference(
            ref=f"blob:sha256:{binding['sha256']}",
            sha256=binding["sha256"],
            size_bytes=binding["size_bytes"],
            media_type=binding["media_type"],
            confidentiality=binding["confidentiality"],
            owner_controlled=bool(binding["owner_controlled"]),
        )

    def _check_quota(
        self,
<<<<<<< HEAD
        index: dict[str, Any],
=======
>>>>>>> feat/lease-store-append-only
        declaration: BlobDeclarationV1,
        *,
        owner_user_id: str,
        daemon_id: str,
        pending: bool,
    ) -> None:
        size = declaration["size_bytes"]
        if size > self._max_blob_bytes:
            raise BlobQuotaError(f"declared blob exceeds per-blob maximum {self._max_blob_bytes}")
        owner_committed: dict[str, int] = {}
        daemon_committed: dict[str, int] = {}
<<<<<<< HEAD
        for binding in index["bindings"].values():
=======
        for binding in self._index["bindings"].values():
>>>>>>> feat/lease-store-append-only
            if binding["owner_user_id"] == owner_user_id:
                owner_committed.setdefault(binding["sha256"], binding["size_bytes"])
            if binding["daemon_id"] == daemon_id:
                daemon_committed.setdefault(binding["sha256"], binding["size_bytes"])
        owner_pending = 0
        daemon_pending = 0
<<<<<<< HEAD
        for upload in index["uploads"].values():
=======
        for upload in self._index["uploads"].values():
>>>>>>> feat/lease-store-append-only
            if upload["status"] != "pending":
                continue
            if upload["owner_user_id"] == owner_user_id:
                owner_pending += upload["size_bytes"]
            if upload["daemon_id"] == daemon_id:
                daemon_pending += upload["size_bytes"]
        if pending:
            owner_pending += size
            daemon_pending += size
        else:
            owner_committed.setdefault(declaration["sha256"], size)
            daemon_committed.setdefault(declaration["sha256"], size)
        if sum(owner_committed.values()) + owner_pending > self._owner_quota_bytes:
            raise BlobQuotaError("per-owner blob quota exceeded")
        if sum(daemon_committed.values()) + daemon_pending > self._daemon_quota_bytes:
            raise BlobQuotaError("per-daemon blob quota exceeded")

    def init_blob(
        self,
        declaration: BlobDeclarationV1 | Mapping[str, Any],
        *,
        owner_user_id: str,
        daemon_id: str,
    ) -> BlobUpload:
        """Reserve quota and return an opaque upload ID for declared content."""
        declared = _parse_declaration(declaration)
        owner = _opaque_id(owner_user_id, "owner_user_id")
        daemon = _opaque_id(daemon_id, "daemon_id")
        if declared["confidentiality"] == "owner_private":
            raise BlobPolicyError("owner_private plaintext must use register_owner_blob")
        key = _binding_key(
            owner_user_id=owner,
            job_id=declared["job_id"],
            lease_id=declared["lease_id"],
            fence=declared["fence"],
            sha256=declared["sha256"],
        )
<<<<<<< HEAD
        with self._locked_index() as index:
            existing = index["bindings"].get(key)
=======
        with self._locked_index():
            existing = self._index["bindings"].get(key)
>>>>>>> feat/lease-store-append-only
            if existing is not None:
                if existing["daemon_id"] != daemon:
                    raise BlobBindingError("blob declaration belongs to another daemon")
                if any(existing[field] != declared[field] for field in declared):
                    raise BlobBindingError("blob binding metadata cannot be changed")
                if existing["owner_controlled"] or existing["upload_id"] is None:
                    raise BlobBindingError("blob binding uses owner-controlled storage")
                return BlobUpload(existing["upload_id"], f"blob:sha256:{declared['sha256']}")
<<<<<<< HEAD
            for upload_id, upload in index["uploads"].items():
=======
            for upload_id, upload in self._index["uploads"].items():
>>>>>>> feat/lease-store-append-only
                same_binding = (
                    upload["owner_user_id"] == owner
                    and upload["daemon_id"] == daemon
                    and upload["job_id"] == declared["job_id"]
                    and upload["lease_id"] == declared["lease_id"]
                    and upload["fence"] == declared["fence"]
                    and upload["sha256"] == declared["sha256"]
                )
                if same_binding:
                    if any(upload[field] != declared[field] for field in declared):
                        raise BlobBindingError("pending blob metadata cannot be changed")
                    return BlobUpload(upload_id, f"blob:sha256:{declared['sha256']}")
                if (
                    upload["sha256"] == declared["sha256"]
                    and upload["size_bytes"] != declared["size_bytes"]
                ):
                    raise BlobStateError("same content hash was declared with another size")
<<<<<<< HEAD
            blob = index["blobs"].get(declared["sha256"])
=======
            blob = self._index["blobs"].get(declared["sha256"])
>>>>>>> feat/lease-store-append-only
            if blob is not None and blob["size_bytes"] != declared["size_bytes"]:
                raise BlobStateError("committed content hash has contradictory size")
            if blob is not None and blob.get("object_present"):
                self._verify_platform_object(declared["sha256"], declared["size_bytes"])
            committed = bool(blob and blob.get("object_present"))
            self._check_quota(
<<<<<<< HEAD
                index,
=======
>>>>>>> feat/lease-store-append-only
                declared,
                owner_user_id=owner,
                daemon_id=daemon,
                pending=not committed,
            )
            upload_id = str(uuid.uuid4())
            record = {
                **declared,
                "owner_user_id": owner,
                "daemon_id": daemon,
                "owner_controlled": False,
                "owner_blob_ref": None,
                "upload_id": upload_id,
                "status": "committed" if committed else "pending",
                "created_at": _utc_text(),
                "committed_at": _utc_text() if committed else None,
                "referenced_at": None,
                "failed_at": None,
            }
<<<<<<< HEAD
            index["uploads"][upload_id] = dict(record)
            if committed:
                index["bindings"][key] = dict(record)
            self._persist(index)
=======
            self._index["uploads"][upload_id] = dict(record)
            if committed:
                self._index["bindings"][key] = dict(record)
            self._persist()
>>>>>>> feat/lease-store-append-only
            return BlobUpload(upload_id, f"blob:sha256:{declared['sha256']}")

    def write_upload(self, upload_id: str, content: bytes) -> None:
        """Append bytes to a pending upload without exposing its staging path."""
        _canonical_uuid(upload_id, "upload_id")
        if type(content) is not bytes:
            raise BlobSchemaError("upload content must be bytes")
<<<<<<< HEAD
        with self._locked_index() as index:
            upload = index["uploads"].get(upload_id)
=======
        with self._locked_index():
            upload = self._index["uploads"].get(upload_id)
>>>>>>> feat/lease-store-append-only
            if upload is None:
                raise BlobStateError("unknown upload")
            if upload["status"] != "pending":
                raise BlobStateError("committed upload cannot accept more bytes")
            staging = self._uploads / f"{upload_id}.part"
            current_size = staging.stat().st_size if staging.exists() else 0
            if current_size + len(content) > upload["size_bytes"]:
                raise BlobSizeMismatchError("upload exceeds declared size")
            with staging.open("ab") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

    def commit_blob(self, upload_id: str, *, owner_user_id: str, daemon_id: str) -> BlobReference:
        """Verify size and hash, then atomically make the content referenceable.

        A corrupt existing CAS object fails closed without deleting the verified
        staging upload, allowing a safe retry after the object is repaired.
        """
        _canonical_uuid(upload_id, "upload_id")
        owner = _opaque_id(owner_user_id, "owner_user_id")
        daemon = _opaque_id(daemon_id, "daemon_id")
<<<<<<< HEAD
        with self._locked_index() as index:
            upload = index["uploads"].get(upload_id)
=======
        with self._locked_index():
            upload = self._index["uploads"].get(upload_id)
>>>>>>> feat/lease-store-append-only
            if upload is None:
                raise BlobStateError("unknown upload")
            if upload["owner_user_id"] != owner or upload["daemon_id"] != daemon:
                raise BlobBindingError("upload belongs to another owner or daemon")
            key = _binding_key(
                owner_user_id=owner,
                job_id=upload["job_id"],
                lease_id=upload["lease_id"],
                fence=upload["fence"],
                sha256=upload["sha256"],
            )
            if upload["status"] == "committed":
<<<<<<< HEAD
                binding = index["bindings"].get(key)
=======
                binding = self._index["bindings"].get(key)
>>>>>>> feat/lease-store-append-only
                if binding is None:
                    raise BlobStateError("committed upload is missing its binding")
                self._verify_platform_object(binding["sha256"], binding["size_bytes"])
                return self._reference_from_binding(binding)

            staging = self._uploads / f"{upload_id}.part"
            actual_size = staging.stat().st_size if staging.exists() else 0
            if actual_size != upload["size_bytes"]:
                raise BlobSizeMismatchError(
                    f"uploaded size {actual_size} does not match {upload['size_bytes']}"
                )
            digest = hashlib.sha256()
            with staging.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if not hmac.compare_digest(digest.hexdigest(), upload["sha256"]):
                raise BlobHashMismatchError("uploaded bytes do not match declared sha256")

            object_path = self._object_path(upload["sha256"])
            object_path.parent.mkdir(parents=True, exist_ok=True)
            if object_path.exists():
                self._verify_platform_object(upload["sha256"], upload["size_bytes"])
                staging.unlink()
            else:
                os.replace(staging, object_path)
            committed_at = _utc_text()
            upload["status"] = "committed"
            upload["committed_at"] = committed_at
<<<<<<< HEAD
            index["bindings"][key] = dict(upload)
            index["blobs"][upload["sha256"]] = {
=======
            self._index["bindings"][key] = dict(upload)
            self._index["blobs"][upload["sha256"]] = {
>>>>>>> feat/lease-store-append-only
                "size_bytes": upload["size_bytes"],
                "object_present": True,
                "created_at": committed_at,
            }
<<<<<<< HEAD
            self._persist(index)
=======
            self._persist()
>>>>>>> feat/lease-store-append-only
            return self._reference_from_binding(upload)

    def register_owner_blob(
        self,
        declaration: BlobDeclarationV1 | Mapping[str, Any],
        *,
        owner_user_id: str,
        daemon_id: str,
        owner_blob_ref: str,
        possession_proof: bytes,
        verify_possession: PossessionVerifier,
    ) -> BlobReference:
        """Register verified owner-CAS content without fetching private plaintext."""
        declared = _parse_declaration(declaration)
        owner = _opaque_id(owner_user_id, "owner_user_id")
        daemon = _opaque_id(daemon_id, "daemon_id")
        if declared["confidentiality"] != "owner_private":
            raise BlobPolicyError("owner-controlled refs require owner_private")
        if type(owner_blob_ref) is not str or not owner_blob_ref or len(owner_blob_ref) > 2048:
            raise BlobSchemaError("owner_blob_ref must be a bounded opaque string")
        try:
            reject_host_path_material(owner_blob_ref, "owner_blob_ref")
        except CapsulePolicyError as exc:
            raise BlobPolicyError(str(exc)) from exc
        if type(possession_proof) is not bytes or not possession_proof:
            raise BlobProofError("proof of possession must be non-empty bytes")
        if not callable(verify_possession):
            raise BlobProofError("a possession verifier is required")
        try:
            proof_valid = verify_possession(declared, owner_blob_ref, possession_proof)
        except Exception as exc:
            raise BlobProofError("proof of possession verification failed") from exc
        if proof_valid is not True:
            raise BlobProofError("proof of possession was rejected")

        key = _binding_key(
            owner_user_id=owner,
            job_id=declared["job_id"],
            lease_id=declared["lease_id"],
            fence=declared["fence"],
            sha256=declared["sha256"],
        )
<<<<<<< HEAD
        with self._locked_index() as index:
            existing = index["bindings"].get(key)
=======
        with self._locked_index():
            existing = self._index["bindings"].get(key)
>>>>>>> feat/lease-store-append-only
            if existing is not None:
                if existing["daemon_id"] != daemon:
                    raise BlobBindingError("owner blob binding belongs to another daemon")
                if any(existing[field] != declared[field] for field in declared):
                    raise BlobBindingError("owner blob binding metadata cannot be changed")
                if existing["owner_blob_ref"] != owner_blob_ref:
                    raise BlobBindingError("owner blob binding is already committed")
                return self._reference_from_binding(existing)
            self._check_quota(
<<<<<<< HEAD
                index,
=======
>>>>>>> feat/lease-store-append-only
                declared,
                owner_user_id=owner,
                daemon_id=daemon,
                pending=False,
            )
            committed_at = _utc_text()
<<<<<<< HEAD
            blob = index["blobs"].get(declared["sha256"])
=======
            blob = self._index["blobs"].get(declared["sha256"])
>>>>>>> feat/lease-store-append-only
            if blob is not None and blob["size_bytes"] != declared["size_bytes"]:
                raise BlobStateError("committed content hash has contradictory size")
            binding = {
                **declared,
                "owner_user_id": owner,
                "daemon_id": daemon,
                "owner_controlled": True,
                "owner_blob_ref": owner_blob_ref,
                "upload_id": None,
                "status": "committed",
                "created_at": committed_at,
                "committed_at": committed_at,
                "referenced_at": None,
                "failed_at": None,
            }
<<<<<<< HEAD
            index["bindings"][key] = binding
            index["blobs"].setdefault(
=======
            self._index["bindings"][key] = binding
            self._index["blobs"].setdefault(
>>>>>>> feat/lease-store-append-only
                declared["sha256"],
                {
                    "size_bytes": declared["size_bytes"],
                    "object_present": False,
                    "created_at": committed_at,
                },
            )
<<<<<<< HEAD
            self._persist(index)
=======
            self._persist()
>>>>>>> feat/lease-store-append-only
            return self._reference_from_binding(binding)

    def validate_reference(
        self,
        blob_ref: str,
        *,
        owner_user_id: str,
        job_id: str,
        lease_id: str,
        fence: int,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> BlobReference:
        """Resolve only an exact committed owner/job/lease/fence content binding."""
        match = _BLOB_REF_RE.fullmatch(blob_ref) if type(blob_ref) is str else None
        if match is None:
            raise BlobSchemaError("blob_ref must be an opaque blob:sha256 reference")
        owner = _opaque_id(owner_user_id, "owner_user_id")
        job = _canonical_uuid(job_id, "job_id")
        lease = _canonical_uuid(lease_id, "lease_id")
        checked_fence = _nonnegative_integer(fence, "fence")
        if type(expected_sha256) is not str or not _SHA256_RE.fullmatch(expected_sha256):
            raise BlobSchemaError("expected_sha256 must be lowercase hex")
        checked_size = _nonnegative_integer(expected_size_bytes, "expected_size_bytes")
        if match.group("sha256") != expected_sha256:
            raise BlobBindingError("blob ref does not match expected content hash")
        key = _binding_key(
            owner_user_id=owner,
            job_id=job,
            lease_id=lease,
            fence=checked_fence,
            sha256=expected_sha256,
        )
<<<<<<< HEAD
        with self._locked_index() as index:
            binding = index["bindings"].get(key)
=======
        with self._locked_index():
            binding = self._index["bindings"].get(key)
>>>>>>> feat/lease-store-append-only
            if binding is None or binding["status"] != "committed":
                raise BlobBindingError(
                    "blob is not committed for this owner, job, lease, and fence"
                )
            if binding["failed_at"] is not None:
                raise BlobBindingError("blob belongs to a failed job")
            if binding["size_bytes"] != checked_size:
                raise BlobBindingError("blob size does not match signed result")
            if not binding["owner_controlled"]:
                self._verify_platform_object(binding["sha256"], binding["size_bytes"])
            return self._reference_from_binding(binding)

    def mark_referenced(
        self,
        blob_ref: str,
        *,
        owner_user_id: str,
        job_id: str,
        lease_id: str,
        fence: int,
    ) -> None:
        """Retain a blob after a verified candidate result references it."""
        match = _BLOB_REF_RE.fullmatch(blob_ref) if type(blob_ref) is str else None
        if match is None:
            raise BlobSchemaError("blob_ref must be an opaque blob:sha256 reference")
        key = _binding_key(
            owner_user_id=_opaque_id(owner_user_id, "owner_user_id"),
            job_id=_canonical_uuid(job_id, "job_id"),
            lease_id=_canonical_uuid(lease_id, "lease_id"),
            fence=_nonnegative_integer(fence, "fence"),
            sha256=match.group("sha256"),
        )
<<<<<<< HEAD
        with self._locked_index() as index:
            binding = index["bindings"].get(key)
            if binding is None or binding["status"] != "committed":
                raise BlobBindingError("cannot retain an uncommitted blob binding")
            binding["referenced_at"] = _utc_text()
            self._persist(index)
=======
        with self._locked_index():
            binding = self._index["bindings"].get(key)
            if binding is None or binding["status"] != "committed":
                raise BlobBindingError("cannot retain an uncommitted blob binding")
            binding["referenced_at"] = _utc_text()
            self._persist()
>>>>>>> feat/lease-store-append-only

    def mark_job_failed(
        self, *, owner_user_id: str, job_id: str, failed_at: datetime | None = None
    ) -> None:
        """Make every binding for a failed job eligible for bounded retention."""
        owner = _opaque_id(owner_user_id, "owner_user_id")
        job = _canonical_uuid(job_id, "job_id")
        stamp = _utc_text(failed_at)
<<<<<<< HEAD
        with self._locked_index() as index:
            for binding in index["bindings"].values():
                if binding["owner_user_id"] == owner and binding["job_id"] == job:
                    binding["failed_at"] = stamp
            self._persist(index)
=======
        with self._locked_index():
            for binding in self._index["bindings"].values():
                if binding["owner_user_id"] == owner and binding["job_id"] == job:
                    binding["failed_at"] = stamp
            self._persist()
>>>>>>> feat/lease-store-append-only

    def collect_garbage(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Delete expired unreferenced or failed-job bindings and orphan objects."""
        checked_at = datetime.now(UTC) if now is None else now
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            raise BlobSchemaError("garbage collection time must be timezone-aware")
        checked_at = checked_at.astimezone(UTC)
<<<<<<< HEAD
        with self._locked_index() as index:
            removed_upload_ids: set[str] = set()
            removed_refs: set[str] = set()
            for upload_id, upload in list(index["uploads"].items()):
=======
        with self._locked_index():
            removed_upload_ids: set[str] = set()
            removed_refs: set[str] = set()
            for upload_id, upload in list(self._index["uploads"].items()):
>>>>>>> feat/lease-store-append-only
                if upload["status"] != "pending":
                    continue
                created_at = _parse_timestamp(upload["created_at"], "upload.created_at")
                if checked_at - created_at < self._ttl:
                    continue
                staging = self._uploads / f"{upload_id}.part"
                if staging.exists():
                    staging.unlink()
<<<<<<< HEAD
                del index["uploads"][upload_id]
                removed_refs.add(f"blob:sha256:{upload['sha256']}")
            for key, binding in list(index["bindings"].items()):
=======
                del self._index["uploads"][upload_id]
                removed_refs.add(f"blob:sha256:{upload['sha256']}")
            for key, binding in list(self._index["bindings"].items()):
>>>>>>> feat/lease-store-append-only
                anchor = binding["failed_at"]
                if anchor is None and binding["referenced_at"] is None:
                    anchor = binding["committed_at"]
                if anchor is None or checked_at - _parse_timestamp(anchor, "retention") < self._ttl:
                    continue
                upload_id = binding.get("upload_id")
                if upload_id is not None:
                    removed_upload_ids.add(upload_id)
<<<<<<< HEAD
                del index["bindings"][key]
            for upload_id in removed_upload_ids:
                index["uploads"].pop(upload_id, None)

            live_hashes = {record["sha256"] for record in index["bindings"].values()}
            for sha256, blob in list(index["blobs"].items()):
=======
                del self._index["bindings"][key]
            for upload_id in removed_upload_ids:
                self._index["uploads"].pop(upload_id, None)

            live_hashes = {record["sha256"] for record in self._index["bindings"].values()}
            for sha256, blob in list(self._index["blobs"].items()):
>>>>>>> feat/lease-store-append-only
                if sha256 in live_hashes:
                    continue
                object_path = self._object_path(sha256)
                if blob["object_present"] and object_path.exists():
                    object_path.unlink()
<<<<<<< HEAD
                del index["blobs"][sha256]
                removed_refs.add(f"blob:sha256:{sha256}")
            if removed_upload_ids or removed_refs:
                self._persist(index)
=======
                del self._index["blobs"][sha256]
                removed_refs.add(f"blob:sha256:{sha256}")
            if removed_upload_ids or removed_refs:
                self._persist()
>>>>>>> feat/lease-store-append-only
            return tuple(sorted(removed_refs))

"""Test-support composition boundary for the dark execution-authority spine.

This module is intentionally outside production composition packages.  The
root cannot be selected through configuration, environment variables, or a
caller-provided string: tests must present the process-local sentinel.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tinyassets.execution_authority.blob_proof import BlobProofStore, BlobRef
from tinyassets.execution_authority.evidence_store import (
    ExecutionEvidenceStore,
    LeaseAllocation,
    TerminalReceipt,
    VerifiedTerminalView,
)
from tinyassets.execution_authority.records import (
    CANDIDATE_DOMAIN,
    CAPSULE_DOMAIN,
    GRANT_DOMAIN,
    TERMINAL_DOMAIN,
    BlobReferenceV1,
    ExecutionCandidateV1,
    ExecutionCapsuleV1,
    ExecutionGrantV1,
    ExecutionRecord,
    ExecutionTerminalV1,
    RecordSigner,
    RecordVerifier,
    SignedExecutionRecord,
    _create_record_signer,
    _create_record_verifier,
)
from tinyassets.execution_authority.verified import Verified


class D0ConfigurationError(RuntimeError):
    """The dark authority root was requested outside its test boundary."""


class D0AuthorityError(RuntimeError):
    """Verified D0 facts did not agree at an authority decision sink."""


_D0_TEST_SENTINEL = object()
_CAPSULE_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
_GRANT_SEED = bytes.fromhex("101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f")
_CANDIDATE_SEED = bytes.fromhex("202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f")
_TERMINAL_SEED = bytes.fromhex("303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f")
_KEY_IDS = MappingProxyType(
    {
        ExecutionCapsuleV1: "d0-test-capsule-key-v1",
        ExecutionGrantV1: "d0-test-grant-key-v1",
        ExecutionCandidateV1: "d0-test-device-key-v1",
        ExecutionTerminalV1: "d0-test-terminal-key-v1",
    }
)
_DOMAIN_BY_RECORD_TYPE = MappingProxyType(
    {
        ExecutionCapsuleV1: CAPSULE_DOMAIN,
        ExecutionGrantV1: GRANT_DOMAIN,
        ExecutionCandidateV1: CANDIDATE_DOMAIN,
        ExecutionTerminalV1: TERMINAL_DOMAIN,
    }
)
_STATE_MARKER = b"d0-authority-state/v1\n"


def test_authority_sentinel() -> object:
    """Return the process-local sentinel used only by focused test harnesses."""

    return _D0_TEST_SENTINEL


def _temporary_state_path(state_dir: Path) -> Path:
    candidate = state_dir.absolute()
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)

    def require_under_temporary_root(path: Path) -> None:
        try:
            inside_temporary_root = os.path.commonpath((str(path), str(temporary_root))) == str(
                temporary_root
            )
        except ValueError:
            inside_temporary_root = False
        if not inside_temporary_root:
            raise D0ConfigurationError(
                "D0 authority state must remain under the physical temporary root"
            )

    require_under_temporary_root(candidate.resolve(strict=False))
    candidate.mkdir(parents=True, exist_ok=True)
    candidate_stat = candidate.lstat()
    if _is_reparse_point(candidate_stat) or not stat.S_ISDIR(candidate_stat.st_mode):
        raise D0ConfigurationError("D0 authority state must be a plain temporary directory")
    resolved = candidate.resolve(strict=True)
    require_under_temporary_root(resolved)
    return resolved


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _entry_stat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise D0ConfigurationError(
            f"D0 authority cannot inspect state entry {path.name!r}"
        ) from exc


def _entry_identity(file_stat: os.stat_result) -> tuple[int, int]:
    device = getattr(file_stat, "st_dev", None)
    inode = getattr(file_stat, "st_ino", None)
    if type(device) is not int or type(inode) is not int or inode == 0:
        raise D0ConfigurationError("D0 authority state identity is unavailable")
    return device, inode


def _require_plain_entry(
    path: Path,
    *,
    directory: bool,
) -> os.stat_result:
    file_stat = _entry_stat(path)
    if file_stat is None:
        raise D0ConfigurationError(f"D0 authority state entry {path.name!r} disappeared")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if _is_reparse_point(file_stat) or not expected_type(file_stat.st_mode):
        kind = "directory" if directory else "file"
        raise D0ConfigurationError(f"D0 authority state entry {path.name!r} must be a plain {kind}")
    if not directory and getattr(file_stat, "st_nlink", 1) != 1:
        raise D0ConfigurationError(f"D0 authority state entry {path.name!r} cannot be hard-linked")
    return file_stat


def _prepare_plain_directory(path: Path) -> tuple[int, int]:
    try:
        path.mkdir()
    except FileExistsError:
        pass
    except OSError as exc:
        raise D0ConfigurationError(
            f"D0 authority cannot create state directory {path.name!r}"
        ) from exc
    return _entry_identity(_require_plain_entry(path, directory=True))


def _open_plain_file(
    path: Path,
    *,
    create: bool,
    writable: bool = False,
) -> int:
    flags = os.O_RDWR if writable else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise D0ConfigurationError(
            f"D0 authority cannot securely open state entry {path.name!r}"
        ) from exc
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = _require_plain_entry(path, directory=False)
        if _entry_identity(descriptor_stat) != _entry_identity(path_stat):
            raise D0ConfigurationError(
                f"D0 authority state entry {path.name!r} changed while opening"
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _require_open_file_unchanged(path: Path, descriptor: int) -> None:
    path_stat = _require_plain_entry(path, directory=False)
    if _entry_identity(os.fstat(descriptor)) != _entry_identity(path_stat):
        raise D0ConfigurationError(f"D0 authority state entry {path.name!r} changed during use")


def _read_open_file(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 4096):
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True, slots=True)
class TestAuthorityRoot:
    """Production-denied composition of genuine mechanisms with test-owned facts."""

    state_dir: Path
    _signer: RecordSigner = field(repr=False, compare=False)
    _verifier: RecordVerifier = field(repr=False, compare=False)
    _evidence: ExecutionEvidenceStore = field(repr=False, compare=False)
    _blobs: BlobProofStore = field(repr=False, compare=False)

    @classmethod
    def create(
        cls,
        *,
        sentinel: object,
        mode: str,
        state_dir: str | Path,
        route_registration: object | None = None,
        issuer: object | None = None,
        key_material: object | None = None,
        verifier: object | None = None,
        adapters: Mapping[str, object] | None = None,
    ) -> TestAuthorityRoot:
        if sentinel is not _D0_TEST_SENTINEL:
            raise D0ConfigurationError("D0 authority requires the test sentinel")
        if mode != "test":
            raise D0ConfigurationError("D0 authority is available only in test mode")
        if route_registration is not None:
            raise D0ConfigurationError("D0 authority cannot register a route or app")
        if issuer is not None:
            raise D0ConfigurationError("D0 authority rejects caller issuer selection")
        if key_material is not None:
            raise D0ConfigurationError("D0 authority rejects caller key material")
        if verifier is not None:
            raise D0ConfigurationError("D0 authority rejects caller verifier selection")
        if adapters:
            raise D0ConfigurationError("D0 authority rejects every external adapter")

        resolved = _temporary_state_path(Path(state_dir))
        blob_root = resolved / "blobs"
        blob_identity = _prepare_plain_directory(blob_root)
        keys = {
            CAPSULE_DOMAIN: Ed25519PrivateKey.from_private_bytes(_CAPSULE_SEED),
            GRANT_DOMAIN: Ed25519PrivateKey.from_private_bytes(_GRANT_SEED),
            CANDIDATE_DOMAIN: Ed25519PrivateKey.from_private_bytes(_CANDIDATE_SEED),
            TERMINAL_DOMAIN: Ed25519PrivateKey.from_private_bytes(_TERMINAL_SEED),
        }
        signing_keys = {
            domain: (_KEY_IDS[record_type], keys[domain])
            for record_type, domain in _DOMAIN_BY_RECORD_TYPE.items()
        }
        verification_keys = {
            domain: (_KEY_IDS[record_type], keys[domain].public_key())
            for record_type, domain in _DOMAIN_BY_RECORD_TYPE.items()
        }
        database_path = resolved / "execution-authority.sqlite3"
        marker_path = resolved / ".d0-authority-initialized"
        database_exists = _entry_stat(database_path) is not None
        marker_exists = _entry_stat(marker_path) is not None
        if database_exists != marker_exists:
            raise D0ConfigurationError("D0 authority database and external marker disagree")
        initialize = not database_exists
        if marker_exists:
            marker_descriptor = _open_plain_file(marker_path, create=False)
            try:
                if _read_open_file(marker_descriptor) != _STATE_MARKER:
                    raise D0ConfigurationError("D0 authority external marker is corrupt")
                _require_open_file_unchanged(marker_path, marker_descriptor)
            finally:
                os.close(marker_descriptor)
        database_descriptor = _open_plain_file(
            database_path,
            create=initialize,
            writable=initialize,
        )
        evidence: ExecutionEvidenceStore | None = None
        try:
            evidence = ExecutionEvidenceStore(
                database_path,
                initialize=initialize,
            )
            _require_open_file_unchanged(database_path, database_descriptor)
            if initialize:
                marker_descriptor = _open_plain_file(
                    marker_path,
                    create=True,
                    writable=True,
                )
                try:
                    os.write(marker_descriptor, _STATE_MARKER)
                    os.fsync(marker_descriptor)
                    _require_open_file_unchanged(marker_path, marker_descriptor)
                finally:
                    os.close(marker_descriptor)
            blobs = BlobProofStore(blob_root)
            if (
                blobs.root_identity != blob_identity
                or _entry_identity(_require_plain_entry(blob_root, directory=True)) != blob_identity
            ):
                raise D0ConfigurationError(
                    "D0 authority blob directory changed during construction"
                )
            return cls(
                state_dir=resolved,
                _signer=_create_record_signer(signing_keys),
                _verifier=_create_record_verifier(
                    verification_keys,
                    verifier_id="d0-test-trust-set-v1",
                ),
                _evidence=evidence,
                _blobs=blobs,
            )
        except BaseException:
            if evidence is not None:
                evidence.close()
            raise
        finally:
            os.close(database_descriptor)

    @staticmethod
    def key_id_for(record_type: type[ExecutionRecord]) -> str:
        try:
            return _KEY_IDS[record_type]
        except KeyError as exc:
            raise D0AuthorityError("record type has no D0 key identity") from exc

    @staticmethod
    def blob_set_digest(blob_refs: tuple[BlobReferenceV1, ...]) -> str:
        if type(blob_refs) is not tuple or any(
            type(blob_ref) is not BlobReferenceV1 for blob_ref in blob_refs
        ):
            raise TypeError("blob_refs must be an immutable BlobReferenceV1 tuple")
        canonical = rfc8785.dumps(
            [
                {
                    "media_type": blob_ref.media_type,
                    "ref": blob_ref.ref,
                    "sha256": blob_ref.sha256,
                    "size_bytes": blob_ref.size_bytes,
                }
                for blob_ref in blob_refs
            ]
        )
        return hashlib.sha256(canonical).hexdigest()

    def sign(self, record: ExecutionRecord) -> SignedExecutionRecord:
        """Sign through the same purpose-bound mechanism used by D0 verification."""

        return self._signer.sign(record)

    def verify(
        self,
        signed: SignedExecutionRecord,
        *,
        verified_at: int,
    ) -> Verified[ExecutionRecord]:
        """Re-derive M1/device-signature evidence; never trust a supplied wrapper."""

        return self._verifier.verify(signed, verified_at=verified_at)

    def allocate_lease(self, *, job_id: str, lease_id: str) -> LeaseAllocation:
        intent = rfc8785.dumps(
            {
                "job_id": job_id,
                "lease_id": lease_id,
                "purpose": "d0-test-authority-allocation",
            }
        )
        return self._evidence.allocate_lease(
            job_id=job_id,
            lease_id=lease_id,
            evidence_bytes=intent,
        )

    def put_blob(self, relative_path: str, content: bytes) -> BlobRef:
        return self._blobs.put_blob(relative_path, content)

    def accept_candidate(
        self,
        *,
        capsule: SignedExecutionRecord,
        grant: SignedExecutionRecord,
        candidate: SignedExecutionRecord,
        verified_at: int,
    ) -> Verified[ExecutionCandidateV1]:
        with self._blobs.coordinated_transaction(self._evidence.transaction):
            return self._accept_candidate_locked(
                capsule=capsule,
                grant=grant,
                candidate=candidate,
                verified_at=verified_at,
            )[2]

    def _accept_candidate_locked(
        self,
        *,
        capsule: SignedExecutionRecord,
        grant: SignedExecutionRecord,
        candidate: SignedExecutionRecord,
        verified_at: int,
    ) -> tuple[
        Verified[ExecutionCapsuleV1],
        Verified[ExecutionGrantV1],
        Verified[ExecutionCandidateV1],
    ]:
        verified_capsule = self._verified_type(capsule, ExecutionCapsuleV1, verified_at)
        verified_grant = self._verified_type(grant, ExecutionGrantV1, verified_at)
        verified_candidate = self._verified_type(candidate, ExecutionCandidateV1, verified_at)
        capsule_value = verified_capsule.value
        grant_value = verified_grant.value
        candidate_value = verified_candidate.value

        self._require_live(
            issued_at=capsule_value.issued_at,
            expires_at=capsule_value.expires_at,
            verified_at=verified_at,
            subject="capsule",
        )
        self._require_live(
            issued_at=None,
            expires_at=grant_value.expires_at,
            verified_at=verified_at,
            subject="grant",
        )
        floor = self._evidence.current_floor(grant_value.job_id)
        expected = (
            capsule_value.owner_id,
            capsule_value.audience_daemon_id,
            capsule_value.job_id,
            capsule_value.capsule_id,
            verified_capsule.evidence_digest,
            capsule_value.generation,
        )
        actual_grant = (
            grant_value.owner_id,
            grant_value.daemon_id,
            grant_value.job_id,
            grant_value.capsule_id,
            grant_value.capsule_digest,
            grant_value.generation,
        )
        if actual_grant != expected:
            raise D0AuthorityError("grant does not bind the exact capsule authority")
        actual_candidate = (
            candidate_value.owner_id,
            candidate_value.daemon_id,
            candidate_value.job_id,
            candidate_value.capsule_id,
            candidate_value.capsule_digest,
            candidate_value.generation,
        )
        if actual_candidate != expected:
            raise D0AuthorityError("candidate does not bind the exact capsule authority")
        if (
            candidate_value.lease_id,
            candidate_value.fence,
        ) != (grant_value.lease_id, grant_value.fence):
            raise D0AuthorityError("candidate does not bind the exact grant lease")
        if (floor.generation, floor.fence) != (
            grant_value.generation,
            grant_value.fence,
        ):
            raise D0AuthorityError("grant is below the durable generation/fence floor")
        if "result_upload" not in grant_value.capability_ceiling:
            raise D0AuthorityError("grant does not authorize result upload")

        fresh_refs: list[BlobReferenceV1] = []
        for blob_ref in candidate_value.blob_refs:
            verified_blob = self._blobs.verify_blob(
                BlobRef(
                    relative_path=blob_ref.ref,
                    sha256=blob_ref.sha256,
                    size=blob_ref.size_bytes,
                ),
                verified_at=verified_at,
            )
            fresh_refs.append(
                BlobReferenceV1(
                    ref=verified_blob.value.relative_path,
                    sha256=verified_blob.value.sha256,
                    size_bytes=verified_blob.value.size,
                    media_type=blob_ref.media_type,
                )
            )
        if tuple(fresh_refs) != candidate_value.blob_refs:
            raise D0AuthorityError("candidate blob references lack exact fresh M2 proof")
        if self.blob_set_digest(tuple(fresh_refs)) != candidate_value.blob_set_digest:
            raise D0AuthorityError("candidate blob-set digest is invalid")
        if len(fresh_refs) != 1:
            raise D0AuthorityError("D0 candidate requires exactly one result blob")
        if candidate_value.result_digest != fresh_refs[0].sha256:
            raise D0AuthorityError("candidate result digest does not bind result bytes")
        return verified_capsule, verified_grant, verified_candidate

    def complete(
        self,
        *,
        capsule: SignedExecutionRecord,
        grant: SignedExecutionRecord,
        candidate: SignedExecutionRecord,
        terminal: SignedExecutionRecord,
        verified_at: int,
    ) -> TerminalReceipt:
        # Physical blob-root coordination is deliberately acquired before the
        # evidence store begins any SQLite transaction.
        with self._blobs.coordinated_transaction(self._evidence.transaction):
            (
                verified_capsule,
                verified_grant,
                verified_candidate,
            ) = self._accept_candidate_locked(
                capsule=capsule,
                grant=grant,
                candidate=candidate,
                verified_at=verified_at,
            )
            verified_terminal = self._verified_type(terminal, ExecutionTerminalV1, verified_at)
            candidate_value = verified_candidate.value
            capsule_value = verified_capsule.value
            grant_value = verified_grant.value
            terminal_value = verified_terminal.value
            expected = (
                candidate_value.owner_id,
                candidate_value.daemon_id,
                candidate_value.job_id,
                candidate_value.capsule_id,
                candidate_value.capsule_digest,
                candidate_value.lease_id,
                candidate_value.generation,
                candidate_value.fence,
                verified_candidate.evidence_digest,
                candidate_value.result_digest,
                candidate_value.blob_set_digest,
            )
            actual = (
                terminal_value.owner_id,
                terminal_value.daemon_id,
                terminal_value.job_id,
                terminal_value.capsule_id,
                terminal_value.capsule_digest,
                terminal_value.lease_id,
                terminal_value.generation,
                terminal_value.fence,
                terminal_value.accepted_candidate_digest,
                terminal_value.accepted_result_digest,
                terminal_value.accepted_blob_set_digest,
            )
            if actual != expected:
                raise D0AuthorityError("terminal result does not bind the accepted candidate")
            if (
                terminal_value.generation,
                terminal_value.fence,
            ) != (grant_value.generation, grant_value.fence):
                raise D0AuthorityError("terminal is below the exact grant fence")
            expected_terminal_state = {
                "succeeded": "succeeded",
                "cancelled": "cancelled",
            }.get(candidate_value.status, "failed")
            if terminal_value.terminal_state != expected_terminal_state:
                raise D0AuthorityError("terminal state contradicts candidate status")
            completed_at = self._timestamp_epoch(terminal_value.completed_at)
            if completed_at < self._timestamp_epoch(capsule_value.issued_at):
                raise D0AuthorityError("terminal completion predates capsule issuance")
            if completed_at > verified_at:
                raise D0AuthorityError("terminal completion time is in the future")

            existing = self._evidence.replay_terminal(
                terminal_value.job_id,
                self._terminal_verifier(verified_at),
            )
            if existing is not None:
                if (
                    existing.fact_digest == verified_terminal.evidence_digest
                    and existing.idempotency_key == terminal_value.idempotency_key
                ):
                    return existing
                if existing.idempotency_key == terminal_value.idempotency_key:
                    raise D0AuthorityError(
                        "terminal idempotency key names changed verified content"
                    )

            fact_bytes = self._signed_wire(terminal)
            evidence_id = hashlib.sha256(fact_bytes).hexdigest()
            try:
                self._evidence.append_terminal_evidence(
                    evidence_id=evidence_id,
                    job_id=terminal_value.job_id,
                    fact_bytes=fact_bytes,
                )
            except sqlite3.IntegrityError:
                pass
            receipt = self._evidence.replay_terminal(
                terminal_value.job_id,
                self._terminal_verifier(verified_at),
            )
            if receipt is None:
                raise D0AuthorityError("terminal evidence did not replay")
            return receipt

    def replay_terminal(
        self,
        job_id: str,
        *,
        verified_at: int,
    ) -> TerminalReceipt | None:
        return self._evidence.replay_terminal(
            job_id,
            self._terminal_verifier(verified_at),
        )

    def _terminal_verifier(self, verified_at: int):
        def verify(fact_bytes: bytes) -> VerifiedTerminalView | None:
            try:
                signed = self._decode_signed_wire(fact_bytes)
                verified = self._verified_type(signed, ExecutionTerminalV1, verified_at)
            except (D0AuthorityError, TypeError, ValueError):
                return None
            terminal = verified.value
            return VerifiedTerminalView(
                job_id=terminal.job_id,
                generation=terminal.generation,
                fence=terminal.fence,
                idempotency_key=terminal.idempotency_key,
                fact_digest=verified.evidence_digest,
                terminal_state=terminal.terminal_state,
                result_digest=terminal.accepted_result_digest,
            )

        return verify

    def _verified_type(self, signed, expected_type, verified_at):
        verified = self._verifier.require_authentic(self.verify(signed, verified_at=verified_at))
        if type(verified.value) is not expected_type:
            raise D0AuthorityError(f"expected {expected_type.__name__} authority record")
        return verified

    @staticmethod
    def _require_live(
        *,
        issued_at: str | None,
        expires_at: str,
        verified_at: int,
        subject: str,
    ) -> None:
        if issued_at is not None and verified_at < TestAuthorityRoot._timestamp_epoch(issued_at):
            raise D0AuthorityError(f"{subject} is not yet valid")
        if verified_at >= TestAuthorityRoot._timestamp_epoch(expires_at):
            raise D0AuthorityError(f"{subject} is expired")

    @staticmethod
    def _timestamp_epoch(value: str) -> int:
        try:
            return int(datetime.fromisoformat(value[:-1] + "+00:00").timestamp())
        except (TypeError, ValueError) as exc:
            raise D0AuthorityError("authority timestamp is invalid") from exc

    @staticmethod
    def _signed_wire(signed: SignedExecutionRecord) -> bytes:
        return rfc8785.dumps(
            {
                "canonical_payload_b64": base64.b64encode(signed.canonical_payload).decode("ascii"),
                "domain": signed.domain,
                "signature_b64": signed.signature_b64,
            }
        )

    @staticmethod
    def _decode_signed_wire(fact_bytes: bytes) -> SignedExecutionRecord:
        def reject_duplicates(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate signed-wire field")
                value[key] = item
            return value

        try:
            payload = json.loads(fact_bytes, object_pairs_hook=reject_duplicates)
            if (
                type(payload) is not dict
                or frozenset(payload) != {"canonical_payload_b64", "domain", "signature_b64"}
                or any(type(value) is not str for value in payload.values())
                or rfc8785.dumps(payload) != fact_bytes
            ):
                raise ValueError("terminal wire shape is invalid")
            canonical_payload = base64.b64decode(
                payload["canonical_payload_b64"],
                validate=True,
            )
            return SignedExecutionRecord(
                domain=payload["domain"],
                canonical_payload=canonical_payload,
                signature_b64=payload["signature_b64"],
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            binascii.Error,
            TypeError,
            ValueError,
        ) as exc:
            raise D0AuthorityError("terminal wire is invalid") from exc

    def close(self) -> None:
        self._evidence.close()

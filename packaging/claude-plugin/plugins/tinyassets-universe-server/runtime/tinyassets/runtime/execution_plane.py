"""Composition root for the authenticated distributed-execution authority.

This module deliberately does not decide the production trust-root design
(KMS/HSM custody, rotation, or active-key distribution).  It only resolves the
currently configured Ed25519 seed and wires the existing authority components
to the same key.  Production must configure the key explicitly; ephemeral keys
are available only through the explicit test/development opt-in.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from nacl.bindings import crypto_sign_SEEDBYTES
from nacl.signing import SigningKey

from tinyassets.api.daemon_enrollment import DaemonEnrollmentService
from tinyassets.runtime.blob_refs import BlobStore
from tinyassets.runtime.daemon_auth import b64decode
from tinyassets.runtime.lease_store import (
    CapsuleVerificationKeyRecord,
    LeaseGrantIssuer,
    LeaseStore,
)
from tinyassets.runtime.signed_records import PlatformSigner, RecordVerifier
from tinyassets.storage import data_dir

SIGNING_KEY_ENV = "TINYASSETS_EXECUTION_SIGNING_KEY"
SIGNING_KEY_ID_ENV = "TINYASSETS_EXECUTION_SIGNING_KEY_ID"
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)


class ExecutionPlaneConfigurationError(RuntimeError):
    """Execution authority configuration is missing or invalid."""


@dataclass(frozen=True)
class ExecutionPlane:
    """One fully wired execution authority stack."""

    enrollment_service: DaemonEnrollmentService
    lease_store: LeaseStore
    blob_store: BlobStore
    platform_signer: PlatformSigner
    record_verifier: RecordVerifier
    lease_grant_issuer: LeaseGrantIssuer
    capsule_verification_key: CapsuleVerificationKeyRecord

    @classmethod
    def from_config(
        cls,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        allow_ephemeral_signing_key: bool = False,
    ) -> ExecutionPlane:
        """Build the authority stack from CWD-independent configuration."""
        signing_key = _resolve_signing_key(
            allow_ephemeral=allow_ephemeral_signing_key
        )
        signer = PlatformSigner(signing_key)
        verifier = RecordVerifier(signing_key.verify_key)
        key_id = os.environ.get(SIGNING_KEY_ID_ENV, "").strip() or (
            "platform-execution:"
            + hashlib.sha256(bytes(signing_key.verify_key)).hexdigest()[:16]
        )
        if not _OPAQUE_ID_RE.fullmatch(key_id):
            raise ExecutionPlaneConfigurationError(
                f"{SIGNING_KEY_ID_ENV} must be an ASCII opaque identifier"
            )
        capsule_key = CapsuleVerificationKeyRecord(
            signing_key_id=key_id,
            verify_key=signing_key.verify_key,
            active=True,
        )
        root = data_dir()
        enrollment_service = DaemonEnrollmentService(
            db_path=root / "daemon-auth.sqlite3",
            clock=lambda: clock().timestamp(),
        )
        lease_store = LeaseStore(
            root / "leases.sqlite3",
            clock=clock,
            key_registry=enrollment_service,
            record_verifier=verifier,
        )
        return cls(
            enrollment_service=enrollment_service,
            lease_store=lease_store,
            blob_store=BlobStore(root / "execution-blobs"),
            platform_signer=signer,
            record_verifier=verifier,
            lease_grant_issuer=LeaseGrantIssuer(
                platform_signer=signer,
                capsule_key=capsule_key,
                supported_request_schema_versions={3},
            ),
            capsule_verification_key=capsule_key,
        )


def _resolve_signing_key(*, allow_ephemeral: bool) -> SigningKey:
    encoded = os.environ.get(SIGNING_KEY_ENV, "").strip()
    if not encoded:
        if allow_ephemeral:
            return SigningKey.generate()
        raise ExecutionPlaneConfigurationError(
            f"{SIGNING_KEY_ENV} is required for distributed execution"
        )
    try:
        seed = b64decode(encoded)
        if len(seed) != crypto_sign_SEEDBYTES:
            raise ValueError
        return SigningKey(seed)
    except (TypeError, ValueError) as exc:
        raise ExecutionPlaneConfigurationError(
            f"{SIGNING_KEY_ENV} must be a base64url Ed25519 seed"
        ) from exc


__all__ = [
    "ExecutionPlane",
    "ExecutionPlaneConfigurationError",
    "SIGNING_KEY_ENV",
    "SIGNING_KEY_ID_ENV",
]

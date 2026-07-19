"""Server-side daemon enrollment and proof-of-possession authentication."""

import hashlib
import hmac
import inspect
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from tinyassets.runtime.daemon_auth import (
    MAX_ACCESS_TOKEN_LIFETIME_SECONDS,
    MAX_CLOCK_SKEW_SECONDS,
    AccessToken,
    DevicePublicIdentity,
    SignedRequest,
    action_affecting_headers,
    b64decode,
    canonical_challenge,
    canonical_challenge_creation,
    canonical_enrollment_completion,
    canonical_request,
    request_body_hash,
)
from tinyassets.storage import data_dir

_CHALLENGE_LIFETIME_SECONDS = 60
_ENROLLMENT_LIFETIME_SECONDS = 300
# Enrollment creation is inherently unauthenticated. Its per-key ceilings stop
# single-identity amplification, while global flood protection is a REQUIRED
# S4/infra edge rate-limit (gateway/Cloudflare). A global app-layer cap is
# deliberately not used because an attacker could fill it and lock out every
# legitimate new daemon.
_MAX_PENDING_ENROLLMENTS_PER_IDENTITY = 8
_ENROLLMENT_CREATION_LIMIT_PER_MINUTE = 16
_MAX_OUTSTANDING_CHALLENGES_PER_DAEMON = 16
_CHALLENGE_CREATION_LIMIT_PER_MINUTE = 30
_ENROLLMENT_APPROVAL_ATTEMPT_LIMIT = 5
_OWNER_ATTEMPT_WINDOW_SECONDS = 300
_TOKEN_ISSUANCE_LIMIT_PER_MINUTE = 8
_MAX_OUTSTANDING_ACCESS_TOKENS = 8
_REQUEST_RATE_LIMIT_PER_MINUTE = 120
# Five minutes at 120/min is 600; retain ten percent scheduling headroom.
_MAX_OUTSTANDING_NONCES = 660
_VERIFICATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_VERIFICATION_CODE_LENGTH = 12


class DaemonApiError(Exception):
    """Typed, safe error matching the distributed-execution API contract."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.request_id = request_id or f"req_{uuid.uuid4().hex}"

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "request_id": self.request_id,
                "details": self.details,
            }
        }


@dataclass(frozen=True)
class EnrollmentHandoff:
    enrollment_id: str
    verification_code: str


@dataclass(frozen=True)
class CompletedEnrollment:
    enrollment_id: str
    daemon_id: str
    owner_user_id: str
    key_thumbprint: str
    credential_epoch: int


@dataclass(frozen=True)
class DaemonChallenge:
    daemon_id: str
    challenge: str
    expires_at: float


@dataclass(frozen=True)
class AuthenticatedDaemon:
    daemon_id: str
    owner_user_id: str
    key_thumbprint: str
    credential_epoch: int


class DaemonEnrollmentService:
    """SQLite-backed enrollment, token, replay, and revocation authority."""

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        path = Path(db_path) if db_path is not None else data_dir() / "daemon-auth.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daemon_enrollments (
                    enrollment_id TEXT PRIMARY KEY,
                    verification_code TEXT NOT NULL UNIQUE,
                    installation_id TEXT NOT NULL,
                    installation_nonce_hash BLOB NOT NULL,
                    ed25519_public_key BLOB NOT NULL,
                    x25519_public_key BLOB NOT NULL,
                    key_thumbprint TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'completed')),
                    owner_user_id TEXT,
                    daemon_id TEXT UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_at REAL
                );
                CREATE TABLE IF NOT EXISTS enrolled_daemons (
                    daemon_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    ed25519_public_key BLOB NOT NULL,
                    x25519_public_key BLOB NOT NULL,
                    key_thumbprint TEXT NOT NULL UNIQUE,
                    credential_epoch INTEGER NOT NULL CHECK (credential_epoch >= 1),
                    revoked_at REAL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daemon_challenges (
                    challenge_hash BLOB PRIMARY KEY,
                    daemon_id TEXT NOT NULL REFERENCES enrolled_daemons(daemon_id),
                    expires_at REAL NOT NULL,
                    used_at REAL
                );
                CREATE TABLE IF NOT EXISTS daemon_challenge_creation_nonces (
                    daemon_id TEXT NOT NULL REFERENCES enrolled_daemons(daemon_id),
                    nonce TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL NOT NULL,
                    PRIMARY KEY (daemon_id, nonce)
                );
                CREATE TABLE IF NOT EXISTS daemon_access_tokens (
                    token_hash BLOB PRIMARY KEY,
                    daemon_id TEXT NOT NULL REFERENCES enrolled_daemons(daemon_id),
                    key_thumbprint TEXT NOT NULL,
                    credential_epoch INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    issued_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daemon_request_nonces (
                    daemon_id TEXT NOT NULL REFERENCES enrolled_daemons(daemon_id),
                    nonce TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL NOT NULL,
                    PRIMARY KEY (daemon_id, nonce)
                );
                CREATE INDEX IF NOT EXISTS daemon_nonce_expiry
                    ON daemon_request_nonces(expires_at);
                CREATE INDEX IF NOT EXISTS daemon_enrollment_identity_created
                    ON daemon_enrollments(key_thumbprint, created_at);
                CREATE INDEX IF NOT EXISTS daemon_challenge_capacity
                    ON daemon_challenges(daemon_id, used_at, expires_at);
                CREATE INDEX IF NOT EXISTS daemon_challenge_creation_nonce_expiry
                    ON daemon_challenge_creation_nonces(expires_at);
                CREATE TABLE IF NOT EXISTS daemon_enrollment_owner_attempts (
                    owner_user_id TEXT PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL,
                    window_started_at REAL NOT NULL,
                    locked_until REAL
                );
                """
            )
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(daemon_enrollments)")
            }
            if "expires_at" not in columns:
                self._connection.execute(
                    "ALTER TABLE daemon_enrollments ADD COLUMN expires_at REAL"
                )
            if "failed_attempts" not in columns:
                self._connection.execute(
                    "ALTER TABLE daemon_enrollments "
                    "ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"
                )
            if "locked_at" not in columns:
                self._connection.execute("ALTER TABLE daemon_enrollments ADD COLUMN locked_at REAL")
            self._connection.execute(
                """
                UPDATE daemon_enrollments
                SET expires_at = created_at + ?
                WHERE expires_at IS NULL
                """,
                (_ENROLLMENT_LIFETIME_SECONDS,),
            )
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS enrolled_daemon_key_thumbprint
                ON enrolled_daemons(key_thumbprint)
                """
            )
            nonce_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(daemon_request_nonces)")
            }
            if "used_at" not in nonce_columns:
                self._connection.execute(
                    "ALTER TABLE daemon_request_nonces ADD COLUMN used_at REAL"
                )
                self._connection.execute(
                    "UPDATE daemon_request_nonces SET used_at = expires_at - ?",
                    (MAX_ACCESS_TOKEN_LIFETIME_SECONDS,),
                )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS daemon_token_expiry
                ON daemon_access_tokens(expires_at)
                """
            )

    @contextmanager
    def _immediate_transaction(self):
        """Serialize an auth decision with revocation across SQLite connections."""
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @staticmethod
    def _token_hash(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    @staticmethod
    def _challenge_hash(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    @staticmethod
    def _require_identifier(value: str, name: str) -> str:
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized or len(normalized) > 256:
            raise DaemonApiError(400, "MALFORMED_REQUEST", f"{name} is required")
        return normalized

    def create_enrollment(self, identity: DevicePublicIdentity) -> EnrollmentHandoff:
        if not isinstance(identity, DevicePublicIdentity):
            raise DaemonApiError(400, "MALFORMED_REQUEST", "device identity is required")
        enrollment_id = f"enr_{uuid.uuid4().hex}"
        created_at = self._clock()
        expires_at = created_at + _ENROLLMENT_LIFETIME_SECONDS
        for _ in range(8):
            verification_code = "".join(
                secrets.choice(_VERIFICATION_ALPHABET) for _ in range(_VERIFICATION_CODE_LENGTH)
            )
            try:
                with self._lock, self._immediate_transaction():
                    self._connection.execute(
                        """
                        DELETE FROM daemon_enrollments
                        WHERE status = 'pending' AND expires_at <= ?
                        """,
                        (created_at,),
                    )
                    pending = self._connection.execute(
                        """
                        SELECT COUNT(*) FROM daemon_enrollments
                        WHERE key_thumbprint = ? AND status = 'pending' AND expires_at > ?
                        """,
                        (identity.key_thumbprint, created_at),
                    ).fetchone()[0]
                    if pending >= _MAX_PENDING_ENROLLMENTS_PER_IDENTITY:
                        raise DaemonApiError(
                            429,
                            "DAEMON_ENROLLMENT_CAPACITY",
                            "Device identity has too many pending enrollments",
                            retryable=True,
                        )
                    created_recently = self._connection.execute(
                        """
                        SELECT COUNT(*) FROM daemon_enrollments
                        WHERE key_thumbprint = ? AND created_at > ?
                        """,
                        (identity.key_thumbprint, created_at - 60),
                    ).fetchone()[0]
                    if created_recently >= _ENROLLMENT_CREATION_LIMIT_PER_MINUTE:
                        raise DaemonApiError(
                            429,
                            "DAEMON_ENROLLMENT_RATE_LIMITED",
                            "Device enrollment creation rate exceeded",
                            retryable=True,
                        )
                    self._connection.execute(
                        """
                        INSERT INTO daemon_enrollments (
                            enrollment_id, verification_code, installation_id,
                            installation_nonce_hash, ed25519_public_key,
                            x25519_public_key, key_thumbprint, status, created_at,
                            expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (
                            enrollment_id,
                            verification_code,
                            identity.installation_id,
                            hashlib.sha256(identity.installation_nonce).digest(),
                            identity.ed25519_public_key,
                            identity.x25519_public_key,
                            identity.key_thumbprint,
                            created_at,
                            expires_at,
                        ),
                    )
                return EnrollmentHandoff(enrollment_id, verification_code)
            except sqlite3.IntegrityError:
                continue
        raise DaemonApiError(
            503,
            "CONTROL_PLANE_UNAVAILABLE",
            "Could not allocate a verification code",
            retryable=True,
        )

    def approve_enrollment(self, enrollment_id: str, *, owner_user_id: str) -> None:
        enrollment_id = self._require_identifier(enrollment_id, "enrollment_id")
        owner_user_id = self._require_identifier(owner_user_id, "owner_user_id")
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT status, owner_user_id, expires_at
                FROM daemon_enrollments WHERE enrollment_id = ?
                """,
                (enrollment_id,),
            ).fetchone()
            if row is None:
                raise DaemonApiError(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
            if row["status"] == "pending" and row["expires_at"] <= self._clock():
                self._connection.execute(
                    "DELETE FROM daemon_enrollments WHERE enrollment_id = ?",
                    (enrollment_id,),
                )
                raise DaemonApiError(410, "ENROLLMENT_EXPIRED", "Enrollment has expired")
            if row["status"] == "completed":
                if row["owner_user_id"] == owner_user_id:
                    return
                raise DaemonApiError(409, "ENROLLMENT_ALREADY_BOUND", "Enrollment is already bound")
            if row["owner_user_id"] not in (None, owner_user_id):
                raise DaemonApiError(409, "ENROLLMENT_ALREADY_BOUND", "Enrollment is already bound")
            self._connection.execute(
                """
                UPDATE daemon_enrollments
                SET status = 'approved', owner_user_id = ?
                WHERE enrollment_id = ?
                """,
                (owner_user_id, enrollment_id),
            )

    def _owner_approval_state(self, owner_user_id: str, now: float) -> sqlite3.Row | None:
        row = self._connection.execute(
            """
            SELECT failed_attempts, window_started_at, locked_until
            FROM daemon_enrollment_owner_attempts WHERE owner_user_id = ?
            """,
            (owner_user_id,),
        ).fetchone()
        if row is not None and row["locked_until"] is not None and row["locked_until"] > now:
            raise DaemonApiError(
                429,
                "ENROLLMENT_APPROVAL_LOCKED",
                "Too many enrollment approval attempts",
                retryable=True,
            )
        if row is not None and row["window_started_at"] <= now - _OWNER_ATTEMPT_WINDOW_SECONDS:
            self._connection.execute(
                "DELETE FROM daemon_enrollment_owner_attempts WHERE owner_user_id = ?",
                (owner_user_id,),
            )
            return None
        return row

    def _record_owner_approval_failure(
        self, owner_user_id: str, now: float, state: sqlite3.Row | None
    ) -> bool:
        attempts = 1 if state is None else int(state["failed_attempts"]) + 1
        locked_until = (
            now + _OWNER_ATTEMPT_WINDOW_SECONDS
            if attempts >= _ENROLLMENT_APPROVAL_ATTEMPT_LIMIT
            else None
        )
        self._connection.execute(
            """
            INSERT INTO daemon_enrollment_owner_attempts (
                owner_user_id, failed_attempts, window_started_at, locked_until
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(owner_user_id) DO UPDATE SET
                failed_attempts = excluded.failed_attempts,
                locked_until = excluded.locked_until
            """,
            (owner_user_id, attempts, now, locked_until),
        )
        return locked_until is not None

    def approve_verification_code(
        self,
        enrollment_id: str,
        verification_code: str,
        *,
        owner_user_id: str,
    ) -> None:
        enrollment_id = self._require_identifier(enrollment_id, "enrollment_id")
        owner_user_id = self._require_identifier(owner_user_id, "owner_user_id")
        if not isinstance(verification_code, str):
            raise DaemonApiError(400, "MALFORMED_REQUEST", "verification_code is required")
        normalized_code = verification_code.strip().upper()
        if len(normalized_code) != _VERIFICATION_CODE_LENGTH:
            raise DaemonApiError(400, "MALFORMED_REQUEST", "verification_code is invalid")
        now = self._clock()
        with self._lock, self._immediate_transaction():
            owner_state = self._owner_approval_state(owner_user_id, now)
            row = self._connection.execute(
                """
                SELECT enrollment_id, verification_code, status, owner_user_id,
                       expires_at, failed_attempts, locked_at
                FROM daemon_enrollments WHERE enrollment_id = ?
                """,
                (enrollment_id,),
            ).fetchone()
            if row is None:
                owner_locked = self._record_owner_approval_failure(owner_user_id, now, owner_state)
                self._connection.commit()
                if owner_locked:
                    raise DaemonApiError(
                        429,
                        "ENROLLMENT_APPROVAL_LOCKED",
                        "Too many enrollment approval attempts",
                        retryable=True,
                    )
                raise DaemonApiError(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
            if row["status"] == "pending" and row["expires_at"] <= now:
                self._connection.execute(
                    "DELETE FROM daemon_enrollments WHERE enrollment_id = ?",
                    (enrollment_id,),
                )
                self._connection.commit()
                raise DaemonApiError(410, "ENROLLMENT_EXPIRED", "Enrollment has expired")
            if row["locked_at"] is not None:
                raise DaemonApiError(
                    429,
                    "ENROLLMENT_APPROVAL_LOCKED",
                    "Too many enrollment approval attempts",
                )
            if not hmac.compare_digest(normalized_code, row["verification_code"]):
                attempts = int(row["failed_attempts"]) + 1
                enrollment_locked = attempts >= _ENROLLMENT_APPROVAL_ATTEMPT_LIMIT
                self._connection.execute(
                    """
                    UPDATE daemon_enrollments
                    SET failed_attempts = ?, locked_at = ?
                    WHERE enrollment_id = ?
                    """,
                    (attempts, now if enrollment_locked else None, enrollment_id),
                )
                owner_locked = self._record_owner_approval_failure(owner_user_id, now, owner_state)
                self._connection.commit()
                if enrollment_locked or owner_locked:
                    raise DaemonApiError(
                        429,
                        "ENROLLMENT_APPROVAL_LOCKED",
                        "Too many enrollment approval attempts",
                        retryable=owner_locked,
                    )
                raise DaemonApiError(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
            if row["status"] == "completed":
                if row["owner_user_id"] == owner_user_id:
                    return
                raise DaemonApiError(409, "ENROLLMENT_ALREADY_BOUND", "Enrollment is already bound")
            if row["owner_user_id"] not in (None, owner_user_id):
                raise DaemonApiError(409, "ENROLLMENT_ALREADY_BOUND", "Enrollment is already bound")
            self._connection.execute(
                """
                UPDATE daemon_enrollments
                SET status = 'approved', owner_user_id = ?
                WHERE enrollment_id = ?
                """,
                (owner_user_id, enrollment_id),
            )
            self._connection.execute(
                "DELETE FROM daemon_enrollment_owner_attempts WHERE owner_user_id = ?",
                (owner_user_id,),
            )

    def complete_enrollment(
        self,
        enrollment_id: str,
        *,
        installation_nonce: str,
        signature: str,
    ) -> CompletedEnrollment:
        enrollment_id = self._require_identifier(enrollment_id, "enrollment_id")
        try:
            nonce = b64decode(installation_nonce)
            proof = b64decode(signature)
        except (TypeError, ValueError):
            raise DaemonApiError(401, "INVALID_DEVICE_PROOF", "Device proof is invalid")
        try:
            with self._lock, self._connection:
                row = self._connection.execute(
                    "SELECT * FROM daemon_enrollments WHERE enrollment_id = ?",
                    (enrollment_id,),
                ).fetchone()
                if row is None:
                    raise DaemonApiError(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
                if row["status"] == "pending":
                    raise DaemonApiError(
                        403,
                        "OWNER_APPROVAL_REQUIRED",
                        "The device owner has not approved this enrollment",
                    )
                if not hmac.compare_digest(
                    hashlib.sha256(nonce).digest(), row["installation_nonce_hash"]
                ):
                    raise DaemonApiError(401, "INVALID_DEVICE_PROOF", "Device proof is invalid")
                try:
                    VerifyKey(row["ed25519_public_key"]).verify(
                        canonical_enrollment_completion(enrollment_id, nonce),
                        proof,
                    )
                except (BadSignatureError, ValueError, TypeError):
                    raise DaemonApiError(401, "INVALID_DEVICE_PROOF", "Device proof is invalid")
                if row["status"] == "completed":
                    daemon = self._connection.execute(
                        "SELECT * FROM enrolled_daemons WHERE daemon_id = ?",
                        (row["daemon_id"],),
                    ).fetchone()
                else:
                    daemon_id = f"daemon_{uuid.uuid4().hex}"
                    self._connection.execute(
                        """
                        INSERT INTO enrolled_daemons (
                            daemon_id, owner_user_id, ed25519_public_key,
                            x25519_public_key, key_thumbprint, credential_epoch, created_at
                        ) VALUES (?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            daemon_id,
                            row["owner_user_id"],
                            row["ed25519_public_key"],
                            row["x25519_public_key"],
                            row["key_thumbprint"],
                            self._clock(),
                        ),
                    )
                    self._connection.execute(
                        """
                        UPDATE daemon_enrollments
                        SET status = 'completed', daemon_id = ?
                        WHERE enrollment_id = ?
                        """,
                        (daemon_id, enrollment_id),
                    )
                    daemon = self._connection.execute(
                        "SELECT * FROM enrolled_daemons WHERE daemon_id = ?",
                        (daemon_id,),
                    ).fetchone()
        except sqlite3.IntegrityError as exc:
            if "key_thumbprint" not in str(exc):
                raise
            raise DaemonApiError(
                409,
                "DEVICE_ALREADY_ENROLLED",
                "Device identity is already enrolled",
            ) from exc
        return CompletedEnrollment(
            enrollment_id=enrollment_id,
            daemon_id=daemon["daemon_id"],
            owner_user_id=daemon["owner_user_id"],
            key_thumbprint=daemon["key_thumbprint"],
            credential_epoch=int(daemon["credential_epoch"]),
        )

    def create_challenge(
        self,
        daemon_id: str,
        *,
        timestamp: int,
        nonce: str,
        signature: str,
    ) -> DaemonChallenge:
        daemon_id = self._require_identifier(daemon_id, "daemon_id")
        now = self._clock()
        with self._lock, self._immediate_transaction():
            daemon = self._connection.execute(
                "SELECT ed25519_public_key, revoked_at FROM enrolled_daemons WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()
            if daemon is None:
                raise DaemonApiError(404, "DAEMON_NOT_FOUND", "Daemon not found")
            if daemon["revoked_at"] is not None:
                raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
            if (
                not isinstance(timestamp, int)
                or isinstance(timestamp, bool)
                or abs(now - timestamp) > MAX_CLOCK_SKEW_SECONDS
            ):
                raise DaemonApiError(
                    401, "CLOCK_SKEW", "Challenge request timestamp is outside allowed skew"
                )
            try:
                VerifyKey(daemon["ed25519_public_key"]).verify(
                    canonical_challenge_creation(daemon_id, timestamp, nonce),
                    b64decode(signature),
                )
            except (BadSignatureError, ValueError, TypeError):
                raise DaemonApiError(
                    401,
                    "INVALID_SIGNATURE",
                    "Challenge request signature is invalid",
                )
            self._connection.execute(
                "DELETE FROM daemon_challenge_creation_nonces WHERE expires_at <= ?",
                (now,),
            )
            replayed = self._connection.execute(
                """
                SELECT 1 FROM daemon_challenge_creation_nonces
                WHERE daemon_id = ? AND nonce = ?
                """,
                (daemon_id, nonce),
            ).fetchone()
            if replayed is not None:
                raise DaemonApiError(
                    401,
                    "REPLAY_DETECTED",
                    "Challenge request nonce was already used",
                )
            self._connection.execute(
                "DELETE FROM daemon_challenges WHERE expires_at <= ?",
                (now,),
            )
            outstanding = self._connection.execute(
                """
                SELECT COUNT(*) FROM daemon_challenges
                WHERE daemon_id = ? AND used_at IS NULL AND expires_at > ?
                """,
                (daemon_id, now),
            ).fetchone()[0]
            if outstanding >= _MAX_OUTSTANDING_CHALLENGES_PER_DAEMON:
                raise DaemonApiError(
                    429,
                    "DAEMON_CHALLENGE_CAPACITY",
                    "Daemon has too many outstanding access-token challenges",
                    retryable=True,
                )
            # Challenge expiry is exactly one minute after creation, so active
            # rows (used or unused) are the per-minute creation ledger.
            created_recently = self._connection.execute(
                """
                SELECT COUNT(*) FROM daemon_challenges
                WHERE daemon_id = ? AND expires_at > ?
                """,
                (daemon_id, now),
            ).fetchone()[0]
            if created_recently >= _CHALLENGE_CREATION_LIMIT_PER_MINUTE:
                raise DaemonApiError(
                    429,
                    "DAEMON_CHALLENGE_RATE_LIMITED",
                    "Daemon access-token challenge creation rate exceeded",
                    retryable=True,
                )
            challenge = secrets.token_urlsafe(32)
            expires_at = now + _CHALLENGE_LIFETIME_SECONDS
            self._connection.execute(
                """
                INSERT INTO daemon_challenge_creation_nonces (
                    daemon_id, nonce, expires_at, used_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    daemon_id,
                    nonce,
                    now + MAX_ACCESS_TOKEN_LIFETIME_SECONDS,
                    now,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO daemon_challenges (challenge_hash, daemon_id, expires_at)
                VALUES (?, ?, ?)
                """,
                (self._challenge_hash(challenge), daemon_id, expires_at),
            )
        return DaemonChallenge(daemon_id, challenge, expires_at)

    def issue_access_token(
        self,
        daemon_id: str,
        challenge: str,
        signature: str,
        *,
        lifetime_seconds: int = MAX_ACCESS_TOKEN_LIFETIME_SECONDS,
    ) -> AccessToken:
        daemon_id = self._require_identifier(daemon_id, "daemon_id")
        challenge = self._require_identifier(challenge, "challenge")
        if not isinstance(lifetime_seconds, int) or not (
            1 <= lifetime_seconds <= MAX_ACCESS_TOKEN_LIFETIME_SECONDS
        ):
            raise DaemonApiError(
                422,
                "TOKEN_LIFETIME_INVALID",
                "Access-token lifetime must be between 1 and 300 seconds",
            )
        now = self._clock()
        challenge_hash = self._challenge_hash(challenge)
        with self._lock, self._immediate_transaction():
            challenge_row = self._connection.execute(
                """
                SELECT daemon_id, expires_at, used_at FROM daemon_challenges
                WHERE challenge_hash = ?
                """,
                (challenge_hash,),
            ).fetchone()
            if challenge_row is None or challenge_row["daemon_id"] != daemon_id:
                raise DaemonApiError(401, "INVALID_CHALLENGE", "Challenge is invalid")
            if challenge_row["used_at"] is not None or challenge_row["expires_at"] <= now:
                raise DaemonApiError(401, "INVALID_CHALLENGE", "Challenge is invalid or expired")
            daemon = self._connection.execute(
                "SELECT * FROM enrolled_daemons WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()
            if daemon is None:
                raise DaemonApiError(404, "DAEMON_NOT_FOUND", "Daemon not found")
            if daemon["revoked_at"] is not None:
                raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
            try:
                VerifyKey(daemon["ed25519_public_key"]).verify(
                    canonical_challenge(daemon_id, challenge),
                    b64decode(signature),
                )
            except (BadSignatureError, ValueError, TypeError):
                raise DaemonApiError(401, "INVALID_SIGNATURE", "Challenge signature is invalid")
            current_daemon = self._connection.execute(
                """
                SELECT key_thumbprint, credential_epoch, revoked_at
                FROM enrolled_daemons WHERE daemon_id = ?
                """,
                (daemon_id,),
            ).fetchone()
            if (
                current_daemon is None
                or current_daemon["revoked_at"] is not None
                or current_daemon["credential_epoch"] != daemon["credential_epoch"]
                or current_daemon["key_thumbprint"] != daemon["key_thumbprint"]
            ):
                raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
            self._connection.execute(
                "DELETE FROM daemon_access_tokens WHERE expires_at <= ?",
                (now,),
            )
            issued_recently = self._connection.execute(
                """
                SELECT COUNT(*) FROM daemon_access_tokens
                WHERE daemon_id = ? AND issued_at > ?
                """,
                (daemon_id, now - 60),
            ).fetchone()[0]
            if issued_recently >= _TOKEN_ISSUANCE_LIMIT_PER_MINUTE:
                raise DaemonApiError(
                    429,
                    "DAEMON_RATE_LIMITED",
                    "Daemon access-token issuance rate exceeded",
                    retryable=True,
                )
            outstanding_tokens = self._connection.execute(
                "SELECT COUNT(*) FROM daemon_access_tokens WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()[0]
            if outstanding_tokens >= _MAX_OUTSTANDING_ACCESS_TOKENS:
                raise DaemonApiError(
                    429,
                    "DAEMON_TOKEN_CAPACITY",
                    "Daemon has too many outstanding access tokens",
                    retryable=True,
                )
            claimed = self._connection.execute(
                """
                UPDATE daemon_challenges SET used_at = ?
                WHERE challenge_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (now, challenge_hash, now),
            )
            if claimed.rowcount != 1:
                raise DaemonApiError(401, "INVALID_CHALLENGE", "Challenge is invalid or expired")
            raw_token = secrets.token_urlsafe(32)
            expires_at = now + lifetime_seconds
            self._connection.execute(
                """
                INSERT INTO daemon_access_tokens (
                    token_hash, daemon_id, key_thumbprint,
                    credential_epoch, expires_at, issued_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self._token_hash(raw_token),
                    daemon_id,
                    current_daemon["key_thumbprint"],
                    current_daemon["credential_epoch"],
                    expires_at,
                    now,
                ),
            )
        return AccessToken(
            value=raw_token,
            daemon_id=daemon_id,
            key_thumbprint=current_daemon["key_thumbprint"],
            credential_epoch=int(current_daemon["credential_epoch"]),
            expires_at=expires_at,
        )

    def _token_record(self, access_token: str) -> sqlite3.Row:
        if not isinstance(access_token, str) or not access_token:
            raise DaemonApiError(401, "INVALID_AUTHENTICATION", "Authentication failed")
        token_hash = self._token_hash(access_token)
        row = self._connection.execute(
            """
            SELECT t.token_hash, t.daemon_id, t.key_thumbprint AS token_thumbprint,
                   t.credential_epoch AS token_epoch, t.expires_at,
                   d.owner_user_id, d.ed25519_public_key,
                   d.key_thumbprint AS current_thumbprint,
                   d.credential_epoch AS current_epoch, d.revoked_at
            FROM daemon_access_tokens AS t
            JOIN enrolled_daemons AS d ON d.daemon_id = t.daemon_id
            WHERE t.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            raise DaemonApiError(401, "INVALID_AUTHENTICATION", "Authentication failed")
        return row

    def verify_request(
        self,
        access_token: str,
        signed_request: SignedRequest,
        body: bytes | None,
        *,
        expected_owner_user_id: str,
    ) -> AuthenticatedDaemon:
        if not isinstance(signed_request, SignedRequest):
            raise DaemonApiError(400, "MALFORMED_REQUEST", "Signed-request fields are required")
        now = self._clock()
        try:
            with self._lock, self._immediate_transaction():
                token = self._token_record(access_token)
                if token["expires_at"] <= now:
                    raise DaemonApiError(401, "TOKEN_EXPIRED", "Access token has expired")
                if (
                    token["revoked_at"] is not None
                    or token["token_epoch"] != token["current_epoch"]
                    or token["token_thumbprint"] != token["current_thumbprint"]
                ):
                    raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
                if abs(now - signed_request.timestamp) > MAX_CLOCK_SKEW_SECONDS:
                    raise DaemonApiError(
                        401, "CLOCK_SKEW", "Request timestamp is outside allowed skew"
                    )
                actual_body_hash = request_body_hash(body)
                if not hmac.compare_digest(actual_body_hash, signed_request.body_hash):
                    raise DaemonApiError(401, "BODY_HASH_MISMATCH", "Request body hash is invalid")
                try:
                    message = canonical_request(
                        signed_request.method,
                        signed_request.path,
                        signed_request.query,
                        dict(signed_request.signed_headers),
                        signed_request.body_hash,
                        signed_request.timestamp,
                        signed_request.nonce,
                    )
                    VerifyKey(token["ed25519_public_key"]).verify(
                        message,
                        b64decode(signed_request.signature),
                    )
                except (BadSignatureError, ValueError, TypeError):
                    raise DaemonApiError(401, "INVALID_SIGNATURE", "Request signature is invalid")
                if token["owner_user_id"] != expected_owner_user_id:
                    raise DaemonApiError(
                        403,
                        "OWNER_SCOPE_DENIED",
                        "Authenticated device lacks authorization for this owner",
                    )
                current_daemon = self._connection.execute(
                    """
                    SELECT key_thumbprint, credential_epoch, revoked_at
                    FROM enrolled_daemons WHERE daemon_id = ?
                    """,
                    (token["daemon_id"],),
                ).fetchone()
                if (
                    current_daemon is None
                    or current_daemon["revoked_at"] is not None
                    or current_daemon["credential_epoch"] != token["token_epoch"]
                    or current_daemon["key_thumbprint"] != token["token_thumbprint"]
                ):
                    raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
                self._connection.execute(
                    "DELETE FROM daemon_request_nonces WHERE expires_at <= ?",
                    (now,),
                )
                requests_recently = self._connection.execute(
                    """
                    SELECT COUNT(*) FROM daemon_request_nonces
                    WHERE daemon_id = ? AND used_at > ?
                    """,
                    (token["daemon_id"], now - 60),
                ).fetchone()[0]
                if requests_recently >= _REQUEST_RATE_LIMIT_PER_MINUTE:
                    raise DaemonApiError(
                        429,
                        "DAEMON_RATE_LIMITED",
                        "Daemon request rate exceeded",
                        retryable=True,
                    )
                outstanding_nonces = self._connection.execute(
                    "SELECT COUNT(*) FROM daemon_request_nonces WHERE daemon_id = ?",
                    (token["daemon_id"],),
                ).fetchone()[0]
                if outstanding_nonces >= _MAX_OUTSTANDING_NONCES:
                    raise DaemonApiError(
                        429,
                        "DAEMON_NONCE_CAPACITY",
                        "Daemon has too many outstanding request nonces",
                        retryable=True,
                    )
                self._connection.execute(
                    """
                    INSERT INTO daemon_request_nonces (daemon_id, nonce, expires_at, used_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        token["daemon_id"],
                        signed_request.nonce,
                        max(
                            token["expires_at"],
                            now + MAX_ACCESS_TOKEN_LIFETIME_SECONDS,
                        ),
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            raise DaemonApiError(401, "REPLAY_DETECTED", "Request nonce was already used")
        return AuthenticatedDaemon(
            daemon_id=token["daemon_id"],
            owner_user_id=token["owner_user_id"],
            key_thumbprint=token["current_thumbprint"],
            credential_epoch=int(token["current_epoch"]),
        )

    def verify_headers(
        self,
        method: str,
        path: str,
        query: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        expected_owner_user_id: str,
    ) -> AuthenticatedDaemon:
        try:
            normalized_headers = {str(name).lower(): value for name, value in headers.items()}
            authorization = normalized_headers["authorization"]
            if not authorization.startswith("Bearer "):
                raise KeyError("Authorization")
            signed = SignedRequest(
                method=method,
                path=path,
                query=query,
                signed_headers=tuple(action_affecting_headers(normalized_headers).items()),
                body_hash=normalized_headers["x-tinyassets-body-sha256"],
                timestamp=int(normalized_headers["x-tinyassets-timestamp"]),
                nonce=normalized_headers["x-tinyassets-nonce"],
                signature=normalized_headers["x-tinyassets-signature"],
            )
        except (KeyError, TypeError, ValueError):
            raise DaemonApiError(401, "INVALID_AUTHENTICATION", "Authentication failed")
        return self.verify_request(
            authorization.removeprefix("Bearer "),
            signed,
            body,
            expected_owner_user_id=expected_owner_user_id,
        )

    def revoke_daemon(self, owner_user_id: str, daemon_id: str) -> int:
        owner_user_id = self._require_identifier(owner_user_id, "owner_user_id")
        daemon_id = self._require_identifier(daemon_id, "daemon_id")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT owner_user_id FROM enrolled_daemons WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()
            if row is None or row["owner_user_id"] != owner_user_id:
                raise DaemonApiError(404, "DAEMON_NOT_FOUND", "Daemon not found")
            self._connection.execute(
                """
                UPDATE enrolled_daemons
                SET credential_epoch = credential_epoch + 1, revoked_at = ?
                WHERE daemon_id = ?
                """,
                (self._clock(), daemon_id),
            )
            epoch = self._connection.execute(
                "SELECT credential_epoch FROM enrolled_daemons WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()["credential_epoch"]
        return int(epoch)


def _malformed(message: str) -> DaemonApiError:
    return DaemonApiError(400, "MALFORMED_REQUEST", message)


def create_router(
    service: DaemonEnrollmentService,
    *,
    owner_resolver: Callable[[Any], str],
):
    """Create the B2 enrollment/token routes without mutating the app router."""

    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter()

    async def body_object(request: Request) -> dict[str, Any]:
        try:
            value = await request.json()
        except Exception as exc:
            raise _malformed("Request body must be a JSON object") from exc
        if not isinstance(value, dict):
            raise _malformed("Request body must be a JSON object")
        return value

    async def owner_for(request: Request) -> str:
        owner = owner_resolver(request)
        if inspect.isawaitable(owner):
            owner = await owner
        if not isinstance(owner, str) or not owner.strip():
            raise DaemonApiError(401, "INVALID_AUTHENTICATION", "Authentication failed")
        return owner

    def unavailable_response() -> JSONResponse:
        error = DaemonApiError(
            503,
            "CONTROL_PLANE_UNAVAILABLE",
            "Control plane is temporarily unavailable",
            retryable=True,
        )
        return JSONResponse(error.as_dict(), status_code=error.status)

    def response(call: Callable[[], Any], status: int = 200) -> JSONResponse:
        try:
            return JSONResponse(call(), status_code=status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-enrollments")
    async def begin_enrollment(request: Request):
        try:
            payload = await body_object(request)
            identity = DevicePublicIdentity(
                installation_id=payload["installation_id"],
                ed25519_public_key=b64decode(payload["ed25519_public_key"]),
                x25519_public_key=b64decode(payload["x25519_public_key"]),
                installation_nonce=b64decode(payload["installation_nonce"]),
                key_backend="remote-device",
                hardware_non_exportable=False,
            )
            enrollment = service.create_enrollment(identity)
            return JSONResponse(
                {
                    "enrollment_id": enrollment.enrollment_id,
                    "verification_code": enrollment.verification_code,
                },
                status_code=201,
            )
        except (KeyError, TypeError, ValueError):
            error = _malformed("Device public keys and installation nonce are required")
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-enrollments:approve")
    async def approve_enrollment(request: Request):
        try:
            payload = await body_object(request)
            owner_user_id = await owner_for(request)
            service.approve_verification_code(
                payload["enrollment_id"],
                payload["verification_code"],
                owner_user_id=owner_user_id,
            )
            return JSONResponse({"status": "approved"})
        except (KeyError, TypeError):
            error = _malformed("enrollment_id and verification_code are required")
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-enrollments/{enrollment_id}:complete")
    async def complete_enrollment(enrollment_id: str, request: Request):
        try:
            payload = await body_object(request)
            value = service.complete_enrollment(
                enrollment_id,
                installation_nonce=payload["installation_nonce"],
                signature=payload["signature"],
            )
            return {
                "enrollment_id": value.enrollment_id,
                "daemon_id": value.daemon_id,
                "key_thumbprint": value.key_thumbprint,
                "credential_epoch": value.credential_epoch,
            }
        except (KeyError, TypeError):
            error = _malformed("installation_nonce and signature are required")
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemons/{daemon_id}:revoke")
    async def revoke_daemon(daemon_id: str, request: Request):
        try:
            owner_user_id = await owner_for(request)
            epoch = service.revoke_daemon(owner_user_id, daemon_id)
            return JSONResponse({"credential_epoch": epoch})
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-access-tokens/challenge")
    async def create_access_challenge(request: Request):
        try:
            payload = await body_object(request)
            value = service.create_challenge(
                payload["daemon_id"],
                timestamp=payload["timestamp"],
                nonce=payload["nonce"],
                signature=payload["signature"],
            )
            return JSONResponse(
                {
                    "daemon_id": value.daemon_id,
                    "challenge": value.challenge,
                    "expires_at": value.expires_at,
                },
                status_code=201,
            )
        except (KeyError, TypeError):
            error = DaemonApiError(
                401,
                "INVALID_AUTHENTICATION",
                "Device proof-of-possession is required",
            )
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-access-tokens")
    async def issue_access_token(request: Request):
        try:
            payload = await body_object(request)
            value = service.issue_access_token(
                payload["daemon_id"],
                payload["challenge"],
                payload["signature"],
            )
            return JSONResponse(
                {
                    "access_token": value.value,
                    "token_type": "Bearer",
                    "daemon_id": value.daemon_id,
                    "key_thumbprint": value.key_thumbprint,
                    "credential_epoch": value.credential_epoch,
                    "expires_at": value.expires_at,
                },
                status_code=201,
            )
        except (KeyError, TypeError):
            error = _malformed("daemon_id, challenge, and signature are required")
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    return router


__all__ = [
    "AuthenticatedDaemon",
    "CompletedEnrollment",
    "DaemonApiError",
    "DaemonChallenge",
    "DaemonEnrollmentService",
    "EnrollmentHandoff",
    "create_router",
]

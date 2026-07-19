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
    b64decode,
    canonical_challenge,
    canonical_request,
    request_body_hash,
)
from tinyassets.storage import data_dir

_CHALLENGE_LIFETIME_SECONDS = 60
_VERIFICATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


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
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enrolled_daemons (
                    daemon_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    ed25519_public_key BLOB NOT NULL,
                    x25519_public_key BLOB NOT NULL,
                    key_thumbprint TEXT NOT NULL,
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
                    PRIMARY KEY (daemon_id, nonce)
                );
                CREATE INDEX IF NOT EXISTS daemon_nonce_expiry
                    ON daemon_request_nonces(expires_at);
                """
            )

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
        for _ in range(8):
            verification_code = "".join(
                secrets.choice(_VERIFICATION_ALPHABET) for _ in range(8)
            )
            try:
                with self._lock, self._connection:
                    self._connection.execute(
                        """
                        INSERT INTO daemon_enrollments (
                            enrollment_id, verification_code, installation_id,
                            installation_nonce_hash, ed25519_public_key,
                            x25519_public_key, key_thumbprint, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
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
                "SELECT status, owner_user_id FROM daemon_enrollments WHERE enrollment_id = ?",
                (enrollment_id,),
            ).fetchone()
            if row is None:
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

    def approve_verification_code(self, verification_code: str, *, owner_user_id: str) -> None:
        if not isinstance(verification_code, str):
            raise DaemonApiError(400, "MALFORMED_REQUEST", "verification_code is required")
        normalized_code = verification_code.strip().upper()
        if len(normalized_code) != 8:
            raise DaemonApiError(400, "MALFORMED_REQUEST", "verification_code is invalid")
        with self._lock:
            row = self._connection.execute(
                "SELECT enrollment_id FROM daemon_enrollments WHERE verification_code = ?",
                (normalized_code,),
            ).fetchone()
        if row is None:
            raise DaemonApiError(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
        self.approve_enrollment(row["enrollment_id"], owner_user_id=owner_user_id)

    def complete_enrollment(self, enrollment_id: str) -> CompletedEnrollment:
        enrollment_id = self._require_identifier(enrollment_id, "enrollment_id")
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
        return CompletedEnrollment(
            enrollment_id=enrollment_id,
            daemon_id=daemon["daemon_id"],
            owner_user_id=daemon["owner_user_id"],
            key_thumbprint=daemon["key_thumbprint"],
            credential_epoch=int(daemon["credential_epoch"]),
        )

    def create_challenge(self, daemon_id: str) -> DaemonChallenge:
        daemon_id = self._require_identifier(daemon_id, "daemon_id")
        now = self._clock()
        challenge = secrets.token_urlsafe(32)
        expires_at = now + _CHALLENGE_LIFETIME_SECONDS
        with self._lock, self._connection:
            daemon = self._connection.execute(
                "SELECT revoked_at FROM enrolled_daemons WHERE daemon_id = ?",
                (daemon_id,),
            ).fetchone()
            if daemon is None:
                raise DaemonApiError(404, "DAEMON_NOT_FOUND", "Daemon not found")
            if daemon["revoked_at"] is not None:
                raise DaemonApiError(410, "CREDENTIAL_REVOKED", "Device credential is revoked")
            self._connection.execute(
                "DELETE FROM daemon_challenges WHERE expires_at < ?",
                (now,),
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
        with self._lock, self._connection:
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
                    daemon["key_thumbprint"],
                    daemon["credential_epoch"],
                    expires_at,
                    now,
                ),
            )
        return AccessToken(
            value=raw_token,
            daemon_id=daemon_id,
            key_thumbprint=daemon["key_thumbprint"],
            credential_epoch=int(daemon["credential_epoch"]),
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
        with self._lock:
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
                raise DaemonApiError(401, "CLOCK_SKEW", "Request timestamp is outside allowed skew")
            actual_body_hash = request_body_hash(body)
            if not hmac.compare_digest(actual_body_hash, signed_request.body_hash):
                raise DaemonApiError(401, "BODY_HASH_MISMATCH", "Request body hash is invalid")
            try:
                message = canonical_request(
                    signed_request.method,
                    signed_request.path,
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
            try:
                with self._connection:
                    self._connection.execute(
                        "DELETE FROM daemon_request_nonces WHERE expires_at < ?",
                        (now,),
                    )
                    self._connection.execute(
                        """
                        INSERT INTO daemon_request_nonces (daemon_id, nonce, expires_at)
                        VALUES (?, ?, ?)
                        """,
                        (
                            token["daemon_id"],
                            signed_request.nonce,
                            max(
                                token["expires_at"],
                                now + MAX_ACCESS_TOKEN_LIFETIME_SECONDS,
                            ),
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
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        expected_owner_user_id: str,
    ) -> AuthenticatedDaemon:
        try:
            authorization = headers["Authorization"]
            if not authorization.startswith("Bearer "):
                raise KeyError("Authorization")
            signed = SignedRequest(
                method=method,
                path=path,
                body_hash=headers["X-TinyAssets-Body-SHA256"],
                timestamp=int(headers["X-TinyAssets-Timestamp"]),
                nonce=headers["X-TinyAssets-Nonce"],
                signature=headers["X-TinyAssets-Signature"],
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
                payload["verification_code"],
                owner_user_id=owner_user_id,
            )
            return JSONResponse({"status": "approved"})
        except (KeyError, TypeError):
            error = _malformed("verification_code is required")
            return JSONResponse(error.as_dict(), status_code=error.status)
        except DaemonApiError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status)
        except Exception:
            return unavailable_response()

    @router.post("/v1/daemon-enrollments/{enrollment_id}:complete")
    async def complete_enrollment(enrollment_id: str):
        def complete() -> dict[str, Any]:
            value = service.complete_enrollment(enrollment_id)
            return {
                "enrollment_id": value.enrollment_id,
                "daemon_id": value.daemon_id,
                "owner_user_id": value.owner_user_id,
                "key_thumbprint": value.key_thumbprint,
                "credential_epoch": value.credential_epoch,
            }

        return response(complete)

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
            value = service.create_challenge(payload["daemon_id"])
            return JSONResponse(
                {
                    "daemon_id": value.daemon_id,
                    "challenge": value.challenge,
                    "expires_at": value.expires_at,
                },
                status_code=201,
            )
        except (KeyError, TypeError):
            error = _malformed("daemon_id is required")
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

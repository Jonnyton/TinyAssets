from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, NoReturn, Protocol

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tinyassets.auth.host_binding import HostBindingIdentity

SCHEMA_VERSION = "host-binding-v1"
POLICY_VERSION = "host-binding-v1"
DOMAIN_SEPARATOR = b"tinyassets.host-principal-proof.v1\0"
MAX_PROOF_TTL_SECONDS = 300
MAX_SUBMISSION_BYTES = 4096
REFUSAL_BUCKET_SECONDS = 0.01
_MAX_SIGNING_INPUT_B64U = 8192
_MAX_ISSUER_OR_AUDIENCE = 2048
_MAX_SUBJECT = 512
_MAX_PRINCIPAL_ID = 256
_I_JSON_MAX_INTEGER = 9_007_199_254_740_991
_POSTGRES_INT_MAX = 2_147_483_647
_HOST_POOL_PRICE_LIMIT = Decimal("1000000000000")
_HOST_POOL_PRICE_SCALE = 6
_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
_PRINCIPAL_TTL_SECONDS = 90 * 24 * 60 * 60
_RENEWAL_WINDOW_SECONDS = 30 * 24 * 60 * 60
_IDEMPOTENCY_LOOKUP_DOMAIN = b"tinyassets.host-enrollment.idempotency-lookup.v1"
_IDEMPOTENCY_BINDING_DOMAIN = b"tinyassets.host-enrollment.idempotency-binding.v1"
_LIFECYCLE_LOOKUP_DOMAIN = b"tinyassets.host-lifecycle.idempotency-lookup.v1"
_LIFECYCLE_BINDING_DOMAIN = b"tinyassets.host-lifecycle.idempotency-binding.v1"
_INVENTORY_CURSOR_DOMAIN = b"tinyassets.host-inventory.cursor.v1"
_INVENTORY_DEFAULT_LIMIT = 25
_INVENTORY_MAX_LIMIT = 100
_MAX_INVENTORY_AUTH_AGE_SECONDS = 300
# No revocation reason values were approved in the frozen v1 artifacts.
REVOCATION_REASON_CODES: frozenset[str] = frozenset()

HOST_BINDING_REFUSAL = MappingProxyType(
    {
        "schema_version": SCHEMA_VERSION,
        "error": "host_binding_refused",
        "retryable": False,
    }
)

_BODY_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_B64U = re.compile(r"[A-Za-z0-9_-]+\Z")


class HostProofRefused(ValueError):
    """A deliberately non-enumerating host-proof refusal."""

    public_error = HOST_BINDING_REFUSAL

    def __init__(self) -> None:
        super().__init__("host binding refused")


class HostProofTimingExceeded(RuntimeError):
    """A refusal exceeded its public timing bucket and must become a server error."""


class HostEnrollmentRefused(HostProofRefused):
    """One non-enumerating refusal for a valid but ineligible enrollment."""


class HostEnrollmentIdempotencyConflict(ValueError):
    """An unexpired idempotency scope named a different enrollment intent."""


class HostEnrollmentWritersDisabled(RuntimeError):
    """Enrollment stays dark until production storage and rollout gates pass."""


class HostInventoryRefused(HostProofRefused):
    """One non-enumerating refusal for private host inventory."""


class HostLifecycleRefused(HostProofRefused):
    """One non-enumerating refusal for an ineligible lifecycle mutation."""


class HostLifecycleIdempotencyConflict(ValueError):
    """An unexpired lifecycle scope named a different intent."""


class HostLifecycleWritersDisabled(RuntimeError):
    """Lifecycle writers stay dark until durable storage and rollout gates pass."""


class HostInventoryStore(Protocol):
    def list_inventory(
        self,
        *,
        issuer: str,
        subject: str,
        after_principal_id: str | None,
        limit: int,
    ) -> list[Mapping[str, object]]: ...


class HostInventoryCoordinator:
    def __init__(
        self,
        *,
        store: HostInventoryStore,
        audience: str,
        cursor_hmac_key: bytes,
    ) -> None:
        if type(audience) is not str or not audience or audience != audience.strip():
            raise ValueError("audience must be non-empty and canonical")
        if type(cursor_hmac_key) is not bytes or len(cursor_hmac_key) < 32:
            raise ValueError("cursor_hmac_key must contain at least 32 bytes")
        self._store = store
        self._audience = audience
        self._cursor_hmac_key = cursor_hmac_key

    def list_inventory(
        self,
        *,
        identity: HostBindingIdentity,
        query: Mapping[str, object],
        now: int,
    ) -> dict[str, object]:
        if (
            type(identity) is not HostBindingIdentity
            or type(now) is not int
            or isinstance(now, bool)
            or type(query) is not dict
            or not hmac.compare_digest(identity.audience, self._audience)
            or "host:manage" not in identity.permissions
            or identity.auth_time > now
            or now - identity.auth_time > _MAX_INVENTORY_AUTH_AGE_SECONDS
        ):
            raise HostInventoryRefused

        try:
            parsed_query = parse_wire_dto("HostInventoryQueryV1", rfc8785.dumps(query))
            limit = parsed_query.get("limit", _INVENTORY_DEFAULT_LIMIT)
            if type(limit) is not int or not 1 <= limit <= _INVENTORY_MAX_LIMIT:
                raise HostProofRefused
            after_principal_id = self._decode_cursor(
                parsed_query.get("cursor"), identity=identity
            )
        except (HostProofRefused, rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
            raise HostInventoryRefused from exc

        records = self._store.list_inventory(
            issuer=identity.issuer,
            subject=identity.subject,
            after_principal_id=after_principal_id,
            limit=limit + 1,
        )
        if type(records) is not list or len(records) > limit + 1:
            raise RuntimeError("host inventory store returned an invalid page")

        items: list[dict[str, object]] = []
        try:
            for record in records[:limit]:
                if (
                    type(record) is not dict
                    or record.get("issuer") != identity.issuer
                    or record.get("subject") != identity.subject
                ):
                    raise HostProofRefused
                item = {
                    field: record[field]
                    for field in (
                        "host_principal_id",
                        "status",
                        "generation",
                        "policy_version",
                        "issued_at",
                        "expires_at",
                    )
                }
                for field in ("last_seen_bucket", "device_label"):
                    if record.get(field) is not None:
                        item[field] = record[field]
                _validate_wire_mapping("HostInventoryItemV1", item)
                items.append(item)
        except (HostProofRefused, KeyError, TypeError, ValueError) as exc:
            raise HostInventoryRefused from exc

        page: dict[str, object] = {"schema_version": SCHEMA_VERSION, "items": items}
        if len(records) > limit:
            page["next_cursor"] = self._encode_cursor(
                identity=identity,
                after_principal_id=items[-1]["host_principal_id"],
            )
        _validate_wire_mapping("HostInventoryPageV1", page)
        return page

    def _encode_cursor(
        self,
        *,
        identity: HostBindingIdentity,
        after_principal_id: object,
    ) -> str:
        if type(after_principal_id) is not str or not after_principal_id:
            raise HostInventoryRefused
        payload = rfc8785.dumps(
            {
                "after_principal_id": after_principal_id,
            }
        )
        signature = hmac.new(
            self._cursor_hmac_key,
            _INVENTORY_CURSOR_DOMAIN
            + b"\0"
            + self._owner_cursor_binding(identity)
            + b"\0"
            + payload,
            hashlib.sha256,
        ).digest()
        return _encode_b64u(payload + signature)

    def _decode_cursor(
        self,
        cursor: object,
        *,
        identity: HostBindingIdentity,
    ) -> str | None:
        if cursor is None:
            return None
        if type(cursor) is not str:
            raise HostProofRefused
        encoded = canonical_b64u(cursor)
        if len(encoded) <= 32:
            raise HostProofRefused
        payload, signature = encoded[:-32], encoded[-32:]
        expected = hmac.new(
            self._cursor_hmac_key,
            _INVENTORY_CURSOR_DOMAIN
            + b"\0"
            + self._owner_cursor_binding(identity)
            + b"\0"
            + payload,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            raise HostProofRefused
        decoded = _parse_json_object(payload)
        if frozenset(decoded) != {"after_principal_id"}:
            raise HostProofRefused
        after_principal_id = decoded.get("after_principal_id")
        if type(after_principal_id) is not str or not after_principal_id:
            raise HostProofRefused
        return after_principal_id

    def _owner_cursor_binding(self, identity: HostBindingIdentity) -> bytes:
        owner = rfc8785.dumps({"issuer": identity.issuer, "subject": identity.subject})
        return hmac.new(
            self._cursor_hmac_key,
            _INVENTORY_CURSOR_DOMAIN + b"\0owner\0" + owner,
            hashlib.sha256,
        ).digest()


@dataclass(frozen=True)
class ProofIssueLimits:
    max_live: int
    principal_per_minute: int
    source_network_per_minute: int


ENROLLMENT_CHALLENGE_LIMITS = ProofIssueLimits(
    max_live=5,
    principal_per_minute=10,
    source_network_per_minute=30,
)
POST_ENROLLMENT_NONCE_LIMITS = ProofIssueLimits(
    max_live=5,
    principal_per_minute=60,
    source_network_per_minute=600,
)


@dataclass(frozen=True)
class HostProofOperationPolicy:
    method: str
    path: str
    permission: str
    signature_roles: frozenset[str]
    intent_dto: str
    result_dto: str


@dataclass(frozen=True)
class HostProofWireContract:
    required_fields: frozenset[str]
    optional_fields: frozenset[str] = frozenset()


_OPERATION_POLICIES = MappingProxyType(
    {
        "enroll": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals",
            "host:enroll",
            frozenset({"new"}),
            "EnrollIntentV1",
            "HostPrincipalResultV1",
        ),
        "inventory": HostProofOperationPolicy(
            "GET",
            "/v1/host-principals",
            "host:manage",
            frozenset(),
            "HostInventoryQueryV1",
            "HostInventoryPageV1",
        ),
        "read": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals/{id}:read",
            "host:manage",
            frozenset({"current"}),
            "PrincipalIntentV1",
            "HostPrincipalDetailV1",
        ),
        "revoke": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals/{id}:revoke",
            "host:manage",
            frozenset({"current"}),
            "RevokeIntentV1",
            "HostPrincipalResultV1",
        ),
        "rotate": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals/{id}:rotate",
            "host:manage",
            frozenset({"current", "new"}),
            "RotateIntentV1",
            "HostPrincipalResultV1",
        ),
        "renew": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals/{id}:renew",
            "host:manage",
            frozenset({"current"}),
            "RenewIntentV1",
            "HostPrincipalResultV1",
        ),
        "recover": HostProofOperationPolicy(
            "POST",
            "/v1/host-principals/{id}:recover",
            "host:recover",
            frozenset({"new"}),
            "RecoverIntentV1",
            "HostRecoveryResultV1",
        ),
        "session_register": HostProofOperationPolicy(
            "POST",
            "/v1/host-sessions",
            "host:manage",
            frozenset({"current"}),
            "SessionRegisterIntentV1",
            "HostSessionResultV1",
        ),
        "session_heartbeat": HostProofOperationPolicy(
            "POST",
            "/v1/host-sessions/{id}:heartbeat",
            "host:manage",
            frozenset({"current"}),
            "SessionHeartbeatIntentV1",
            "HostHeartbeatResultV1",
        ),
        "session_deregister": HostProofOperationPolicy(
            "POST",
            "/v1/host-sessions/{id}:deregister",
            "host:manage",
            frozenset({"current"}),
            "SessionDeregisterIntentV1",
            "HostSessionDeregisterResultV1",
        ),
    }
)

_DIRECT_ACCOUNT_REVOKE_POLICY = HostProofOperationPolicy(
    "POST",
    "/v1/host-principals/{id}:revoke",
    "host:recover",
    frozenset(),
    "AccountRevokeIntentV1",
    "HostPrincipalResultV1",
)


def _wire(required: str = "", optional: str = "") -> HostProofWireContract:
    return HostProofWireContract(frozenset(required.split()), frozenset(optional.split()))


_WIRE_CONTRACTS = MappingProxyType(
    {
        "HostChallengeRequestV1": _wire("schema_version operation intent"),
        "HostChallengeV1": _wire(
            "schema_version challenge_id_b64u signing_input_b64u expires_at policy_version"
        ),
        "HostProofSubmissionV1": _wire("schema_version challenge_id_b64u signatures"),
        "EnrollIntentV1": _wire("idempotency_key_b64u public_jwk", "device_label"),
        "HostInventoryQueryV1": _wire(optional="cursor limit"),
        "PrincipalIntentV1": _wire("host_principal_id expected_generation"),
        "RevokeIntentV1": _wire(
            "host_principal_id expected_generation idempotency_key_b64u", "reason_code"
        ),
        "RotateIntentV1": _wire(
            "host_principal_id expected_generation idempotency_key_b64u new_public_jwk"
        ),
        "RenewIntentV1": _wire("host_principal_id expected_generation idempotency_key_b64u"),
        "RecoverIntentV1": _wire(
            "host_principal_id expected_generation idempotency_key_b64u new_public_jwk",
            "device_label",
        ),
        "AccountRevokeIntentV1": _wire(
            "schema_version host_principal_id expected_generation idempotency_key_b64u",
            "reason_code",
        ),
        "SessionRegisterIntentV1": _wire(
            "host_principal_id expected_generation provider capability_id visibility "
            "price_floor max_concurrent always_active idempotency_key_b64u"
        ),
        "SessionHeartbeatIntentV1": _wire("host_principal_id expected_generation host_session_id"),
        "SessionDeregisterIntentV1": _wire(
            "host_principal_id expected_generation host_session_id idempotency_key_b64u"
        ),
        "HostPrincipalResultV1": _wire(
            "schema_version host_principal_id host_principal_generation status expires_at "
            "policy_version"
        ),
        "HostBindingErrorV1": _wire("schema_version error retryable"),
        "HostInventoryItemV1": _wire(
            "host_principal_id status generation policy_version issued_at expires_at",
            "last_seen_bucket device_label",
        ),
        "HostInventoryPageV1": _wire("schema_version items", "next_cursor"),
        "HostPrincipalDetailV1": _wire(
            "host_principal_id status generation policy_version "
            "issued_at expires_at jwk_thumbprint",
            "last_seen_bucket device_label",
        ),
        "HostRecoveryResultV1": _wire("revoked replacement"),
        "HostSessionResultV1": _wire("host_session_id host_principal_id host_principal_generation"),
        "HostHeartbeatResultV1": _wire("host_session_id accepted_generation status"),
        "HostSessionDeregisterResultV1": _wire("host_session_id status"),
    }
)


@dataclass(frozen=True)
class HostProofBindingV1:
    schema_version: str
    policy_version: str
    operation: str
    permission: str
    issuer: str
    subject: str
    audience: str
    method: str
    path: str
    body_sha256: str
    key_thumbprints: Mapping[str, str]
    host_principal_id: str | None
    expected_generation: int | None
    challenge_id_b64u: str
    issued_at: int
    expires_at: int


@dataclass(frozen=True)
class HostPrincipalResultV1:
    schema_version: str
    host_principal_id: str
    host_principal_generation: int
    status: str
    expires_at: int
    policy_version: str


@dataclass(frozen=True)
class HostRecoveryResultV1:
    revoked: HostPrincipalResultV1
    replacement: HostPrincipalResultV1


@dataclass(frozen=True)
class HostLifecyclePrincipalV1:
    """Secret-free current principal state required at a lifecycle authority boundary."""

    issuer: str = dataclass_field(repr=False)
    subject: str = dataclass_field(repr=False)
    host_principal_id: str = dataclass_field(repr=False)
    generation: int
    status: str
    issued_at: int
    expires_at: int
    policy_version: str
    public_jwk: Mapping[str, object] = dataclass_field(repr=False)
    key_thumbprint: str = dataclass_field(repr=False)
    device_label: str | None = dataclass_field(default=None, repr=False)

    def to_result(self) -> HostPrincipalResultV1:
        return HostPrincipalResultV1(
            schema_version=SCHEMA_VERSION,
            host_principal_id=self.host_principal_id,
            host_principal_generation=self.generation,
            status=self.status,
            expires_at=self.expires_at,
            policy_version=self.policy_version,
        )


def host_principal_authority_is_current(
    principal: HostLifecyclePrincipalV1,
    *,
    expected_generation: int,
    now: int,
) -> bool:
    """Prospective fence for every protected-work start and commit boundary."""

    return (
        type(principal) is HostLifecyclePrincipalV1
        and type(expected_generation) is int
        and not isinstance(expected_generation, bool)
        and type(now) is int
        and not isinstance(now, bool)
        and now >= 0
        and principal.status == "active"
        and principal.generation == expected_generation
        and now < principal.expires_at
    )


LifecycleResult = HostPrincipalResultV1 | HostRecoveryResultV1


@dataclass(frozen=True)
class HostLifecycleTransactionRequest:
    """Secret-scrubbed input to one atomic lifecycle CAS transaction."""

    issuer: str = dataclass_field(repr=False)
    subject: str = dataclass_field(repr=False)
    operation: str
    host_principal_id: str = dataclass_field(repr=False)
    expected_generation: int
    challenge_id_b64u: str = dataclass_field(repr=False)
    idempotency_lookup_hash: str = dataclass_field(repr=False)
    idempotency_binding_hash: str = dataclass_field(repr=False)
    idempotency_expires_at: int
    transaction_time: int
    new_public_jwk: Mapping[str, object] | None = dataclass_field(default=None, repr=False)
    new_key_thumbprint: str | None = dataclass_field(default=None, repr=False)
    replacement_principal_id: str | None = dataclass_field(default=None, repr=False)
    device_label: str | None = dataclass_field(default=None, repr=False)


@dataclass(frozen=True)
class HostLifecycleTransactionOutcome:
    status: Literal["committed", "replayed", "idempotency_conflict", "refused"]
    result: LifecycleResult | None = None

    def __post_init__(self) -> None:
        if self.status not in {"committed", "replayed", "idempotency_conflict", "refused"}:
            raise ValueError("invalid host lifecycle outcome")
        if self.status == "committed":
            if type(self.result) not in {HostPrincipalResultV1, HostRecoveryResultV1}:
                raise ValueError("committed lifecycle outcome requires a result")
        elif self.result is not None:
            raise ValueError("non-committed lifecycle outcome cannot carry a result")


class HostLifecycleTransactionStore(Protocol):
    def load_principal(
        self, *, issuer: str, subject: str, host_principal_id: str
    ) -> HostLifecyclePrincipalV1 | None: ...

    def commit_lifecycle(
        self, request: HostLifecycleTransactionRequest
    ) -> HostLifecycleTransactionOutcome:
        """CAS challenge, idempotency, generation, terminal state, and key uniqueness."""


@dataclass(frozen=True)
class HostEnrollmentTransactionRequest:
    """Secret-scrubbed input to one fixed-order atomic transaction."""

    issuer: str
    subject: str
    audience: str
    policy_version: str
    method: str
    path: str
    body_sha256: str
    key_thumbprint: str
    challenge_id_b64u: str
    idempotency_lookup_hash: str
    idempotency_binding_hash: str
    idempotency_expires_at: int
    transaction_time: int
    candidate_result: HostPrincipalResultV1


@dataclass(frozen=True)
class HostEnrollmentTransactionOutcome:
    status: Literal["committed", "replayed", "idempotency_conflict", "refused"]
    result: HostPrincipalResultV1 | None = None

    def __post_init__(self) -> None:
        if self.status not in {"committed", "replayed", "idempotency_conflict", "refused"}:
            raise ValueError("invalid host enrollment outcome")
        if self.status == "committed":
            if type(self.result) is not HostPrincipalResultV1:
                raise ValueError("committed enrollment outcome requires a result")
        elif self.result is not None:
            raise ValueError("non-committed enrollment outcome cannot carry a result")


class HostEnrollmentTransactionStore(Protocol):
    def commit_enrollment(
        self, request: HostEnrollmentTransactionRequest
    ) -> HostEnrollmentTransactionOutcome:
        """CAS challenge, idempotency, uniqueness, and principal atomically."""


def _new_principal_id() -> str:
    return "hp_" + secrets.token_urlsafe(24)


class HostEnrollmentCoordinator:
    """Verify fresh enrollment authority before invoking one atomic store seam."""

    def __init__(
        self,
        *,
        store: HostEnrollmentTransactionStore,
        idempotency_hmac_key: bytes,
        writers_enabled: bool = False,
        new_principal_id: Callable[[], str] = _new_principal_id,
    ) -> None:
        if type(idempotency_hmac_key) is not bytes or len(idempotency_hmac_key) < 32:
            raise ValueError("idempotency_hmac_key must contain at least 32 bytes")
        if type(writers_enabled) is not bool:
            raise TypeError("writers_enabled must be boolean")
        self._store = store
        self._idempotency_hmac_key = idempotency_hmac_key
        self._writers_enabled = writers_enabled
        self._new_principal_id = new_principal_id

    def complete_enrollment(
        self,
        *,
        submission_json: bytes | str,
        binding: HostProofBindingV1,
        enroll_intent: Mapping[str, object],
        signing_input_b64u: str,
        now: int,
    ) -> HostPrincipalResultV1:
        if not self._writers_enabled:
            raise HostEnrollmentWritersDisabled
        if type(binding) is not HostProofBindingV1 or type(now) is not int or now < 0:
            raise HostEnrollmentRefused

        policy = operation_policy("enroll")
        if (
            binding.schema_version != SCHEMA_VERSION
            or binding.policy_version != POLICY_VERSION
            or binding.operation != "enroll"
            or binding.permission != policy.permission
            or binding.method != policy.method
            or binding.path != policy.path
            or binding.host_principal_id is not None
            or binding.expected_generation is not None
            or frozenset(binding.key_thumbprints) != {"new"}
            or type(enroll_intent) is not dict
        ):
            raise HostEnrollmentRefused

        try:
            canonical_intent = rfc8785.dumps(enroll_intent)
            parsed_intent = parse_wire_dto("EnrollIntentV1", canonical_intent)
        except (HostProofRefused, rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
            raise HostEnrollmentRefused from exc
        body_sha256 = "sha256:" + hashlib.sha256(canonical_intent).hexdigest()
        if not hmac.compare_digest(body_sha256, binding.body_sha256):
            raise HostEnrollmentRefused

        idempotency_key_b64u = parsed_intent["idempotency_key_b64u"]
        public_jwk = parsed_intent["public_jwk"]
        if type(idempotency_key_b64u) is not str or type(public_jwk) is not dict:
            raise HostEnrollmentRefused
        raw_idempotency_key = canonical_b64u(idempotency_key_b64u, size=32)
        try:
            thumbprint = jwk_thumbprint(public_jwk)
        except HostProofRefused as exc:
            raise HostEnrollmentRefused from exc
        if not hmac.compare_digest(thumbprint, binding.key_thumbprints["new"]):
            raise HostEnrollmentRefused

        principal_id = self._new_principal_id()
        if (
            type(principal_id) is not str
            or not principal_id
            or principal_id != principal_id.strip()
            or len(principal_id) > 128
        ):
            raise RuntimeError("new_principal_id returned an invalid identifier")

        lookup_fields = {
            "issuer": binding.issuer,
            "subject": binding.subject,
            "audience": binding.audience,
            "policy_version": binding.policy_version,
            "operation": binding.operation,
            "method": binding.method,
            "path": binding.path,
            "key_thumbprint": thumbprint,
            "idempotency_key_b64u": idempotency_key_b64u,
        }
        request = HostEnrollmentTransactionRequest(
            issuer=binding.issuer,
            subject=binding.subject,
            audience=binding.audience,
            policy_version=binding.policy_version,
            method=binding.method,
            path=binding.path,
            body_sha256=binding.body_sha256,
            key_thumbprint=thumbprint,
            challenge_id_b64u=binding.challenge_id_b64u,
            idempotency_lookup_hash=self._keyed_hash(
                _IDEMPOTENCY_LOOKUP_DOMAIN, lookup_fields, raw_idempotency_key
            ),
            idempotency_binding_hash=self._keyed_hash(
                _IDEMPOTENCY_BINDING_DOMAIN,
                {**lookup_fields, "body_sha256": binding.body_sha256},
                raw_idempotency_key,
            ),
            idempotency_expires_at=now + _IDEMPOTENCY_TTL_SECONDS,
            transaction_time=now,
            candidate_result=HostPrincipalResultV1(
                schema_version=SCHEMA_VERSION,
                host_principal_id=principal_id,
                host_principal_generation=1,
                status="active",
                expires_at=now + _PRINCIPAL_TTL_SECONDS,
                policy_version=POLICY_VERSION,
            ),
        )
        outcome: HostEnrollmentTransactionOutcome | None = None

        def commit_verified_challenge(challenge_id_b64u: str) -> bool:
            nonlocal outcome
            if not hmac.compare_digest(challenge_id_b64u, request.challenge_id_b64u):
                return False
            outcome = self._store.commit_enrollment(request)
            if type(outcome) is not HostEnrollmentTransactionOutcome:
                raise RuntimeError("host enrollment store returned an invalid outcome")
            return outcome.status != "replayed"

        verify_host_proof(
            submission_json,
            binding=binding,
            public_jwks={"new": public_jwk},
            signing_input_b64u=signing_input_b64u,
            now=now,
            consume_once=commit_verified_challenge,
        )
        if outcome is None:
            raise RuntimeError("verified enrollment completed without a store outcome")
        if outcome.status == "idempotency_conflict":
            raise HostEnrollmentIdempotencyConflict
        if outcome.status == "refused":
            raise HostEnrollmentRefused
        if outcome.status != "committed" or outcome.result is None:
            raise RuntimeError("host enrollment store returned an invalid terminal outcome")
        return outcome.result

    def _keyed_hash(
        self,
        domain: bytes,
        fields: Mapping[str, object],
        raw_idempotency_key: bytes,
    ) -> str:
        message = domain + b"\0" + raw_idempotency_key + b"\0" + rfc8785.dumps(dict(fields))
        digest = hmac.new(self._idempotency_hmac_key, message, hashlib.sha256).hexdigest()
        return "hmac-sha256:" + digest


class HostLifecycleCoordinator:
    """Verify lifecycle proof before one atomic store-owned state transition."""

    _OPERATIONS = frozenset({"revoke", "rotate", "renew", "recover"})

    def __init__(
        self,
        *,
        store: HostLifecycleTransactionStore,
        idempotency_hmac_key: bytes,
        writers_enabled: bool = False,
        new_principal_id: Callable[[], str] = _new_principal_id,
    ) -> None:
        if type(idempotency_hmac_key) is not bytes or len(idempotency_hmac_key) < 32:
            raise ValueError("idempotency_hmac_key must contain at least 32 bytes")
        if type(writers_enabled) is not bool:
            raise TypeError("writers_enabled must be boolean")
        self._store = store
        self._idempotency_hmac_key = idempotency_hmac_key
        self._writers_enabled = writers_enabled
        self._new_principal_id = new_principal_id

    def complete_lifecycle(
        self,
        *,
        submission_json: bytes | str,
        binding: HostProofBindingV1,
        intent: Mapping[str, object],
        signing_input_b64u: str,
        now: int,
    ) -> LifecycleResult:
        if not self._writers_enabled:
            raise HostLifecycleWritersDisabled
        if (
            type(binding) is not HostProofBindingV1
            or binding.operation not in self._OPERATIONS
            or type(intent) is not dict
            or type(now) is not int
            or isinstance(now, bool)
            or now < 0
        ):
            raise HostLifecycleRefused

        policy = operation_policy(binding.operation)
        if (
            binding.schema_version != SCHEMA_VERSION
            or binding.policy_version != POLICY_VERSION
            or binding.permission != policy.permission
            or binding.method != policy.method
            or binding.path != policy.path
            or binding.host_principal_id is None
            or type(binding.expected_generation) is not int
            or isinstance(binding.expected_generation, bool)
            or binding.expected_generation < 1
            or frozenset(binding.key_thumbprints) != policy.signature_roles
        ):
            raise HostLifecycleRefused

        try:
            canonical_intent = rfc8785.dumps(intent)
            parsed_intent = parse_wire_dto(policy.intent_dto, canonical_intent)
        except (HostProofRefused, rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
            raise HostLifecycleRefused from exc
        if (
            parsed_intent["host_principal_id"] != binding.host_principal_id
            or parsed_intent["expected_generation"] != binding.expected_generation
            or not hmac.compare_digest(
                "sha256:" + hashlib.sha256(canonical_intent).hexdigest(),
                binding.body_sha256,
            )
        ):
            raise HostLifecycleRefused

        principal = self._store.load_principal(
            issuer=binding.issuer,
            subject=binding.subject,
            host_principal_id=binding.host_principal_id,
        )
        if type(principal) is not HostLifecyclePrincipalV1 or now >= principal.expires_at:
            raise HostLifecycleRefused
        retrying_terminal = (
            binding.operation in {"revoke", "recover"}
            and principal.status == "revoked"
            and binding.expected_generation == principal.generation - 1
        )
        if not retrying_terminal and not host_principal_authority_is_current(
            principal, expected_generation=binding.expected_generation, now=now
        ):
            raise HostLifecycleRefused
        if binding.operation == "renew" and now < principal.expires_at - _RENEWAL_WINDOW_SECONDS:
            raise HostLifecycleRefused

        idempotency_key_b64u = parsed_intent.get("idempotency_key_b64u")
        if type(idempotency_key_b64u) is not str:
            raise HostLifecycleRefused
        try:
            raw_idempotency_key = canonical_b64u(idempotency_key_b64u, size=32)
        except HostProofRefused as exc:
            raise HostLifecycleRefused from exc

        public_jwks: dict[str, Mapping[str, object]] = {}
        new_public_jwk: Mapping[str, object] | None = None
        new_key_thumbprint: str | None = None
        if "current" in policy.signature_roles:
            if not hmac.compare_digest(
                principal.key_thumbprint, binding.key_thumbprints["current"]
            ):
                raise HostLifecycleRefused
            public_jwks["current"] = principal.public_jwk
        if "new" in policy.signature_roles:
            candidate_jwk = parsed_intent.get("new_public_jwk")
            if type(candidate_jwk) is not dict:
                raise HostLifecycleRefused
            try:
                new_key_thumbprint = jwk_thumbprint(candidate_jwk)
            except HostProofRefused as exc:
                raise HostLifecycleRefused from exc
            if not hmac.compare_digest(new_key_thumbprint, binding.key_thumbprints["new"]):
                raise HostLifecycleRefused
            new_public_jwk = candidate_jwk
            public_jwks["new"] = candidate_jwk

        replacement_principal_id: str | None = None
        if binding.operation == "recover":
            replacement_principal_id = self._new_principal_id()
            if (
                type(replacement_principal_id) is not str
                or not replacement_principal_id
                or replacement_principal_id != replacement_principal_id.strip()
                or len(replacement_principal_id) > 128
                or replacement_principal_id == principal.host_principal_id
            ):
                raise RuntimeError("new_principal_id returned an invalid replacement identifier")

        lookup_fields = {
            "issuer": binding.issuer,
            "subject": binding.subject,
            "policy_version": binding.policy_version,
            "operation": binding.operation,
            "path": binding.path,
            "host_principal_id": binding.host_principal_id,
            "expected_generation": binding.expected_generation,
            "key_thumbprints": dict(binding.key_thumbprints),
            "idempotency_key_b64u": idempotency_key_b64u,
        }
        request = HostLifecycleTransactionRequest(
            issuer=binding.issuer,
            subject=binding.subject,
            operation=binding.operation,
            host_principal_id=binding.host_principal_id,
            expected_generation=binding.expected_generation,
            challenge_id_b64u=binding.challenge_id_b64u,
            idempotency_lookup_hash=self._keyed_hash(
                _LIFECYCLE_LOOKUP_DOMAIN, lookup_fields, raw_idempotency_key
            ),
            idempotency_binding_hash=self._keyed_hash(
                _LIFECYCLE_BINDING_DOMAIN,
                {**lookup_fields, "body_sha256": binding.body_sha256},
                raw_idempotency_key,
            ),
            idempotency_expires_at=now + _IDEMPOTENCY_TTL_SECONDS,
            transaction_time=now,
            new_public_jwk=new_public_jwk,
            new_key_thumbprint=new_key_thumbprint,
            replacement_principal_id=replacement_principal_id,
            device_label=parsed_intent.get("device_label"),
        )
        outcome: HostLifecycleTransactionOutcome | None = None

        def commit_verified_challenge(challenge_id_b64u: str) -> bool:
            nonlocal outcome
            if not hmac.compare_digest(challenge_id_b64u, request.challenge_id_b64u):
                return False
            outcome = self._store.commit_lifecycle(request)
            if type(outcome) is not HostLifecycleTransactionOutcome:
                raise RuntimeError("host lifecycle store returned an invalid outcome")
            return outcome.status != "replayed"

        verify_host_proof(
            submission_json,
            binding=binding,
            public_jwks=public_jwks,
            signing_input_b64u=signing_input_b64u,
            now=now,
            consume_once=commit_verified_challenge,
        )
        if outcome is None:
            raise RuntimeError("verified lifecycle operation completed without a store outcome")
        if outcome.status == "idempotency_conflict":
            raise HostLifecycleIdempotencyConflict
        if outcome.status == "refused":
            raise HostLifecycleRefused
        if outcome.status != "committed" or outcome.result is None:
            raise RuntimeError("host lifecycle store returned an invalid terminal outcome")
        return outcome.result

    def _keyed_hash(
        self,
        domain: bytes,
        fields: Mapping[str, object],
        raw_idempotency_key: bytes,
    ) -> str:
        message = domain + b"\0" + raw_idempotency_key + b"\0" + rfc8785.dumps(dict(fields))
        digest = hmac.new(self._idempotency_hmac_key, message, hashlib.sha256).hexdigest()
        return "hmac-sha256:" + digest


def operation_policy(operation: str) -> HostProofOperationPolicy:
    if type(operation) is not str:
        raise HostProofRefused
    try:
        return _OPERATION_POLICIES[operation]
    except KeyError as exc:
        raise HostProofRefused from exc


def direct_account_revoke_policy() -> HostProofOperationPolicy:
    return _DIRECT_ACCOUNT_REVOKE_POLICY


def wire_contract(dto_name: str) -> HostProofWireContract:
    if type(dto_name) is not str:
        raise HostProofRefused
    try:
        return _WIRE_CONTRACTS[dto_name]
    except KeyError as exc:
        raise HostProofRefused from exc


def parse_wire_dto(dto_name: str, document: bytes | str) -> dict[str, Any]:
    payload = _parse_json_object(document)
    contract = wire_contract(dto_name)
    fields = frozenset(payload)
    if not contract.required_fields <= fields or not fields <= (
        contract.required_fields | contract.optional_fields
    ):
        raise HostProofRefused
    if (
        "schema_version" in contract.required_fields
        and payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise HostProofRefused
    _validate_wire_semantics(dto_name, payload)
    return payload


def validate_route_path_id(
    operation: str,
    *,
    intent: Mapping[str, object],
    path_id: str,
) -> None:
    field_by_operation = {
        "read": "host_principal_id",
        "revoke": "host_principal_id",
        "rotate": "host_principal_id",
        "renew": "host_principal_id",
        "recover": "host_principal_id",
        "session_heartbeat": "host_session_id",
        "session_deregister": "host_session_id",
    }
    field = field_by_operation.get(operation)
    if (
        field is None
        or type(intent) is not dict
        or type(path_id) is not str
        or type(intent.get(field)) is not str
        or not hmac.compare_digest(intent[field], path_id)
    ):
        raise HostProofRefused


def _validate_wire_semantics(dto_name: str, payload: dict[str, Any]) -> None:
    string_fields = {
        "host_principal_id",
        "host_session_id",
        "provider",
        "capability_id",
        "visibility",
        "status",
        "policy_version",
        "cursor",
        "next_cursor",
        "last_seen_bucket",
        "device_label",
        "reason_code",
        "error",
        "jwk_thumbprint",
    }
    for field in string_fields & payload.keys():
        _require_wire_string(payload[field], maximum=2048)

    for field in (
        "expected_generation",
        "host_principal_generation",
        "generation",
        "accepted_generation",
        "max_concurrent",
    ):
        if field in payload and (
            type(payload[field]) is not int or not 1 <= payload[field] <= _I_JSON_MAX_INTEGER
        ):
            raise HostProofRefused
    for field in ("issued_at", "expires_at"):
        if field in payload and (
            type(payload[field]) is not int or not 0 <= payload[field] <= _I_JSON_MAX_INTEGER
        ):
            raise HostProofRefused
    if "limit" in payload and (
        type(payload["limit"]) is not int or not 1 <= payload["limit"] <= 100
    ):
        raise HostProofRefused
    for field in ("always_active", "retryable"):
        if field in payload and type(payload[field]) is not bool:
            raise HostProofRefused

    for field in ("challenge_id_b64u", "idempotency_key_b64u"):
        if field in payload:
            canonical_b64u(payload[field], size=32)
    if "signing_input_b64u" in payload:
        canonical_b64u(payload["signing_input_b64u"])
    if "jwk_thumbprint" in payload:
        canonical_b64u(payload["jwk_thumbprint"], size=32)
    if "policy_version" in payload and payload["policy_version"] != POLICY_VERSION:
        raise HostProofRefused
    for field in ("public_jwk", "new_public_jwk"):
        if field in payload:
            _public_key_bytes(payload[field])
    if "device_label" in payload and (
        len(payload["device_label"]) > 64
        or payload["device_label"] != _nfc(payload["device_label"])
    ):
        raise HostProofRefused
    if "reason_code" in payload and payload["reason_code"] not in REVOCATION_REASON_CODES:
        raise HostProofRefused

    if dto_name == "HostChallengeRequestV1":
        operation = payload.get("operation")
        policy = operation_policy(operation)
        if not policy.signature_roles or type(payload.get("intent")) is not dict:
            raise HostProofRefused
        _validate_wire_mapping(policy.intent_dto, payload["intent"])
    elif dto_name == "HostProofSubmissionV1":
        signatures = payload.get("signatures")
        if type(signatures) is not dict or not signatures:
            raise HostProofRefused
        for role, signature in signatures.items():
            if type(role) is not str:
                raise HostProofRefused
            canonical_b64u(signature, size=64)
    elif dto_name == "SessionRegisterIntentV1":
        if payload["provider"] not in {"local", "claude", "codex", "gemini"}:
            raise HostProofRefused
        if payload["visibility"] not in {"self", "network", "paid"}:
            raise HostProofRefused
        if payload["max_concurrent"] > _POSTGRES_INT_MAX:
            raise HostProofRefused
        price_floor = payload["price_floor"]
        if price_floor is not None and (
            type(price_floor) not in {int, float}
            or isinstance(price_floor, bool)
            or not _exact_host_pool_price(price_floor)
        ):
            raise HostProofRefused
    elif dto_name == "HostHeartbeatResultV1" and payload["status"] != "active":
        raise HostProofRefused
    elif dto_name == "HostSessionDeregisterResultV1" and payload["status"] != "deleted":
        raise HostProofRefused
    elif dto_name == "HostBindingErrorV1" and payload["error"] != "host_binding_refused":
        raise HostProofRefused
    elif dto_name in {
        "HostPrincipalResultV1",
        "HostInventoryItemV1",
        "HostPrincipalDetailV1",
    } and payload["status"] not in {"pending", "active", "revoked", "expired"}:
        raise HostProofRefused

    if dto_name == "HostInventoryPageV1":
        items = payload.get("items")
        if type(items) is not list:
            raise HostProofRefused
        for item in items:
            _validate_wire_mapping("HostInventoryItemV1", item)
    elif dto_name == "HostRecoveryResultV1":
        _validate_wire_mapping("HostPrincipalResultV1", payload.get("revoked"))
        _validate_wire_mapping("HostPrincipalResultV1", payload.get("replacement"))


def _validate_wire_mapping(dto_name: str, payload: object) -> None:
    if type(payload) is not dict:
        raise HostProofRefused
    contract = wire_contract(dto_name)
    fields = frozenset(payload)
    if not contract.required_fields <= fields or not fields <= (
        contract.required_fields | contract.optional_fields
    ):
        raise HostProofRefused
    if (
        "schema_version" in contract.required_fields
        and payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise HostProofRefused
    _validate_wire_semantics(dto_name, payload)


def _require_wire_string(value: object, *, maximum: int) -> None:
    if type(value) is not str or not value or len(value) > maximum:
        raise HostProofRefused
    _validate_unicode(value)


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _finite_nonnegative(value: int | float) -> bool:
    if type(value) is int:
        return 0 <= value <= _I_JSON_MAX_INTEGER
    return math.isfinite(value) and value >= 0


def _exact_host_pool_price(value: int | float) -> bool:
    """Accept only JCS numbers preserved exactly by PostgreSQL numeric(18,6)."""

    if not _finite_nonnegative(value):
        return False
    try:
        canonical_number = rfc8785.dumps(value).decode("ascii")
        numeric = Decimal(canonical_number)
    except (UnicodeError, ValueError, rfc8785.CanonicalizationError):
        return False
    return (
        numeric < _HOST_POOL_PRICE_LIMIT and numeric.as_tuple().exponent >= -_HOST_POOL_PRICE_SCALE
    )


def canonical_b64u(value: str, *, size: int | None = None) -> bytes:
    expected_length = None if size is None else (4 * size + 2) // 3
    if (
        type(value) is not str
        or (expected_length is not None and len(value) != expected_length)
        or _B64U.fullmatch(value) is None
    ):
        raise HostProofRefused
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise HostProofRefused from exc
    if _encode_b64u(decoded) != value or (size is not None and len(decoded) != size):
        raise HostProofRefused
    return decoded


def jwk_thumbprint(jwk: Mapping[str, object]) -> str:
    raw = _public_key_bytes(jwk)
    canonical = rfc8785.dumps({"crv": "Ed25519", "kty": "OKP", "x": _encode_b64u(raw)})
    return _encode_b64u(hashlib.sha256(canonical).digest())


def host_proof_signing_bytes(binding: HostProofBindingV1) -> bytes:
    _validate_binding(binding, now=None)
    if not operation_policy(binding.operation).signature_roles:
        raise HostProofRefused
    try:
        canonical = rfc8785.dumps(_binding_payload(binding))
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise HostProofRefused from exc
    return DOMAIN_SEPARATOR + canonical


def verify_host_proof(
    submission_json: bytes | str,
    *,
    binding: HostProofBindingV1,
    public_jwks: Mapping[str, Mapping[str, object]],
    signing_input_b64u: str,
    now: int,
    consume_once: Callable[[str], bool],
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Verify one closed HostProofV1 and atomically consume its challenge/nonce.

    ``consume_once`` is the storage seam: it must perform a compare-and-set and
    return true exactly once. Signature verification happens before that seam.
    """

    started_at = monotonic()
    try:
        _validate_binding(binding, now=now)
        policy = operation_policy(binding.operation)
        if not policy.signature_roles:
            raise HostProofRefused
        expected_roles = policy.signature_roles
        if type(public_jwks) is not dict or frozenset(public_jwks) != expected_roles:
            raise HostProofRefused

        submission = _parse_submission(submission_json)
        if submission["schema_version"] != SCHEMA_VERSION:
            raise HostProofRefused
        if not hmac.compare_digest(submission["challenge_id_b64u"], binding.challenge_id_b64u):
            raise HostProofRefused
        signatures = submission["signatures"]
        if type(signatures) is not dict or frozenset(signatures) != expected_roles:
            raise HostProofRefused

        expected_input = host_proof_signing_bytes(binding)
        if type(signing_input_b64u) is not str or len(signing_input_b64u) > _MAX_SIGNING_INPUT_B64U:
            raise HostProofRefused
        presented_input = canonical_b64u(signing_input_b64u)
        if not hmac.compare_digest(presented_input, expected_input):
            raise HostProofRefused

        public_keys: dict[str, Ed25519PublicKey] = {}
        raw_keys: set[bytes] = set()
        for role in sorted(expected_roles):
            raw_key = _public_key_bytes(public_jwks[role])
            if raw_key in raw_keys:
                raise HostProofRefused
            raw_keys.add(raw_key)
            if not hmac.compare_digest(
                jwk_thumbprint(public_jwks[role]), binding.key_thumbprints[role]
            ):
                raise HostProofRefused
            public_keys[role] = Ed25519PublicKey.from_public_bytes(raw_key)

        for role in sorted(expected_roles):
            signature = canonical_b64u(signatures[role], size=64)
            public_keys[role].verify(signature, expected_input)

    except HostProofRefused:
        refuse_host_binding(started_at=started_at, monotonic=monotonic, sleeper=sleeper)
    except (InvalidSignature, KeyError, TypeError, ValueError, UnicodeError) as exc:
        try:
            refuse_host_binding(started_at=started_at, monotonic=monotonic, sleeper=sleeper)
        except HostProofRefused as refused:
            raise refused from exc

    if consume_once(binding.challenge_id_b64u) is not True:
        refuse_host_binding(started_at=started_at, monotonic=monotonic, sleeper=sleeper)


def refuse_host_binding(
    *,
    started_at: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> NoReturn:
    """Pad public refusals to one bucket; over-budget work becomes operational failure."""

    elapsed = max(0.0, monotonic() - started_at)
    if elapsed > REFUSAL_BUCKET_SECONDS:
        raise HostProofTimingExceeded("host proof refusal exceeded its timing bucket")
    remaining = REFUSAL_BUCKET_SECONDS - elapsed
    if remaining > 0:
        sleeper(remaining)
    raise HostProofRefused


def _binding_payload(binding: HostProofBindingV1) -> dict[str, object]:
    return {
        "schema_version": binding.schema_version,
        "policy_version": binding.policy_version,
        "operation": binding.operation,
        "permission": binding.permission,
        "issuer": binding.issuer,
        "subject": binding.subject,
        "audience": binding.audience,
        "method": binding.method,
        "path": binding.path,
        "body_sha256": binding.body_sha256,
        "key_thumbprints": dict(binding.key_thumbprints),
        "host_principal_id": binding.host_principal_id,
        "expected_generation": binding.expected_generation,
        "challenge_id_b64u": binding.challenge_id_b64u,
        "issued_at": binding.issued_at,
        "expires_at": binding.expires_at,
    }


def _validate_binding(binding: HostProofBindingV1, *, now: int | None) -> None:
    if type(binding) is not HostProofBindingV1:
        raise HostProofRefused
    policy = operation_policy(binding.operation)
    if (
        binding.schema_version != SCHEMA_VERSION
        or binding.policy_version != POLICY_VERSION
        or binding.method != policy.method
        or binding.path != policy.path
        or binding.permission != policy.permission
        or type(binding.issuer) is not str
        or not binding.issuer
        or len(binding.issuer) > _MAX_ISSUER_OR_AUDIENCE
        or type(binding.subject) is not str
        or not binding.subject
        or len(binding.subject) > _MAX_SUBJECT
        or type(binding.audience) is not str
        or not binding.audience
        or len(binding.audience) > _MAX_ISSUER_OR_AUDIENCE
        or type(binding.body_sha256) is not str
        or _BODY_DIGEST.fullmatch(binding.body_sha256) is None
        or type(binding.issued_at) is not int
        or type(binding.expires_at) is not int
        or isinstance(binding.issued_at, bool)
        or isinstance(binding.expires_at, bool)
        or binding.expires_at <= binding.issued_at
        or binding.expires_at - binding.issued_at > MAX_PROOF_TTL_SECONDS
    ):
        raise HostProofRefused
    _validate_unicode(binding.issuer)
    _validate_unicode(binding.subject)
    _validate_unicode(binding.audience)
    canonical_b64u(binding.challenge_id_b64u, size=32)
    if (
        type(binding.key_thumbprints) is not dict
        or frozenset(binding.key_thumbprints) != policy.signature_roles
    ):
        raise HostProofRefused
    for role, thumbprint in binding.key_thumbprints.items():
        if type(role) is not str:
            raise HostProofRefused
        canonical_b64u(thumbprint, size=32)
    if binding.operation == "enroll":
        if binding.host_principal_id is not None or binding.expected_generation is not None:
            raise HostProofRefused
    elif (
        type(binding.host_principal_id) is not str
        or not binding.host_principal_id
        or len(binding.host_principal_id) > _MAX_PRINCIPAL_ID
        or type(binding.expected_generation) is not int
        or isinstance(binding.expected_generation, bool)
        or binding.expected_generation < 1
    ):
        raise HostProofRefused
    if now is not None and (
        type(now) is not int
        or isinstance(now, bool)
        or binding.issued_at > now
        or binding.expires_at <= now
    ):
        raise HostProofRefused


def _public_key_bytes(jwk: Mapping[str, object]) -> bytes:
    if type(jwk) is not dict or frozenset(jwk) != {"kty", "crv", "x"}:
        raise HostProofRefused
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise HostProofRefused
    return canonical_b64u(jwk.get("x"), size=32)


def _parse_submission(submission_json: bytes | str) -> dict[str, Any]:
    parsed = parse_wire_dto("HostProofSubmissionV1", submission_json)
    if type(parsed["schema_version"]) is not str or type(parsed["challenge_id_b64u"]) is not str:
        raise HostProofRefused
    return parsed


def _parse_json_object(document: bytes | str) -> dict[str, Any]:
    try:
        if type(document) is bytes:
            if len(document) > MAX_SUBMISSION_BYTES:
                raise HostProofRefused
            text = document.decode("utf-8", errors="strict")
        elif type(document) is str:
            if len(document.encode("utf-8", errors="strict")) > MAX_SUBMISSION_BYTES:
                raise HostProofRefused
            text = document
        else:
            raise HostProofRefused
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_non_finite_json,
        )
        _validate_unicode(parsed)
    except (json.JSONDecodeError, UnicodeError, TypeError, ValueError) as exc:
        raise HostProofRefused from exc
    if type(parsed) is not dict:
        raise HostProofRefused
    return parsed


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_non_finite_json(_constant: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def _validate_unicode(value: object) -> None:
    if type(value) is str:
        value.encode("utf-8", errors="strict")
    elif type(value) is dict:
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)
    elif type(value) is list:
        for item in value:
            _validate_unicode(item)


def _encode_b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

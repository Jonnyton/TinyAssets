from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, NoReturn

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

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
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_members)
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

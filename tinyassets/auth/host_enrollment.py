"""Writer-disabled host-principal enrollment transaction boundary.

This module deliberately does not provide production persistence or a route.
It verifies a fresh HostProofV1 outside the storage write lock, removes raw
idempotency material, and hands one closed request to the atomic store that is
implemented by the later production-storage lane.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol

import rfc8785

from tinyassets.auth.host_proof import (
    POLICY_VERSION,
    SCHEMA_VERSION,
    HostProofBindingV1,
    HostProofRefused,
    canonical_b64u,
    jwk_thumbprint,
    operation_policy,
    parse_wire_dto,
    verify_host_proof,
)

_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
_PRINCIPAL_TTL_SECONDS = 90 * 24 * 60 * 60
_LOOKUP_DOMAIN = b"tinyassets.host-enrollment.idempotency-lookup.v1"
_BINDING_DOMAIN = b"tinyassets.host-enrollment.idempotency-binding.v1"


class HostEnrollmentRefused(HostProofRefused):
    """One non-enumerating refusal class for a valid but ineligible binding."""


class HostEnrollmentIdempotencyConflict(ValueError):
    """The same unexpired idempotency scope named a different intent."""


class HostEnrollmentWritersDisabled(RuntimeError):
    """Enrollment remains dark until production storage and rollout gates pass."""


@dataclass(frozen=True)
class HostPrincipalResultV1:
    schema_version: str
    host_principal_id: str
    generation: int
    status: str
    expires_at: int
    policy_version: str


@dataclass(frozen=True)
class HostEnrollmentTransactionRequest:
    """Secret-scrubbed input to one fixed-order atomic storage transaction."""

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
    """Closed result from the atomic challenge/idempotency/uniqueness commit."""

    status: Literal["committed", "replayed", "idempotency_conflict", "refused"]
    result: HostPrincipalResultV1 | None = None

    def __post_init__(self) -> None:
        if self.status == "committed":
            if type(self.result) is not HostPrincipalResultV1:
                raise ValueError("committed enrollment outcome requires a result")
        elif self.result is not None:
            raise ValueError("non-committed enrollment outcome cannot carry a result")


class HostEnrollmentTransactionStore(Protocol):
    def commit_enrollment(
        self, request: HostEnrollmentTransactionRequest
    ) -> HostEnrollmentTransactionOutcome:
        """Atomically CAS challenge, lock idempotency/uniqueness, and commit.

        A valid conflict or cross-subject refusal consumes the fresh challenge
        and returns its typed outcome. ``replayed`` is reserved for a challenge
        that was already consumed. An exception must roll back every write.
        """


def _new_principal_id() -> str:
    return "hp_" + secrets.token_urlsafe(24)


class HostEnrollmentCoordinator:
    """Verify fresh enrollment authority and invoke one atomic store seam."""

    def __init__(
        self,
        *,
        store: HostEnrollmentTransactionStore,
        idempotency_hmac_key: bytes,
        writers_enabled: bool = False,
        new_principal_id: Callable[[], str] = _new_principal_id,
    ) -> None:
        if not isinstance(idempotency_hmac_key, bytes) or len(idempotency_hmac_key) < 32:
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
        ):
            raise HostEnrollmentRefused

        try:
            canonical_intent = rfc8785.dumps(dict(enroll_intent))
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
        binding_fields = {**lookup_fields, "body_sha256": binding.body_sha256}
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
                _LOOKUP_DOMAIN, lookup_fields, raw_idempotency_key
            ),
            idempotency_binding_hash=self._keyed_hash(
                _BINDING_DOMAIN, binding_fields, raw_idempotency_key
            ),
            idempotency_expires_at=now + _IDEMPOTENCY_TTL_SECONDS,
            transaction_time=now,
            candidate_result=HostPrincipalResultV1(
                schema_version=SCHEMA_VERSION,
                host_principal_id=principal_id,
                generation=1,
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
        return "hmac-sha256:" + hmac.new(
            self._idempotency_hmac_key, message, hashlib.sha256
        ).hexdigest()

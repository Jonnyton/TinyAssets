"""Immutable D0 execution records and domain-separated M1 verification.

Signing and verification capabilities are constructed only through
package-private composition seams.  Their public operations derive the domain,
contract, key, and field classification from the concrete record type; callers
cannot supply a binder, issuer, key, domain override, or unbound-field escape.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, final

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .verified import Verified

CAPSULE_DOMAIN = "tinyassets.execution-capsule.v1"
GRANT_DOMAIN = "tinyassets.execution-grant.v1"
CANDIDATE_DOMAIN = "tinyassets.execution-candidate.v1"
TERMINAL_DOMAIN = "tinyassets.execution-terminal.v1"

_MAX_JSON_INTEGER = (1 << 53) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_CANDIDATE_STATES = frozenset(
    {
        "succeeded",
        "job_failed",
        "cancelled",
        "timed_out",
        "policy_rejected",
        "infrastructure_failed",
    }
)
_TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})


class RecordAuthorityError(ValueError):
    """A signed record failed its closed domain, schema, or signature contract."""


def _require_string(value: object, field_name: str) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{field_name} must be a nonempty canonical string")
    if any(ord(character) < 0x20 for character in value):
        raise ValueError(f"{field_name} contains a control character")


def _require_digest(value: object, field_name: str) -> None:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _require_integer(
    value: object,
    field_name: str,
    *,
    minimum: int = 0,
) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} has an invalid JSON integer type")
    if value < minimum or value > _MAX_JSON_INTEGER:
        raise ValueError(f"{field_name} is outside the JSON integer range")


def _require_timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not str or _RFC3339_UTC_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical RFC 3339 UTC timestamp") from exc
    return parsed


def _require_sorted_unique_strings(
    value: object,
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise TypeError(f"{field_name} must be an immutable string tuple")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    if any(not item or item.strip() != item for item in value):
        raise ValueError(f"{field_name} contains an invalid string")
    if tuple(sorted(set(value))) != value:
        raise ValueError(f"{field_name} must be sorted and duplicate-free")


@final
@dataclass(frozen=True, slots=True)
class BlobReferenceV1:
    """Canonical blob identity carried by a device-signed candidate."""

    ref: str
    sha256: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        _require_string(self.ref, "blob ref")
        _require_digest(self.sha256, "blob sha256")
        _require_integer(self.size_bytes, "blob size_bytes")
        _require_string(self.media_type, "blob media_type")


@final
@dataclass(frozen=True, slots=True)
class ExecutionCapsuleV1:
    signing_key_id: str
    owner_id: str
    audience_daemon_id: str
    job_id: str
    capsule_id: str
    attempt: int
    generation: int
    source_id: str
    source_digest: str
    policy_id: str
    policy_digest: str
    issued_at: str
    expires_at: str
    max_wall_time_seconds: int
    max_memory_bytes: int
    max_output_bytes: int
    schema_version: Literal["execution-capsule/v1"] = field(
        default="execution-capsule/v1",
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "signing_key_id",
            "owner_id",
            "audience_daemon_id",
            "job_id",
            "capsule_id",
            "source_id",
            "policy_id",
        ):
            _require_string(getattr(self, name), name)
        _require_integer(self.attempt, "attempt", minimum=1)
        _require_integer(self.generation, "generation", minimum=1)
        _require_digest(self.source_digest, "source_digest")
        _require_digest(self.policy_digest, "policy_digest")
        issued_at = _require_timestamp(self.issued_at, "issued_at")
        expires_at = _require_timestamp(self.expires_at, "expires_at")
        if issued_at >= expires_at:
            raise ValueError("capsule expiry must be after issuance")
        _require_integer(
            self.max_wall_time_seconds,
            "max_wall_time_seconds",
            minimum=1,
        )
        _require_integer(self.max_memory_bytes, "max_memory_bytes", minimum=1)
        _require_integer(self.max_output_bytes, "max_output_bytes", minimum=1)


@final
@dataclass(frozen=True, slots=True)
class ExecutionGrantV1:
    signing_key_id: str
    owner_id: str
    daemon_id: str
    job_id: str
    capsule_id: str
    capsule_digest: str
    lease_id: str
    generation: int
    fence: int
    expires_at: str
    capability_ceiling: tuple[str, ...]
    idempotency_key: str
    schema_version: Literal["execution-grant/v1"] = field(
        default="execution-grant/v1",
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "signing_key_id",
            "owner_id",
            "daemon_id",
            "job_id",
            "capsule_id",
            "lease_id",
            "idempotency_key",
        ):
            _require_string(getattr(self, name), name)
        _require_digest(self.capsule_digest, "capsule_digest")
        _require_integer(self.generation, "generation", minimum=1)
        _require_integer(self.fence, "fence", minimum=1)
        _require_timestamp(self.expires_at, "expires_at")
        _require_sorted_unique_strings(
            self.capability_ceiling,
            "capability_ceiling",
            allow_empty=False,
        )


@final
@dataclass(frozen=True, slots=True)
class ExecutionCandidateV1:
    device_key_id: str
    owner_id: str
    daemon_id: str
    job_id: str
    capsule_id: str
    capsule_digest: str
    lease_id: str
    generation: int
    fence: int
    result_digest: str
    blob_refs: tuple[BlobReferenceV1, ...]
    blob_set_digest: str
    status: str
    idempotency_key: str
    schema_version: Literal["execution-candidate/v1"] = field(
        default="execution-candidate/v1",
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "device_key_id",
            "owner_id",
            "daemon_id",
            "job_id",
            "capsule_id",
            "lease_id",
            "idempotency_key",
        ):
            _require_string(getattr(self, name), name)
        _require_digest(self.capsule_digest, "capsule_digest")
        _require_integer(self.generation, "generation", minimum=1)
        _require_integer(self.fence, "fence", minimum=1)
        _require_digest(self.result_digest, "result_digest")
        if type(self.blob_refs) is not tuple or any(
            type(blob_ref) is not BlobReferenceV1 for blob_ref in self.blob_refs
        ):
            raise TypeError("blob_refs must be an immutable BlobReferenceV1 tuple")
        if tuple(sorted(self.blob_refs, key=lambda item: item.ref)) != self.blob_refs:
            raise ValueError("blob_refs must use canonical ref order")
        if len({item.ref for item in self.blob_refs}) != len(self.blob_refs):
            raise ValueError("blob_refs must not contain duplicate refs")
        _require_digest(self.blob_set_digest, "blob_set_digest")
        if type(self.status) is not str or self.status not in _CANDIDATE_STATES:
            raise ValueError("candidate status is invalid")


@final
@dataclass(frozen=True, slots=True)
class ExecutionTerminalV1:
    signing_key_id: str
    owner_id: str
    daemon_id: str
    job_id: str
    capsule_id: str
    capsule_digest: str
    lease_id: str
    generation: int
    fence: int
    accepted_candidate_digest: str
    accepted_result_digest: str
    accepted_blob_set_digest: str
    terminal_state: str
    completed_at: str
    idempotency_key: str
    schema_version: Literal["execution-terminal/v1"] = field(
        default="execution-terminal/v1",
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "signing_key_id",
            "owner_id",
            "daemon_id",
            "job_id",
            "capsule_id",
            "lease_id",
            "idempotency_key",
        ):
            _require_string(getattr(self, name), name)
        for name in (
            "capsule_digest",
            "accepted_candidate_digest",
            "accepted_result_digest",
            "accepted_blob_set_digest",
        ):
            _require_digest(getattr(self, name), name)
        _require_integer(self.generation, "generation", minimum=1)
        _require_integer(self.fence, "fence", minimum=1)
        if type(self.terminal_state) is not str or self.terminal_state not in _TERMINAL_STATES:
            raise ValueError("terminal_state is invalid")
        _require_timestamp(self.completed_at, "completed_at")


ExecutionRecord: TypeAlias = (
    ExecutionCapsuleV1 | ExecutionGrantV1 | ExecutionCandidateV1 | ExecutionTerminalV1
)


@final
@dataclass(frozen=True, slots=True)
class SignedExecutionRecord:
    """Canonical payload and its domain-separated Ed25519 signature."""

    domain: str
    canonical_payload: bytes
    signature_b64: str

    def __post_init__(self) -> None:
        if type(self.domain) is not str or not self.domain or "\0" in self.domain:
            raise TypeError("signed record domain is malformed")
        if type(self.canonical_payload) is not bytes or not self.canonical_payload:
            raise TypeError("signed record canonical payload is malformed")
        if type(self.signature_b64) is not str or not self.signature_b64:
            raise TypeError("signed record signature is malformed")


class FieldDisposition(StrEnum):
    ROW_BOUND = "row_bound"
    SPECIALIZED_VALIDATED = "specialized_validated"
    INERT = "inert"


@final
@dataclass(frozen=True, slots=True)
class SignedRecordContract:
    domain: str
    schema_version: str
    record_type: type[ExecutionRecord]
    key_field: str
    fields: Mapping[str, FieldDisposition]

    def __post_init__(self) -> None:
        if type(self.fields) is not MappingProxyType or not self.fields:
            raise TypeError("record contract fields must be a frozen mapping")
        if frozenset(self.fields.values()) - frozenset(FieldDisposition):
            raise TypeError("record contract contains an unclassified field")


def _frozen_fields(
    *,
    row_bound: tuple[str, ...],
    specialized: tuple[str, ...],
    inert: Mapping[str, str] | None = None,
) -> Mapping[str, FieldDisposition]:
    classified: dict[str, FieldDisposition] = {}
    classified.update({name: FieldDisposition.ROW_BOUND for name in row_bound})
    classified.update({name: FieldDisposition.SPECIALIZED_VALIDATED for name in specialized})
    for name, reason in (inert or {}).items():
        _require_string(reason, f"inert reason for {name}")
        classified[name] = FieldDisposition.INERT
    return MappingProxyType(classified)


_CONTRACTS = MappingProxyType(
    {
        CAPSULE_DOMAIN: SignedRecordContract(
            domain=CAPSULE_DOMAIN,
            schema_version="execution-capsule/v1",
            record_type=ExecutionCapsuleV1,
            key_field="signing_key_id",
            fields=_frozen_fields(
                row_bound=(
                    "owner_id",
                    "audience_daemon_id",
                    "job_id",
                    "capsule_id",
                    "attempt",
                    "generation",
                    "source_id",
                    "source_digest",
                    "policy_id",
                    "policy_digest",
                    "issued_at",
                    "expires_at",
                    "max_wall_time_seconds",
                    "max_memory_bytes",
                    "max_output_bytes",
                ),
                specialized=("schema_version", "signing_key_id"),
            ),
        ),
        GRANT_DOMAIN: SignedRecordContract(
            domain=GRANT_DOMAIN,
            schema_version="execution-grant/v1",
            record_type=ExecutionGrantV1,
            key_field="signing_key_id",
            fields=_frozen_fields(
                row_bound=(
                    "owner_id",
                    "daemon_id",
                    "job_id",
                    "capsule_id",
                    "capsule_digest",
                    "lease_id",
                    "generation",
                    "fence",
                    "expires_at",
                    "capability_ceiling",
                    "idempotency_key",
                ),
                specialized=("schema_version", "signing_key_id"),
            ),
        ),
        CANDIDATE_DOMAIN: SignedRecordContract(
            domain=CANDIDATE_DOMAIN,
            schema_version="execution-candidate/v1",
            record_type=ExecutionCandidateV1,
            key_field="device_key_id",
            fields=_frozen_fields(
                row_bound=(
                    "owner_id",
                    "daemon_id",
                    "job_id",
                    "capsule_id",
                    "capsule_digest",
                    "lease_id",
                    "generation",
                    "fence",
                    "result_digest",
                    "blob_refs",
                    "blob_set_digest",
                    "status",
                    "idempotency_key",
                ),
                specialized=("schema_version", "device_key_id"),
            ),
        ),
        TERMINAL_DOMAIN: SignedRecordContract(
            domain=TERMINAL_DOMAIN,
            schema_version="execution-terminal/v1",
            record_type=ExecutionTerminalV1,
            key_field="signing_key_id",
            fields=_frozen_fields(
                row_bound=(
                    "owner_id",
                    "daemon_id",
                    "job_id",
                    "capsule_id",
                    "capsule_digest",
                    "lease_id",
                    "generation",
                    "fence",
                    "accepted_candidate_digest",
                    "accepted_result_digest",
                    "accepted_blob_set_digest",
                    "terminal_state",
                    "completed_at",
                    "idempotency_key",
                ),
                specialized=("schema_version", "signing_key_id"),
            ),
        ),
    }
)
_DOMAIN_BY_TYPE = MappingProxyType(
    {contract.record_type: domain for domain, contract in _CONTRACTS.items()}
)


def record_contract_for(record_type: type[ExecutionRecord]) -> SignedRecordContract:
    """Return the immutable source-defined contract for a concrete record type."""

    domain = _DOMAIN_BY_TYPE.get(record_type)
    if domain is None:
        raise RecordAuthorityError("record type has no immutable domain contract")
    return _CONTRACTS[domain]


def _blob_payload(blob_ref: BlobReferenceV1) -> dict[str, object]:
    return {
        "ref": blob_ref.ref,
        "sha256": blob_ref.sha256,
        "size_bytes": blob_ref.size_bytes,
        "media_type": blob_ref.media_type,
    }


def _payload(record: ExecutionRecord) -> dict[str, object]:
    if type(record) is ExecutionCapsuleV1:
        return {
            "schema_version": record.schema_version,
            "signing_key_id": record.signing_key_id,
            "owner_id": record.owner_id,
            "audience_daemon_id": record.audience_daemon_id,
            "job_id": record.job_id,
            "capsule_id": record.capsule_id,
            "attempt": record.attempt,
            "generation": record.generation,
            "source_id": record.source_id,
            "source_digest": record.source_digest,
            "policy_id": record.policy_id,
            "policy_digest": record.policy_digest,
            "issued_at": record.issued_at,
            "expires_at": record.expires_at,
            "max_wall_time_seconds": record.max_wall_time_seconds,
            "max_memory_bytes": record.max_memory_bytes,
            "max_output_bytes": record.max_output_bytes,
        }
    if type(record) is ExecutionGrantV1:
        return {
            "schema_version": record.schema_version,
            "signing_key_id": record.signing_key_id,
            "owner_id": record.owner_id,
            "daemon_id": record.daemon_id,
            "job_id": record.job_id,
            "capsule_id": record.capsule_id,
            "capsule_digest": record.capsule_digest,
            "lease_id": record.lease_id,
            "generation": record.generation,
            "fence": record.fence,
            "expires_at": record.expires_at,
            "capability_ceiling": list(record.capability_ceiling),
            "idempotency_key": record.idempotency_key,
        }
    if type(record) is ExecutionCandidateV1:
        return {
            "schema_version": record.schema_version,
            "device_key_id": record.device_key_id,
            "owner_id": record.owner_id,
            "daemon_id": record.daemon_id,
            "job_id": record.job_id,
            "capsule_id": record.capsule_id,
            "capsule_digest": record.capsule_digest,
            "lease_id": record.lease_id,
            "generation": record.generation,
            "fence": record.fence,
            "result_digest": record.result_digest,
            "blob_refs": [_blob_payload(item) for item in record.blob_refs],
            "blob_set_digest": record.blob_set_digest,
            "status": record.status,
            "idempotency_key": record.idempotency_key,
        }
    if type(record) is ExecutionTerminalV1:
        return {
            "schema_version": record.schema_version,
            "signing_key_id": record.signing_key_id,
            "owner_id": record.owner_id,
            "daemon_id": record.daemon_id,
            "job_id": record.job_id,
            "capsule_id": record.capsule_id,
            "capsule_digest": record.capsule_digest,
            "lease_id": record.lease_id,
            "generation": record.generation,
            "fence": record.fence,
            "accepted_candidate_digest": record.accepted_candidate_digest,
            "accepted_result_digest": record.accepted_result_digest,
            "accepted_blob_set_digest": record.accepted_blob_set_digest,
            "terminal_state": record.terminal_state,
            "completed_at": record.completed_at,
            "idempotency_key": record.idempotency_key,
        }
    raise RecordAuthorityError("record type has no immutable domain contract")


def canonical_payload_bytes(record: ExecutionRecord) -> bytes:
    """Return RFC 8785 canonical bytes for a final-shaped record."""

    try:
        return rfc8785.dumps(_payload(record))
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise RecordAuthorityError("record payload is not canonical JSON") from exc


def _signature_preimage(domain: str, canonical_payload: bytes) -> bytes:
    return (domain + "\0").encode("utf-8") + hashlib.sha256(canonical_payload).digest()


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field {key!r}")
        value[key] = item
    return value


def _require_exact_fields(
    payload: object,
    contract: SignedRecordContract,
) -> dict[str, object]:
    if type(payload) is not dict:
        raise RecordAuthorityError("signed record payload must be a JSON object")
    if any(type(name) is not str for name in payload):
        raise RecordAuthorityError("signed record field names must be strings")
    expected = frozenset(contract.fields)
    actual = frozenset(payload)
    if actual != expected:
        raise RecordAuthorityError("signed record fields differ from the immutable domain contract")
    if payload.get("schema_version") != contract.schema_version:
        raise RecordAuthorityError("signed record schema version is invalid")
    return payload


def _require_raw_type(
    payload: Mapping[str, object],
    name: str,
    expected_type: type,
) -> None:
    if type(payload[name]) is not expected_type:
        raise RecordAuthorityError(f"signed record field {name!r} has an invalid JSON type")


def _decode_blob_refs(value: object) -> tuple[BlobReferenceV1, ...]:
    if type(value) is not list:
        raise RecordAuthorityError("signed record field 'blob_refs' has an invalid JSON type")
    decoded: list[BlobReferenceV1] = []
    for item in value:
        if type(item) is not dict or frozenset(item) != {
            "ref",
            "sha256",
            "size_bytes",
            "media_type",
        }:
            raise RecordAuthorityError("candidate blob reference fields are invalid")
        for name, expected_type in (
            ("ref", str),
            ("sha256", str),
            ("size_bytes", int),
            ("media_type", str),
        ):
            if type(item[name]) is not expected_type:
                raise RecordAuthorityError(
                    f"candidate blob field {name!r} has an invalid JSON type"
                )
        try:
            decoded.append(BlobReferenceV1(**item))
        except (TypeError, ValueError) as exc:
            raise RecordAuthorityError("candidate blob reference is invalid") from exc
    return tuple(decoded)


def _decode_record(
    contract: SignedRecordContract,
    raw_payload: object,
) -> ExecutionRecord:
    payload = _require_exact_fields(raw_payload, contract)
    try:
        if contract.record_type is ExecutionCapsuleV1:
            string_fields = frozenset(contract.fields) - {
                "attempt",
                "generation",
                "max_wall_time_seconds",
                "max_memory_bytes",
                "max_output_bytes",
            }
            for name in string_fields:
                _require_raw_type(payload, name, str)
            for name in frozenset(contract.fields) - string_fields:
                _require_raw_type(payload, name, int)
            values = dict(payload)
            values.pop("schema_version")
            return ExecutionCapsuleV1(**values)
        if contract.record_type is ExecutionGrantV1:
            for name in frozenset(contract.fields) - {
                "generation",
                "fence",
                "capability_ceiling",
            }:
                _require_raw_type(payload, name, str)
            _require_raw_type(payload, "generation", int)
            _require_raw_type(payload, "fence", int)
            _require_raw_type(payload, "capability_ceiling", list)
            if any(type(item) is not str for item in payload["capability_ceiling"]):
                raise RecordAuthorityError("capability_ceiling has an invalid JSON type")
            values = dict(payload)
            values.pop("schema_version")
            values["capability_ceiling"] = tuple(values["capability_ceiling"])
            return ExecutionGrantV1(**values)
        if contract.record_type is ExecutionCandidateV1:
            for name in frozenset(contract.fields) - {
                "generation",
                "fence",
                "blob_refs",
            }:
                _require_raw_type(payload, name, str)
            _require_raw_type(payload, "generation", int)
            _require_raw_type(payload, "fence", int)
            values = dict(payload)
            values.pop("schema_version")
            values["blob_refs"] = _decode_blob_refs(values["blob_refs"])
            return ExecutionCandidateV1(**values)
        if contract.record_type is ExecutionTerminalV1:
            for name in frozenset(contract.fields) - {"generation", "fence"}:
                _require_raw_type(payload, name, str)
            _require_raw_type(payload, "generation", int)
            _require_raw_type(payload, "fence", int)
            values = dict(payload)
            values.pop("schema_version")
            return ExecutionTerminalV1(**values)
    except RecordAuthorityError:
        raise
    except TypeError as exc:
        raise RecordAuthorityError("signed record contains an invalid JSON type") from exc
    except ValueError as exc:
        message = str(exc)
        if "integer" in message:
            raise RecordAuthorityError(message) from exc
        raise RecordAuthorityError(f"signed record validation failed: {message}") from exc
    raise RecordAuthorityError("signed record domain contract is unavailable")


def _raw_public_key(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _authority_capabilities(mint_m1, auth_checker):
    @final
    class RecordSigner:
        """Purpose-bound Ed25519 signing capability for a composition root."""

        __slots__ = ("__keys",)

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise TypeError("RecordSigner is constructed only by an authority root")

        def sign(self, record: ExecutionRecord) -> SignedExecutionRecord:
            domain = _DOMAIN_BY_TYPE.get(type(record))
            if domain is None:
                raise RecordAuthorityError("record type has no immutable domain contract")
            key_entry = self.__keys.get(domain)
            if key_entry is None:
                raise RecordAuthorityError("record signing domain is unavailable")
            expected_key_id, private_key = key_entry
            contract = _CONTRACTS[domain]
            if getattr(record, contract.key_field) != expected_key_id:
                raise RecordAuthorityError(
                    "record key identity does not match the signing capability"
                )
            canonical = canonical_payload_bytes(record)
            signature = private_key.sign(_signature_preimage(domain, canonical))
            return SignedExecutionRecord(
                domain=domain,
                canonical_payload=canonical,
                signature_b64=base64.b64encode(signature).decode("ascii"),
            )

    @final
    class RecordVerifier:
        """Purpose-bound verifier whose evidence is exact-instance scoped.

        A verifier created for one authority root cannot issue M1 evidence that
        another root accepts, even when both instances are package-authentic.
        """

        __slots__ = ("__issuer", "__keys", "__verifier_id")

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise TypeError("RecordVerifier is constructed only by an authority root")

        def verify(
            self,
            signed: SignedExecutionRecord,
            *,
            verified_at: int,
        ) -> Verified[ExecutionRecord]:
            if type(signed) is not SignedExecutionRecord:
                raise RecordAuthorityError("signed record carrier is malformed")
            contract = _CONTRACTS.get(signed.domain)
            key_entry = self.__keys.get(signed.domain)
            if contract is None or key_entry is None:
                raise RecordAuthorityError("signed record domain is unknown")
            expected_key_id, public_key = key_entry
            try:
                signature = base64.b64decode(
                    signed.signature_b64,
                    validate=True,
                )
                public_key.verify(
                    signature,
                    _signature_preimage(
                        signed.domain,
                        signed.canonical_payload,
                    ),
                )
            except (InvalidSignature, ValueError, binascii.Error) as exc:
                raise RecordAuthorityError("signed record signature is invalid") from exc
            try:
                payload = json.loads(
                    signed.canonical_payload,
                    object_pairs_hook=_reject_duplicate_members,
                )
                canonical = rfc8785.dumps(payload)
            except rfc8785.IntegerDomainError as exc:
                raise RecordAuthorityError(
                    "signed record integer is outside the JSON integer range"
                ) from exc
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                TypeError,
                rfc8785.CanonicalizationError,
            ) as exc:
                raise RecordAuthorityError("signed record JSON is malformed") from exc
            if canonical != signed.canonical_payload:
                raise RecordAuthorityError("signed record payload is not RFC 8785 canonical JSON")
            record = _decode_record(contract, payload)
            if getattr(record, contract.key_field) != expected_key_id:
                raise RecordAuthorityError(
                    "signed record key identity does not match the trust set"
                )
            digest = hashlib.sha256(canonical).hexdigest()
            evidence = mint_m1(
                record,
                domain=signed.domain,
                evidence_digest=digest,
                verifier_id=self.__verifier_id,
                verified_at=verified_at,
                issuer=self.__issuer,
            )
            return self.require_authentic(evidence)

        def require_authentic(
            self,
            evidence: Verified[ExecutionRecord],
        ) -> Verified[ExecutionRecord]:
            """Reject M1 evidence issued by any other authority verifier."""

            return auth_checker(
                evidence,
                expected_mechanism="m1",
                expected_issuer=self.__issuer,
            )

    def create_signer(
        keys: Mapping[str, tuple[str, Ed25519PrivateKey]],
    ) -> RecordSigner:
        if not isinstance(keys, Mapping) or not keys:
            raise TypeError("authority signer keys must be a nonempty mapping")
        copied: dict[str, tuple[str, Ed25519PrivateKey]] = {}
        purpose_by_public_key: dict[bytes, str] = {}
        for domain, entry in keys.items():
            if domain not in _CONTRACTS:
                raise TypeError("authority signer contains an unknown domain")
            if (
                type(entry) is not tuple
                or len(entry) != 2
                or type(entry[0]) is not str
                or not entry[0]
                or not isinstance(entry[1], Ed25519PrivateKey)
            ):
                raise TypeError("authority signer key entry is malformed")
            public_key = _raw_public_key(entry[1].public_key())
            prior_domain = purpose_by_public_key.get(public_key)
            if prior_domain is not None and prior_domain != domain:
                raise TypeError("Ed25519 public key reuse across purpose domains is forbidden")
            purpose_by_public_key[public_key] = domain
            copied[domain] = entry
        instance = object.__new__(RecordSigner)
        object.__setattr__(instance, "_RecordSigner__keys", MappingProxyType(copied))
        return instance

    def create_verifier(
        keys: Mapping[str, tuple[str, Ed25519PublicKey]],
        *,
        verifier_id: str,
    ) -> RecordVerifier:
        if not isinstance(keys, Mapping) or not keys:
            raise TypeError("authority verifier keys must be a nonempty mapping")
        _require_string(verifier_id, "verifier_id")
        copied: dict[str, tuple[str, Ed25519PublicKey]] = {}
        purpose_by_public_key: dict[bytes, str] = {}
        for domain, entry in keys.items():
            if domain not in _CONTRACTS:
                raise TypeError("authority verifier contains an unknown domain")
            if (
                type(entry) is not tuple
                or len(entry) != 2
                or type(entry[0]) is not str
                or not entry[0]
                or not isinstance(entry[1], Ed25519PublicKey)
            ):
                raise TypeError("authority verifier key entry is malformed")
            public_key = _raw_public_key(entry[1])
            prior_domain = purpose_by_public_key.get(public_key)
            if prior_domain is not None and prior_domain != domain:
                raise TypeError("Ed25519 public key reuse across purpose domains is forbidden")
            purpose_by_public_key[public_key] = domain
            copied[domain] = entry
        instance = object.__new__(RecordVerifier)
        object.__setattr__(
            instance,
            "_RecordVerifier__keys",
            MappingProxyType(copied),
        )
        object.__setattr__(
            instance,
            "_RecordVerifier__verifier_id",
            verifier_id,
        )
        object.__setattr__(
            instance,
            "_RecordVerifier__issuer",
            object(),
        )
        return instance

    return RecordSigner, RecordVerifier, create_signer, create_verifier


_VERIFIED_CAPABILITIES_INSTALLED = False


def _install_verified_capabilities(mint_m1, auth_checker) -> None:
    global RecordSigner
    global RecordVerifier
    global _VERIFIED_CAPABILITIES_INSTALLED
    global _create_record_signer
    global _create_record_verifier

    if _VERIFIED_CAPABILITIES_INSTALLED:
        raise RuntimeError("record verification capabilities are already installed")
    (
        RecordSigner,
        RecordVerifier,
        _create_record_signer,
        _create_record_verifier,
    ) = _authority_capabilities(mint_m1, auth_checker)
    _VERIFIED_CAPABILITIES_INSTALLED = True


__all__ = [
    "BlobReferenceV1",
    "CANDIDATE_DOMAIN",
    "CAPSULE_DOMAIN",
    "ExecutionCandidateV1",
    "ExecutionCapsuleV1",
    "ExecutionGrantV1",
    "ExecutionRecord",
    "ExecutionTerminalV1",
    "FieldDisposition",
    "GRANT_DOMAIN",
    "RecordAuthorityError",
    "RecordSigner",
    "RecordVerifier",
    "SignedExecutionRecord",
    "SignedRecordContract",
    "TERMINAL_DOMAIN",
    "canonical_payload_bytes",
    "record_contract_for",
]

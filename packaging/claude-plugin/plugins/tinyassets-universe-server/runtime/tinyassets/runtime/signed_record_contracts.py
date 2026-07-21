"""Source-defined catalog of signed-record authority contracts."""

from __future__ import annotations

import base64
import binascii
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from nacl.signing import VerifyKey

from tinyassets.runtime.execution_capsule import hash_canonical_jcs
from tinyassets.runtime.signed_record_contract import (
    FieldDisposition,
    JSONValue,
    SignedFieldRule,
    SignedRecordContract,
    SignedRecordContractRegistry,
)

LEASE_GRANT_DOMAIN_SEPARATOR = b"tinyassets.lease-grant.v2\0"
COMPLETION_ATTESTATION_DOMAIN_SEPARATOR = (
    b"tinyassets.completion-attestation.v1\0"
)
_LEASE_GRANT_SCHEMA_VERSION = "lease-grant/v2"
_COMPLETION_ATTESTATION_SCHEMA_VERSION = "completion-attestation/v1"
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class LeaseGrantValidationContext:
    device_key_registry: object


@dataclass(frozen=True)
class CompletionAttestationValidationContext:
    stored_receipt: Mapping[str, JSONValue] | None
    row_status: object
    accepted_result_id: object
    accepted_result_sha256: object

    def __post_init__(self) -> None:
        if isinstance(self.stored_receipt, Mapping):
            object.__setattr__(
                self,
                "stored_receipt",
                MappingProxyType(dict(self.stored_receipt)),
            )


def _parse_timestamp(value: object) -> None:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("stored lease timestamp is corrupt")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("stored lease timestamp is corrupt") from exc


def _validate_lease_grant(
    payload: Mapping[str, JSONValue],
    context: object,
) -> None:
    if not isinstance(context, LeaseGrantValidationContext):
        raise ValueError("lease grant validation context is missing or invalid")
    required_strings = frozenset(payload) - {
        "device_key_epoch",
        "fence",
        "repo_mode",
    }
    if any(
        type(payload.get(field)) is not str or not payload[field]
        for field in required_strings
    ):
        raise ValueError("platform lease grant is missing or malformed")
    if (
        payload["schema_version"] != _LEASE_GRANT_SCHEMA_VERSION
        or payload["device_key_epoch"] < 1
        or payload["fence"] < 1
    ):
        raise ValueError("platform lease grant is missing or malformed")
    _parse_timestamp(payload["issued_at"])
    _parse_timestamp(payload["expires_at"])

    capability_class = payload["capability_class"]
    repo_mode = payload["repo_mode"]
    if capability_class not in {"repo", "source_exec"}:
        raise ValueError("platform lease grant is missing or malformed")
    if capability_class == "repo":
        if repo_mode not in {"repo_read", "repo_exec", "coding"}:
            raise ValueError("platform lease grant is missing or malformed")
    elif repo_mode is not None:
        raise ValueError("platform lease grant is missing or malformed")
    if not _SHA256_RE.fullmatch(payload["runner_policy_sha256"]):
        raise ValueError("platform lease grant is missing or malformed")
    if not _OCI_DIGEST_RE.fullmatch(payload["image_digest"]):
        raise ValueError("platform lease grant is missing or malformed")

    try:
        raw_key = base64.b64decode(payload["device_verify_key"], validate=True)
        grant_verify_key = VerifyKey(raw_key)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise ValueError(
            "platform lease grant has a malformed device verification key"
        ) from exc
    resolver = getattr(context.device_key_registry, "resolve_device_key", None)
    if not callable(resolver):
        raise ValueError("platform device-key registry is unavailable")
    device_key_id = payload["device_key_id"]
    registered = resolver(device_key_id)
    if registered is None or getattr(registered, "device_key_id", None) != device_key_id:
        raise ValueError("stored candidate device key is not registered")
    if (
        getattr(registered, "credential_epoch", None) != payload["device_key_epoch"]
        or getattr(registered, "active", None) is not True
    ):
        raise ValueError("stored candidate device key is inactive or has changed epoch")
    registered_key = getattr(registered, "verify_key", None)
    if (
        not isinstance(registered_key, VerifyKey)
        or not hmac.compare_digest(bytes(registered_key), bytes(grant_verify_key))
    ):
        raise ValueError(
            "device registry does not match the grant's signed verification key"
        )


def _validate_completion_attestation(
    payload: Mapping[str, JSONValue],
    context: object,
) -> None:
    if not isinstance(context, CompletionAttestationValidationContext):
        raise ValueError(
            "completion attestation validation context is missing or invalid"
        )
    required_strings = frozenset(payload) - {"fence", "owner_user_id"}
    if any(
        type(payload.get(field)) is not str or not payload[field]
        for field in required_strings
    ):
        raise ValueError("platform completion attestation is missing or malformed")
    if (
        payload["schema_version"] != _COMPLETION_ATTESTATION_SCHEMA_VERSION
        or payload["fence"] < 1
        or payload["status"] not in _TERMINAL_STATUSES
        or not _SHA256_RE.fullmatch(payload["capsule_sha256"])
        or not _SHA256_RE.fullmatch(payload["result_sha256"])
        or payload["result_id"] != f"result:{payload['result_sha256']}"
    ):
        raise ValueError("platform completion attestation is missing or malformed")
    _parse_timestamp(payload["completed_at"])
    receipt_request = {
        "job_id": payload["job_id"],
        "daemon_id": payload["daemon_id"],
        "lease_id": payload["lease_id"],
        "fence": payload["fence"],
        "capsule_sha256": payload["capsule_sha256"],
        "result_sha256": payload["result_sha256"],
    }
    expected_receipt_id = f"completion:{hash_canonical_jcs(receipt_request).hex()}"
    if payload["receipt_id"] != expected_receipt_id:
        raise ValueError("platform completion attestation receipt id is invalid")
    receipt = {
        "receipt_id": payload["receipt_id"],
        "job_id": payload["job_id"],
        "status": payload["status"],
        "accepted_result_sha256": payload["result_sha256"],
        "completed_at": payload["completed_at"],
    }
    if context.stored_receipt != receipt:
        raise ValueError("durable completion receipt does not match signed attestation")
    if context.row_status in _TERMINAL_STATUSES:
        if context.row_status != payload["status"]:
            raise ValueError(
                "terminal row status does not match signed attestation"
            )
    elif context.row_status != "leased":
        raise ValueError("terminal row reset is inconsistent with signed attestation")
    for field, row_value, expected_value in (
        ("accepted_result_id", context.accepted_result_id, payload["result_id"]),
        (
            "accepted_result_sha256",
            context.accepted_result_sha256,
            payload["result_sha256"],
        ),
    ):
        if row_value is not None and row_value != expected_value:
            raise ValueError(
                f"terminal row {field} does not match signed attestation"
            )


def _row_bound(*json_types: type) -> SignedFieldRule:
    return SignedFieldRule(FieldDisposition.ROW_BOUND, json_types)


def _specialized(*json_types: type) -> SignedFieldRule:
    return SignedFieldRule(FieldDisposition.SPECIALIZED_VALIDATED, json_types)


LEASE_GRANT_V2_CONTRACT = SignedRecordContract(
    name="lease-grant-v2",
    domain_separator=LEASE_GRANT_DOMAIN_SEPARATOR,
    fields={
        "schema_version": _specialized(str),
        "job_id": _row_bound(str),
        "owner_user_id": _row_bound(str),
        "daemon_id": _row_bound(str),
        "device_key_id": _specialized(str),
        "device_verify_key": _specialized(str),
        "device_key_epoch": _specialized(int),
        "lease_id": _row_bound(str),
        "fence": _row_bound(int),
        "issued_at": _row_bound(str),
        "expires_at": _row_bound(str),
        "capsule_id": _row_bound(str),
        "capsule_sha256": _row_bound(str),
        "capability_class": _specialized(str),
        "repo_mode": _specialized(str, type(None)),
        "runner_policy_sha256": _specialized(str),
        "image_digest": _specialized(str),
    },
    specialized_validator=_validate_lease_grant,
)

COMPLETION_ATTESTATION_V1_CONTRACT = SignedRecordContract(
    name="completion-attestation-v1",
    domain_separator=COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
    fields={
        "schema_version": _specialized(str),
        "receipt_id": _specialized(str),
        "job_id": _row_bound(str),
        "owner_user_id": SignedFieldRule(
            FieldDisposition.INERT,
            (str,),
            "audit metadata only; forbidden from authorizing replay or selecting resources",
        ),
        "daemon_id": _row_bound(str),
        "lease_id": _row_bound(str),
        "fence": _row_bound(int),
        "capsule_id": _row_bound(str),
        "capsule_sha256": _row_bound(str),
        "result_id": _row_bound(str),
        "result_sha256": _row_bound(str),
        "status": _specialized(str),
        "completed_at": _specialized(str),
    },
    specialized_validator=_validate_completion_attestation,
)

SIGNED_RECORD_CONTRACTS: Mapping[bytes, SignedRecordContract] = (
    SignedRecordContractRegistry.freeze(
        LEASE_GRANT_V2_CONTRACT,
        COMPLETION_ATTESTATION_V1_CONTRACT,
    )
)

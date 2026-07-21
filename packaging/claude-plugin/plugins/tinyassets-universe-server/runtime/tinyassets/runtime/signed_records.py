"""Shared M1 verification for platform-signed authority records.

``Verified`` custody makes row-only DML unable to mint authenticated authority
and makes accidental or casual reconstruction conspicuous. It is not proof
against arbitrary in-process Python execution: such code can bypass Python
object privacy and can also reach the signing and verification key objects.
That S0 boundary is enforced outside this module.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic, TypeVar, final

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from tinyassets.runtime.execution_capsule import (
    CapsuleCanonicalizationError,
    canonicalize_jcs,
    hash_canonical_jcs,
    sign_domain_separated_ed25519,
    verify_domain_separated_ed25519,
)
<<<<<<< HEAD
from tinyassets.runtime.signed_record_contracts import SIGNED_RECORD_CONTRACTS
=======
<<<<<<< HEAD
from tinyassets.runtime.signed_record_contracts import SIGNED_RECORD_CONTRACTS
=======
>>>>>>> feat/patch-loop-leasestore-fix2
>>>>>>> feat/m1-unbound-denylist


class StoredStateCorruptError(RuntimeError):
    """Persisted authority state failed cryptographic or binding validation."""


T = TypeVar("T")


<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> feat/m1-unbound-denylist
def _json_type_strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _json_type_strict_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_type_strict_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)
<<<<<<< HEAD
=======
=======
@dataclass(frozen=True)
class SignedFieldContract:
    """Immutable accounting for every field signed under one domain."""

    row_bound_fields: frozenset[str]
    specialized_fields: frozenset[str]
    inert_fields: frozenset[str]

    def __post_init__(self) -> None:
        partitions = (
            self.row_bound_fields,
            self.specialized_fields,
            self.inert_fields,
        )
        if any(
            type(partition) is not frozenset
            or any(type(field) is not str or not field for field in partition)
            for partition in partitions
        ):
            raise TypeError("signed field contract partitions must be frozensets of names")
        if (
            self.row_bound_fields & self.specialized_fields
            or self.row_bound_fields & self.inert_fields
            or self.specialized_fields & self.inert_fields
        ):
            raise ValueError("signed field contract partitions must not overlap")
        if not self.fields:
            raise ValueError("signed field contract must classify at least one field")

    @property
    def fields(self) -> frozenset[str]:
        return self.row_bound_fields | self.specialized_fields | self.inert_fields


LEASE_GRANT_DOMAIN_SEPARATOR = b"tinyassets.lease-grant.v2\0"
COMPLETION_ATTESTATION_DOMAIN_SEPARATOR = b"tinyassets.completion-attestation.v1\0"

DEFAULT_SIGNED_FIELD_CONTRACTS = MappingProxyType(
    {
        LEASE_GRANT_DOMAIN_SEPARATOR: SignedFieldContract(
            row_bound_fields=frozenset(
                {
                    "job_id",
                    "daemon_id",
                    "lease_id",
                    "fence",
                    "issued_at",
                    "expires_at",
                    "capsule_id",
                    "capsule_sha256",
                }
            ),
            specialized_fields=frozenset(
                {
                    "schema_version",
                    "owner_user_id",
                    "device_key_id",
                    "device_verify_key",
                    "device_key_epoch",
                    "capability_class",
                    "repo_mode",
                    "runner_policy_sha256",
                    "image_digest",
                }
            ),
            inert_fields=frozenset(),
        ),
        COMPLETION_ATTESTATION_DOMAIN_SEPARATOR: SignedFieldContract(
            row_bound_fields=frozenset({"job_id"}),
            specialized_fields=frozenset(
                {
                    "schema_version",
                    "receipt_id",
                    "owner_user_id",
                    "daemon_id",
                    "lease_id",
                    "fence",
                    "capsule_id",
                    "capsule_sha256",
                    "result_id",
                    "result_sha256",
                    "status",
                    "completed_at",
                }
            ),
            inert_fields=frozenset(),
        ),
    }
)
>>>>>>> feat/patch-loop-leasestore-fix2
>>>>>>> feat/m1-unbound-denylist


def _verified_contract():
    construction_token = object()

    @final
    @dataclass(frozen=True, init=False)
    class Verified(Generic[T]):
        """Frozen DML-proof wrapper minted after record verification."""

        payload: T

        def __init__(self, payload: T, *, _token: object | None = None) -> None:
            if _token is not construction_token:
                raise TypeError("Verified can only be constructed by RecordVerifier")
            object.__setattr__(self, "payload", payload)

        def __init_subclass__(cls, **kwargs: Any) -> None:
            raise TypeError("Verified cannot be subclassed")

        def __copy__(self):
            raise TypeError("Verified proof wrappers cannot be copied")

        def __deepcopy__(self, memo: dict[int, Any]):
            raise TypeError("Verified proof wrappers cannot be copied")

        def __reduce__(self):
            raise TypeError("Verified proof wrappers cannot be pickled")

        def __reduce_ex__(self, protocol: int):
            raise TypeError("Verified proof wrappers cannot be pickled")

    class RecordVerifier:
        """Verify one platform key's domain-separated signed JSON records."""

        __slots__ = ("__verify_key",)

        def __init__(self, verify_key: VerifyKey) -> None:
            if not isinstance(verify_key, VerifyKey):
                raise TypeError("verify_key must be an Ed25519 VerifyKey")
            self.__verify_key = verify_key

        def verify(
            self,
            domain: bytes,
            signed_json: str,
            signature: str,
            row_bindings: Mapping[str, Any],
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> feat/m1-unbound-denylist
            *,
            validation_context: object | None = None,
        ) -> Verified[Mapping[str, Any]]:
            if type(domain) is not bytes or not domain:
                raise StoredStateCorruptError("signed record domain is malformed")
            contract = SIGNED_RECORD_CONTRACTS.get(domain)
<<<<<<< HEAD
=======
=======
        ) -> Verified[Mapping[str, Any]]:
            if type(domain) is not bytes or not domain:
                raise StoredStateCorruptError("signed record domain is malformed")
            contract = DEFAULT_SIGNED_FIELD_CONTRACTS.get(domain)
>>>>>>> feat/patch-loop-leasestore-fix2
>>>>>>> feat/m1-unbound-denylist
            if contract is None:
                raise StoredStateCorruptError(
                    "signed record domain has no immutable field contract"
                )
            try:
                if type(signed_json) is not str or type(signature) is not str:
                    raise TypeError
                payload = json.loads(
                    signed_json,
                    object_pairs_hook=_reject_duplicate_members,
                )
                if type(payload) is not dict:
                    raise TypeError
                signature_bytes = base64.b64decode(signature, validate=True)
                verify_domain_separated_ed25519(
                    hash_canonical_jcs(payload),
                    signature_bytes,
                    domain_separator=domain,
                    verify_key=self.__verify_key,
                )
            except (BadSignatureError, binascii.Error) as exc:
                raise StoredStateCorruptError(
                    "signed record signature is invalid"
                ) from exc
            except (
                CapsuleCanonicalizationError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise StoredStateCorruptError("signed record is malformed") from exc
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> feat/m1-unbound-denylist
            if payload.keys() != contract.fields.keys():
                raise StoredStateCorruptError(
                    "signed record fields differ from its immutable field contract"
                )
            for field, rule in contract.fields.items():
                if type(payload[field]) not in rule.json_types:
                    raise StoredStateCorruptError(
                        f"signed record field {field!r} has an invalid JSON type"
                    )
            if not isinstance(row_bindings, Mapping) or any(
                type(field) is not str for field in row_bindings
            ):
                raise StoredStateCorruptError(
                    "signed record row bindings are malformed"
                )
            if frozenset(row_bindings) != contract.row_bound_fields:
                raise StoredStateCorruptError(
                    "signed record row bindings differ from its immutable field contract"
                )
            for field, value in row_bindings.items():
                if not _json_type_strict_equal(payload[field], value):
                    raise StoredStateCorruptError(
                        f"signed record does not match row binding {field!r}"
                    )
            if contract.specialized_validator is not None:
                try:
                    contract.specialized_validator(payload, validation_context)
                except Exception as exc:
                    raise StoredStateCorruptError(
                        "signed record specialized validation failed"
                    ) from exc
<<<<<<< HEAD
=======
=======
            if not isinstance(row_bindings, Mapping):
                raise StoredStateCorruptError(
                    "signed record row bindings are malformed"
                )
            bound_fields = frozenset(row_bindings)
            if any(type(field) is not str for field in bound_fields):
                raise StoredStateCorruptError(
                    "signed record row bindings are malformed"
                )
            if bound_fields != contract.row_bound_fields:
                raise StoredStateCorruptError(
                    "signed record row bindings differ from its immutable field contract"
                )
            if frozenset(payload) != contract.fields:
                raise StoredStateCorruptError(
                    "signed record fields differ from its immutable field contract"
                )
            for field, value in row_bindings.items():
                if payload[field] != value:
                    raise StoredStateCorruptError(
                        f"signed record does not match row binding {field!r}"
                    )
>>>>>>> feat/patch-loop-leasestore-fix2
>>>>>>> feat/m1-unbound-denylist
            return Verified(MappingProxyType(payload), _token=construction_token)

        def _matches(self, verify_key: VerifyKey) -> bool:
            return hmac.compare_digest(
                bytes(self.__verify_key),
                bytes(verify_key),
            )

    return Verified, RecordVerifier


Verified, RecordVerifier = _verified_contract()


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member {key!r}")
        value[key] = item
    return value


class PlatformSigner:
    """Non-retaining platform signer with no storage dependency."""

    __slots__ = ("__signing_key",)

    def __init__(self, signing_key: SigningKey) -> None:
        if not isinstance(signing_key, SigningKey):
            raise TypeError("signing_key must be an Ed25519 SigningKey")
        self.__signing_key = signing_key

    def sign(
        self,
        domain: bytes,
        payload: Mapping[str, Any],
    ) -> tuple[str, str]:
        if type(domain) is not bytes or not domain:
            raise TypeError("domain must be non-empty bytes")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> feat/m1-unbound-denylist
        contract = SIGNED_RECORD_CONTRACTS.get(domain)
        if contract is None:
            raise TypeError("signed record domain has no immutable field contract")
        record = dict(payload)
        if record.keys() != contract.fields.keys():
            raise TypeError(
                "signed record fields differ from its immutable field contract"
            )
        for field, rule in contract.fields.items():
            if type(record[field]) not in rule.json_types:
                raise TypeError(
                    f"signed record field {field!r} has an invalid JSON type"
                )
<<<<<<< HEAD
=======
=======
        record = dict(payload)
>>>>>>> feat/patch-loop-leasestore-fix2
>>>>>>> feat/m1-unbound-denylist
        digest = hash_canonical_jcs(record)
        signature = sign_domain_separated_ed25519(
            digest,
            domain_separator=domain,
            signing_key=self.__signing_key,
        )
        return (
            canonicalize_jcs(record).decode("utf-8"),
            base64.b64encode(signature).decode("ascii"),
        )

    def matches(self, verifier: RecordVerifier) -> bool:
        return isinstance(verifier, RecordVerifier) and verifier._matches(
            self.__signing_key.verify_key
        )

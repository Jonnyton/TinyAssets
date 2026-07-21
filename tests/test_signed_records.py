from __future__ import annotations

import base64
import copy
import inspect
import pickle
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from nacl.signing import SigningKey

import tinyassets.runtime.signed_records as signed_records_module
from tinyassets.runtime.execution_capsule import (
    canonicalize_jcs,
    hash_canonical_jcs,
    sign_domain_separated_ed25519,
)
from tinyassets.runtime.signed_record_contract import (
    FieldDisposition,
    SignedFieldRule,
    SignedRecordContract,
    SignedRecordContractRegistry,
)
from tinyassets.runtime.signed_record_contracts import (
    COMPLETION_ATTESTATION_V1_CONTRACT,
    LEASE_GRANT_DOMAIN_SEPARATOR,
    LEASE_GRANT_V2_CONTRACT,
    SIGNED_RECORD_CONTRACTS,
    LeaseGrantValidationContext,
)
from tinyassets.runtime.signed_records import (
    PlatformSigner,
    RecordVerifier,
    StoredStateCorruptError,
    Verified,
)

_DOMAIN = LEASE_GRANT_DOMAIN_SEPARATOR


class _BypassValidationContext:
    @staticmethod
    def validate_lease_grant(payload) -> None:
        del payload

    @staticmethod
    def validate_completion_attestation(payload) -> None:
        del payload


_BYPASS_CONTEXT = _BypassValidationContext()
_DEVICE_KEY = SigningKey.generate()
_LEASE_CONTEXT = LeaseGrantValidationContext(
    SimpleNamespace(
        resolve_device_key=lambda device_key_id: (
            SimpleNamespace(
                device_key_id="device-key:builder-1",
                verify_key=_DEVICE_KEY.verify_key,
                credential_epoch=1,
                active=True,
            )
            if device_key_id == "device-key:builder-1"
            else None
        )
    )
)


def _accept_specialized(payload, context) -> None:
    del payload, context


def test_contract_registry_is_immutable_and_rejects_duplicate_domain() -> None:
    source_fields = {
        "job_id": SignedFieldRule(FieldDisposition.ROW_BOUND, (str,)),
    }
    contract = SignedRecordContract(
        name="test-record-v1",
        domain_separator=b"tinyassets.test-record.v1\0",
        fields=source_fields,
        specialized_validator=None,
    )
    source_fields["future"] = SignedFieldRule(FieldDisposition.INERT, (str,), "audit")
    registry = SignedRecordContractRegistry.freeze(contract)

    assert tuple(contract.fields) == ("job_id",)
    assert registry[contract.domain_separator] is contract
    with pytest.raises(TypeError):
        contract.fields["future"] = source_fields["future"]  # type: ignore[index]
    with pytest.raises(TypeError):
        registry[b"tinyassets.other.v1\0"] = contract  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate domain separator"):
        SignedRecordContractRegistry.freeze(contract, contract)


def test_inert_field_requires_documented_reason() -> None:
    with pytest.raises(ValueError, match="inert_reason"):
        SignedFieldRule(FieldDisposition.INERT, (str,))
    with pytest.raises(ValueError, match="inert_reason"):
        SignedFieldRule(FieldDisposition.ROW_BOUND, (str,), "not inert")

    inert = SignedFieldRule(
        FieldDisposition.INERT,
        (str,),
        "audit metadata only",
    )
    assert inert.inert_reason == "audit metadata only"

    specialized = SignedFieldRule(FieldDisposition.SPECIALIZED_VALIDATED, (str,))
    with pytest.raises(ValueError, match="validator"):
        SignedRecordContract(
            name="missing-validator",
            domain_separator=b"tinyassets.missing-validator.v1\0",
            fields={"schema_version": specialized},
            specialized_validator=None,
        )
    with pytest.raises(ValueError, match="validator"):
        SignedRecordContract(
            name="unexpected-validator",
            domain_separator=b"tinyassets.unexpected-validator.v1\0",
            fields={"job_id": SignedFieldRule(FieldDisposition.ROW_BOUND, (str,))},
            specialized_validator=_accept_specialized,
        )


def test_existing_domain_contract_field_dispositions_are_complete_snapshots() -> None:
    assert {
        name: rule.disposition
        for name, rule in LEASE_GRANT_V2_CONTRACT.fields.items()
    } == {
        "schema_version": FieldDisposition.SPECIALIZED_VALIDATED,
        "job_id": FieldDisposition.ROW_BOUND,
        "owner_user_id": FieldDisposition.ROW_BOUND,
        "daemon_id": FieldDisposition.ROW_BOUND,
        "device_key_id": FieldDisposition.SPECIALIZED_VALIDATED,
        "device_verify_key": FieldDisposition.SPECIALIZED_VALIDATED,
        "device_key_epoch": FieldDisposition.SPECIALIZED_VALIDATED,
        "lease_id": FieldDisposition.ROW_BOUND,
        "fence": FieldDisposition.ROW_BOUND,
        "issued_at": FieldDisposition.ROW_BOUND,
        "expires_at": FieldDisposition.ROW_BOUND,
        "capsule_id": FieldDisposition.ROW_BOUND,
        "capsule_sha256": FieldDisposition.ROW_BOUND,
        "capability_class": FieldDisposition.SPECIALIZED_VALIDATED,
        "repo_mode": FieldDisposition.SPECIALIZED_VALIDATED,
        "runner_policy_sha256": FieldDisposition.SPECIALIZED_VALIDATED,
        "image_digest": FieldDisposition.SPECIALIZED_VALIDATED,
    }
    assert {
        name: rule.disposition
        for name, rule in COMPLETION_ATTESTATION_V1_CONTRACT.fields.items()
    } == {
        "schema_version": FieldDisposition.SPECIALIZED_VALIDATED,
        "receipt_id": FieldDisposition.SPECIALIZED_VALIDATED,
        "job_id": FieldDisposition.ROW_BOUND,
        "owner_user_id": FieldDisposition.INERT,
        "daemon_id": FieldDisposition.ROW_BOUND,
        "lease_id": FieldDisposition.ROW_BOUND,
        "fence": FieldDisposition.ROW_BOUND,
        "capsule_id": FieldDisposition.ROW_BOUND,
        "capsule_sha256": FieldDisposition.ROW_BOUND,
        "result_id": FieldDisposition.ROW_BOUND,
        "result_sha256": FieldDisposition.ROW_BOUND,
        "status": FieldDisposition.SPECIALIZED_VALIDATED,
        "completed_at": FieldDisposition.SPECIALIZED_VALIDATED,
    }
    assert SIGNED_RECORD_CONTRACTS == {
        LEASE_GRANT_V2_CONTRACT.domain_separator: LEASE_GRANT_V2_CONTRACT,
        COMPLETION_ATTESTATION_V1_CONTRACT.domain_separator: (
            COMPLETION_ATTESTATION_V1_CONTRACT
        ),
    }


def _payload(**changes):
    payload = {
        "schema_version": "lease-grant/v2",
        "job_id": "job-1",
        "owner_user_id": "user:owner-1",
        "daemon_id": "daemon:builder-1",
        "device_key_id": "device-key:builder-1",
        "device_verify_key": base64.b64encode(bytes(_DEVICE_KEY.verify_key)).decode(
            "ascii"
        ),
        "device_key_epoch": 1,
        "lease_id": "lease-1",
        "fence": 3,
        "issued_at": "2026-07-19T12:00:00.000000Z",
        "expires_at": "2026-07-19T12:02:00.000000Z",
        "capsule_id": "capsule-1",
        "capsule_sha256": "a" * 64,
        "capability_class": "repo",
        "repo_mode": "coding",
        "runner_policy_sha256": "b" * 64,
        "image_digest": f"sha256:{'c' * 64}",
    }
    payload.update(changes)
    return payload


def _completion_payload(**changes):
    payload = {
        "schema_version": "completion-attestation/v1",
        "receipt_id": "completion:receipt-1",
        "job_id": "job-1",
        "owner_user_id": "user:audit-only",
        "daemon_id": "daemon:builder-1",
        "lease_id": "lease-1",
        "fence": 3,
        "capsule_id": "capsule-1",
        "capsule_sha256": "a" * 64,
        "result_id": "result:" + "b" * 64,
        "result_sha256": "b" * 64,
        "status": "succeeded",
        "completed_at": "2026-07-19T12:01:00.000000Z",
    }
    payload.update(changes)
    return payload


def _low_level_sign(
    key: SigningKey,
    domain: bytes,
    payload: dict,
) -> tuple[str, str]:
    signature = sign_domain_separated_ed25519(
        hash_canonical_jcs(payload),
        domain_separator=domain,
        signing_key=key,
    )
    return (
        canonicalize_jcs(payload).decode("utf-8"),
        base64.b64encode(signature).decode("ascii"),
    )


def _row_bindings(payload):
    return {
        field: payload[field]
        for field in (
            "job_id",
            "owner_user_id",
            "daemon_id",
            "lease_id",
            "fence",
            "issued_at",
            "expires_at",
            "capsule_id",
            "capsule_sha256",
        )
    }


def _test_verifier(key) -> RecordVerifier:
    return RecordVerifier(key.verify_key)


def test_verify_has_no_unbound_fields_parameter() -> None:
    assert "unbound_fields" not in inspect.signature(RecordVerifier.verify).parameters


def test_unknown_domain_is_rejected_by_signer_and_verifier() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = _payload()
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)
    unknown_domain = b"tinyassets.unknown.v1\0"

    with pytest.raises(TypeError, match="contract"):
        signer.sign(unknown_domain, payload)
    with pytest.raises(StoredStateCorruptError, match="contract"):
        verifier.verify(
            unknown_domain,
            signed_json,
            signature,
            _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
        )


@pytest.mark.parametrize(
    ("domain", "payload"),
    [
        (_DOMAIN, _payload(future_authority="attacker-controlled")),
        (
            COMPLETION_ATTESTATION_V1_CONTRACT.domain_separator,
            _completion_payload(future_authority="attacker-controlled"),
        ),
    ],
    ids=["lease-grant", "completion-attestation"],
)
def test_extra_validly_signed_field_fails_closed(
    domain: bytes,
    payload: dict,
) -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)

    with pytest.raises(TypeError, match="field contract"):
        signer.sign(domain, payload)
    signed_json, signature = _low_level_sign(key, domain, payload)
    row_bindings = {
        name: payload[name]
        for name in SIGNED_RECORD_CONTRACTS[domain].row_bound_fields
    }
    with pytest.raises(StoredStateCorruptError, match="field contract"):
        verifier.verify(
            domain,
            signed_json,
            signature,
            row_bindings,
            validation_context=_LEASE_CONTEXT,
        )


def test_missing_contract_field_fails_closed() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = _payload()
    del payload["image_digest"]

    with pytest.raises(TypeError, match="field contract"):
        signer.sign(_DOMAIN, payload)
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)
    with pytest.raises(StoredStateCorruptError, match="field contract"):
        verifier.verify(
            _DOMAIN,
            signed_json,
            signature,
            _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
        )


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_row_bindings_must_exactly_equal_contract_row_bound_fields(
    mutation: str,
) -> None:
    key = SigningKey.generate()
    payload = _payload()
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)
    row_bindings = _row_bindings(payload)
    if mutation == "missing":
        del row_bindings["owner_user_id"]
    else:
        row_bindings["schema_version"] = payload["schema_version"]

    with pytest.raises(StoredStateCorruptError, match="row bindings"):
        RecordVerifier(key.verify_key).verify(
            _DOMAIN,
            signed_json,
            signature,
            row_bindings,
            validation_context=_LEASE_CONTEXT,
        )


@pytest.mark.parametrize("field", ["owner_user_id", "status"])
def test_caller_cannot_bind_inert_or_specialized_fields(field: str) -> None:
    key = SigningKey.generate()
    payload = _completion_payload()
    signed_json, signature = _low_level_sign(
        key,
        COMPLETION_ATTESTATION_V1_CONTRACT.domain_separator,
        payload,
    )
    row_bindings = {
        name: payload[name]
        for name in COMPLETION_ATTESTATION_V1_CONTRACT.row_bound_fields
    }
    row_bindings[field] = payload[field]

    with pytest.raises(StoredStateCorruptError, match="row bindings"):
        RecordVerifier(key.verify_key).verify(
            COMPLETION_ATTESTATION_V1_CONTRACT.domain_separator,
            signed_json,
            signature,
            row_bindings,
            validation_context=_LEASE_CONTEXT,
        )


def test_specialized_validation_failure_does_not_mint_verified() -> None:
    key = SigningKey.generate()
    payload = _payload()
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)

    with pytest.raises(StoredStateCorruptError, match="specialized validation"):
        RecordVerifier(key.verify_key).verify(
            _DOMAIN,
            signed_json,
            signature,
            _row_bindings(payload),
            validation_context=LeaseGrantValidationContext(None),
        )


def test_validation_context_cannot_replace_registered_domain_semantics() -> None:
    key = SigningKey.generate()
    payload = _payload(schema_version="attacker-version")
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)

    with pytest.raises(StoredStateCorruptError, match="specialized validation"):
        RecordVerifier(key.verify_key).verify(
            _DOMAIN,
            signed_json,
            signature,
            _row_bindings(payload),
            validation_context=_BYPASS_CONTEXT,
        )


@pytest.mark.parametrize(
    ("payload_value", "binding_value"),
    [(True, 1), (1, 1.0)],
)
def test_binding_equality_is_recursive_and_json_type_strict(
    payload_value,
    binding_value,
) -> None:
    assert not signed_records_module._json_type_strict_equal(
        {"outer": [payload_value]},
        {"outer": [binding_value]},
    )


def test_domain_separator_selects_contract_not_payload_shape() -> None:
    key = SigningKey.generate()
    completion_payload = _completion_payload()

    with pytest.raises(TypeError, match="field contract"):
        PlatformSigner(key).sign(_DOMAIN, completion_payload)


def test_declared_json_types_are_exact_for_signing_and_verification() -> None:
    key = SigningKey.generate()
    payload = _payload(fence=True)
    with pytest.raises(TypeError, match="JSON type"):
        PlatformSigner(key).sign(_DOMAIN, payload)

    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)
    with pytest.raises(StoredStateCorruptError, match="JSON type"):
        RecordVerifier(key.verify_key).verify(
            _DOMAIN,
            signed_json,
            signature,
            _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
        )


def test_verified_is_frozen_and_public_construction_bypasses_are_refused() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = _test_verifier(key)
    payload = _payload()
    signed_json, signature = signer.sign(_DOMAIN, payload)

    with pytest.raises(TypeError, match="RecordVerifier"):
        Verified(payload)
    with pytest.raises(TypeError, match="RecordVerifier"):
        Verified(payload, _token=object())

    with pytest.raises(TypeError, match="cannot be subclassed"):
        type("ForgedVerified", (Verified,), {})

    verified = verifier.verify(
        _DOMAIN,
        signed_json,
        signature,
        _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
    )

    assert verified.payload == payload
    assert getattr(Verified, "__final__", False) is True
    module_globals = vars(signed_records_module)
    assert "_mint_verified" not in module_globals
    assert not {
        name for name, value in module_globals.items() if type(value) is object
    }
    for operation in (
        lambda: copy.copy(verified),
        lambda: copy.deepcopy(verified),
        lambda: pickle.dumps(verified),
        lambda: verified.__reduce__(),
        lambda: verified.__reduce_ex__(pickle.HIGHEST_PROTOCOL),
    ):
        with pytest.raises(TypeError, match="Verified proof wrapper"):
            operation()
    with pytest.raises(FrozenInstanceError):
        verified.payload = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        verified.payload["fence"] = 4  # type: ignore[index]
    print(
        "VERIFIED_CUSTODY_CONTRACT_ENFORCED: "
        "sentinel_global=False subclass=False copy=False deepcopy=False pickle=False"
    )


def test_verified_custody_is_not_an_arbitrary_in_process_python_boundary() -> None:
    """DML cannot mint proofs; arbitrary Python can bypass object/key privacy."""
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = _test_verifier(key)
    payload = _payload(job_id="outside", fence=9)

    forged = object.__new__(Verified)
    object.__setattr__(forged, "payload", payload)

    assert forged.payload == payload
    assert bytes(getattr(verifier, "_RecordVerifier__verify_key")) == bytes(
        key.verify_key
    )
    assert bytes(getattr(signer, "_PlatformSigner__signing_key")) == bytes(key)
    assert "DML" in (signed_records_module.__doc__ or "")
    assert "arbitrary in-process Python execution" in (
        signed_records_module.__doc__ or ""
    )


def test_record_verifier_uses_contract_partitions_without_caller_accounting() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = _payload()
    signed_json, signature = signer.sign(_DOMAIN, payload)

    verified = verifier.verify(
        _DOMAIN,
        signed_json,
        signature,
        _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
    )
    assert verified.payload == payload

    incomplete_payload = dict(payload)
    del incomplete_payload["owner_user_id"]
    incomplete_json, incomplete_signature = _low_level_sign(
        key, _DOMAIN, incomplete_payload
    )
    with pytest.raises(StoredStateCorruptError, match="field contract") as rejection:
        verifier.verify(
            _DOMAIN,
            incomplete_json,
            incomplete_signature,
            _row_bindings(payload),
            validation_context=_LEASE_CONTEXT,
        )
    print(f"OMITTED_SIGNED_FIELD_REJECTED: {rejection.value}")


def test_domain_contract_rejects_unclassified_signed_field_even_if_caller_unbinds_it() -> None:
    key = SigningKey.generate()
    verifier = RecordVerifier(key.verify_key)
    payload = _payload(future_authority="attacker-controlled")
    row_bindings = _row_bindings(payload)
    signed_json, signature = _low_level_sign(key, _DOMAIN, payload)
    legacy_escape_hatch = {}
    if "unbound_fields" in inspect.signature(verifier.verify).parameters:
        legacy_escape_hatch["unbound_fields"] = frozenset(payload) - frozenset(
            row_bindings
        )

    with pytest.raises(StoredStateCorruptError, match="field contract"):
        verifier.verify(
            _DOMAIN,
            signed_json,
            signature,
            row_bindings,
            validation_context=_LEASE_CONTEXT,
            **legacy_escape_hatch,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("malformed_json", "malformed"),
        ("duplicate_field", "malformed"),
        ("malformed_signature", "signature"),
        ("wrong_signature", "signature"),
        ("wrong_domain", "field contract"),
        ("row_binding", "row binding"),
    ],
)
def test_record_verifier_fails_closed_for_every_untrusted_input(
    mutation: str,
    message: str,
) -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = _test_verifier(key)
    payload = _payload()
    signed_json, signature = signer.sign(domain=_DOMAIN, payload=payload)
    domain = _DOMAIN
    row_bindings = _row_bindings(payload)

    if mutation == "malformed_json":
        signed_json = "{"
    elif mutation == "duplicate_field":
        signed_json = '{"job_id":"job-1","fence":2,"fence":3}'
    elif mutation == "malformed_signature":
        signature = "not-base64"
    elif mutation == "wrong_signature":
        _, signature = PlatformSigner(SigningKey.generate()).sign(
            domain=_DOMAIN,
            payload=payload,
        )
    elif mutation == "wrong_domain":
        domain = b"tinyassets.other-record.v1\0"
    else:
        row_bindings["fence"] = 4

    with pytest.raises(StoredStateCorruptError, match=message):
        verifier.verify(
            domain=domain,
            signed_json=signed_json,
            signature=signature,
            row_bindings=row_bindings,
            validation_context=_LEASE_CONTEXT,
        )


def test_key_custody_objects_expose_no_raw_key_or_store() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)

    assert not hasattr(signer, "signing_key")
    assert not hasattr(signer, "store")
    assert not hasattr(verifier, "verify_key")
    assert not hasattr(verifier, "store")
    assert signer.matches(verifier)
    assert not signer.matches(RecordVerifier(SigningKey.generate().verify_key))


def test_lease_store_consumes_verifier_and_issuer_consumes_signer() -> None:
    from tinyassets.runtime.lease_store import LeaseGrantIssuer, LeaseStore

    store_parameters = inspect.signature(LeaseStore).parameters
    issuer_parameters = inspect.signature(LeaseGrantIssuer).parameters

    assert "record_verifier" in store_parameters
    assert "grant_verify_key" not in store_parameters
    assert "platform_signer" in issuer_parameters
    assert "signing_key" not in issuer_parameters

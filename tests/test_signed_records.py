from __future__ import annotations

import copy
import inspect
import pickle
from dataclasses import FrozenInstanceError

import pytest
from nacl.signing import SigningKey

import tinyassets.runtime.signed_records as signed_records_module
from tinyassets.runtime.signed_records import (
    PlatformSigner,
    RecordVerifier,
    StoredStateCorruptError,
    Verified,
)

_DOMAIN = b"tinyassets.test-record.v1\0"


def test_verified_is_frozen_and_public_construction_bypasses_are_refused() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = {"job_id": "job-1", "fence": 3}
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
        payload,
        unbound_fields=frozenset(),
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
    verifier = RecordVerifier(key.verify_key)
    payload = {"job_id": "outside", "fence": 9}

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


def test_record_verifier_rejects_omitted_signed_fields_unless_declared_unbound() -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = {"job_id": "job-1", "fence": 3, "capsule_id": "capsule-1"}
    signed_json, signature = signer.sign(_DOMAIN, payload)

    with pytest.raises(
        StoredStateCorruptError,
        match="declared unbound",
    ) as rejection:
        verifier.verify(
            _DOMAIN,
            signed_json,
            signature,
            {"job_id": "job-1", "fence": 3},
            unbound_fields=frozenset(),
        )
    print(f"OMITTED_SIGNED_FIELD_REJECTED: {rejection.value}")

    verified = verifier.verify(
        _DOMAIN,
        signed_json,
        signature,
        {"job_id": "job-1", "fence": 3},
        unbound_fields=frozenset({"capsule_id"}),
    )

    assert verified.payload == payload


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("malformed_json", "malformed"),
        ("duplicate_field", "malformed"),
        ("malformed_signature", "signature"),
        ("wrong_signature", "signature"),
        ("wrong_domain", "signature"),
        ("row_binding", "row binding"),
    ],
)
def test_record_verifier_fails_closed_for_every_untrusted_input(
    mutation: str,
    message: str,
) -> None:
    key = SigningKey.generate()
    signer = PlatformSigner(key)
    verifier = RecordVerifier(key.verify_key)
    payload = {"job_id": "job-1", "fence": 3}
    signed_json, signature = signer.sign(domain=_DOMAIN, payload=payload)
    domain = _DOMAIN
    row_bindings = dict(payload)

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
            unbound_fields=frozenset(),
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

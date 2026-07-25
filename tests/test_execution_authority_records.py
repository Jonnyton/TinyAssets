from __future__ import annotations

import base64
import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError, replace

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_CAPSULE_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
_GRANT_SEED = bytes.fromhex("101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f")
_DEVICE_SEED = bytes.fromhex("1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
_TERMINAL_SEED = bytes.fromhex("202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f")
_CAPSULE_KEY = Ed25519PrivateKey.from_private_bytes(_CAPSULE_SEED)
_GRANT_KEY = Ed25519PrivateKey.from_private_bytes(_GRANT_SEED)
_DEVICE_KEY = Ed25519PrivateKey.from_private_bytes(_DEVICE_SEED)
_TERMINAL_KEY = Ed25519PrivateKey.from_private_bytes(_TERMINAL_SEED)
CAPSULE_DOMAIN = "tinyassets.execution-capsule.v1"
GRANT_DOMAIN = "tinyassets.execution-grant.v1"
CANDIDATE_DOMAIN = "tinyassets.execution-candidate.v1"
TERMINAL_DOMAIN = "tinyassets.execution-terminal.v1"


def _api():
    try:
        import tinyassets.execution_authority as authority
        import tinyassets.execution_authority.records as records
    except ImportError as exc:
        pytest.fail(f"D0 signed-record API is missing: {exc}")
    return authority, records


def _capsule(**changes: object):
    authority, _ = _api()
    values: dict[str, object] = {
        "signing_key_id": "test-platform-capsule-1",
        "owner_id": "user:owner-1",
        "audience_daemon_id": "daemon:builder-1",
        "job_id": "job-1",
        "capsule_id": "capsule-1",
        "attempt": 1,
        "generation": 2,
        "source_id": "source:bundle-1",
        "source_digest": "1" * 64,
        "policy_id": "policy:repo-coding-v1",
        "policy_digest": "2" * 64,
        "issued_at": "2026-07-24T12:00:00Z",
        "expires_at": "2026-07-24T12:02:00Z",
        "max_wall_time_seconds": 120,
        "max_memory_bytes": 536_870_912,
        "max_output_bytes": 1_048_576,
    }
    values.update(changes)
    return authority.ExecutionCapsuleV1(**values)


def _grant(**changes: object):
    authority, _ = _api()
    values: dict[str, object] = {
        "signing_key_id": "test-platform-grant-1",
        "owner_id": "user:owner-1",
        "daemon_id": "daemon:builder-1",
        "job_id": "job-1",
        "capsule_id": "capsule-1",
        "capsule_digest": "3" * 64,
        "lease_id": "lease-1",
        "generation": 2,
        "fence": 2,
        "expires_at": "2026-07-24T12:02:00Z",
        "capability_ceiling": ("model_broker", "result_upload"),
        "idempotency_key": "idem:grant-1",
    }
    values.update(changes)
    return authority.ExecutionGrantV1(**values)


def _candidate(**changes: object):
    authority, _ = _api()
    values: dict[str, object] = {
        "device_key_id": "test-device-result-1",
        "owner_id": "user:owner-1",
        "daemon_id": "daemon:builder-1",
        "job_id": "job-1",
        "capsule_id": "capsule-1",
        "capsule_digest": "3" * 64,
        "lease_id": "lease-1",
        "generation": 2,
        "fence": 2,
        "result_digest": "4" * 64,
        "blob_refs": (
            authority.BlobReferenceV1(
                ref="result.bin",
                sha256="5" * 64,
                size_bytes=14,
                media_type="application/octet-stream",
            ),
        ),
        "blob_set_digest": "6" * 64,
        "status": "succeeded",
        "idempotency_key": "idem:candidate-1",
    }
    values.update(changes)
    return authority.ExecutionCandidateV1(**values)


def _terminal(**changes: object):
    authority, _ = _api()
    values: dict[str, object] = {
        "signing_key_id": "test-platform-terminal-1",
        "owner_id": "user:owner-1",
        "daemon_id": "daemon:builder-1",
        "job_id": "job-1",
        "capsule_id": "capsule-1",
        "capsule_digest": "3" * 64,
        "lease_id": "lease-1",
        "generation": 2,
        "fence": 2,
        "accepted_candidate_digest": "7" * 64,
        "accepted_result_digest": "4" * 64,
        "accepted_blob_set_digest": "6" * 64,
        "terminal_state": "succeeded",
        "completed_at": "2026-07-24T12:01:00Z",
        "idempotency_key": "idem:terminal-1",
    }
    values.update(changes)
    return authority.ExecutionTerminalV1(**values)


def _authority():
    _, records = _api()
    signer = records._create_record_signer(
        {
            CAPSULE_DOMAIN: ("test-platform-capsule-1", _CAPSULE_KEY),
            GRANT_DOMAIN: ("test-platform-grant-1", _GRANT_KEY),
            CANDIDATE_DOMAIN: ("test-device-result-1", _DEVICE_KEY),
            TERMINAL_DOMAIN: ("test-platform-terminal-1", _TERMINAL_KEY),
        }
    )
    verifier = records._create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                _CAPSULE_KEY.public_key(),
            ),
            GRANT_DOMAIN: (
                "test-platform-grant-1",
                _GRANT_KEY.public_key(),
            ),
            CANDIDATE_DOMAIN: (
                "test-device-result-1",
                _DEVICE_KEY.public_key(),
            ),
            TERMINAL_DOMAIN: (
                "test-platform-terminal-1",
                _TERMINAL_KEY.public_key(),
            ),
        },
        verifier_id="test-trust-set-v1",
    )
    return signer, verifier


@pytest.mark.parametrize(
    ("record_factory", "domain", "schema_version"),
    (
        (_capsule, CAPSULE_DOMAIN, "execution-capsule/v1"),
        (_grant, GRANT_DOMAIN, "execution-grant/v1"),
        (_candidate, CANDIDATE_DOMAIN, "execution-candidate/v1"),
        (_terminal, TERMINAL_DOMAIN, "execution-terminal/v1"),
    ),
)
def test_all_record_types_use_rfc8785_and_exact_domain_separated_ed25519_vectors(
    record_factory,
    domain: str,
    schema_version: str,
) -> None:
    authority, _ = _api()
    record = record_factory()
    signer, verifier = _authority()

    signed = signer.sign(record)
    expected_payload = json.loads(signed.canonical_payload)
    expected_canonical = rfc8785.dumps(expected_payload)
    expected_preimage = (domain + "\0").encode("utf-8") + hashlib.sha256(
        expected_canonical
    ).digest()
    expected_key = {
        CAPSULE_DOMAIN: _CAPSULE_KEY,
        GRANT_DOMAIN: _GRANT_KEY,
        CANDIDATE_DOMAIN: _DEVICE_KEY,
        TERMINAL_DOMAIN: _TERMINAL_KEY,
    }[domain]

    assert signed.domain == domain
    assert signed.canonical_payload == expected_canonical
    assert expected_payload["schema_version"] == schema_version
    assert base64.b64decode(signed.signature_b64, validate=True) == (
        expected_key.sign(expected_preimage)
    )
    assert authority.canonical_payload_bytes(record) == expected_canonical
    assert verifier.verify(signed, verified_at=123).value == record


def _resign_raw(
    signed,
    *,
    payload: dict[str, object] | None = None,
    domain: str | None = None,
    canonicalize: bool = True,
):
    authority, _ = _api()
    selected_domain = signed.domain if domain is None else domain
    selected_payload = json.loads(signed.canonical_payload) if payload is None else payload
    canonical = (
        rfc8785.dumps(selected_payload)
        if canonicalize
        else json.dumps(
            selected_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    key = {
        CAPSULE_DOMAIN: _CAPSULE_KEY,
        GRANT_DOMAIN: _GRANT_KEY,
        CANDIDATE_DOMAIN: _DEVICE_KEY,
        TERMINAL_DOMAIN: _TERMINAL_KEY,
    }[selected_domain]
    signature = key.sign(
        (selected_domain + "\0").encode("utf-8") + hashlib.sha256(canonical).digest()
    )
    return authority.SignedExecutionRecord(
        domain=selected_domain,
        canonical_payload=canonical,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


@pytest.mark.parametrize(
    "mutation",
    ("unknown_domain", "unknown_version", "unknown_field"),
)
def test_unknown_domain_version_or_field_fails_closed(mutation: str) -> None:
    authority, _ = _api()
    signer, verifier = _authority()
    signed = signer.sign(_capsule())

    if mutation == "unknown_domain":
        forged = replace(signed, domain="tinyassets.execution-unknown.v1")
    else:
        payload = json.loads(signed.canonical_payload)
        if mutation == "unknown_version":
            payload["schema_version"] = "execution-capsule/v2"
        else:
            payload["caller_authority"] = True
        forged = _resign_raw(signed, payload=payload)

    with pytest.raises(authority.RecordAuthorityError, match="domain|schema|field"):
        verifier.verify(forged, verified_at=123)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("attempt", True),
        ("generation", 2.5),
        ("max_wall_time_seconds", "120"),
    ),
)
def test_json_type_confusion_fails_even_with_a_valid_signature(
    field: str,
    value: object,
) -> None:
    authority, _ = _api()
    signer, verifier = _authority()
    signed = signer.sign(_capsule())
    payload = json.loads(signed.canonical_payload)
    payload[field] = value

    with pytest.raises(authority.RecordAuthorityError, match="type"):
        verifier.verify(_resign_raw(signed, payload=payload), verified_at=123)


@pytest.mark.parametrize("value", (-1, 2**53))
def test_json_integer_bounds_fail_even_with_a_valid_signature(value: int) -> None:
    authority, _ = _api()
    signer, verifier = _authority()
    signed = signer.sign(_capsule())
    payload = json.loads(signed.canonical_payload)
    payload["generation"] = value

    with pytest.raises(authority.RecordAuthorityError, match="integer|range"):
        verifier.verify(
            _resign_raw(
                signed,
                payload=payload,
                canonicalize=value <= (2**53 - 1),
            ),
            verified_at=123,
        )


@pytest.mark.parametrize("wrong_domain", (GRANT_DOMAIN, CANDIDATE_DOMAIN, TERMINAL_DOMAIN))
def test_cross_domain_signature_reuse_fails(wrong_domain: str) -> None:
    authority, _ = _api()
    signer, verifier = _authority()
    signed = signer.sign(_capsule())
    replayed = replace(signed, domain=wrong_domain)

    with pytest.raises(
        authority.RecordAuthorityError,
        match="signature|schema|field",
    ):
        verifier.verify(replayed, verified_at=123)


def test_record_contracts_are_frozen_and_nested_collections_are_immutable() -> None:
    authority, _ = _api()
    candidate = _candidate()
    grant = _grant()

    with pytest.raises(FrozenInstanceError):
        candidate.fence = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        candidate.blob_refs[0].sha256 = "9" * 64  # type: ignore[misc]
    assert isinstance(candidate.blob_refs, tuple)
    assert isinstance(grant.capability_ceiling, tuple)
    for record_type in (
        authority.BlobReferenceV1,
        authority.ExecutionCapsuleV1,
        authority.ExecutionGrantV1,
        authority.ExecutionCandidateV1,
        authority.ExecutionTerminalV1,
        authority.SignedExecutionRecord,
    ):
        assert getattr(record_type, "__final__", False) is True


def test_public_sign_and_verify_calls_offer_no_authority_escape_hatches() -> None:
    authority, _ = _api()
    forbidden = {
        "binder",
        "unbound_fields",
        "issuer",
        "key",
        "verify_key",
        "domain",
        "contract",
    }

    assert forbidden.isdisjoint(inspect.signature(authority.RecordSigner.sign).parameters)
    assert forbidden.isdisjoint(inspect.signature(authority.RecordVerifier.verify).parameters)


def test_signer_and_verifier_reject_public_key_reuse_across_purposes() -> None:
    _, records = _api()
    reused_private = {
        CAPSULE_DOMAIN: ("test-platform-capsule-1", _CAPSULE_KEY),
        GRANT_DOMAIN: ("test-platform-grant-1", _CAPSULE_KEY),
    }
    reused_public = {
        domain: (key_id, key.public_key()) for domain, (key_id, key) in reused_private.items()
    }

    with pytest.raises(TypeError, match="purpose|reuse|domain"):
        records._create_record_signer(reused_private)
    with pytest.raises(TypeError, match="purpose|reuse|domain"):
        records._create_record_verifier(
            reused_public,
            verifier_id="test-trust-set-v1",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("issued_at", "20260724T120000Z"),
        ("issued_at", "2026-07-24 12:00:00Z"),
        ("expires_at", "20260724T120200Z"),
        ("expires_at", "2026-07-24 12:02:00Z"),
    ),
)
def test_capsule_rejects_noncanonical_rfc3339_utc_forms(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match="RFC 3339|canonical|timestamp"):
        _capsule(**{field: value})


def test_capsule_compares_fractional_timestamps_chronologically() -> None:
    capsule = _capsule(
        issued_at="2026-07-24T12:00:00.1Z",
        expires_at="2026-07-24T12:00:00.11Z",
    )

    assert capsule.issued_at.endswith(".1Z")
    assert capsule.expires_at.endswith(".11Z")


@pytest.mark.parametrize(
    ("factory", "changes"),
    (
        (_grant, {"expires_at": "2026-07-24 12:02:00Z"}),
        (_terminal, {"completed_at": "20260724T120100Z"}),
    ),
)
def test_all_signed_record_timestamps_require_canonical_rfc3339_utc(
    factory,
    changes: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="RFC 3339|canonical|timestamp"):
        factory(**changes)

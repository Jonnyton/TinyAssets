from __future__ import annotations

import copy
import gc
import pickle
import weakref
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_PLATFORM_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")


def _api():
    try:
        import tinyassets.execution_authority as authority
        import tinyassets.execution_authority.verified as verified_module
        from tinyassets.execution_authority.records import (
            CAPSULE_DOMAIN,
            ExecutionCapsuleV1,
            _create_record_signer,
            _create_record_verifier,
        )
        from tinyassets.execution_authority.verified import Verified
    except ImportError as exc:
        pytest.fail(f"D0 verified-evidence API is missing: {exc}")
    return (
        authority,
        verified_module,
        CAPSULE_DOMAIN,
        ExecutionCapsuleV1,
        _create_record_signer,
        _create_record_verifier,
        Verified,
    )


def _capsule():
    _, _, _, ExecutionCapsuleV1, _, _, _ = _api()
    return ExecutionCapsuleV1(
        signing_key_id="test-platform-capsule-1",
        owner_id="user:owner-1",
        audience_daemon_id="daemon:builder-1",
        job_id="job-1",
        capsule_id="capsule-1",
        attempt=1,
        generation=2,
        source_id="source:bundle-1",
        source_digest="1" * 64,
        policy_id="policy:repo-coding-v1",
        policy_digest="2" * 64,
        issued_at="2026-07-24T12:00:00Z",
        expires_at="2026-07-24T12:02:00Z",
        max_wall_time_seconds=120,
        max_memory_bytes=536_870_912,
        max_output_bytes=1_048_576,
    )


def _verified_capsule():
    _, _, CAPSULE_DOMAIN, _, _create_record_signer, _create_record_verifier, _ = _api()
    private_key = Ed25519PrivateKey.from_private_bytes(_PLATFORM_SEED)
    signer = _create_record_signer({CAPSULE_DOMAIN: ("test-platform-capsule-1", private_key)})
    verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                private_key.public_key(),
            )
        },
        verifier_id="test-trust-set-v1",
    )
    return verifier.verify(signer.sign(_capsule()), verified_at=123)


def test_verified_refuses_direct_construction_and_token_free_minting() -> None:
    authority, verified_module, CAPSULE_DOMAIN, _, _, _, Verified = _api()
    with pytest.raises(TypeError, match="verification|constructed"):
        Verified(
            value=_capsule(),
            mechanism="m1",
            domain=CAPSULE_DOMAIN,
            evidence_digest="3" * 64,
            verifier_id="caller",
            verified_at=123,
        )

    assert "_mint_m1_verified" not in authority.__dict__
    assert "_mint_m2_verified" not in authority.__dict__
    assert "_mint_m3_verified" not in authority.__dict__
    for name in ("_mint_m1_verified", "_mint_m2_verified", "_mint_m3_verified"):
        assert not hasattr(verified_module, name)


def test_verified_module_exposes_no_callable_raw_mint_capability() -> None:
    _, verified_module, _, _, _, _, _ = _api()

    assert [
        name
        for name, value in vars(verified_module).items()
        if "mint" in name.casefold() and callable(value)
    ] == []
    assert not hasattr(verified_module, "_take_bootstrap_capabilities")


def test_verified_is_final_frozen_noncopyable_and_nonpickleable() -> None:
    _, _, _, _, _, _, Verified = _api()
    verified = _verified_capsule()

    with pytest.raises(TypeError, match="subclass"):
        type("ForgedVerified", (Verified,), {})
    with pytest.raises(FrozenInstanceError):
        verified.domain = "other"  # type: ignore[misc]
    for operation in (
        lambda: copy.copy(verified),
        lambda: copy.deepcopy(verified),
        lambda: pickle.dumps(verified),
        lambda: verified.__reduce__(),
        lambda: verified.__reduce_ex__(pickle.HIGHEST_PROTOCOL),
    ):
        with pytest.raises(TypeError, match="cop|pickl"):
            operation()

    assert getattr(Verified, "__final__", False) is True


def test_object_new_and_public_slot_population_does_not_forge_provenance() -> None:
    _, verified_module, CAPSULE_DOMAIN, _, _, _, Verified = _api()
    checker = getattr(verified_module, "_require_authentic_verified", None)
    assert callable(checker), "package-owned authenticity checker is missing"
    authentic = _verified_capsule()
    assert checker(authentic, expected_mechanism="m1") is authentic

    forged = object.__new__(Verified)
    for name, value in (
        ("value", _capsule()),
        ("mechanism", "m1"),
        ("domain", CAPSULE_DOMAIN),
        ("evidence_digest", authentic.evidence_digest),
        ("verifier_id", "test-trust-set-v1"),
        ("verified_at", 123),
    ):
        object.__setattr__(forged, name, value)

    with pytest.raises(TypeError, match="authentic|provenance"):
        checker(forged, expected_mechanism="m1")


def test_genuine_hidden_markers_cannot_be_transplanted_into_a_forgery() -> None:
    (
        _,
        _,
        CAPSULE_DOMAIN,
        _,
        _create_record_signer,
        _create_record_verifier,
        Verified,
    ) = _api()
    private_key = Ed25519PrivateKey.from_private_bytes(_PLATFORM_SEED)
    signer = _create_record_signer({CAPSULE_DOMAIN: ("test-platform-capsule-1", private_key)})
    verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                private_key.public_key(),
            )
        },
        verifier_id="test-trust-set-v1",
    )
    authentic = verifier.verify(signer.sign(_capsule()), verified_at=123)
    extracted: dict[str, object] = {}
    for name in ("_Verified__provenance", "_Verified__issuer"):
        try:
            extracted[name] = object.__getattribute__(authentic, name)
        except AttributeError:
            pass

    forged = object.__new__(Verified)
    for name in (
        "value",
        "mechanism",
        "domain",
        "evidence_digest",
        "verifier_id",
        "verified_at",
    ):
        object.__setattr__(forged, name, getattr(authentic, name))
    for name, value in extracted.items():
        object.__setattr__(forged, name, value)

    with pytest.raises(TypeError, match="authentic|provenance"):
        verifier.require_authentic(forged)
    assert extracted == {}


def test_authenticity_registry_does_not_keep_verified_evidence_alive() -> None:
    _, _, _, _, _, _, _ = _api()
    authentic = _verified_capsule()
    reference = weakref.ref(authentic)

    del authentic
    gc.collect()

    assert reference() is None


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("value", None),
        ("mechanism", "m2"),
        ("domain", "tinyassets.execution.capsule.forged"),
        ("evidence_digest", "0" * 64),
        ("verifier_id", "forged-root-v1"),
        ("verified_at", 124),
    ],
)
def test_record_verifier_rejects_mutated_genuine_evidence_fields(
    field_name: str,
    replacement: object,
) -> None:
    (
        _,
        _,
        CAPSULE_DOMAIN,
        _,
        _create_record_signer,
        _create_record_verifier,
        _,
    ) = _api()
    private_key = Ed25519PrivateKey.from_private_bytes(_PLATFORM_SEED)
    signer = _create_record_signer({CAPSULE_DOMAIN: ("test-platform-capsule-1", private_key)})
    verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                private_key.public_key(),
            )
        },
        verifier_id="test-trust-set-v1",
    )
    authentic = verifier.verify(signer.sign(_capsule()), verified_at=123)
    if field_name == "value":
        replacement = _capsule()
        assert replacement == authentic.value and replacement is not authentic.value

    object.__setattr__(authentic, field_name, replacement)

    with pytest.raises(TypeError, match="snapshot"):
        verifier.require_authentic(authentic)


def test_mapping_proxy_backing_dict_is_not_accepted_as_deeply_immutable() -> None:
    _, verified_module, _, _, _, _, _ = _api()
    backing = {"authority": "original"}
    apparent_read_only = MappingProxyType(backing)

    assert verified_module._is_deeply_immutable(apparent_read_only) is False
    backing["authority"] = "mutated"
    assert apparent_read_only["authority"] == "mutated"


def test_record_verifier_mints_m1_only_after_real_ed25519_verification() -> None:
    _, _, CAPSULE_DOMAIN, _, _, _, _ = _api()
    verified = _verified_capsule()

    assert verified.value == _capsule()
    assert verified.mechanism == "m1"
    assert verified.domain == CAPSULE_DOMAIN
    assert len(verified.evidence_digest) == 64
    assert verified.verifier_id == "test-trust-set-v1"
    assert verified.verified_at == 123


def test_record_verifier_refuses_a_signature_from_an_untrusted_key() -> None:
    authority, _, CAPSULE_DOMAIN, _, _create_record_signer, _create_record_verifier, _ = _api()
    trusted_key = Ed25519PrivateKey.from_private_bytes(_PLATFORM_SEED)
    attacker_key = Ed25519PrivateKey.from_private_bytes(b"\xff" * 32)
    signer = _create_record_signer({CAPSULE_DOMAIN: ("test-platform-capsule-1", attacker_key)})
    verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                trusted_key.public_key(),
            )
        },
        verifier_id="test-trust-set-v1",
    )

    with pytest.raises(authority.RecordAuthorityError, match="signature"):
        verifier.verify(signer.sign(_capsule()), verified_at=123)


def test_authority_sink_rejects_m1_from_an_alternate_verifier_issuer() -> None:
    (
        _,
        _,
        CAPSULE_DOMAIN,
        _,
        _create_record_signer,
        _create_record_verifier,
        _,
    ) = _api()
    trusted_key = Ed25519PrivateKey.from_private_bytes(_PLATFORM_SEED)
    alternate_key = Ed25519PrivateKey.from_private_bytes(b"\xfe" * 32)
    trusted_verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                trusted_key.public_key(),
            )
        },
        verifier_id="trusted-root-v1",
    )
    alternate_signer = _create_record_signer(
        {CAPSULE_DOMAIN: ("test-platform-capsule-1", alternate_key)}
    )
    alternate_verifier = _create_record_verifier(
        {
            CAPSULE_DOMAIN: (
                "test-platform-capsule-1",
                alternate_key.public_key(),
            )
        },
        verifier_id="alternate-root-v1",
    )
    alternate_evidence = alternate_verifier.verify(
        alternate_signer.sign(_capsule()),
        verified_at=123,
    )

    assert alternate_verifier.require_authentic(alternate_evidence) is alternate_evidence
    with pytest.raises(TypeError, match="issuer"):
        trusted_verifier.require_authentic(alternate_evidence)

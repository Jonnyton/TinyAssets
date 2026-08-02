from __future__ import annotations

import base64
import copy
import hashlib
import json
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tinyassets.auth.host_proof import (
    DOMAIN_SEPARATOR,
    ENROLLMENT_CHALLENGE_LIMITS,
    HOST_BINDING_REFUSAL,
    MAX_SUBMISSION_BYTES,
    POST_ENROLLMENT_NONCE_LIMITS,
    REFUSAL_BUCKET_SECONDS,
    HostEnrollmentCoordinator,
    HostEnrollmentIdempotencyConflict,
    HostEnrollmentRefused,
    HostEnrollmentTransactionOutcome,
    HostEnrollmentTransactionRequest,
    HostEnrollmentWritersDisabled,
    HostPrincipalResultV1,
    HostProofBindingV1,
    HostProofRefused,
    HostProofTimingExceeded,
    canonical_b64u,
    direct_account_revoke_policy,
    host_proof_signing_bytes,
    jwk_thumbprint,
    operation_policy,
    parse_wire_dto,
    refuse_host_binding,
    validate_route_path_id,
    verify_host_proof,
    wire_contract,
)

ISSUER = "https://example.authkit.app"
AUDIENCE = "https://tinyassets.io/host-binding"
NOW = 1_800_000_000


def _b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _key(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _jwk(key: Ed25519PrivateKey) -> dict[str, str]:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64u(raw)}


def _binding(
    operation: str = "enroll",
    *,
    keys: dict[str, Ed25519PrivateKey] | None = None,
) -> HostProofBindingV1:
    policy = operation_policy(operation)
    role_keys = keys if keys is not None else {"new": _key(1)}
    return HostProofBindingV1(
        schema_version="host-binding-v1",
        policy_version="host-binding-v1",
        operation=operation,
        permission=policy.permission,
        issuer=ISSUER,
        subject="user_01HOSTOWNER",
        audience=AUDIENCE,
        method=policy.method,
        path=policy.path,
        body_sha256="sha256:" + "ab" * 32,
        key_thumbprints={role: jwk_thumbprint(_jwk(key)) for role, key in role_keys.items()},
        host_principal_id=None if operation == "enroll" else "hp_01HOST",
        expected_generation=None if operation == "enroll" else 7,
        challenge_id_b64u=_b64u(bytes(range(32))),
        issued_at=NOW - 30,
        expires_at=NOW + 270,
    )


def _submission(
    binding: HostProofBindingV1,
    keys: dict[str, Ed25519PrivateKey],
    *,
    signing_input: bytes | None = None,
) -> bytes:
    message = signing_input if signing_input is not None else host_proof_signing_bytes(binding)
    return rfc8785.dumps(
        {
            "schema_version": "host-binding-v1",
            "challenge_id_b64u": binding.challenge_id_b64u,
            "signatures": {role: _b64u(key.sign(message)) for role, key in keys.items()},
        }
    )


def _verify(
    binding: HostProofBindingV1,
    keys: dict[str, Ed25519PrivateKey],
    *,
    submission: bytes | None = None,
    presented_jwks: dict[str, dict[str, str]] | None = None,
    signing_input_b64u: str | None = None,
    consume_once=lambda _nonce: True,
    monotonic=None,
    sleeper=None,
) -> None:
    timing = {}
    if monotonic is not None:
        timing["monotonic"] = monotonic
    if sleeper is not None:
        timing["sleeper"] = sleeper
    verify_host_proof(
        submission if submission is not None else _submission(binding, keys),
        binding=binding,
        public_jwks=(
            presented_jwks
            if presented_jwks is not None
            else {role: _jwk(key) for role, key in keys.items()}
        ),
        signing_input_b64u=(
            signing_input_b64u
            if signing_input_b64u is not None
            else _b64u(host_proof_signing_bytes(binding))
        ),
        now=NOW,
        consume_once=consume_once,
        **timing,
    )


def test_closed_operation_route_scope_and_signature_role_matrix() -> None:
    expected = {
        "enroll": (
            "POST",
            "/v1/host-principals",
            "host:enroll",
            {"new"},
            "EnrollIntentV1",
            "HostPrincipalResultV1",
        ),
        "inventory": (
            "GET",
            "/v1/host-principals",
            "host:manage",
            set(),
            "HostInventoryQueryV1",
            "HostInventoryPageV1",
        ),
        "read": (
            "POST",
            "/v1/host-principals/{id}:read",
            "host:manage",
            {"current"},
            "PrincipalIntentV1",
            "HostPrincipalDetailV1",
        ),
        "revoke": (
            "POST",
            "/v1/host-principals/{id}:revoke",
            "host:manage",
            {"current"},
            "RevokeIntentV1",
            "HostPrincipalResultV1",
        ),
        "rotate": (
            "POST",
            "/v1/host-principals/{id}:rotate",
            "host:manage",
            {"current", "new"},
            "RotateIntentV1",
            "HostPrincipalResultV1",
        ),
        "renew": (
            "POST",
            "/v1/host-principals/{id}:renew",
            "host:manage",
            {"current"},
            "RenewIntentV1",
            "HostPrincipalResultV1",
        ),
        "recover": (
            "POST",
            "/v1/host-principals/{id}:recover",
            "host:recover",
            {"new"},
            "RecoverIntentV1",
            "HostRecoveryResultV1",
        ),
        "session_register": (
            "POST",
            "/v1/host-sessions",
            "host:manage",
            {"current"},
            "SessionRegisterIntentV1",
            "HostSessionResultV1",
        ),
        "session_heartbeat": (
            "POST",
            "/v1/host-sessions/{id}:heartbeat",
            "host:manage",
            {"current"},
            "SessionHeartbeatIntentV1",
            "HostHeartbeatResultV1",
        ),
        "session_deregister": (
            "POST",
            "/v1/host-sessions/{id}:deregister",
            "host:manage",
            {"current"},
            "SessionDeregisterIntentV1",
            "HostSessionDeregisterResultV1",
        ),
    }

    assert {
        name: (
            policy.method,
            policy.path,
            policy.permission,
            set(policy.signature_roles),
            policy.intent_dto,
            policy.result_dto,
        )
        for name in expected
        if (policy := operation_policy(name))
    } == expected
    with pytest.raises(HostProofRefused):
        operation_policy("owner_selected_admin")


def test_direct_account_revoke_is_a_separate_recent_recovery_contract() -> None:
    policy = direct_account_revoke_policy()
    assert (
        policy.method,
        policy.path,
        policy.permission,
        set(policy.signature_roles),
        policy.intent_dto,
        policy.result_dto,
    ) == (
        "POST",
        "/v1/host-principals/{id}:revoke",
        "host:recover",
        set(),
        "AccountRevokeIntentV1",
        "HostPrincipalResultV1",
    )


def test_normative_v1_wire_dto_field_sets_are_closed() -> None:
    expected = {
        "HostChallengeRequestV1": ({"schema_version", "operation", "intent"}, set()),
        "HostChallengeV1": (
            {
                "schema_version",
                "challenge_id_b64u",
                "signing_input_b64u",
                "expires_at",
                "policy_version",
            },
            set(),
        ),
        "HostProofSubmissionV1": ({"schema_version", "challenge_id_b64u", "signatures"}, set()),
        "EnrollIntentV1": ({"idempotency_key_b64u", "public_jwk"}, {"device_label"}),
        "HostInventoryQueryV1": (set(), {"cursor", "limit"}),
        "PrincipalIntentV1": ({"host_principal_id", "expected_generation"}, set()),
        "RevokeIntentV1": (
            {"host_principal_id", "expected_generation", "idempotency_key_b64u"},
            {"reason_code"},
        ),
        "RotateIntentV1": (
            {"host_principal_id", "expected_generation", "idempotency_key_b64u", "new_public_jwk"},
            set(),
        ),
        "RenewIntentV1": (
            {"host_principal_id", "expected_generation", "idempotency_key_b64u"},
            set(),
        ),
        "RecoverIntentV1": (
            {"host_principal_id", "expected_generation", "idempotency_key_b64u", "new_public_jwk"},
            {"device_label"},
        ),
        "AccountRevokeIntentV1": (
            {"schema_version", "host_principal_id", "expected_generation", "idempotency_key_b64u"},
            {"reason_code"},
        ),
        "SessionRegisterIntentV1": (
            {
                "host_principal_id",
                "expected_generation",
                "provider",
                "capability_id",
                "visibility",
                "price_floor",
                "max_concurrent",
                "always_active",
                "idempotency_key_b64u",
            },
            set(),
        ),
        "SessionHeartbeatIntentV1": (
            {"host_principal_id", "expected_generation", "host_session_id"},
            set(),
        ),
        "SessionDeregisterIntentV1": (
            {"host_principal_id", "expected_generation", "host_session_id", "idempotency_key_b64u"},
            set(),
        ),
        "HostPrincipalResultV1": (
            {
                "schema_version",
                "host_principal_id",
                "host_principal_generation",
                "status",
                "expires_at",
                "policy_version",
            },
            set(),
        ),
        "HostBindingErrorV1": ({"schema_version", "error", "retryable"}, set()),
        "HostInventoryItemV1": (
            {
                "host_principal_id",
                "status",
                "generation",
                "policy_version",
                "issued_at",
                "expires_at",
            },
            {"last_seen_bucket", "device_label"},
        ),
        "HostInventoryPageV1": ({"schema_version", "items"}, {"next_cursor"}),
        "HostPrincipalDetailV1": (
            {
                "host_principal_id",
                "status",
                "generation",
                "policy_version",
                "issued_at",
                "expires_at",
                "jwk_thumbprint",
            },
            {"last_seen_bucket", "device_label"},
        ),
        "HostRecoveryResultV1": ({"revoked", "replacement"}, set()),
        "HostSessionResultV1": (
            {"host_session_id", "host_principal_id", "host_principal_generation"},
            set(),
        ),
        "HostHeartbeatResultV1": ({"host_session_id", "accepted_generation", "status"}, set()),
        "HostSessionDeregisterResultV1": ({"host_session_id", "status"}, set()),
    }

    assert {
        name: (set(wire_contract(name).required_fields), set(wire_contract(name).optional_fields))
        for name in expected
    } == expected


def test_wire_dto_parser_rejects_missing_extra_duplicate_and_wrong_schema() -> None:
    valid = {
        "schema_version": "host-binding-v1",
        "challenge_id_b64u": _b64u(b"c" * 32),
        "signatures": {"new": _b64u(b"s" * 64)},
    }
    assert parse_wire_dto("HostProofSubmissionV1", rfc8785.dumps(valid)) == valid
    for invalid in (
        {key: value for key, value in valid.items() if key != "signatures"},
        {**valid, "owner": "attacker"},
        {**valid, "schema_version": "host-binding-v2"},
    ):
        with pytest.raises(HostProofRefused):
            parse_wire_dto("HostProofSubmissionV1", rfc8785.dumps(invalid))
    with pytest.raises(HostProofRefused):
        parse_wire_dto(
            "HostProofSubmissionV1",
            b'{"schema_version":"host-binding-v1","challenge_id_b64u":"x",'
            b'"signatures":{},"signatures":{}}',
        )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_wire_dto_parser_rejects_non_finite_i_json_numbers(constant: str) -> None:
    document = (
        '{"host_principal_id":"hp_1","expected_generation":1,'
        '"provider":"local","capability_id":"cap:model","visibility":"self",'
        f'"price_floor":{constant},"max_concurrent":1,"always_active":false,'
        f'"idempotency_key_b64u":"{_b64u(b"i" * 32)}"}}'
    )
    with pytest.raises(HostProofRefused):
        parse_wire_dto("SessionRegisterIntentV1", document)


def test_challenge_request_closes_operation_and_nested_intent_semantics() -> None:
    valid_intent = {
        "idempotency_key_b64u": _b64u(b"i" * 32),
        "public_jwk": _jwk(_key(1)),
        "device_label": "Laptop",
    }
    valid = {
        "schema_version": "host-binding-v1",
        "operation": "enroll",
        "intent": valid_intent,
    }
    assert parse_wire_dto("HostChallengeRequestV1", rfc8785.dumps(valid)) == valid

    for invalid in (
        {**valid, "operation": "admin_override"},
        {**valid, "intent": {**valid_intent, "idempotency_key_b64u": "short"}},
        {**valid, "intent": {**valid_intent, "device_label": "e\u0301"}},
        {**valid, "intent": {**valid_intent, "public_jwk": {**_jwk(_key(1)), "alg": "EdDSA"}}},
    ):
        with pytest.raises(HostProofRefused):
            parse_wire_dto("HostChallengeRequestV1", rfc8785.dumps(invalid))


def test_session_registration_closes_current_host_pool_enums_types_and_ranges() -> None:
    valid = {
        "host_principal_id": "hp_1",
        "expected_generation": 1,
        "provider": "local",
        "capability_id": "goal_planner:model",
        "visibility": "self",
        "price_floor": None,
        "max_concurrent": 1,
        "always_active": False,
        "idempotency_key_b64u": _b64u(b"i" * 32),
    }
    assert parse_wire_dto("SessionRegisterIntentV1", rfc8785.dumps(valid)) == valid

    for field, value in (
        ("provider", "unknown"),
        ("visibility", "public"),
        ("expected_generation", True),
        ("max_concurrent", 0),
        ("always_active", 1),
        ("price_floor", -0.01),
        ("max_concurrent", 2_147_483_648),
        ("price_floor", 1_000_000_000_000),
        ("price_floor", 0.0000004),
        ("price_floor", 1.2345678),
        ("capability_id", ""),
    ):
        with pytest.raises(HostProofRefused):
            parse_wire_dto("SessionRegisterIntentV1", rfc8785.dumps({**valid, field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_concurrent", 2_147_483_647),
        ("price_floor", 0),
        ("price_floor", 0.000001),
        ("price_floor", 999_999_999_999.1234),
    ],
)
def test_session_registration_accepts_exact_postgres_numeric_boundaries(
    field: str,
    value: int | float,
) -> None:
    valid = {
        "host_principal_id": "hp_1",
        "expected_generation": 1,
        "provider": "local",
        "capability_id": "goal_planner:model",
        "visibility": "self",
        "price_floor": None,
        "max_concurrent": 1,
        "always_active": False,
        "idempotency_key_b64u": _b64u(b"i" * 32),
    }

    parsed = parse_wire_dto("SessionRegisterIntentV1", rfc8785.dumps({**valid, field: value}))

    assert parsed[field] == value


def test_i_json_safe_integer_domain_rejects_oversized_numbers_without_overflow() -> None:
    huge = "1" + "0" * 1000
    document = (
        '{"host_principal_id":"hp_1","expected_generation":1,'
        '"provider":"local","capability_id":"cap:model","visibility":"self",'
        f'"price_floor":{huge},"max_concurrent":1,"always_active":false,'
        f'"idempotency_key_b64u":"{_b64u(b"i" * 32)}"}}'
    )
    with pytest.raises(HostProofRefused):
        parse_wire_dto("SessionRegisterIntentV1", document)

    principal = f'{{"host_principal_id":"hp_1","expected_generation":{huge}}}'
    with pytest.raises(HostProofRefused):
        parse_wire_dto("PrincipalIntentV1", principal)


def test_revocation_reason_is_fail_closed_until_spec_names_allowlisted_codes() -> None:
    valid = {
        "host_principal_id": "hp_1",
        "expected_generation": 1,
        "idempotency_key_b64u": _b64u(b"i" * 32),
    }
    assert parse_wire_dto("RevokeIntentV1", rfc8785.dumps(valid)) == valid

    with pytest.raises(HostProofRefused):
        parse_wire_dto("RevokeIntentV1", rfc8785.dumps({**valid, "reason_code": "other"}))


def test_fixed_status_and_error_enums_fail_closed() -> None:
    for dto_name, valid, field in (
        (
            "HostHeartbeatResultV1",
            {"host_session_id": "hs_1", "accepted_generation": 1, "status": "active"},
            "status",
        ),
        (
            "HostSessionDeregisterResultV1",
            {"host_session_id": "hs_1", "status": "deleted"},
            "status",
        ),
        (
            "HostBindingErrorV1",
            {
                "schema_version": "host-binding-v1",
                "error": "host_binding_refused",
                "retryable": False,
            },
            "error",
        ),
        (
            "HostPrincipalResultV1",
            {
                "schema_version": "host-binding-v1",
                "host_principal_id": "hp_1",
                "host_principal_generation": 1,
                "status": "active",
                "expires_at": NOW + 300,
                "policy_version": "host-binding-v1",
            },
            "status",
        ),
    ):
        assert parse_wire_dto(dto_name, rfc8785.dumps(valid)) == valid
        with pytest.raises(HostProofRefused):
            parse_wire_dto(dto_name, rfc8785.dumps({**valid, field: "other"}))


def test_policy_version_and_thumbprint_encoding_are_exact() -> None:
    challenge = {
        "schema_version": "host-binding-v1",
        "challenge_id_b64u": _b64u(b"c" * 32),
        "signing_input_b64u": _b64u(b"signing-input"),
        "expires_at": NOW + 300,
        "policy_version": "host-binding-v1",
    }
    assert parse_wire_dto("HostChallengeV1", rfc8785.dumps(challenge)) == challenge
    with pytest.raises(HostProofRefused):
        parse_wire_dto(
            "HostChallengeV1",
            rfc8785.dumps({**challenge, "policy_version": "host-binding-v0"}),
        )

    detail = {
        "host_principal_id": "hp_1",
        "status": "active",
        "generation": 1,
        "policy_version": "host-binding-v1",
        "issued_at": NOW,
        "expires_at": NOW + 300,
        "jwk_thumbprint": _b64u(b"t" * 32),
    }
    assert parse_wire_dto("HostPrincipalDetailV1", rfc8785.dumps(detail)) == detail
    with pytest.raises(HostProofRefused):
        parse_wire_dto(
            "HostPrincipalDetailV1",
            rfc8785.dumps({**detail, "jwk_thumbprint": "not-canonical"}),
        )


@pytest.mark.parametrize(
    ("operation", "field"),
    [
        ("read", "host_principal_id"),
        ("revoke", "host_principal_id"),
        ("rotate", "host_principal_id"),
        ("renew", "host_principal_id"),
        ("recover", "host_principal_id"),
        ("session_heartbeat", "host_session_id"),
        ("session_deregister", "host_session_id"),
    ],
)
def test_substituted_route_id_must_equal_the_typed_intent_id(operation: str, field: str) -> None:
    intent = {field: "exact-id"}
    validate_route_path_id(operation, intent=intent, path_id="exact-id")
    with pytest.raises(HostProofRefused):
        validate_route_path_id(operation, intent=intent, path_id="other-id")


@pytest.mark.parametrize(
    "operation",
    [
        "enroll",
        "read",
        "revoke",
        "rotate",
        "renew",
        "recover",
        "session_register",
        "session_heartbeat",
        "session_deregister",
    ],
)
def test_each_proof_requiring_operation_verifies(operation: str) -> None:
    roles = operation_policy(operation).signature_roles
    keys = {role: _key(index + 1) for index, role in enumerate(sorted(roles))}
    binding = _binding(operation, keys=keys)

    _verify(binding, keys)


def test_inventory_cannot_construct_device_proof_signing_bytes() -> None:
    with pytest.raises(HostProofRefused):
        host_proof_signing_bytes(_binding("inventory", keys={}))


def test_signing_bytes_are_exact_rfc8785_bytes_with_domain_separation() -> None:
    binding = _binding()
    expected_payload = {
        "audience": binding.audience,
        "body_sha256": binding.body_sha256,
        "challenge_id_b64u": binding.challenge_id_b64u,
        "expected_generation": None,
        "expires_at": binding.expires_at,
        "host_principal_id": None,
        "issued_at": binding.issued_at,
        "issuer": binding.issuer,
        "key_thumbprints": binding.key_thumbprints,
        "method": "POST",
        "operation": "enroll",
        "path": "/v1/host-principals",
        "permission": "host:enroll",
        "policy_version": "host-binding-v1",
        "schema_version": "host-binding-v1",
        "subject": binding.subject,
    }
    expected = b"tinyassets.host-principal-proof.v1\0" + rfc8785.dumps(expected_payload)

    assert DOMAIN_SEPARATOR == b"tinyassets.host-principal-proof.v1\0"
    assert host_proof_signing_bytes(binding) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "host-binding-v2"),
        ("policy_version", "host-binding-v0"),
        ("operation", "recover"),
        ("permission", "host:manage"),
        ("issuer", "https://attacker.example"),
        ("subject", "user_OTHER"),
        ("audience", "https://tinyassets.io/mcp"),
        ("method", "GET"),
        ("path", "/v1/host-principals/{id}:read"),
        ("body_sha256", "sha256:" + "cd" * 32),
        ("key_thumbprints", {"new": _b64u(b"z" * 32)}),
        ("host_principal_id", "hp_OTHER"),
        ("expected_generation", 8),
        ("challenge_id_b64u", _b64u(b"x" * 32)),
        ("issued_at", NOW - 31),
        ("expires_at", NOW + 269),
    ],
)
def test_every_signed_binding_field_is_load_bearing(field: str, value: object) -> None:
    key = _key(1)
    original = _binding()
    tampered = replace(original, **{field: value})

    with pytest.raises(HostProofRefused):
        _verify(tampered, {"new": key}, submission=_submission(original, {"new": key}))


def test_unicode_normalization_variants_do_not_share_a_signature() -> None:
    key = _key(1)
    nfc = replace(_binding(), subject=unicodedata.normalize("NFC", "Cafe\u0301"))
    nfd = replace(nfc, subject=unicodedata.normalize("NFD", nfc.subject))
    assert nfc.subject != nfd.subject

    with pytest.raises(HostProofRefused):
        _verify(nfd, {"new": key}, submission=_submission(nfc, {"new": key}))


def test_exact_rfc8037_jwk_and_canonical_base64url_are_required() -> None:
    key = _key(1)
    binding = _binding()
    valid = _jwk(key)
    invalid_jwks = [
        {**valid, "alg": "EdDSA"},
        {**valid, "kty": "EC"},
        {**valid, "crv": "X25519"},
        {**valid, "x": valid["x"] + "="},
        {**valid, "x": _b64u(b"short")},
        {**valid, "x": "***"},
    ]

    assert canonical_b64u(valid["x"], size=32) == key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    for jwk in invalid_jwks:
        with pytest.raises(HostProofRefused):
            _verify(binding, {"new": key}, presented_jwks={"new": jwk})


@pytest.mark.parametrize("mutation", ["padding", "short", "extra_role", "missing_role"])
def test_signature_shape_and_exact_role_map_fail_closed(mutation: str) -> None:
    key = _key(1)
    binding = _binding()
    raw = json.loads(_submission(binding, {"new": key}))
    if mutation == "padding":
        raw["signatures"]["new"] += "="
    elif mutation == "short":
        raw["signatures"]["new"] = _b64u(b"short")
    elif mutation == "extra_role":
        raw["signatures"]["current"] = raw["signatures"]["new"]
    else:
        raw["signatures"] = {}

    with pytest.raises(HostProofRefused):
        _verify(binding, {"new": key}, submission=rfc8785.dumps(raw))


def test_rotation_requires_distinct_keys_signing_the_same_input_in_fixed_roles() -> None:
    keys = {"current": _key(1), "new": _key(2)}
    binding = _binding("rotate", keys=keys)
    _verify(binding, keys)

    raw = json.loads(_submission(binding, keys))
    raw["signatures"]["current"], raw["signatures"]["new"] = (
        raw["signatures"]["new"],
        raw["signatures"]["current"],
    )
    with pytest.raises(HostProofRefused):
        _verify(binding, keys, submission=rfc8785.dumps(raw))

    same_key_binding = _binding("rotate", keys={"current": _key(1), "new": _key(1)})
    with pytest.raises(HostProofRefused):
        _verify(same_key_binding, {"current": _key(1), "new": _key(1)})


def test_signature_without_the_domain_separator_is_refused() -> None:
    key = _key(1)
    binding = _binding()
    canonical_only = host_proof_signing_bytes(binding)[len(DOMAIN_SEPARATOR) :]
    with pytest.raises(HostProofRefused):
        _verify(
            binding,
            {"new": key},
            submission=_submission(binding, {"new": key}, signing_input=canonical_only),
        )


@pytest.mark.parametrize(
    "binding",
    [
        replace(_binding(), issued_at=NOW + 1),
        replace(_binding(), expires_at=NOW),
        replace(_binding(), expires_at=NOW + 271),
    ],
)
def test_proof_time_window_is_current_and_at_most_five_minutes(
    binding: HostProofBindingV1,
) -> None:
    with pytest.raises(HostProofRefused):
        _verify(binding, {"new": _key(1)})


def test_transport_signing_input_must_be_exact_and_canonical() -> None:
    key = _key(1)
    binding = _binding()
    canonical = _b64u(host_proof_signing_bytes(binding))
    for variant in (canonical + "=", _b64u(host_proof_signing_bytes(binding) + b"x")):
        with pytest.raises(HostProofRefused):
            _verify(binding, {"new": key}, signing_input_b64u=variant)


def test_nonce_is_consumed_only_after_valid_proof_and_replay_is_refused() -> None:
    key = _key(1)
    binding = _binding()
    consumed: set[str] = set()

    def consume_once(nonce: str) -> bool:
        if nonce in consumed:
            return False
        consumed.add(nonce)
        return True

    _verify(binding, {"new": key}, consume_once=consume_once)
    with pytest.raises(HostProofRefused):
        _verify(binding, {"new": key}, consume_once=consume_once)
    assert consumed == {binding.challenge_id_b64u}

    invalid = bytearray(_submission(binding, {"new": key}))
    invalid[-3] = ord("A") if invalid[-3] != ord("A") else ord("B")
    calls: list[str] = []
    with pytest.raises(HostProofRefused):
        _verify(
            binding,
            {"new": key},
            submission=bytes(invalid),
            consume_once=lambda nonce: calls.append(nonce) is None,
        )
    assert calls == []


def test_consume_backend_failure_propagates_instead_of_becoming_proof_refusal() -> None:
    def unavailable(_nonce: str) -> bool:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        _verify(_binding(), {"new": _key(1)}, consume_once=unavailable)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"host-binding-v1","schema_version":"host-binding-v1",'
        b'"challenge_id_b64u":"x","signatures":{}}',
        b'{"schema_version":"host-binding-v1","challenge_id_b64u":"x",'
        b'"signatures":{"new":"a","new":"b"}}',
        b'{"schema_version":"host-binding-v1","challenge_id_b64u":"\\ud800",'
        b'"signatures":{"new":"a"}}',
    ],
)
def test_duplicate_json_members_and_invalid_unicode_are_refused(raw: bytes) -> None:
    with pytest.raises(HostProofRefused):
        verify_host_proof(
            raw,
            binding=_binding(),
            public_jwks={"new": _jwk(_key(1))},
            signing_input_b64u=_b64u(host_proof_signing_bytes(_binding())),
            now=NOW,
            consume_once=lambda _nonce: True,
        )


def test_non_finite_numeric_binding_is_refused() -> None:
    binding = replace(_binding(), issued_at=float("nan"))
    with pytest.raises(HostProofRefused):
        _verify(binding, {"new": _key(1)})


def test_enrollment_and_post_enrollment_issuance_limits_are_separate() -> None:
    assert ENROLLMENT_CHALLENGE_LIMITS.max_live == 5
    assert ENROLLMENT_CHALLENGE_LIMITS.principal_per_minute == 10
    assert ENROLLMENT_CHALLENGE_LIMITS.source_network_per_minute == 30
    assert POST_ENROLLMENT_NONCE_LIMITS.max_live == 5
    assert POST_ENROLLMENT_NONCE_LIMITS.principal_per_minute == 60
    assert POST_ENROLLMENT_NONCE_LIMITS.source_network_per_minute == 600
    assert ENROLLMENT_CHALLENGE_LIMITS is not POST_ENROLLMENT_NONCE_LIMITS


def test_refusal_work_is_size_bounded_and_has_one_non_enumerating_public_shape() -> None:
    key = _key(1)
    binding = _binding()
    failures = []
    for action in (
        lambda: operation_policy("unknown"),
        lambda: _verify(replace(binding, expires_at=NOW), {"new": key}),
        lambda: _verify(binding, {"new": key}, consume_once=lambda _nonce: False),
        lambda: verify_host_proof(
            b"{" + b"x" * MAX_SUBMISSION_BYTES + b"}",
            binding=binding,
            public_jwks={"new": _jwk(key)},
            signing_input_b64u=_b64u(host_proof_signing_bytes(binding)),
            now=NOW,
            consume_once=lambda _nonce: True,
        ),
    ):
        with pytest.raises(HostProofRefused) as raised:
            action()
        failures.append((str(raised.value), raised.value.public_error))

    assert failures == [("host binding refused", HOST_BINDING_REFUSAL)] * 4


@pytest.mark.parametrize(
    ("failure_class", "elapsed"),
    [
        ("authentication", 0.001),
        ("rate_limit", 0.002),
        ("absence", 0.003),
        ("mismatch", 0.004),
        ("replay", 0.009),
    ],
)
def test_shared_refusal_timing_class_is_reason_agnostic(
    failure_class: str,
    elapsed: float,
) -> None:
    assert failure_class
    slept: list[float] = []

    with pytest.raises(HostProofRefused):
        refuse_host_binding(
            started_at=10.0,
            monotonic=lambda: 10.0 + elapsed,
            sleeper=slept.append,
        )

    assert elapsed + slept[0] == pytest.approx(REFUSAL_BUCKET_SECONDS)


@pytest.mark.parametrize("failure", ["mismatch", "replay"])
def test_verifier_uses_shared_refusal_timing_class(failure: str) -> None:
    key = _key(1)
    binding = _binding()
    slept: list[float] = []
    elapsed = 0.003 if failure == "mismatch" else 0.008
    clocks = iter([10.0, 10.0 + elapsed])
    kwargs = (
        {"submission": _submission(replace(binding, subject="other"), {"new": key})}
        if failure == "mismatch"
        else {"consume_once": lambda _nonce: False}
    )

    with pytest.raises(HostProofRefused):
        _verify(
            binding,
            {"new": key},
            monotonic=lambda: next(clocks),
            sleeper=slept.append,
            **kwargs,
        )

    assert elapsed + slept[0] == pytest.approx(REFUSAL_BUCKET_SECONDS)


def test_over_budget_refusal_becomes_an_operational_timing_error() -> None:
    with pytest.raises(HostProofTimingExceeded):
        refuse_host_binding(
            started_at=10.0,
            monotonic=lambda: 10.0 + REFUSAL_BUCKET_SECONDS + 0.001,
            sleeper=lambda _seconds: pytest.fail("over-budget refusal must not be padded"),
        )


def test_valid_enrollment_proof_verifies_before_one_use_consumption() -> None:
    key = _key(1)
    binding = _binding()
    observed: list[str] = []

    _verify(
        binding,
        {"new": key},
        consume_once=lambda nonce: observed.append(nonce) is None,
    )

    assert observed == [binding.challenge_id_b64u]


class _ResponseLost(RuntimeError):
    pass


class _EnrollmentContractStore:
    """Atomic shared-store model; production persistence remains task 3.2."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumed: set[str] = set()
        self._receipts: dict[str, tuple[str, HostPrincipalResultV1, int]] = {}
        self._principals: dict[tuple[str, str, str], HostPrincipalResultV1] = {}
        self._key_owners: dict[tuple[str, str], str] = {}
        self.mutation_count = 0
        self.requests: list[HostEnrollmentTransactionRequest] = []
        self.fail_before_commit_once = False
        self.lose_response_after_commit_once = False

    def commit_enrollment(
        self, request: HostEnrollmentTransactionRequest
    ) -> HostEnrollmentTransactionOutcome:
        lose_response = False
        with self._lock:
            self.requests.append(request)
            if request.challenge_id_b64u in self._consumed:
                return HostEnrollmentTransactionOutcome("replayed")

            consumed = set(self._consumed)
            receipts = copy.copy(self._receipts)
            principals = copy.copy(self._principals)
            key_owners = copy.copy(self._key_owners)
            mutation_count = self.mutation_count
            consumed.add(request.challenge_id_b64u)

            receipt = receipts.get(request.idempotency_lookup_hash)
            if receipt is not None and receipt[2] > request.transaction_time:
                binding_hash, result, _expiry = receipt
                self._consumed = consumed
                if binding_hash != request.idempotency_binding_hash:
                    return HostEnrollmentTransactionOutcome("idempotency_conflict")
                return HostEnrollmentTransactionOutcome("committed", result)
            receipts.pop(request.idempotency_lookup_hash, None)

            key_owner = key_owners.get((request.issuer, request.key_thumbprint))
            if key_owner is not None and key_owner != request.subject:
                self._consumed = consumed
                return HostEnrollmentTransactionOutcome("refused")

            principal_key = (request.issuer, request.subject, request.key_thumbprint)
            result = principals.get(principal_key)
            if result is None:
                result = request.candidate_result
                principals[principal_key] = result
                key_owners[(request.issuer, request.key_thumbprint)] = request.subject
                mutation_count += 1
            receipts[request.idempotency_lookup_hash] = (
                request.idempotency_binding_hash,
                result,
                request.idempotency_expires_at,
            )
            if self.fail_before_commit_once:
                self.fail_before_commit_once = False
                raise RuntimeError("injected pre-commit crash")

            self._consumed = consumed
            self._receipts = receipts
            self._principals = principals
            self._key_owners = key_owners
            self.mutation_count = mutation_count
            if self.lose_response_after_commit_once:
                self.lose_response_after_commit_once = False
                lose_response = True

        if lose_response:
            raise _ResponseLost("injected response loss after commit")
        return HostEnrollmentTransactionOutcome("committed", result)


def _enrollment(
    store: _EnrollmentContractStore,
    *,
    principal_id: str = "hp_winner",
    enabled: bool = True,
) -> HostEnrollmentCoordinator:
    return HostEnrollmentCoordinator(
        store=store,
        idempotency_hmac_key=b"k" * 32,
        writers_enabled=enabled,
        new_principal_id=lambda: principal_id,
    )


def _complete_enrollment(
    coordinator: HostEnrollmentCoordinator,
    key: Ed25519PrivateKey,
    *,
    subject: str = "user_01HOSTOWNER",
    challenge_seed: int = 1,
    idempotency_seed: int = 9,
    device_label: str | None = None,
    now: int = NOW,
) -> HostPrincipalResultV1:
    intent: dict[str, object] = {
        "idempotency_key_b64u": _b64u(bytes([idempotency_seed]) * 32),
        "public_jwk": _jwk(key),
    }
    if device_label is not None:
        intent["device_label"] = device_label
    canonical_intent = rfc8785.dumps(intent)
    policy = operation_policy("enroll")
    binding = HostProofBindingV1(
        schema_version="host-binding-v1",
        policy_version="host-binding-v1",
        operation="enroll",
        permission=policy.permission,
        issuer=ISSUER,
        subject=subject,
        audience=AUDIENCE,
        method=policy.method,
        path=policy.path,
        body_sha256="sha256:" + hashlib.sha256(canonical_intent).hexdigest(),
        key_thumbprints={"new": jwk_thumbprint(_jwk(key))},
        host_principal_id=None,
        expected_generation=None,
        challenge_id_b64u=_b64u(bytes([challenge_seed]) * 32),
        issued_at=now - 30,
        expires_at=now + 270,
    )
    return coordinator.complete_enrollment(
        submission_json=_submission(binding, {"new": key}),
        binding=binding,
        enroll_intent=intent,
        signing_input_b64u=_b64u(host_proof_signing_bytes(binding)),
        now=now,
    )


def test_enrollment_writers_default_dark_and_scrub_raw_idempotency_material() -> None:
    store = _EnrollmentContractStore()
    key = _key(1)
    with pytest.raises(HostEnrollmentWritersDisabled):
        _complete_enrollment(_enrollment(store, enabled=False), key)
    assert store.requests == []

    _complete_enrollment(_enrollment(store), key)
    request_text = repr(store.requests[-1])
    assert _b64u(bytes([9]) * 32) not in request_text
    assert repr(b"k" * 32) not in request_text


def test_enrollment_crash_and_response_loss_converge_with_fresh_challenge() -> None:
    store = _EnrollmentContractStore()
    coordinator = _enrollment(store)
    key = _key(1)
    store.fail_before_commit_once = True
    with pytest.raises(RuntimeError, match="pre-commit"):
        _complete_enrollment(coordinator, key, challenge_seed=1)
    assert store.mutation_count == 0

    store.lose_response_after_commit_once = True
    with pytest.raises(_ResponseLost):
        _complete_enrollment(coordinator, key, challenge_seed=1)
    assert store.mutation_count == 1
    with pytest.raises(HostProofRefused):
        _complete_enrollment(coordinator, key, challenge_seed=1)

    recovered = _complete_enrollment(coordinator, key, challenge_seed=2)
    assert recovered.host_principal_id == "hp_winner"
    assert recovered.host_principal_generation == 1
    assert store.mutation_count == 1


def test_enrollment_changed_body_conflicts_until_receipt_expires() -> None:
    store = _EnrollmentContractStore()
    coordinator = _enrollment(store)
    key = _key(1)
    original = _complete_enrollment(coordinator, key, challenge_seed=1)
    with pytest.raises(HostEnrollmentIdempotencyConflict):
        _complete_enrollment(
            coordinator, key, challenge_seed=2, device_label="changed", now=NOW + 86_399
        )

    after_expiry = _complete_enrollment(
        coordinator, key, challenge_seed=3, device_label="changed", now=NOW + 86_400
    )
    assert after_expiry == original
    assert store.mutation_count == 1


def test_enrollment_concurrency_has_one_winner_but_distinct_devices_do_not_merge() -> None:
    store = _EnrollmentContractStore()
    key = _key(1)
    servers = (_enrollment(store, principal_id="hp_a"), _enrollment(store, principal_id="hp_b"))
    barrier = threading.Barrier(16)

    def enroll(index: int) -> HostPrincipalResultV1:
        barrier.wait()
        return _complete_enrollment(
            servers[index % 2],
            key,
            challenge_seed=index + 1,
            idempotency_seed=index + 1,
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(enroll, range(16)))
    assert len({result.host_principal_id for result in results}) == 1
    assert {result.host_principal_generation for result in results} == {1}
    assert store.mutation_count == 1

    other = _complete_enrollment(
        _enrollment(store, principal_id="hp_other"),
        _key(2),
        challenge_seed=20,
        idempotency_seed=20,
    )
    assert other.host_principal_id not in {result.host_principal_id for result in results}
    assert store.mutation_count == 2


def test_cross_subject_key_reuse_is_non_enumerating() -> None:
    store = _EnrollmentContractStore()
    key = _key(1)
    first = _complete_enrollment(_enrollment(store, principal_id="hp_private"), key)
    with pytest.raises(HostEnrollmentRefused) as refusal:
        _complete_enrollment(
            _enrollment(store, principal_id="hp_attacker"),
            key,
            subject="user_01OTHER",
            challenge_seed=2,
            idempotency_seed=2,
        )
    assert refusal.value.public_error == HOST_BINDING_REFUSAL
    assert first.host_principal_id not in repr(refusal.value)
    assert "user_01HOSTOWNER" not in repr(refusal.value)

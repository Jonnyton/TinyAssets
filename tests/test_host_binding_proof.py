from __future__ import annotations

import base64
import json
import unicodedata
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
    HostProofBindingV1,
    HostProofRefused,
    canonical_b64u,
    host_proof_signing_bytes,
    jwk_thumbprint,
    operation_policy,
    verify_host_proof,
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
    role_keys = keys or {"new": _key(1)}
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
    message = signing_input or host_proof_signing_bytes(binding)
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
) -> None:
    verify_host_proof(
        submission or _submission(binding, keys),
        binding=binding,
        public_jwks=presented_jwks or {role: _jwk(key) for role, key in keys.items()},
        signing_input_b64u=signing_input_b64u or _b64u(host_proof_signing_bytes(binding)),
        now=NOW,
        consume_once=consume_once,
    )


def test_closed_operation_route_scope_and_signature_role_matrix() -> None:
    expected = {
        "enroll": ("POST", "/v1/host-principals", "host:enroll", frozenset({"new"})),
        "inventory": ("GET", "/v1/host-principals", "host:manage", frozenset()),
        "read": ("POST", "/v1/host-principals/{id}:read", "host:manage", frozenset({"current"})),
        "revoke": (
            "POST",
            "/v1/host-principals/{id}:revoke",
            "host:manage",
            frozenset({"current"}),
        ),
        "rotate": (
            "POST",
            "/v1/host-principals/{id}:rotate",
            "host:manage",
            frozenset({"current", "new"}),
        ),
        "renew": ("POST", "/v1/host-principals/{id}:renew", "host:manage", frozenset({"current"})),
        "recover": ("POST", "/v1/host-principals/{id}:recover", "host:recover", frozenset({"new"})),
        "session_register": ("POST", "/v1/host-sessions", "host:manage", frozenset({"current"})),
        "session_heartbeat": (
            "POST",
            "/v1/host-sessions/{id}:heartbeat",
            "host:manage",
            frozenset({"current"}),
        ),
        "session_deregister": (
            "POST",
            "/v1/host-sessions/{id}:deregister",
            "host:manage",
            frozenset({"current"}),
        ),
    }

    assert {
        name: (policy.method, policy.path, policy.permission, policy.signature_roles)
        for name in expected
        if (policy := operation_policy(name))
    } == expected
    with pytest.raises(HostProofRefused):
        operation_policy("owner_selected_admin")


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

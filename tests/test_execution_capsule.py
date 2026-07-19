"""ExecutionCapsuleV1 contract and integrity tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import struct
from datetime import UTC, datetime
from typing import Any

import pytest
from nacl.signing import SigningKey


def _payload() -> dict[str, Any]:
    from tinyassets.runtime.execution_capsule import canonicalize_jcs

    inline_request = {
        "kind": "isolated_execution_request",
        "schema_version": 3,
        "prompt": "repair the failing branch",
        "temperature": 0.25,
        "tags": ["patch", "review"],
    }
    request_bytes = canonicalize_jcs(inline_request)
    return {
        "schema_version": "execution-capsule/v1",
        "capsule_id": "123e4567-e89b-42d3-a456-426614174000",
        "job_id": "123e4567-e89b-42d3-a456-426614174001",
        "attempt": 2,
        "audience_daemon_id": "daemon:builder-1",
        "owner_user_id": "user:owner-1",
        "universe_scope": {
            "universe_id": "universe:alpha",
            "capability_id": "cap:alpha:execute-7",
            "scope_version": 4,
            "permissions": [
                "read_source",
                "execute_repo",
                "produce_patch",
                "produce_artifact",
            ],
        },
        "branch": {
            "branch_definition_id": "branch:repair-loop",
            "branch_version_sha256": "1" * 64,
        },
        "node": {
            "node_id": "node:repair",
            "node_version_sha256": "2" * 64,
            "node_kind": "coding",
        },
        "base": {
            "vcs": "git",
            "object_format": "sha1",
            "commit": "3" * 40,
            "tree": "4" * 40,
        },
        "source_blob": {
            "ref": "blob:source:abc123",
            "media_type": "application/vnd.tinyassets.git-bundle.v1",
            "content_sha256": "5" * 64,
            "transport_sha256": "6" * 64,
            "size_bytes": 123_456,
            "manifest_sha256": "7" * 64,
            "confidentiality": "owner_private",
            "encryption": {
                "scheme": "x25519-chacha20poly1305-v1",
                "recipient_device_key_id": "device-key:builder-1",
                "wrapped_content_key_b64": base64.b64encode(b"wrapped-key").decode(),
            },
            "producer": {
                "daemon_id": "daemon:source-1",
                "device_key_id": "device-key:source-1",
                "signature_b64": base64.b64encode(b"s" * 64).decode(),
            },
        },
        "execution_request": {
            "schema_version": 3,
            "ref": None,
            "inline": inline_request,
            "sha256": hashlib.sha256(request_bytes).hexdigest(),
            "size_bytes": len(request_bytes),
        },
        "allowed_capability": {
            "class": "repo",
            "repo_mode": "coding",
            "action_policy_id": "policy:actions:1",
            "action_policy_sha256": "8" * 64,
            "runner_policy_sha256": "9" * 64,
            "image_digest": f"sha256:{'a' * 64}",
        },
        "model_broker_route": {
            "route_id": "route:model:1",
            "route_version": 5,
            "policy_sha256": "b" * 64,
            "grant_ref": "grant:model:abc123",
            "allowed_model_classes": ["reasoning", "coding"],
            "max_calls": 12,
            "max_input_tokens": 200_000,
            "max_output_tokens": 40_000,
            "expires_at": "2026-07-19T01:00:00Z",
        },
        "resource_limits": {
            "cpu_millis": 1_000,
            "memory_bytes": 2 * 1024**3,
            "pids": 256,
            "workspace_bytes": 8 * 1024**3,
            "workspace_inodes": 200_000,
            "tmpfs_bytes": 512 * 1024**2,
            "wall_time_seconds": 1_800,
            "stdout_bytes": 25 * 1024**2,
            "stderr_bytes": 25 * 1024**2,
            "patch_bytes": 5 * 1024**2,
            "patch_files": 200,
            "patch_changed_lines": 50_000,
            "network": "model_broker_only",
            "egress_policy_id": "policy:egress:1",
            "egress_policy_sha256": "c" * 64,
        },
        "lease": {
            "lease_id": "123e4567-e89b-42d3-a456-426614174002",
            "fence": 17,
            "issued_at": "2026-07-19T00:00:00Z",
            "expires_at": "2026-07-19T01:00:00Z",
        },
        "issued_at": "2026-07-19T00:00:00Z",
        "not_before": "2026-07-19T00:00:00Z",
        "expires_at": "2026-07-19T01:00:00Z",
    }


def test_jcs_matches_rfc8785_primitive_and_utf16_sorting_examples() -> None:
    try:
        from tinyassets.runtime.execution_capsule import canonicalize_jcs
    except ModuleNotFoundError as exc:
        pytest.fail(f"execution capsule module is not implemented: {exc}")

    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "string": "€$\u000f\nA'B\"\\\\\"/",
        "literals": [None, True, False],
    }
    expected = (
        '{"literals":[null,true,false],'
        '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert canonicalize_jcs(value) == expected.encode()

    sorted_keys = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "😀": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    encoded = canonicalize_jcs(sorted_keys).decode()
    assert list(__import__("json").loads(encoded)) == [
        "\r",
        "1",
        "\u0080",
        "ö",
        "€",
        "😀",
        "דּ",
    ]


@pytest.mark.parametrize(
    ("ieee754_hex", "expected"),
    [
        ("0000000000000000", "0"),
        ("8000000000000000", "0"),
        ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"),
        ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"),
        ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"),
        ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"),
        ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"),
        ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"),
        ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"),
        ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"),
        ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"),
        ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ],
)
def test_jcs_matches_rfc8785_appendix_b_binary64_samples(
    ieee754_hex: str, expected: str
) -> None:
    from tinyassets.runtime.execution_capsule import canonicalize_jcs

    value = struct.unpack(">d", bytes.fromhex(ieee754_hex))[0]
    assert canonicalize_jcs(value) == expected.encode()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_jcs_rejects_non_finite_numbers(value: float) -> None:
    from tinyassets.runtime.execution_capsule import (
        CapsuleCanonicalizationError,
        canonicalize_jcs,
    )

    with pytest.raises(CapsuleCanonicalizationError):
        canonicalize_jcs(value)


def test_valid_capsule_is_stably_hashed_signed_bound_and_accepted() -> None:
    try:
        from tinyassets.runtime.execution_capsule import (
            create_execution_capsule,
            verify_execution_capsule,
        )
    except ImportError as exc:
        pytest.fail(f"execution capsule signing API is not implemented: {exc}")

    signing_key = SigningKey.generate()
    payload = _payload()
    capsule = create_execution_capsule(
        payload,
        signing_key=signing_key,
        signing_key_id="platform-key:1",
    )

    canonical_payload = __import__(
        "tinyassets.runtime.execution_capsule", fromlist=["canonicalize_jcs"]
    ).canonicalize_jcs(payload)
    payload_digest = hashlib.sha256(canonical_payload).digest()
    assert capsule["integrity"]["capsule_sha256"] == payload_digest.hex()
    signature = base64.b64decode(capsule["integrity"]["signature_b64"], validate=True)
    signing_key.verify_key.verify(
        b"tinyassets.execution-capsule.v1\0" + payload_digest,
        signature,
    )

    verified = verify_execution_capsule(
        _wire_bytes(capsule),
        verify_key=signing_key.verify_key,
        expected_signing_key_id="platform-key:1",
        signing_key_active=True,
        expected_audience_daemon_id="daemon:builder-1",
        expected_job_id="123e4567-e89b-42d3-a456-426614174001",
        expected_lease_fence=17,
        supported_request_schema_versions=frozenset({3}),
        now=datetime(2026, 7, 19, 0, 30, tzinfo=UTC),
    )
    assert verified == capsule


def _signed_capsule(signing_key: SigningKey) -> dict[str, Any]:
    from tinyassets.runtime.execution_capsule import create_execution_capsule

    return create_execution_capsule(
        _payload(), signing_key=signing_key, signing_key_id="platform-key:1"
    )


def _wire_bytes(capsule: dict[str, Any]) -> bytes:
    return json.dumps(
        capsule, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sync_inline_request(capsule: dict[str, Any]) -> None:
    from tinyassets.runtime.execution_capsule import canonicalize_jcs

    request = capsule["payload"]["execution_request"]
    request_bytes = canonicalize_jcs(request["inline"])
    request["sha256"] = hashlib.sha256(request_bytes).hexdigest()
    request["size_bytes"] = len(request_bytes)


def _resign(capsule: dict[str, Any], signing_key: SigningKey) -> dict[str, Any]:
    from tinyassets.runtime.execution_capsule import (
        CAPSULE_DOMAIN_SEPARATOR,
        canonicalize_jcs,
    )

    signed = copy.deepcopy(capsule)
    digest = hashlib.sha256(canonicalize_jcs(signed["payload"])).digest()
    signed["integrity"]["capsule_sha256"] = digest.hex()
    signed["integrity"]["signature_b64"] = base64.b64encode(
        signing_key.sign(CAPSULE_DOMAIN_SEPARATOR + digest).signature
    ).decode()
    return signed


def _verification_arguments(
    signing_key: SigningKey, **overrides: Any
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "verify_key": signing_key.verify_key,
        "expected_signing_key_id": "platform-key:1",
        "signing_key_active": True,
        "expected_audience_daemon_id": "daemon:builder-1",
        "expected_job_id": "123e4567-e89b-42d3-a456-426614174001",
        "expected_lease_fence": 17,
        "supported_request_schema_versions": frozenset({3}),
        "now": datetime(2026, 7, 19, 0, 30, tzinfo=UTC),
    }
    arguments.update(overrides)
    return arguments


def _verify(capsule: dict[str, Any], signing_key: SigningKey, **overrides: Any) -> Any:
    from tinyassets.runtime.execution_capsule import verify_execution_capsule

    arguments = _verification_arguments(signing_key, **overrides)
    return verify_execution_capsule(_wire_bytes(capsule), **arguments)


def _leaf_paths(value: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if type(value) is dict:
        paths: list[tuple[Any, ...]] = []
        for key, item in value.items():
            paths.extend(_leaf_paths(item, prefix + (key,)))
        return paths
    if type(value) is list:
        paths = []
        for index, item in enumerate(value):
            paths.extend(_leaf_paths(item, prefix + (index,)))
        return paths
    return [prefix]


def _mutate_leaf(value: Any) -> Any:
    if value is None:
        return "mutated"
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is float:
        return value + 0.125
    if type(value) is str:
        return value + "-mutated"
    raise AssertionError(f"unexpected leaf type {type(value).__name__}")


def _replace_at_path(root: Any, path: tuple[Any, ...], value: Any) -> None:
    target = root
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("member", "duplicate"),
    [
        (
            b'"audience_daemon_id":"daemon:builder-1"',
            b'"audience_daemon_id":"daemon:first-wins",'
            b'"audience_daemon_id":"daemon:builder-1"',
        ),
        (
            b'"owner_user_id":"user:owner-1"',
            b'"owner_user_id":"user:first-wins",'
            b'"owner_user_id":"user:owner-1"',
        ),
    ],
    ids=["audience", "owner"],
)
def test_raw_wire_duplicate_members_are_rejected_before_semantic_decoding(
    member: bytes, duplicate: bytes
) -> None:
    from tinyassets.runtime.execution_capsule import (
        CapsuleSchemaError,
        verify_execution_capsule,
    )

    signing_key = SigningKey.generate()
    wire = _wire_bytes(_signed_capsule(signing_key))
    assert wire.count(member) == 1
    ambiguous_wire = wire.replace(member, duplicate, 1)

    with pytest.raises(CapsuleSchemaError, match="duplicate JSON member"):
        verify_execution_capsule(
            ambiguous_wire, **_verification_arguments(signing_key)
        )


def test_public_verifier_rejects_decoded_dicts_to_force_raw_wire_parsing() -> None:
    from tinyassets.runtime.execution_capsule import (
        CapsuleSchemaError,
        verify_execution_capsule,
    )

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    with pytest.raises(CapsuleSchemaError, match="raw JSON bytes"):
        verify_execution_capsule(capsule, **_verification_arguments(signing_key))


def test_mutating_every_signed_payload_field_fails_ed25519_verification() -> None:
    from tinyassets.runtime.execution_capsule import (
        CapsuleIntegrityError,
        canonicalize_jcs,
    )

    signing_key = SigningKey.generate()
    original = _signed_capsule(signing_key)
    paths = _leaf_paths(original["payload"])
    assert len(paths) >= 75, "fixture must cover every V1 field and nested variant"

    for path in paths:
        tampered = copy.deepcopy(original)
        target = tampered["payload"]
        for component in path:
            target = target[component]
        _replace_at_path(tampered["payload"], path, _mutate_leaf(target))
        digest = hashlib.sha256(canonicalize_jcs(tampered["payload"])).digest()
        tampered["integrity"]["capsule_sha256"] = digest.hex()
        with pytest.raises(CapsuleIntegrityError, match="signature"):
            _verify(tampered, signing_key)


def test_mutated_signature_is_rejected_loudly() -> None:
    from tinyassets.runtime.execution_capsule import CapsuleIntegrityError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    signature = bytearray(base64.b64decode(capsule["integrity"]["signature_b64"]))
    signature[0] ^= 1
    capsule["integrity"]["signature_b64"] = base64.b64encode(signature).decode()

    with pytest.raises(CapsuleIntegrityError, match="signature"):
        _verify(capsule, signing_key)


def test_payload_mutation_without_rehash_is_rejected_by_content_hash() -> None:
    from tinyassets.runtime.execution_capsule import CapsuleIntegrityError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["node"]["node_kind"] = "different-kind"

    with pytest.raises(CapsuleIntegrityError, match="capsule_sha256"):
        _verify(capsule, signing_key)


@pytest.mark.parametrize(
    ("overrides", "binding_name"),
    [
        ({"expected_audience_daemon_id": "daemon:other"}, "audience daemon"),
        ({"expected_job_id": "123e4567-e89b-42d3-a456-426614174099"}, "job"),
        ({"expected_lease_fence": 18}, "lease fence"),
    ],
)
def test_replay_to_another_daemon_job_or_fence_is_rejected(
    overrides: dict[str, Any], binding_name: str
) -> None:
    from tinyassets.runtime.execution_capsule import CapsuleBindingError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    with pytest.raises(CapsuleBindingError, match=binding_name):
        _verify(capsule, signing_key, **overrides)


@pytest.mark.parametrize("capability_class", ["repo", "source_exec"])
@pytest.mark.parametrize(
    "capability_id",
    [
        "LEGACY_UNBOUND",
        "UNBOUND",
        "cap:legacy_unbound:1",
        "cap:un-bound:1",
        "cap:un_bound:1",
        "cap:un.bound:1",
        "LEGACYUNBOUND",
    ],
)
def test_unbound_capability_is_permanently_rejected_for_every_sandbox_class(
    capability_class: str, capability_id: str
) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["universe_scope"]["capability_id"] = capability_id
    capsule["payload"]["allowed_capability"]["class"] = capability_class
    capsule["payload"]["allowed_capability"]["repo_mode"] = (
        "coding" if capability_class == "repo" else None
    )
    capsule["payload"]["universe_scope"]["permissions"] = (
        ["read_source", "execute_repo", "produce_patch", "produce_artifact"]
        if capability_class == "repo"
        else ["read_source", "execute_source", "produce_artifact"]
    )
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsulePolicyError, match="permanently forbidden"):
        _verify(capsule, signing_key)


def test_legitimate_capability_merely_containing_unbound_text_is_allowed() -> None:
    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["universe_scope"]["capability_id"] = (
        "cap:boundary-unbounded-work:1"
    )
    capsule = _resign(capsule, signing_key)

    assert _verify(capsule, signing_key) == capsule


@pytest.mark.parametrize(
    "capability_id",
    [
        "unbound",
        "legacy_unbound",
        "cap:unbound",
        "cap:legacy:unbound",
        "legacyunbound",
    ],
)
def test_bare_unbound_capability_sentinels_are_rejected(
    capability_id: str,
) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["universe_scope"]["capability_id"] = capability_id
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsulePolicyError, match="permanently forbidden"):
        _verify(capsule, signing_key)


@pytest.mark.parametrize("capability_id", ["ＵＮＢＯＵＮＤ", "unbоund"])
def test_non_ascii_capability_ids_are_rejected_as_malformed(
    capability_id: str,
) -> None:
    from tinyassets.runtime.execution_capsule import CapsuleSchemaError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["universe_scope"]["capability_id"] = capability_id
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsuleSchemaError, match="ASCII opaque identifier"):
        _verify(capsule, signing_key)


def test_path_field_and_absolute_path_value_are_rejected_even_when_signed() -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    with_path_field = _signed_capsule(signing_key)
    with_path_field["payload"]["execution_request"]["inline"]["workspace_path"] = (
        "C:\\Users\\runner\\repo"
    )
    inline_bytes = __import__(
        "tinyassets.runtime.execution_capsule", fromlist=["canonicalize_jcs"]
    ).canonicalize_jcs(with_path_field["payload"]["execution_request"]["inline"])
    with_path_field["payload"]["execution_request"]["sha256"] = hashlib.sha256(
        inline_bytes
    ).hexdigest()
    with_path_field["payload"]["execution_request"]["size_bytes"] = len(inline_bytes)
    with_path_field = _resign(with_path_field, signing_key)
    with pytest.raises(CapsulePolicyError, match="path field"):
        _verify(with_path_field, signing_key)

    with_path_value = _signed_capsule(signing_key)
    with_path_value["payload"]["source_blob"]["ref"] = "/srv/tinyassets/source.bundle"
    with_path_value = _resign(with_path_value, signing_key)
    with pytest.raises(CapsulePolicyError, match="host path"):
        _verify(with_path_value, signing_key)


@pytest.mark.parametrize(
    ("field_name", "encoded_path"),
    [
        (
            "workspace_path_b64",
            base64.b64encode(b"/etc/passwd").decode("ascii"),
        ),
        (
            "workspace_path_base64",
            base64.b64encode(b"/etc/passwd").decode("ascii"),
        ),
        ("workspace_path_hex", b"/etc/passwd".hex()),
    ],
)
def test_encoded_path_field_names_are_rejected_by_their_base_name(
    field_name: str, encoded_path: str
) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["execution_request"]["inline"][field_name] = encoded_path
    _sync_inline_request(capsule)
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsulePolicyError, match="path field"):
        _verify(capsule, signing_key)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda capsule: capsule["payload"]["execution_request"]["inline"].update(
            {"nested": {"inputs": ["/etc/passwd"]}}
        ),
        lambda capsule: capsule["payload"]["model_broker_route"].update(
            {"allowed_model_classes": ["/etc/passwd"]}
        ),
    ],
    ids=["inline-array", "typed-list"],
)
def test_path_strings_in_every_array_shape_are_rejected(
    mutate: Any,
) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    mutate(capsule)
    _sync_inline_request(capsule)
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsulePolicyError, match="host path"):
        _verify(capsule, signing_key)


@pytest.mark.parametrize("path_value", ["/etc/shadow", "file:///etc/passwd"])
def test_path_bearing_b64_fields_must_be_canonical_base64(path_value: str) -> None:
    from tinyassets.runtime.execution_capsule import CapsuleSchemaError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["execution_request"]["inline"]["nested"] = {
        "payload_b64": path_value
    }
    _sync_inline_request(capsule)
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsuleSchemaError, match="canonical.*base64"):
        _verify(capsule, signing_key)


def test_legitimate_b64_blob_in_inline_request_is_accepted() -> None:
    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["execution_request"]["inline"]["nested"] = {
        "payload_b64": base64.b64encode(b"legitimate opaque blob").decode("ascii")
    }
    _sync_inline_request(capsule)
    capsule = _resign(capsule, signing_key)

    assert _verify(capsule, signing_key) == capsule


@pytest.mark.parametrize(
    "injection",
    [
        ("capsule", "future_field"),
        ("payload", "future_field"),
        ("payload.source_blob", "future_field"),
        ("integrity", "future_field"),
    ],
)
def test_unknown_or_extra_capsule_keys_are_rejected(injection: tuple[str, str]) -> None:
    from tinyassets.runtime.execution_capsule import CapsuleSchemaError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    object_path, key = injection
    target: dict[str, Any] = capsule
    if object_path != "capsule":
        for component in object_path.split("."):
            target = target[component]
    target[key] = "unexpected"
    if object_path not in {"capsule", "integrity"}:
        capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsuleSchemaError, match="unknown fields"):
        _verify(capsule, signing_key)


def test_unknown_capsule_and_request_schema_versions_fail_closed() -> None:
    from tinyassets.runtime.execution_capsule import CapsuleBindingError, CapsuleSchemaError

    signing_key = SigningKey.generate()
    future_capsule = _signed_capsule(signing_key)
    future_capsule["payload"]["schema_version"] = "execution-capsule/v2"
    future_capsule = _resign(future_capsule, signing_key)
    with pytest.raises(CapsuleSchemaError, match="unsupported capsule schema"):
        _verify(future_capsule, signing_key)

    future_request = _signed_capsule(signing_key)
    future_request["payload"]["execution_request"]["schema_version"] = 999
    future_request = _resign(future_request, signing_key)
    with pytest.raises(CapsuleBindingError, match="schema v999 is not supported"):
        _verify(future_request, signing_key)


def test_key_status_and_all_active_time_windows_fail_closed() -> None:
    from tinyassets.runtime.execution_capsule import CapsuleKeyError, CapsuleTimeError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    with pytest.raises(CapsuleKeyError, match="not active"):
        _verify(capsule, signing_key, signing_key_active=False)
    with pytest.raises(CapsuleTimeError, match="not active yet"):
        _verify(capsule, signing_key, now=datetime(2026, 7, 18, 23, 59, tzinfo=UTC))
    with pytest.raises(CapsuleTimeError, match="expired"):
        _verify(capsule, signing_key, now=datetime(2026, 7, 19, 1, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    ("field", "maximum"),
    [
        ("cpu_millis", 1_000),
        ("memory_bytes", 2 * 1024**3),
        ("pids", 256),
        ("workspace_bytes", 8 * 1024**3),
        ("workspace_inodes", 200_000),
        ("tmpfs_bytes", 512 * 1024**2),
        ("wall_time_seconds", 1_800),
        ("stdout_bytes", 25 * 1024**2),
        ("stderr_bytes", 25 * 1024**2),
        ("patch_bytes", 5 * 1024**2),
        ("patch_files", 200),
        ("patch_changed_lines", 50_000),
    ],
)
def test_initial_resource_policy_maximums_are_enforced(field: str, maximum: int) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["resource_limits"][field] = maximum + 1
    capsule = _resign(capsule, signing_key)
    with pytest.raises(CapsulePolicyError, match=field):
        _verify(capsule, signing_key)


def test_initial_model_call_maximum_is_enforced() -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["model_broker_route"]["max_calls"] = 33
    capsule = _resign(capsule, signing_key)
    with pytest.raises(CapsulePolicyError, match="max_calls"):
        _verify(capsule, signing_key)


def test_request_reference_union_and_safe_integer_domain_are_strict() -> None:
    from tinyassets.runtime.execution_capsule import CapsuleSchemaError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["execution_request"]["ref"] = "blob:request:1"
    capsule = _resign(capsule, signing_key)
    with pytest.raises(CapsuleSchemaError, match="exactly one"):
        _verify(capsule, signing_key)

    negative = _signed_capsule(signing_key)
    negative["payload"]["attempt"] = -1
    negative = _resign(negative, signing_key)
    with pytest.raises(CapsuleSchemaError, match="integer"):
        _verify(negative, signing_key)


def _deep_object(depth: int) -> dict[str, Any]:
    root: dict[str, Any] = {}
    cursor = root
    for _ in range(depth):
        child: dict[str, Any] = {}
        cursor["nested"] = child
        cursor = child
    return root


def _json_token_count(value: Any) -> int:
    stack = [value]
    tokens = 0
    while stack:
        item = stack.pop()
        tokens += 1
        if type(item) is dict:
            tokens += len(item)
            stack.extend(item.values())
        elif type(item) is list:
            stack.extend(item)
    return tokens


def test_create_and_public_verify_share_the_same_maximum_depth() -> None:
    from tinyassets.runtime.execution_capsule import (
        MAX_CAPSULE_NESTING_DEPTH,
        CapsuleSchemaError,
        canonicalize_jcs,
        create_execution_capsule,
    )

    signing_key = SigningKey.generate()
    # capsule -> payload -> execution_request -> inline consumes four levels.
    max_inline_depth = MAX_CAPSULE_NESTING_DEPTH - 4

    payload = _payload()
    payload["execution_request"]["inline"] = _deep_object(max_inline_depth)
    request_bytes = canonicalize_jcs(payload["execution_request"]["inline"])
    payload["execution_request"]["sha256"] = hashlib.sha256(request_bytes).hexdigest()
    payload["execution_request"]["size_bytes"] = len(request_bytes)
    capsule = create_execution_capsule(
        payload,
        signing_key=signing_key,
        signing_key_id="platform-key:1",
    )

    assert _verify(capsule, signing_key) == capsule

    too_deep_payload = _payload()
    too_deep_payload["execution_request"]["inline"] = _deep_object(
        max_inline_depth + 1
    )
    request_bytes = canonicalize_jcs(
        too_deep_payload["execution_request"]["inline"]
    )
    too_deep_payload["execution_request"]["sha256"] = hashlib.sha256(
        request_bytes
    ).hexdigest()
    too_deep_payload["execution_request"]["size_bytes"] = len(request_bytes)
    with pytest.raises(CapsuleSchemaError, match="depth"):
        create_execution_capsule(
            too_deep_payload,
            signing_key=signing_key,
            signing_key_id="platform-key:1",
        )

    too_deep_capsule = copy.deepcopy(capsule)
    too_deep_capsule["payload"]["execution_request"]["inline"] = _deep_object(
        max_inline_depth + 1
    )
    _sync_inline_request(too_deep_capsule)
    too_deep_capsule = _resign(too_deep_capsule, signing_key)
    with pytest.raises(CapsuleSchemaError, match="depth"):
        _verify(too_deep_capsule, signing_key)


def test_create_and_public_verify_share_the_same_maximum_token_count() -> None:
    from tinyassets.runtime.execution_capsule import (
        CapsuleSchemaError,
        canonicalize_jcs,
        create_execution_capsule,
    )

    signing_key = SigningKey.generate()
    max_capsule_tokens = 500_000
    payload = _payload()
    payload["execution_request"]["inline"] = {}
    request_bytes = canonicalize_jcs(payload["execution_request"]["inline"])
    payload["execution_request"]["sha256"] = hashlib.sha256(request_bytes).hexdigest()
    payload["execution_request"]["size_bytes"] = len(request_bytes)
    baseline_capsule = create_execution_capsule(
        payload,
        signing_key=signing_key,
        signing_key_id="platform-key:1",
    )
    baseline_tokens = _json_token_count(baseline_capsule)
    max_inline_members = (max_capsule_tokens - baseline_tokens) // 2

    inline = {f"k{index}": "" for index in range(max_inline_members)}
    boundary_value = [0]
    inline["k0"] = boundary_value
    payload["execution_request"]["inline"] = inline
    request_bytes = canonicalize_jcs(inline)
    payload["execution_request"]["sha256"] = hashlib.sha256(request_bytes).hexdigest()
    payload["execution_request"]["size_bytes"] = len(request_bytes)
    capsule = create_execution_capsule(
        payload,
        signing_key=signing_key,
        signing_key_id="platform-key:1",
    )

    assert _json_token_count(capsule) == max_capsule_tokens
    assert _verify(capsule, signing_key) == capsule

    boundary_value.append(1)
    request_bytes = canonicalize_jcs(inline)
    payload["execution_request"]["sha256"] = hashlib.sha256(request_bytes).hexdigest()
    payload["execution_request"]["size_bytes"] = len(request_bytes)
    with pytest.raises(CapsuleSchemaError, match="token count"):
        create_execution_capsule(
            payload,
            signing_key=signing_key,
            signing_key_id="platform-key:1",
        )


def test_raw_wire_member_limit_is_enforced_before_json_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tinyassets.runtime.execution_capsule as execution_capsule

    signing_key = SigningKey.generate()
    raw_capsule = b"[" + b"{}," * 500_000 + b"{}]"

    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("json.loads must not run for an oversized token stream")

    monkeypatch.setattr(execution_capsule.json, "loads", fail_if_called)
    with pytest.raises(
        execution_capsule.CapsuleSchemaError,
        match="(?:token|container) count",
    ):
        execution_capsule.verify_execution_capsule(
            raw_capsule,
            **_verification_arguments(signing_key),
        )


def test_raw_wire_scalar_token_limit_is_enforced_before_json_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tinyassets.runtime.execution_capsule as execution_capsule

    signing_key = SigningKey.generate()
    raw_capsule = b"[" + b"0," * 500_000 + b"0]"

    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("json.loads must not run for an oversized token stream")

    monkeypatch.setattr(execution_capsule.json, "loads", fail_if_called)
    with pytest.raises(
        execution_capsule.CapsuleSchemaError,
        match="token count",
    ):
        execution_capsule.verify_execution_capsule(
            raw_capsule,
            **_verification_arguments(signing_key),
        )


@pytest.mark.parametrize("depth", [100, 500, 1_000, 5_000])
def test_deep_create_input_raises_typed_capsule_error(depth: int) -> None:
    from tinyassets.runtime.execution_capsule import (
        ExecutionCapsuleError,
        create_execution_capsule,
    )

    payload = _payload()
    payload["execution_request"]["inline"] = _deep_object(depth)

    with pytest.raises(ExecutionCapsuleError, match="depth"):
        create_execution_capsule(
            payload,
            signing_key=SigningKey.generate(),
            signing_key_id="platform-key:1",
        )


@pytest.mark.parametrize("depth", [100, 500, 1_000, 5_000])
def test_deep_raw_wire_verification_raises_typed_capsule_error(depth: int) -> None:
    from tinyassets.runtime.execution_capsule import (
        ExecutionCapsuleError,
        verify_execution_capsule,
    )

    signing_key = SigningKey.generate()
    wire = b'{"nested":' * depth + b"null" + b"}" * depth

    with pytest.raises(ExecutionCapsuleError, match="depth"):
        verify_execution_capsule(wire, **_verification_arguments(signing_key))


@pytest.mark.parametrize("depth", [100, 500, 1_000, 5_000])
def test_deep_direct_canonicalization_raises_typed_capsule_error(depth: int) -> None:
    from tinyassets.runtime.execution_capsule import (
        ExecutionCapsuleError,
        canonicalize_jcs,
    )

    with pytest.raises(ExecutionCapsuleError, match="depth"):
        canonicalize_jcs(_deep_object(depth))


@pytest.mark.parametrize(
    ("capability_class", "repo_mode", "permissions"),
    [
        ("repo", "repo_read", []),
        ("repo", "repo_read", ["read_source", "execute_repo"]),
        ("repo", "repo_read", ["read_source", "execute_source"]),
        ("repo", "repo_read", ["read_source", "produce_patch"]),
        ("repo", "repo_exec", ["read_source"]),
        ("repo", "repo_exec", ["execute_repo", "execute_source"]),
        ("repo", "repo_exec", ["execute_repo", "produce_patch"]),
        ("repo", "coding", ["read_source", "produce_patch"]),
        ("repo", "coding", ["read_source", "execute_repo"]),
        ("repo", "coding", ["execute_repo", "produce_patch", "execute_source"]),
        ("source_exec", None, ["read_source"]),
        ("source_exec", None, ["execute_source", "execute_repo"]),
        ("source_exec", None, ["execute_source", "produce_patch"]),
    ],
)
def test_executor_class_and_mode_reject_incompatible_permissions(
    capability_class: str,
    repo_mode: str | None,
    permissions: list[str],
) -> None:
    from tinyassets.runtime.execution_capsule import CapsulePolicyError

    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["allowed_capability"]["class"] = capability_class
    capsule["payload"]["allowed_capability"]["repo_mode"] = repo_mode
    capsule["payload"]["universe_scope"]["permissions"] = permissions
    capsule = _resign(capsule, signing_key)

    with pytest.raises(CapsulePolicyError, match="permissions"):
        _verify(capsule, signing_key)


@pytest.mark.parametrize(
    ("capability_class", "repo_mode", "permissions"),
    [
        ("repo", "repo_read", ["read_source", "produce_artifact"]),
        ("repo", "repo_exec", ["read_source", "execute_repo", "produce_artifact"]),
        (
            "repo",
            "coding",
            ["read_source", "execute_repo", "produce_patch", "produce_artifact"],
        ),
        ("source_exec", None, ["read_source", "execute_source", "produce_artifact"]),
    ],
)
def test_executor_class_and_mode_accept_matching_permissions(
    capability_class: str,
    repo_mode: str | None,
    permissions: list[str],
) -> None:
    signing_key = SigningKey.generate()
    capsule = _signed_capsule(signing_key)
    capsule["payload"]["allowed_capability"]["class"] = capability_class
    capsule["payload"]["allowed_capability"]["repo_mode"] = repo_mode
    capsule["payload"]["universe_scope"]["permissions"] = permissions
    capsule = _resign(capsule, signing_key)

    assert _verify(capsule, signing_key) == capsule

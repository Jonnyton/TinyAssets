"""ExecutionResultV1 canonicalization, signature, and binding attacks."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from nacl.signing import SigningKey

JOB_ID = "123e4567-e89b-42d3-a456-426614174001"
CAPSULE_ID = "123e4567-e89b-42d3-a456-426614174000"
LEASE_ID = "123e4567-e89b-42d3-a456-426614174002"
CAPSULE_SHA256 = "a" * 64
PATCH_SHA256 = "b" * 64


def result_body() -> dict[str, Any]:
    return {
        "schema_version": "execution-result/v1",
        "job_id": JOB_ID,
        "capsule_id": CAPSULE_ID,
        "capsule_sha256": CAPSULE_SHA256,
        "lease_id": LEASE_ID,
        "fence": 17,
        "outcome": "succeeded",
        "executor": {
            "daemon_id": "daemon:builder-1",
            "device_key_id": "device-key:builder-1",
            "capability_class": "repo",
            "backend": "linux-bwrap",
            "runner_policy_sha256": "c" * 64,
            "image_digest": f"sha256:{'d' * 64}",
        },
        "repo_patch": {
            "format": "git-diff-v1",
            "blob_ref": f"blob:sha256:{PATCH_SHA256}",
            "blob_sha256": PATCH_SHA256,
            "size_bytes": 123,
            "base_commit": "1" * 40,
            "base_tree": "2" * 40,
            "resulting_tree": "3" * 40,
            "file_count": 1,
            "added_lines": 4,
            "deleted_lines": 2,
        },
        "source_output": None,
        "logs": [
            {
                "stream": "stdout",
                "blob_ref": f"blob:sha256:{'e' * 64}",
                "blob_sha256": "e" * 64,
                "size_bytes": 20,
            }
        ],
        "checks": [
            {
                "check_id": "pytest",
                "outcome": "passed",
                "exit_code": 0,
                "duration_ms": 900,
                "stdout_sha256": "e" * 64,
                "stderr_sha256": None,
            }
        ],
        "usage": {
            "wall_time_ms": 1_000,
            "cpu_time_ms": 500,
            "peak_memory_bytes": 10_000,
            "model_calls": 1,
            "model_input_tokens": 200,
            "model_output_tokens": 50,
        },
        "revalidation": {
            "exact_base_verified": True,
            "patch_applies_cleanly": True,
            "path_policy_passed": True,
            "limits_passed": True,
            "resulting_tree": "3" * 40,
            "verifier_policy_sha256": "f" * 64,
        },
        "destruction": {
            "confirmed": True,
            "confirmed_at": "2026-07-19T00:30:00Z",
            "backend_receipt_sha256": "9" * 64,
        },
        "completed_at": "2026-07-19T00:31:00Z",
    }


def create_result(
    body: dict[str, Any], key: SigningKey | None = None
) -> tuple[dict[str, Any], SigningKey]:
    from tinyassets.runtime.execution_result import create_execution_result

    signing_key = key or SigningKey.generate()
    result = create_execution_result(
        body,
        signing_key=signing_key,
        device_key_id="device-key:builder-1",
        repo_mode="coding",
    )
    return result, signing_key


def verify_result(
    result: dict[str, Any] | bytes, key: SigningKey, **overrides: Any
) -> dict[str, Any]:
    from tinyassets.runtime.execution_result import verify_execution_result

    expected = {
        "verify_key": key.verify_key,
        "expected_device_key_id": "device-key:builder-1",
        "device_key_active": True,
        "expected_daemon_id": "daemon:builder-1",
        "expected_job_id": JOB_ID,
        "expected_capsule_id": CAPSULE_ID,
        "expected_capsule_sha256": CAPSULE_SHA256,
        "expected_lease_id": LEASE_ID,
        "expected_fence": 17,
        "expected_capability_class": "repo",
        "expected_repo_mode": "coding",
        "expected_runner_policy_sha256": "c" * 64,
        "expected_image_digest": f"sha256:{'d' * 64}",
    }
    expected.update(overrides)
    raw = (
        result if isinstance(result, bytes) else json.dumps(result, separators=(",", ":")).encode()
    )
    return verify_execution_result(raw, **expected)


def test_result_hash_and_signature_reuse_capsule_canonical_primitives() -> None:
    from tinyassets.runtime.execution_capsule import canonicalize_jcs
    from tinyassets.runtime.execution_result import RESULT_DOMAIN_SEPARATOR

    body = result_body()
    result, key = create_result(body)

    expected_digest = __import__("hashlib").sha256(canonicalize_jcs(body)).digest()
    assert result["signature"]["result_sha256"] == expected_digest.hex()
    key.verify_key.verify(
        RESULT_DOMAIN_SEPARATOR + expected_digest,
        __import__("base64").b64decode(result["signature"]["signature_b64"]),
    )
    assert verify_result(result, key) == result


@pytest.mark.parametrize(
    "binding_override",
    [
        {"expected_job_id": "123e4567-e89b-42d3-a456-426614174099"},
        {"expected_lease_id": "123e4567-e89b-42d3-a456-426614174099"},
        {"expected_fence": 18},
        {"expected_capsule_sha256": "0" * 64},
    ],
)
def test_result_replay_to_another_job_lease_fence_or_capsule_is_rejected(
    binding_override: dict[str, Any],
) -> None:
    from tinyassets.runtime.execution_result import ResultBindingError

    result, key = create_result(result_body())
    with pytest.raises(ResultBindingError):
        verify_result(result, key, **binding_override)


def test_result_rejects_injected_path_field_and_host_path_value() -> None:
    from tinyassets.runtime.execution_result import ResultPolicyError, ResultSchemaError

    body = result_body()
    body["repo_patch"]["path"] = "work/output.diff"
    with pytest.raises((ResultPolicyError, ResultSchemaError)):
        create_result(body)

    body = result_body()
    body["repo_patch"]["blob_ref"] = "C:\\host\\output.diff"
    with pytest.raises(ResultPolicyError):
        create_result(body)


def test_result_tampering_breaks_hash_before_binding_is_accepted() -> None:
    from tinyassets.runtime.execution_result import ResultIntegrityError

    result, key = create_result(result_body())
    tampered = copy.deepcopy(result)
    tampered["repo_patch"]["blob_sha256"] = "0" * 64
    with pytest.raises(ResultIntegrityError):
        verify_result(tampered, key)


def test_result_wire_rejects_duplicate_json_members() -> None:
    from tinyassets.runtime.execution_result import ResultSchemaError

    result, key = create_result(result_body())
    raw = json.dumps(result, separators=(",", ":")).encode()
    duplicate = b'{"job_id":"duplicate",' + raw[1:]
    with pytest.raises(ResultSchemaError, match="duplicate JSON member"):
        verify_result(duplicate, key)


def test_unsafe_integer_still_raises_typed_result_error() -> None:
    from tinyassets.runtime.execution_result import ResultSchemaError

    result, key = create_result(result_body())
    result["usage"]["wall_time_ms"] = 2**60
    with pytest.raises(ResultSchemaError):
        verify_result(result, key)


def test_repo_read_cannot_smuggle_patch_and_success_requires_cleanup() -> None:
    from tinyassets.runtime.execution_result import ResultPolicyError

    with pytest.raises(ResultPolicyError, match="only repo/coding"):
        from tinyassets.runtime.execution_result import create_execution_result

        create_execution_result(
            result_body(),
            signing_key=SigningKey.generate(),
            device_key_id="device-key:builder-1",
            repo_mode="repo_read",
        )

    body = result_body()
    body["destruction"]["confirmed"] = False
    with pytest.raises(ResultPolicyError, match="confirmed destruction"):
        create_result(body)


def test_source_exec_artifact_candidate_is_typed_and_patch_free() -> None:
    from tinyassets.runtime.execution_result import create_execution_result

    body = result_body()
    body["executor"]["capability_class"] = "source_exec"
    body["repo_patch"] = None
    body["source_output"] = {
        "media_type": "application/json",
        "blob_ref": f"blob:sha256:{'7' * 64}",
        "blob_sha256": "7" * 64,
        "size_bytes": 44,
    }
    body["revalidation"]["resulting_tree"] = None
    key = SigningKey.generate()
    result = create_execution_result(
        body,
        signing_key=key,
        device_key_id="device-key:builder-1",
        repo_mode=None,
    )
    verified = verify_result(
        result,
        key,
        expected_capability_class="source_exec",
        expected_repo_mode=None,
    )
    assert verified["repo_patch"] is None
    assert verified["source_output"]["blob_sha256"] == "7" * 64

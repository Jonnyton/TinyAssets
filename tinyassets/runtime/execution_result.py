"""Signed, typed candidate results for distributed execution jobs.

The signature covers the complete result body except the ``signature`` member;
including that member would make ``result_sha256`` self-referential.  The body
uses the capsule's shared JCS, SHA-256, and domain-separated Ed25519 primitives.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hmac
import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal, TypedDict, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from tinyassets.runtime.execution_capsule import (
    CapsuleCanonicalizationError,
    CapsulePolicyError,
    CapsuleSchemaError,
    hash_canonical_jcs,
    reject_host_path_material,
    sign_domain_separated_ed25519,
    verify_domain_separated_ed25519,
)

RESULT_SCHEMA_VERSION = "execution-result/v1"
RESULT_DOMAIN_SEPARATOR = b"tinyassets.execution-result.v1\0"
MAX_RESULT_WIRE_BYTES = 8 * 1024 * 1024
MAX_PATCH_BYTES = 5 * 1024 * 1024
MAX_PATCH_FILES = 200
MAX_PATCH_CHANGED_LINES = 50_000
_JSON_SAFE_INTEGER_MAX = 2**53 - 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class ResultExecutorV1(TypedDict):
    daemon_id: str
    device_key_id: str
    capability_class: Literal["repo", "source_exec"]
    backend: Literal["linux-bwrap", "linux-rootless-oci", "windows-wsl2-podman"]
    runner_policy_sha256: str
    image_digest: str


class RepoPatchV1(TypedDict):
    format: Literal["git-diff-v1"]
    blob_ref: str
    blob_sha256: str
    size_bytes: int
    base_commit: str
    base_tree: str
    resulting_tree: str
    file_count: int
    added_lines: int
    deleted_lines: int


class SourceOutputV1(TypedDict):
    media_type: str
    blob_ref: str
    blob_sha256: str
    size_bytes: int


class ResultLogV1(TypedDict):
    stream: Literal["stdout", "stderr", "runner"]
    blob_ref: str
    blob_sha256: str
    size_bytes: int


class ResultCheckV1(TypedDict):
    check_id: str
    outcome: Literal["passed", "failed", "skipped"]
    exit_code: int | None
    duration_ms: int
    stdout_sha256: str | None
    stderr_sha256: str | None


class ResultUsageV1(TypedDict):
    wall_time_ms: int
    cpu_time_ms: int
    peak_memory_bytes: int
    model_calls: int
    model_input_tokens: int
    model_output_tokens: int


class ResultRevalidationV1(TypedDict):
    exact_base_verified: bool
    patch_applies_cleanly: bool
    path_policy_passed: bool
    limits_passed: bool
    resulting_tree: str | None
    verifier_policy_sha256: str


class ResultDestructionV1(TypedDict):
    confirmed: bool
    confirmed_at: str | None
    backend_receipt_sha256: str | None


class ResultSignatureV1(TypedDict):
    algorithm: Literal["ed25519"]
    device_key_id: str
    result_sha256: str
    signature_b64: str


class ExecutionResultBodyV1(TypedDict):
    schema_version: Literal["execution-result/v1"]
    job_id: str
    capsule_id: str
    capsule_sha256: str
    lease_id: str
    fence: int
    outcome: Literal[
        "succeeded",
        "job_failed",
        "cancelled",
        "timed_out",
        "policy_rejected",
        "infrastructure_failed",
    ]
    executor: ResultExecutorV1
    repo_patch: RepoPatchV1 | None
    source_output: SourceOutputV1 | None
    logs: list[ResultLogV1]
    checks: list[ResultCheckV1]
    usage: ResultUsageV1
    revalidation: ResultRevalidationV1
    destruction: ResultDestructionV1
    completed_at: str


class ExecutionResultV1(ExecutionResultBodyV1):
    signature: ResultSignatureV1


class ExecutionResultError(ValueError):
    """Base class for explicit candidate-result rejection."""


class ResultSchemaError(ExecutionResultError):
    """Raised when a candidate does not match the pinned V1 schema."""


class ResultIntegrityError(ExecutionResultError):
    """Raised when canonical content hash or signature verification fails."""


class ResultKeyError(ExecutionResultError):
    """Raised when the expected daemon device key is invalid or inactive."""


class ResultBindingError(ExecutionResultError):
    """Raised when job, capsule, lease, fence, or executor binding differs."""


class ResultPolicyError(ExecutionResultError):
    """Raised when a typed result violates a permanent execution policy."""


class _DuplicateJsonMemberError(ValueError):
    pass


def _schema_keys(schema: type) -> frozenset[str]:
    return cast(frozenset[str], schema.__required_keys__)


def _exact_object(value: Any, schema: type, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ResultSchemaError(f"{path} must be a JSON object")
    actual = frozenset(value)
    expected = _schema_keys(schema)
    if not all(type(key) is str for key in actual):
        raise ResultSchemaError(f"{path} keys must be strings")
    if expected - actual:
        raise ResultSchemaError(f"{path} missing fields {sorted(expected - actual)}")
    if actual - expected:
        raise ResultSchemaError(f"{path} has unknown fields {sorted(actual - expected)}")
    return value


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMemberError(key)
        result[key] = value
    return result


def _decode_wire(raw_result: bytes) -> dict[str, Any]:
    if type(raw_result) is not bytes:
        raise ResultSchemaError("verify_execution_result requires raw JSON bytes")
    if len(raw_result) > MAX_RESULT_WIRE_BYTES:
        raise ResultSchemaError(f"result wire document exceeds {MAX_RESULT_WIRE_BYTES} bytes")
    try:
        value = json.loads(raw_result, object_pairs_hook=_reject_duplicate_members)
    except _DuplicateJsonMemberError as exc:
        raise ResultSchemaError(f"duplicate JSON member {exc.args[0]!r}") from exc
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ResultSchemaError("result wire document is not valid JSON") from exc
    if type(value) is not dict:
        raise ResultSchemaError("result wire document must decode to a JSON object")
    return value


def _text(obj: dict[str, Any], key: str, path: str) -> str:
    value = obj[key]
    if type(value) is not str or not value:
        raise ResultSchemaError(f"{path}.{key} must be a non-empty string")
    return value


def _opaque_id(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    if not _OPAQUE_ID_RE.fullmatch(value):
        raise ResultSchemaError(f"{path}.{key} must be an ASCII opaque identifier")
    return value


def _integer(obj: dict[str, Any], key: str, path: str) -> int:
    value = obj[key]
    if type(value) is not int or not 0 <= value <= _JSON_SAFE_INTEGER_MAX:
        raise ResultSchemaError(f"{path}.{key} must be a non-negative safe integer")
    return value


def _boolean(obj: dict[str, Any], key: str, path: str) -> bool:
    value = obj[key]
    if type(value) is not bool:
        raise ResultSchemaError(f"{path}.{key} must be boolean")
    return value


def _literal(obj: dict[str, Any], key: str, allowed: frozenset[str], path: str) -> str:
    value = _text(obj, key, path)
    if value not in allowed:
        raise ResultSchemaError(f"{path}.{key} has unsupported value {value!r}")
    return value


def _sha256(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    if not _SHA256_RE.fullmatch(value):
        raise ResultSchemaError(f"{path}.{key} must be lowercase SHA-256 hex")
    return value


def _nullable_sha256(obj: dict[str, Any], key: str, path: str) -> str | None:
    if obj[key] is None:
        return None
    return _sha256(obj, key, path)


def _uuid(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ResultSchemaError(f"{path}.{key} must be a canonical RFC 4122 UUID") from exc
    if str(parsed) != value or parsed.variant != uuid.RFC_4122:
        raise ResultSchemaError(f"{path}.{key} must be a canonical RFC 4122 UUID")
    return value


def _timestamp_value(value: Any, path: str) -> datetime:
    if type(value) is not str or not _TIMESTAMP_RE.fullmatch(value):
        raise ResultSchemaError(f"{path} must be RFC 3339 UTC with Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ResultSchemaError(f"{path} must be a real RFC 3339 timestamp") from exc


def _decode_signature(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ResultSchemaError("signature.signature_b64 must be canonical base64") from exc
    if len(decoded) != 64 or base64.b64encode(decoded).decode("ascii") != value:
        raise ResultSchemaError("signature.signature_b64 must encode 64 bytes")
    return decoded


def _validate_body_structure(value: Any) -> dict[str, Any]:
    body = _exact_object(value, ExecutionResultBodyV1, "result")
    executor = _exact_object(body["executor"], ResultExecutorV1, "result.executor")
    body["executor"] = executor

    patch = body["repo_patch"]
    if patch is not None:
        body["repo_patch"] = _exact_object(patch, RepoPatchV1, "result.repo_patch")
    output = body["source_output"]
    if output is not None:
        body["source_output"] = _exact_object(output, SourceOutputV1, "result.source_output")
    if type(body["logs"]) is not list:
        raise ResultSchemaError("result.logs must be an array")
    body["logs"] = [
        _exact_object(log, ResultLogV1, f"result.logs[{index}]")
        for index, log in enumerate(body["logs"])
    ]
    if type(body["checks"]) is not list:
        raise ResultSchemaError("result.checks must be an array")
    body["checks"] = [
        _exact_object(check, ResultCheckV1, f"result.checks[{index}]")
        for index, check in enumerate(body["checks"])
    ]
    for key, schema in (
        ("usage", ResultUsageV1),
        ("revalidation", ResultRevalidationV1),
        ("destruction", ResultDestructionV1),
    ):
        body[key] = _exact_object(body[key], schema, f"result.{key}")
    return body


def _validate_structure(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _exact_object(value, ExecutionResultV1, "result")
    body = _validate_body_structure(
        {key: result[key] for key in _schema_keys(ExecutionResultBodyV1)}
    )
    signature = _exact_object(result["signature"], ResultSignatureV1, "signature")
    return body, signature


def _reject_paths(body: dict[str, Any]) -> None:
    try:
        reject_host_path_material(body, "result")
    except (CapsulePolicyError, CapsuleSchemaError) as exc:
        raise ResultPolicyError(str(exc)) from exc


def _result_digest(body: dict[str, Any]) -> bytes:
    try:
        return hash_canonical_jcs(body)
    except CapsuleCanonicalizationError as exc:
        raise ResultSchemaError(str(exc)) from exc


def _validate_semantics(body: dict[str, Any], *, repo_mode: str | None) -> None:
    _result_digest(body)

    if body["schema_version"] != RESULT_SCHEMA_VERSION:
        raise ResultSchemaError(f"unsupported result schema version {body['schema_version']!r}")
    for key in ("job_id", "capsule_id", "lease_id"):
        _uuid(body, key, "result")
    _sha256(body, "capsule_sha256", "result")
    _integer(body, "fence", "result")
    outcome = _literal(
        body,
        "outcome",
        frozenset(
            {
                "succeeded",
                "job_failed",
                "cancelled",
                "timed_out",
                "policy_rejected",
                "infrastructure_failed",
            }
        ),
        "result",
    )

    executor = body["executor"]
    _opaque_id(executor, "daemon_id", "result.executor")
    _opaque_id(executor, "device_key_id", "result.executor")
    capability_class = _literal(
        executor,
        "capability_class",
        frozenset({"repo", "source_exec"}),
        "result.executor",
    )
    _literal(
        executor,
        "backend",
        frozenset({"linux-bwrap", "linux-rootless-oci", "windows-wsl2-podman"}),
        "result.executor",
    )
    _sha256(executor, "runner_policy_sha256", "result.executor")
    if not _OCI_DIGEST_RE.fullmatch(_text(executor, "image_digest", "result.executor")):
        raise ResultSchemaError("result.executor.image_digest must be immutable")

    patch = body["repo_patch"]
    output = body["source_output"]
    if capability_class == "repo":
        if repo_mode not in {"repo_read", "repo_exec", "coding"}:
            raise ResultBindingError("repo result requires its capsule repo_mode")
        if output is not None:
            raise ResultPolicyError("repo result cannot contain source_output")
        if patch is not None and repo_mode != "coding":
            raise ResultPolicyError("only repo/coding may return repo_patch")
    else:
        if repo_mode is not None:
            raise ResultBindingError("source_exec result requires repo_mode null")
        if patch is not None:
            raise ResultPolicyError("source_exec result cannot contain repo_patch")

    if patch is not None:
        _literal(patch, "format", frozenset({"git-diff-v1"}), "result.repo_patch")
        _text(patch, "blob_ref", "result.repo_patch")
        _sha256(patch, "blob_sha256", "result.repo_patch")
        if _integer(patch, "size_bytes", "result.repo_patch") > MAX_PATCH_BYTES:
            raise ResultPolicyError("repo patch exceeds the 5 MiB policy maximum")
        for key in ("base_commit", "base_tree", "resulting_tree"):
            if not _GIT_OBJECT_RE.fullmatch(_text(patch, key, "result.repo_patch")):
                raise ResultSchemaError(f"result.repo_patch.{key} is not a git object id")
        if _integer(patch, "file_count", "result.repo_patch") > MAX_PATCH_FILES:
            raise ResultPolicyError("repo patch exceeds the 200-file policy maximum")
        changed_lines = _integer(patch, "added_lines", "result.repo_patch") + _integer(
            patch, "deleted_lines", "result.repo_patch"
        )
        if changed_lines > MAX_PATCH_CHANGED_LINES:
            raise ResultPolicyError("repo patch exceeds changed-line policy maximum")

    if output is not None:
        _text(output, "media_type", "result.source_output")
        _text(output, "blob_ref", "result.source_output")
        _sha256(output, "blob_sha256", "result.source_output")
        _integer(output, "size_bytes", "result.source_output")

    for index, log in enumerate(body["logs"]):
        path = f"result.logs[{index}]"
        _literal(log, "stream", frozenset({"stdout", "stderr", "runner"}), path)
        _text(log, "blob_ref", path)
        _sha256(log, "blob_sha256", path)
        _integer(log, "size_bytes", path)
    for index, check in enumerate(body["checks"]):
        path = f"result.checks[{index}]"
        _opaque_id(check, "check_id", path)
        _literal(check, "outcome", frozenset({"passed", "failed", "skipped"}), path)
        if check["exit_code"] is not None:
            _integer(check, "exit_code", path)
        _integer(check, "duration_ms", path)
        _nullable_sha256(check, "stdout_sha256", path)
        _nullable_sha256(check, "stderr_sha256", path)
    for key in _schema_keys(ResultUsageV1):
        _integer(body["usage"], key, "result.usage")

    revalidation = body["revalidation"]
    for key in (
        "exact_base_verified",
        "patch_applies_cleanly",
        "path_policy_passed",
        "limits_passed",
    ):
        _boolean(revalidation, key, "result.revalidation")
    if revalidation["resulting_tree"] is not None and not _GIT_OBJECT_RE.fullmatch(
        revalidation["resulting_tree"]
    ):
        raise ResultSchemaError("result.revalidation.resulting_tree is not a git object id")
    _sha256(revalidation, "verifier_policy_sha256", "result.revalidation")

    destruction = body["destruction"]
    _boolean(destruction, "confirmed", "result.destruction")
    if destruction["confirmed_at"] is not None:
        _timestamp_value(destruction["confirmed_at"], "result.destruction.confirmed_at")
    _nullable_sha256(destruction, "backend_receipt_sha256", "result.destruction")
    _timestamp_value(body["completed_at"], "result.completed_at")

    if outcome == "succeeded":
        if not all(
            revalidation[key]
            for key in (
                "exact_base_verified",
                "patch_applies_cleanly",
                "path_policy_passed",
                "limits_passed",
            )
        ):
            raise ResultPolicyError("successful result requires passed revalidation")
        if patch is not None and revalidation["resulting_tree"] != patch["resulting_tree"]:
            raise ResultPolicyError("revalidation tree does not match candidate patch")
        if not destruction["confirmed"]:
            raise ResultPolicyError("successful result requires confirmed destruction")
        if destruction["confirmed_at"] is None or destruction["backend_receipt_sha256"] is None:
            raise ResultPolicyError("confirmed destruction requires timestamp and receipt")


def _validate_signature(signature: dict[str, Any]) -> bytes:
    _literal(signature, "algorithm", frozenset({"ed25519"}), "signature")
    _opaque_id(signature, "device_key_id", "signature")
    _sha256(signature, "result_sha256", "signature")
    return _decode_signature(_text(signature, "signature_b64", "signature"))


def create_execution_result(
    body: ExecutionResultBodyV1 | dict[str, Any],
    *,
    signing_key: SigningKey,
    device_key_id: str,
    repo_mode: Literal["repo_read", "repo_exec", "coding"] | None,
) -> ExecutionResultV1:
    """Validate and daemon-sign an immutable candidate result body."""
    body_object = _validate_body_structure(copy.deepcopy(body))
    _reject_paths(body_object)
    _validate_semantics(body_object, repo_mode=repo_mode)
    if not isinstance(signing_key, SigningKey):
        raise ResultKeyError("signing_key must be a PyNaCl Ed25519 SigningKey")
    if type(device_key_id) is not str or not _OPAQUE_ID_RE.fullmatch(device_key_id):
        raise ResultKeyError("device_key_id must be an ASCII opaque identifier")
    if body_object["executor"]["device_key_id"] != device_key_id:
        raise ResultBindingError("executor device key does not match signing key id")

    digest = _result_digest(body_object)
    signature_bytes = sign_domain_separated_ed25519(
        digest,
        domain_separator=RESULT_DOMAIN_SEPARATOR,
        signing_key=signing_key,
    )
    result = {
        **body_object,
        "signature": {
            "algorithm": "ed25519",
            "device_key_id": device_key_id,
            "result_sha256": digest.hex(),
            "signature_b64": base64.b64encode(signature_bytes).decode("ascii"),
        },
    }
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RESULT_WIRE_BYTES:
        raise ResultPolicyError("result wire document exceeds maximum size")
    return cast(ExecutionResultV1, result)


def verify_execution_result(
    raw_result: bytes,
    *,
    verify_key: VerifyKey,
    expected_device_key_id: str,
    device_key_active: bool,
    expected_daemon_id: str,
    expected_job_id: str,
    expected_capsule_id: str,
    expected_capsule_sha256: str,
    expected_lease_id: str,
    expected_fence: int,
    expected_capability_class: Literal["repo", "source_exec"],
    expected_repo_mode: Literal["repo_read", "repo_exec", "coding"] | None,
    expected_runner_policy_sha256: str,
    expected_image_digest: str,
) -> ExecutionResultV1:
    """Verify raw wire bytes and every device, capsule, and lease binding."""
    decoded = _decode_wire(raw_result)
    result_copy = copy.deepcopy(decoded)
    body, signature = _validate_structure(result_copy)
    signature_bytes = _validate_signature(signature)
    digest = _result_digest(body)
    if not hmac.compare_digest(signature["result_sha256"], digest.hex()):
        raise ResultIntegrityError("result_sha256 does not match canonical result body")
    if not isinstance(verify_key, VerifyKey):
        raise ResultKeyError("verify_key must be a PyNaCl Ed25519 VerifyKey")
    if signature["device_key_id"] != expected_device_key_id:
        raise ResultKeyError("result device key id is not the expected key")
    if device_key_active is not True:
        raise ResultKeyError("result device key is not active")
    try:
        verify_domain_separated_ed25519(
            digest,
            signature_bytes,
            domain_separator=RESULT_DOMAIN_SEPARATOR,
            verify_key=verify_key,
        )
    except (BadSignatureError, ValueError) as exc:
        raise ResultIntegrityError("Ed25519 result signature verification failed") from exc

    _reject_paths(body)
    _validate_semantics(body, repo_mode=expected_repo_mode)
    expected = {
        "job_id": expected_job_id,
        "capsule_id": expected_capsule_id,
        "capsule_sha256": expected_capsule_sha256,
        "lease_id": expected_lease_id,
        "fence": expected_fence,
    }
    for key, value in expected.items():
        if body[key] != value:
            raise ResultBindingError(f"result {key} binding does not match")
    executor = body["executor"]
    executor_expected = {
        "device_key_id": expected_device_key_id,
        "daemon_id": expected_daemon_id,
        "capability_class": expected_capability_class,
        "runner_policy_sha256": expected_runner_policy_sha256,
        "image_digest": expected_image_digest,
    }
    for key, value in executor_expected.items():
        if executor[key] != value:
            raise ResultBindingError(f"result executor {key} binding does not match")
    return cast(ExecutionResultV1, {**body, "signature": signature})


def result_blob_references(result: ExecutionResultV1) -> tuple[tuple[str, str, int], ...]:
    """Return every ``(ref, sha256, size)`` tuple bound into a verified result."""
    refs: list[tuple[str, str, int]] = []
    if result["repo_patch"] is not None:
        patch = result["repo_patch"]
        refs.append((patch["blob_ref"], patch["blob_sha256"], patch["size_bytes"]))
    if result["source_output"] is not None:
        output = result["source_output"]
        refs.append((output["blob_ref"], output["blob_sha256"], output["size_bytes"]))
    refs.extend((log["blob_ref"], log["blob_sha256"], log["size_bytes"]) for log in result["logs"])
    return tuple(refs)

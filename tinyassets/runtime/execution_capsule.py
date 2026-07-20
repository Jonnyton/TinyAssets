"""Signed, fail-closed execution capsules for isolated TinyAssets jobs.

The wire contract is deliberately standalone: integration into the existing
runner is a later slice.  This module owns the RFC 8785 canonicalizer because
capsule integrity must not depend on an optional serializer.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import hmac
import json
import math
import re
import unicodedata
import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, BinaryIO, Literal, TypedDict, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

_JSON_SAFE_INTEGER_MAX = 2**53 - 1

CAPSULE_SCHEMA_VERSION = "execution-capsule/v1"
SUPPORTED_CAPSULE_SCHEMA_VERSIONS = frozenset({CAPSULE_SCHEMA_VERSION})
CAPSULE_DOMAIN_SEPARATOR = b"tinyassets.execution-capsule.v1\0"
MAX_INLINE_REQUEST_BYTES = 4_000_000
MAX_CAPSULE_NESTING_DEPTH = 64
MAX_CAPSULE_WIRE_BYTES = 8 * 1024 * 1024
_MAX_CAPSULE_TOKENS = 500_000
_MAX_CAPSULE_CONTAINERS = 500_000
_MAX_CAPSULE_SCALAR_BYTES = 8 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)
_ENCODED_FIELD_SUFFIX_RE = re.compile(
    r"(?:_(?:b16|b32|b64|b85|base16|base32|base64|base85|hex|bytes|encoded))+$"
)
_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)Z$"
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

_PERMISSIONS = frozenset(
    {
        "read_source",
        "execute_repo",
        "execute_source",
        "produce_patch",
        "produce_artifact",
    }
)
_SANDBOX_CLASSES = frozenset({"repo", "source_exec"})
_REPO_MODES = frozenset({"repo_read", "repo_exec", "coding"})
# S0's authoritative binding state is ScopeKind.LEGACY_UNBOUND, whose platform
# wire value is exactly ``legacy_unbound`` (sandbox_policy.py).  The capsule
# check is only a defense-in-depth tripwire for that known platform sentinel;
# it must not guess that otherwise legitimate capability IDs are "unbound".
_UNBOUND_CAPABILITY_SENTINELS = frozenset({"legacy_unbound"})
_UNBOUND_SENTINELS_NORMALIZED = frozenset(
    re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", sentinel).casefold())
    for sentinel in _UNBOUND_CAPABILITY_SENTINELS
)
# Section 5.2 names the modes and permissions but leaves incompatible cells
# implicit.  Keep common read/artifact permissions, and fail closed for every
# executor permission outside the one mode that authorizes it.
_CAPABILITY_PERMISSION_POLICY = {
    ("repo", "repo_read"): (
        frozenset({"read_source"}),
        frozenset({"execute_repo", "execute_source", "produce_patch"}),
    ),
    ("repo", "repo_exec"): (
        frozenset({"execute_repo"}),
        frozenset({"execute_source", "produce_patch"}),
    ),
    ("repo", "coding"): (
        frozenset({"execute_repo", "produce_patch"}),
        frozenset({"execute_source"}),
    ),
    ("source_exec", None): (
        frozenset({"execute_source"}),
        frozenset({"execute_repo", "produce_patch"}),
    ),
}
_POLICY_MAXIMUMS = {
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
}


class UniverseScopeV1(TypedDict):
    universe_id: str
    capability_id: str
    scope_version: int
    permissions: list[
        Literal[
            "read_source",
            "execute_repo",
            "execute_source",
            "produce_patch",
            "produce_artifact",
        ]
    ]


class BranchReferenceV1(TypedDict):
    branch_definition_id: str
    branch_version_sha256: str


class NodeReferenceV1(TypedDict):
    node_id: str
    node_version_sha256: str
    node_kind: str


class BaseReferenceV1(TypedDict):
    vcs: Literal["git"]
    object_format: Literal["sha1", "sha256"]
    commit: str
    tree: str


class SourceEncryptionV1(TypedDict):
    scheme: Literal["x25519-chacha20poly1305-v1"]
    recipient_device_key_id: str
    wrapped_content_key_b64: str


class SourceProducerV1(TypedDict):
    daemon_id: str
    device_key_id: str
    signature_b64: str


class SourceBlobV1(TypedDict):
    ref: str
    media_type: Literal["application/vnd.tinyassets.git-bundle.v1"]
    content_sha256: str
    transport_sha256: str
    size_bytes: int
    manifest_sha256: str
    confidentiality: Literal["public", "owner_private", "host_visible_private"]
    encryption: SourceEncryptionV1 | None
    producer: SourceProducerV1


class ExecutionRequestReferenceV1(TypedDict):
    schema_version: int
    ref: str | None
    inline: dict[str, Any] | None
    sha256: str
    size_bytes: int


AllowedCapabilityV1 = TypedDict(
    "AllowedCapabilityV1",
    {
        "class": Literal["repo", "source_exec"],
        "repo_mode": Literal["repo_read", "repo_exec", "coding"] | None,
        "action_policy_id": str,
        "action_policy_sha256": str,
        "runner_policy_sha256": str,
        "image_digest": str,
    },
)


class ModelBrokerRouteV1(TypedDict):
    route_id: str
    route_version: int
    policy_sha256: str
    grant_ref: str
    allowed_model_classes: list[str]
    max_calls: int
    max_input_tokens: int
    max_output_tokens: int
    expires_at: str


class ResourceLimitsV1(TypedDict):
    cpu_millis: int
    memory_bytes: int
    pids: int
    workspace_bytes: int
    workspace_inodes: int
    tmpfs_bytes: int
    wall_time_seconds: int
    stdout_bytes: int
    stderr_bytes: int
    patch_bytes: int
    patch_files: int
    patch_changed_lines: int
    network: Literal["none", "model_broker_only"]
    egress_policy_id: str
    egress_policy_sha256: str


class LeaseV1(TypedDict):
    lease_id: str
    fence: int
    issued_at: str
    expires_at: str


class ExecutionCapsulePayloadV1(TypedDict):
    schema_version: Literal["execution-capsule/v1"]
    capsule_id: str
    job_id: str
    attempt: int
    audience_daemon_id: str
    owner_user_id: str
    universe_scope: UniverseScopeV1
    branch: BranchReferenceV1
    node: NodeReferenceV1
    base: BaseReferenceV1
    source_blob: SourceBlobV1
    execution_request: ExecutionRequestReferenceV1
    allowed_capability: AllowedCapabilityV1
    model_broker_route: ModelBrokerRouteV1
    resource_limits: ResourceLimitsV1
    lease: LeaseV1
    issued_at: str
    not_before: str
    expires_at: str


class CapsuleIntegrityV1(TypedDict):
    canonicalization: Literal["RFC8785-JCS"]
    hash_algorithm: Literal["sha256"]
    capsule_sha256: str
    signature_algorithm: Literal["ed25519"]
    signing_key_id: str
    signature_b64: str


class ExecutionCapsuleV1(TypedDict):
    payload: ExecutionCapsulePayloadV1
    integrity: CapsuleIntegrityV1

_ESCAPE_RE = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
for _codepoint in range(0x20):
    _ESCAPES.setdefault(chr(_codepoint), f"\\u{_codepoint:04x}")


class ExecutionCapsuleError(ValueError):
    """Base class for every explicit execution-capsule rejection."""


class CapsuleCanonicalizationError(ExecutionCapsuleError):
    """Raised when a value is outside RFC 8785's I-JSON domain."""


class CapsuleSchemaError(ExecutionCapsuleError):
    """Raised when a capsule does not match the pinned V1 wire schema."""


class CapsuleIntegrityError(ExecutionCapsuleError):
    """Raised when the content hash or Ed25519 signature is invalid."""


class CapsuleKeyError(ExecutionCapsuleError):
    """Raised when the expected platform signing key is absent or inactive."""


class CapsuleBindingError(ExecutionCapsuleError):
    """Raised when audience, job, request schema, or lease binding mismatches."""


class CapsulePolicyError(ExecutionCapsuleError):
    """Raised when a sandbox capsule violates a permanent policy invariant."""


class CapsuleTimeError(ExecutionCapsuleError):
    """Raised when capsule, route, or lease timestamps are invalid or inactive."""


class _DuplicateJsonMemberError(ValueError):
    pass


def _preflight_json_value(
    value: Any,
    *,
    path: str,
    error_type: type[ExecutionCapsuleError] = CapsuleSchemaError,
    initial_depth: int = 1,
) -> None:
    """Bound JSON-shaped values before deepcopy or recursive validation."""
    stack: list[tuple[Any, int, bool]] = [(value, initial_depth, False)]
    active_containers: set[int] = set()
    tokens = 0
    containers = 0
    scalar_bytes = 0

    while stack:
        item, depth, exiting = stack.pop()
        if exiting:
            active_containers.remove(id(item))
            continue
        if depth > MAX_CAPSULE_NESTING_DEPTH:
            raise error_type(
                f"{path} exceeds maximum JSON depth {MAX_CAPSULE_NESTING_DEPTH}"
            )
        tokens += 1
        if tokens > _MAX_CAPSULE_TOKENS:
            raise error_type(f"{path} exceeds maximum JSON token count")

        if type(item) is dict:
            containers += 1
            if containers > _MAX_CAPSULE_CONTAINERS:
                raise error_type(f"{path} exceeds maximum JSON container count")
            container_id = id(item)
            if container_id in active_containers:
                raise error_type(f"{path} contains a cyclic JSON object")
            active_containers.add(container_id)
            stack.append((item, depth, True))
            for key, child in item.items():
                if type(key) is not str:
                    raise error_type(f"{path} contains a non-string object key")
                tokens += 1
                if tokens > _MAX_CAPSULE_TOKENS:
                    raise error_type(f"{path} exceeds maximum JSON token count")
                if len(key) > _MAX_CAPSULE_SCALAR_BYTES:
                    raise error_type(f"{path} exceeds maximum decoded JSON scalar size")
                try:
                    scalar_bytes += len(key.encode("utf-8"))
                except UnicodeEncodeError as exc:
                    raise error_type(
                        f"{path} contains a lone Unicode surrogate"
                    ) from exc
                stack.append((child, depth + 1, False))
        elif type(item) is list:
            containers += 1
            if containers > _MAX_CAPSULE_CONTAINERS:
                raise error_type(f"{path} exceeds maximum JSON container count")
            container_id = id(item)
            if container_id in active_containers:
                raise error_type(f"{path} contains a cyclic JSON array")
            active_containers.add(container_id)
            stack.append((item, depth, True))
            stack.extend((child, depth + 1, False) for child in reversed(item))
        elif type(item) is str:
            if len(item) > _MAX_CAPSULE_SCALAR_BYTES:
                raise error_type(f"{path} exceeds maximum decoded JSON scalar size")
            try:
                scalar_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise error_type(f"{path} contains a lone Unicode surrogate") from exc
        elif item is None or type(item) in {bool, int, float}:
            scalar_bytes += 32
        else:
            raise error_type(
                f"{path} contains non-JSON type {type(item).__name__}"
            )

        if scalar_bytes > _MAX_CAPSULE_SCALAR_BYTES:
            raise error_type(f"{path} exceeds maximum decoded JSON scalar size")


def _preflight_json_wire(raw_capsule: bytes) -> None:
    if len(raw_capsule) > MAX_CAPSULE_WIRE_BYTES:
        raise CapsuleSchemaError(
            f"capsule wire document exceeds {MAX_CAPSULE_WIRE_BYTES} bytes"
        )

    depth = 0
    tokens = 0
    containers = 0
    in_string = False
    escaped = False
    in_atom = False
    for byte in raw_capsule:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_atom = False
            in_string = True
            tokens += 1
        elif byte in {0x5B, 0x7B}:
            in_atom = False
            depth += 1
            tokens += 1
            containers += 1
            if depth > MAX_CAPSULE_NESTING_DEPTH:
                raise CapsuleSchemaError(
                    "capsule wire document exceeds maximum JSON depth "
                    f"{MAX_CAPSULE_NESTING_DEPTH}"
                )
            if containers > _MAX_CAPSULE_CONTAINERS:
                raise CapsuleSchemaError(
                    "capsule wire document exceeds maximum JSON container count"
                )
        elif byte in {0x5D, 0x7D}:
            in_atom = False
            depth -= 1
        elif byte in {0x2C, 0x3A, 0x20, 0x09, 0x0A, 0x0D}:
            in_atom = False
        elif not in_atom:
            in_atom = True
            tokens += 1

        if tokens > _MAX_CAPSULE_TOKENS:
            raise CapsuleSchemaError(
                "capsule wire document exceeds maximum JSON token count"
            )


def _reject_duplicate_json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMemberError(key)
        result[key] = value
    return result


def _decode_execution_capsule_wire(raw_capsule: bytes) -> dict[str, Any]:
    if type(raw_capsule) is not bytes:
        raise CapsuleSchemaError(
            "verify_execution_capsule requires raw JSON bytes from the wire"
        )
    _preflight_json_wire(raw_capsule)
    try:
        decoded = json.loads(
            raw_capsule,
            object_pairs_hook=_reject_duplicate_json_members,
        )
    except _DuplicateJsonMemberError as exc:
        raise CapsuleSchemaError(f"duplicate JSON member {exc.args[0]!r}") from exc
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise CapsuleSchemaError("capsule wire document is not valid JSON") from exc
    _preflight_json_value(decoded, path="capsule")
    if type(decoded) is not dict:
        raise CapsuleSchemaError("capsule wire document must decode to a JSON object")
    return decoded


def _write_jcs_string(value: str, sink: BinaryIO) -> None:
    def replace(match: re.Match[str]) -> str:
        return _ESCAPES[match.group(0)]

    sink.write(b'"')
    try:
        sink.write(_ESCAPE_RE.sub(replace, value).encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise CapsuleCanonicalizationError(
            "JCS strings cannot contain lone Unicode surrogates"
        ) from exc
    sink.write(b'"')


def _write_jcs_float(value: float, sink: BinaryIO) -> None:
    """Write ECMAScript's shortest binary64 representation used by JCS."""
    if not math.isfinite(value):
        raise CapsuleCanonicalizationError("JCS numbers cannot be NaN or infinite")
    if value == 0:
        sink.write(b"0")
        return
    if value < 0:
        sink.write(b"-")
        _write_jcs_float(-value, sink)
        return

    rendered = str(value)
    exponent_text = ""
    exponent = 0
    exponent_at = rendered.find("e")
    if exponent_at > 0:
        exponent_text = rendered[exponent_at:]
        if exponent_text[2:3] == "0":
            exponent_text = exponent_text[:2] + exponent_text[3:]
        rendered = rendered[:exponent_at]
        exponent = int(exponent_text[1:])

    integer = rendered
    fraction = ""
    dot = ""
    dot_at = rendered.find(".")
    if dot_at > 0:
        integer = rendered[:dot_at]
        fraction = rendered[dot_at + 1 :]
        dot = "."
    if fraction == "0":
        fraction = ""
        dot = ""

    if 0 < exponent < 21:
        integer += fraction
        fraction = ""
        dot = ""
        exponent_text = ""
        zeros = exponent - len(integer)
        while zeros >= 0:
            integer += "0"
            zeros -= 1
    elif -7 < exponent < 0:
        fraction = integer + fraction
        integer = "0"
        dot = "."
        exponent_text = ""
        zeros = exponent
        while zeros < -1:
            fraction = "0" + fraction
            zeros += 1

    sink.write(f"{integer}{dot}{fraction}{exponent_text}".encode("ascii"))


def _write_jcs(value: Any, sink: BinaryIO) -> None:
    if value is None:
        sink.write(b"null")
    elif type(value) is bool:
        sink.write(b"true" if value else b"false")
    elif type(value) is int:
        if not -_JSON_SAFE_INTEGER_MAX <= value <= _JSON_SAFE_INTEGER_MAX:
            raise CapsuleCanonicalizationError(
                f"integer {value} exceeds the IEEE-754 safe integer domain"
            )
        sink.write(str(value).encode("ascii"))
    elif type(value) is float:
        _write_jcs_float(value, sink)
    elif type(value) is str:
        _write_jcs_string(value, sink)
    elif type(value) is list:
        sink.write(b"[")
        for index, item in enumerate(value):
            if index:
                sink.write(b",")
            _write_jcs(item, sink)
        sink.write(b"]")
    elif type(value) is dict:
        try:
            items = sorted(value.items(), key=lambda item: item[0].encode("utf-16be"))
        except (AttributeError, UnicodeEncodeError) as exc:
            raise CapsuleCanonicalizationError(
                "JCS object keys must be valid Unicode strings"
            ) from exc
        sink.write(b"{")
        for index, (key, item) in enumerate(items):
            if type(key) is not str:
                raise CapsuleCanonicalizationError("JCS object keys must be strings")
            if index:
                sink.write(b",")
            _write_jcs_string(key, sink)
            sink.write(b":")
            _write_jcs(item, sink)
        sink.write(b"}")
    elif isinstance(value, (Mapping, Sequence)):
        raise CapsuleCanonicalizationError(
            "JCS accepts only JSON-native dict and list containers"
        )
    else:
        raise CapsuleCanonicalizationError(
            f"{type(value).__name__} is not a JSON-native JCS value"
        )


def canonicalize_jcs(value: Any) -> bytes:
    """Return RFC 8785/JCS canonical UTF-8 bytes for a JSON-native value."""
    _preflight_json_value(
        value,
        path="JCS input",
        error_type=CapsuleCanonicalizationError,
    )
    sink = BytesIO()
    _write_jcs(value, sink)
    return sink.getvalue()


def hash_canonical_jcs(value: Any) -> bytes:
    """Return SHA-256 over the shared RFC 8785/JCS representation."""
    return hashlib.sha256(canonicalize_jcs(value)).digest()


def sign_domain_separated_ed25519(
    digest: bytes, *, domain_separator: bytes, signing_key: SigningKey
) -> bytes:
    """Sign a canonical content digest under a pinned protocol domain."""
    return signing_key.sign(domain_separator + digest).signature


def verify_domain_separated_ed25519(
    digest: bytes,
    signature: bytes,
    *,
    domain_separator: bytes,
    verify_key: VerifyKey,
) -> None:
    """Verify a canonical content digest under a pinned protocol domain."""
    verify_key.verify(domain_separator + digest, signature)


def _schema_keys(schema: type) -> frozenset[str]:
    return cast(frozenset[str], schema.__required_keys__)


def _exact_object(value: Any, schema: type, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CapsuleSchemaError(f"{path} must be a JSON object")
    expected = _schema_keys(schema)
    actual = frozenset(value)
    if not all(type(key) is str for key in actual):
        raise CapsuleSchemaError(f"{path} keys must be strings")
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise CapsuleSchemaError(f"{path} missing fields {sorted(missing)}")
    if extra:
        raise CapsuleSchemaError(f"{path} has unknown fields {sorted(extra)}")
    return value


def _validate_payload_structure(value: Any) -> dict[str, Any]:
    payload = _exact_object(value, ExecutionCapsulePayloadV1, "payload")
    nested = (
        ("universe_scope", UniverseScopeV1),
        ("branch", BranchReferenceV1),
        ("node", NodeReferenceV1),
        ("base", BaseReferenceV1),
        ("source_blob", SourceBlobV1),
        ("execution_request", ExecutionRequestReferenceV1),
        ("allowed_capability", AllowedCapabilityV1),
        ("model_broker_route", ModelBrokerRouteV1),
        ("resource_limits", ResourceLimitsV1),
        ("lease", LeaseV1),
    )
    for key, schema in nested:
        _exact_object(payload[key], schema, f"payload.{key}")

    source_blob = payload["source_blob"]
    encryption = source_blob["encryption"]
    if encryption is not None:
        _exact_object(encryption, SourceEncryptionV1, "payload.source_blob.encryption")
    _exact_object(
        source_blob["producer"], SourceProducerV1, "payload.source_blob.producer"
    )

    inline = payload["execution_request"]["inline"]
    if inline is not None and type(inline) is not dict:
        raise CapsuleSchemaError("payload.execution_request.inline must be an object or null")
    return payload


def _validate_capsule_structure(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    capsule = _exact_object(value, ExecutionCapsuleV1, "capsule")
    payload = _validate_payload_structure(capsule["payload"])
    integrity = _exact_object(capsule["integrity"], CapsuleIntegrityV1, "integrity")
    return payload, integrity


def _path_field_name(key: str) -> bool:
    normalized = re.sub(r"[-\s]+", "_", key).casefold()
    base_name = _ENCODED_FIELD_SUFFIX_RE.sub("", normalized)
    # Defense in depth over the authoritative Layer-A/S6 sandbox: encoded
    # path fields are rejected by their declared meaning, not by guessing at
    # every possible path spelling in their value.
    return (
        base_name in {"path", "cwd", "directory", "worktree", "mount", "mounts"}
        or base_name.endswith("_path")
        or base_name.endswith("_dir")
        or base_name.endswith("_directory")
    )


def _looks_like_host_path(value: str) -> bool:
    lowered = value.casefold()
    return (
        value.startswith(("/", "\\\\", "//", "~/", "~\\", "./", ".\\", "../", "..\\"))
        or bool(_WINDOWS_ABSOLUTE_PATH_RE.match(value))
        or lowered.startswith("file:")
    )


def _reject_path_material(
    value: Any,
    path: str = "payload",
    *,
    validate_b64: bool = True,
) -> None:
    if type(value) is str:
        if _looks_like_host_path(value):
            raise CapsulePolicyError(f"{path} contains a forbidden host path")
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise CapsuleSchemaError(f"{path} contains a non-string key")
            if _path_field_name(key):
                raise CapsulePolicyError(f"{path}.{key} is a forbidden path field")
            item_path = f"{path}.{key}"
            if key.casefold().endswith("_b64"):
                if validate_b64:
                    if type(item) is not str:
                        raise CapsuleSchemaError(
                            f"{item_path} must be canonical base64"
                        )
                    _decode_b64(item, item_path)
            else:
                _reject_path_material(item, item_path, validate_b64=validate_b64)
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_path_material(
                item,
                f"{path}[{index}]",
                validate_b64=validate_b64,
            )


def reject_host_path_material(
    value: Any,
    path: str = "payload",
    *,
    validate_b64: bool = True,
) -> None:
    """Reject host-path fields and values using the capsule's policy rules."""
    _reject_path_material(value, path, validate_b64=validate_b64)


def _assert_capsule_json_domain(value: Any, path: str = "payload") -> None:
    if value is None or type(value) in {bool, str}:
        return
    if type(value) is int:
        if not 0 <= value <= _JSON_SAFE_INTEGER_MAX:
            raise CapsuleSchemaError(
                f"{path} integer must be between 0 and {_JSON_SAFE_INTEGER_MAX}"
            )
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise CapsuleSchemaError(f"{path} contains a non-finite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _assert_capsule_json_domain(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise CapsuleSchemaError(f"{path} contains a non-string key")
            _assert_capsule_json_domain(item, f"{path}.{key}")
        return
    raise CapsuleSchemaError(f"{path} contains non-JSON type {type(value).__name__}")


def _text(obj: dict[str, Any], key: str, path: str) -> str:
    value = obj[key]
    if type(value) is not str or not value:
        raise CapsuleSchemaError(f"{path}.{key} must be a non-empty string")
    return value


def _opaque_id(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    if not _OPAQUE_ID_RE.fullmatch(value):
        raise CapsuleSchemaError(
            f"{path}.{key} must be an ASCII opaque identifier"
        )
    return value


def _integer(obj: dict[str, Any], key: str, path: str) -> int:
    value = obj[key]
    if type(value) is not int or not 0 <= value <= _JSON_SAFE_INTEGER_MAX:
        raise CapsuleSchemaError(f"{path}.{key} must be a non-negative safe integer")
    return value


def _literal(
    obj: dict[str, Any], key: str, allowed: Collection[str], path: str
) -> str:
    value = _text(obj, key, path)
    if value not in allowed:
        raise CapsuleSchemaError(f"{path}.{key} has unsupported value {value!r}")
    return value


def _sha256(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    if not _SHA256_RE.fullmatch(value):
        raise CapsuleSchemaError(f"{path}.{key} must be lowercase SHA-256 hex")
    return value


def _uuid(obj: dict[str, Any], key: str, path: str) -> str:
    value = _text(obj, key, path)
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise CapsuleSchemaError(f"{path}.{key} must be a canonical RFC 4122 UUID") from exc
    if str(parsed) != value or parsed.variant != uuid.RFC_4122:
        raise CapsuleSchemaError(f"{path}.{key} must be a canonical RFC 4122 UUID")
    return value


def _timestamp(obj: dict[str, Any], key: str, path: str) -> datetime:
    value = _text(obj, key, path)
    if not _TIMESTAMP_RE.fullmatch(value):
        raise CapsuleSchemaError(f"{path}.{key} must be RFC 3339 UTC with Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CapsuleSchemaError(f"{path}.{key} must be a real RFC 3339 timestamp") from exc


def _decode_b64(value: str, path: str, *, exact_bytes: int | None = None) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CapsuleSchemaError(f"{path} must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise CapsuleSchemaError(f"{path} must be canonical padded base64")
    if exact_bytes is not None and len(decoded) != exact_bytes:
        raise CapsuleSchemaError(f"{path} must encode exactly {exact_bytes} bytes")
    if exact_bytes is None and not decoded:
        raise CapsuleSchemaError(f"{path} must not be empty")
    return decoded


def _is_unbound_capability(value: str) -> bool:
    # The opaque-ID gate has already enforced ASCII.  NFKC + casefold + removal
    # of the permitted separators prevents spelling evasions of the one exact
    # platform sentinel.  S0's resolved scope binding remains authoritative;
    # arbitrary "unbound-like" capability IDs are intentionally not rejected.
    folded = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^a-z0-9]", "", folded)
    return normalized in _UNBOUND_SENTINELS_NORMALIZED


def _validate_payload_semantics(payload: dict[str, Any]) -> None:
    _assert_capsule_json_domain(payload)
    canonicalize_jcs(payload)

    if payload["schema_version"] not in SUPPORTED_CAPSULE_SCHEMA_VERSIONS:
        raise CapsuleSchemaError(
            f"unsupported capsule schema version {payload['schema_version']!r}"
        )
    _uuid(payload, "capsule_id", "payload")
    _uuid(payload, "job_id", "payload")
    _integer(payload, "attempt", "payload")
    _opaque_id(payload, "audience_daemon_id", "payload")
    _opaque_id(payload, "owner_user_id", "payload")

    scope = payload["universe_scope"]
    _opaque_id(scope, "universe_id", "payload.universe_scope")
    capability_id = _opaque_id(scope, "capability_id", "payload.universe_scope")
    _integer(scope, "scope_version", "payload.universe_scope")
    permissions = scope["permissions"]
    if type(permissions) is not list or any(
        type(permission) is not str or permission not in _PERMISSIONS
        for permission in permissions
    ):
        raise CapsuleSchemaError("payload.universe_scope.permissions is invalid")

    branch = payload["branch"]
    _opaque_id(branch, "branch_definition_id", "payload.branch")
    _sha256(branch, "branch_version_sha256", "payload.branch")

    node = payload["node"]
    _opaque_id(node, "node_id", "payload.node")
    _sha256(node, "node_version_sha256", "payload.node")
    _text(node, "node_kind", "payload.node")

    base = payload["base"]
    _literal(base, "vcs", {"git"}, "payload.base")
    object_format = _literal(base, "object_format", {"sha1", "sha256"}, "payload.base")
    object_hex_length = 40 if object_format == "sha1" else 64
    for key in ("commit", "tree"):
        value = _text(base, key, "payload.base")
        if not re.fullmatch(rf"[0-9a-f]{{{object_hex_length}}}", value):
            raise CapsuleSchemaError(
                f"payload.base.{key} must match the declared {object_format} format"
            )

    source = payload["source_blob"]
    _text(source, "ref", "payload.source_blob")
    _literal(
        source,
        "media_type",
        {"application/vnd.tinyassets.git-bundle.v1"},
        "payload.source_blob",
    )
    for key in ("content_sha256", "transport_sha256", "manifest_sha256"):
        _sha256(source, key, "payload.source_blob")
    _integer(source, "size_bytes", "payload.source_blob")
    _literal(
        source,
        "confidentiality",
        {"public", "owner_private", "host_visible_private"},
        "payload.source_blob",
    )
    encryption = source["encryption"]
    if encryption is not None:
        _literal(
            encryption,
            "scheme",
            {"x25519-chacha20poly1305-v1"},
            "payload.source_blob.encryption",
        )
        _opaque_id(
            encryption,
            "recipient_device_key_id",
            "payload.source_blob.encryption",
        )
        wrapped = _text(
            encryption, "wrapped_content_key_b64", "payload.source_blob.encryption"
        )
        _decode_b64(wrapped, "payload.source_blob.encryption.wrapped_content_key_b64")
    producer = source["producer"]
    _opaque_id(producer, "daemon_id", "payload.source_blob.producer")
    _opaque_id(producer, "device_key_id", "payload.source_blob.producer")
    producer_signature = _text(
        producer, "signature_b64", "payload.source_blob.producer"
    )
    _decode_b64(
        producer_signature,
        "payload.source_blob.producer.signature_b64",
        exact_bytes=64,
    )

    request = payload["execution_request"]
    _integer(request, "schema_version", "payload.execution_request")
    request_ref = request["ref"]
    request_inline = request["inline"]
    if (request_ref is None) == (request_inline is None):
        raise CapsuleSchemaError(
            "exactly one of payload.execution_request.ref and inline must be non-null"
        )
    if request_ref is not None:
        if type(request_ref) is not str or not request_ref:
            raise CapsuleSchemaError("payload.execution_request.ref must be an opaque ref")
    else:
        request_bytes = canonicalize_jcs(request_inline)
        if len(request_bytes) > MAX_INLINE_REQUEST_BYTES:
            raise CapsulePolicyError("inline execution request exceeds 4,000,000 bytes")
        declared_hash = _sha256(request, "sha256", "payload.execution_request")
        if not hmac.compare_digest(declared_hash, hashlib.sha256(request_bytes).hexdigest()):
            raise CapsuleSchemaError("inline execution request sha256 does not match")
        if _integer(request, "size_bytes", "payload.execution_request") != len(request_bytes):
            raise CapsuleSchemaError("inline execution request size_bytes does not match")
    _sha256(request, "sha256", "payload.execution_request")
    request_size = _integer(request, "size_bytes", "payload.execution_request")
    if request_inline is not None and request_size > MAX_INLINE_REQUEST_BYTES:
        raise CapsulePolicyError("inline execution request exceeds 4,000,000 bytes")

    capability = payload["allowed_capability"]
    capability_class = _literal(
        capability, "class", _SANDBOX_CLASSES, "payload.allowed_capability"
    )
    repo_mode = capability["repo_mode"]
    if capability_class == "repo":
        if repo_mode not in _REPO_MODES:
            raise CapsuleSchemaError("repo capability requires a valid repo_mode")
    elif repo_mode is not None:
        raise CapsuleSchemaError("source_exec capability requires repo_mode null")
    required_permissions, forbidden_permissions = _CAPABILITY_PERMISSION_POLICY[
        (capability_class, repo_mode)
    ]
    permission_set = frozenset(permissions)
    missing_permissions = required_permissions - permission_set
    incompatible_permissions = forbidden_permissions & permission_set
    if missing_permissions or incompatible_permissions:
        details = []
        if missing_permissions:
            details.append(f"missing {sorted(missing_permissions)}")
        if incompatible_permissions:
            details.append(f"incompatible {sorted(incompatible_permissions)}")
        raise CapsulePolicyError(
            "payload.universe_scope.permissions do not match "
            f"{capability_class}/{repo_mode}: {', '.join(details)}"
        )
    _opaque_id(capability, "action_policy_id", "payload.allowed_capability")
    for key in ("action_policy_sha256", "runner_policy_sha256"):
        _sha256(capability, key, "payload.allowed_capability")
    image_digest = _text(capability, "image_digest", "payload.allowed_capability")
    if not _OCI_DIGEST_RE.fullmatch(image_digest):
        raise CapsuleSchemaError("payload.allowed_capability.image_digest must be immutable")
    if _is_unbound_capability(capability_id):
        raise CapsulePolicyError(
            "the LEGACY_UNBOUND platform sentinel is permanently forbidden "
            f"for sandbox execution class {capability_class!r}"
        )

    route = payload["model_broker_route"]
    _opaque_id(route, "route_id", "payload.model_broker_route")
    _integer(route, "route_version", "payload.model_broker_route")
    _sha256(route, "policy_sha256", "payload.model_broker_route")
    _text(route, "grant_ref", "payload.model_broker_route")
    model_classes = route["allowed_model_classes"]
    if type(model_classes) is not list or any(
        type(model_class) is not str or not model_class for model_class in model_classes
    ):
        raise CapsuleSchemaError("payload.model_broker_route.allowed_model_classes is invalid")
    max_calls = _integer(route, "max_calls", "payload.model_broker_route")
    if max_calls > 32:
        raise CapsulePolicyError("payload.model_broker_route.max_calls exceeds 32")
    _integer(route, "max_input_tokens", "payload.model_broker_route")
    _integer(route, "max_output_tokens", "payload.model_broker_route")
    _timestamp(route, "expires_at", "payload.model_broker_route")

    limits = payload["resource_limits"]
    for key, maximum in _POLICY_MAXIMUMS.items():
        if _integer(limits, key, "payload.resource_limits") > maximum:
            raise CapsulePolicyError(
                f"payload.resource_limits.{key} exceeds initial maximum {maximum}"
            )
    _literal(limits, "network", {"none", "model_broker_only"}, "payload.resource_limits")
    _opaque_id(limits, "egress_policy_id", "payload.resource_limits")
    _sha256(limits, "egress_policy_sha256", "payload.resource_limits")

    lease = payload["lease"]
    _uuid(lease, "lease_id", "payload.lease")
    _integer(lease, "fence", "payload.lease")
    lease_issued = _timestamp(lease, "issued_at", "payload.lease")
    lease_expires = _timestamp(lease, "expires_at", "payload.lease")
    if lease_expires <= lease_issued:
        raise CapsuleTimeError("payload.lease.expires_at must be after issued_at")

    issued = _timestamp(payload, "issued_at", "payload")
    not_before = _timestamp(payload, "not_before", "payload")
    expires = _timestamp(payload, "expires_at", "payload")
    if not issued <= not_before < expires:
        raise CapsuleTimeError(
            "payload timestamps must satisfy issued_at <= not_before < expires_at"
        )


def _validate_integrity(integrity: dict[str, Any]) -> bytes:
    _literal(integrity, "canonicalization", {"RFC8785-JCS"}, "integrity")
    _literal(integrity, "hash_algorithm", {"sha256"}, "integrity")
    _sha256(integrity, "capsule_sha256", "integrity")
    _literal(integrity, "signature_algorithm", {"ed25519"}, "integrity")
    signing_key_id = _opaque_id(integrity, "signing_key_id", "integrity")
    if _looks_like_host_path(signing_key_id):
        raise CapsulePolicyError("integrity.signing_key_id cannot be a host path")
    signature_b64 = _text(integrity, "signature_b64", "integrity")
    return _decode_b64(signature_b64, "integrity.signature_b64", exact_bytes=64)


def create_execution_capsule(
    payload: ExecutionCapsulePayloadV1 | dict[str, Any],
    *,
    signing_key: SigningKey,
    signing_key_id: str,
) -> ExecutionCapsuleV1:
    """Validate and sign an immutable V1 payload with an Ed25519 platform key."""
    # Account for the capsule object that will wrap this payload so creation
    # enforces the same root-relative depth as public wire verification.
    _preflight_json_value(payload, path="payload", initial_depth=2)
    payload_copy = copy.deepcopy(payload)
    payload_object = _validate_payload_structure(payload_copy)
    _reject_path_material(payload_object)
    _validate_payload_semantics(payload_object)
    if not isinstance(signing_key, SigningKey):
        raise CapsuleKeyError("signing_key must be a PyNaCl Ed25519 SigningKey")
    if type(signing_key_id) is not str or not signing_key_id:
        raise CapsuleKeyError("signing_key_id must be a non-empty string")
    if not _OPAQUE_ID_RE.fullmatch(signing_key_id):
        raise CapsuleKeyError("signing_key_id must be an ASCII opaque identifier")
    if _looks_like_host_path(signing_key_id):
        raise CapsulePolicyError("signing_key_id cannot be a host path")

    digest = hash_canonical_jcs(payload_object)
    signature = sign_domain_separated_ed25519(
        digest,
        domain_separator=CAPSULE_DOMAIN_SEPARATOR,
        signing_key=signing_key,
    )
    capsule: dict[str, Any] = {
        "payload": payload_object,
        "integrity": {
            "canonicalization": "RFC8785-JCS",
            "hash_algorithm": "sha256",
            "capsule_sha256": digest.hex(),
            "signature_algorithm": "ed25519",
            "signing_key_id": signing_key_id,
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        },
    }
    _preflight_json_value(capsule, path="capsule")
    _preflight_json_wire(canonicalize_jcs(capsule))
    return cast(ExecutionCapsuleV1, capsule)


def _verify_execution_capsule_trusted(
    capsule: ExecutionCapsuleV1 | dict[str, Any],
    *,
    verify_key: VerifyKey,
    expected_signing_key_id: str,
    signing_key_active: bool,
    expected_audience_daemon_id: str,
    expected_job_id: str,
    expected_lease_fence: int,
    supported_request_schema_versions: Collection[int],
    now: datetime | None = None,
) -> ExecutionCapsuleV1:
    """Verify an already-trusted decoded object.

    This private path exists only for locally created in-memory capsules and
    objects returned by the duplicate-rejecting wire parser below.  Network
    callers must use ``verify_execution_capsule`` with raw bytes.
    """
    _preflight_json_value(capsule, path="capsule")
    capsule_copy = copy.deepcopy(capsule)
    payload, integrity = _validate_capsule_structure(capsule_copy)
    _reject_path_material(payload, validate_b64=False)
    signature = _validate_integrity(integrity)

    digest = hash_canonical_jcs(payload)
    if not hmac.compare_digest(integrity["capsule_sha256"], digest.hex()):
        raise CapsuleIntegrityError("capsule_sha256 does not match canonical payload")
    if type(expected_signing_key_id) is not str or not expected_signing_key_id:
        raise CapsuleKeyError("expected_signing_key_id must be a non-empty string")
    if not _OPAQUE_ID_RE.fullmatch(expected_signing_key_id):
        raise CapsuleKeyError(
            "expected_signing_key_id must be an ASCII opaque identifier"
        )
    if integrity["signing_key_id"] != expected_signing_key_id:
        raise CapsuleKeyError("capsule signing key id is not the expected key")
    if signing_key_active is not True:
        raise CapsuleKeyError("capsule signing key is not active")
    if not isinstance(verify_key, VerifyKey):
        raise CapsuleKeyError("verify_key must be a PyNaCl Ed25519 VerifyKey")
    try:
        verify_domain_separated_ed25519(
            digest,
            signature,
            domain_separator=CAPSULE_DOMAIN_SEPARATOR,
            verify_key=verify_key,
        )
    except (BadSignatureError, ValueError) as exc:
        raise CapsuleIntegrityError("Ed25519 capsule signature verification failed") from exc

    _reject_path_material(payload)
    _validate_payload_semantics(payload)
    try:
        supported_versions = frozenset(supported_request_schema_versions)
    except (TypeError, ValueError) as exc:
        raise CapsuleBindingError("supported request schema versions are invalid") from exc
    if any(type(version) is not int for version in supported_versions):
        raise CapsuleBindingError("supported request schema versions must be integers")
    request_version = payload["execution_request"]["schema_version"]
    if request_version not in supported_versions:
        raise CapsuleBindingError(
            f"execution request schema v{request_version} is not supported; "
            f"supports {sorted(supported_versions)}"
        )

    if payload["audience_daemon_id"] != expected_audience_daemon_id:
        raise CapsuleBindingError("capsule audience daemon binding does not match")
    if payload["job_id"] != expected_job_id:
        raise CapsuleBindingError("capsule job binding does not match")
    if type(expected_lease_fence) is not int or expected_lease_fence < 0:
        raise CapsuleBindingError("expected lease fence must be a non-negative integer")
    if payload["lease"]["fence"] != expected_lease_fence:
        raise CapsuleBindingError("capsule lease fence binding does not match")

    checked_at = datetime.now(UTC) if now is None else now
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
        raise CapsuleTimeError("verification time must be timezone-aware")
    checked_at = checked_at.astimezone(UTC)
    if checked_at < _timestamp(payload, "not_before", "payload"):
        raise CapsuleTimeError("capsule is not active yet")
    if checked_at >= _timestamp(payload, "expires_at", "payload"):
        raise CapsuleTimeError("capsule has expired")
    lease = payload["lease"]
    if checked_at < _timestamp(lease, "issued_at", "payload.lease"):
        raise CapsuleTimeError("capsule lease is not active yet")
    if checked_at >= _timestamp(lease, "expires_at", "payload.lease"):
        raise CapsuleTimeError("capsule lease has expired")
    route = payload["model_broker_route"]
    if checked_at >= _timestamp(route, "expires_at", "payload.model_broker_route"):
        raise CapsuleTimeError("capsule model broker route has expired")
    return cast(ExecutionCapsuleV1, capsule_copy)


def verify_execution_capsule(
    raw_capsule: bytes,
    *,
    verify_key: VerifyKey,
    expected_signing_key_id: str,
    signing_key_active: bool,
    expected_audience_daemon_id: str,
    expected_job_id: str,
    expected_lease_fence: int,
    supported_request_schema_versions: Collection[int],
    now: datetime | None = None,
) -> ExecutionCapsuleV1:
    """Decode raw wire bytes and verify every V1 integrity and binding rule.

    Raw bytes are mandatory so duplicate JSON members are rejected before a
    decoder can collapse them.  There is intentionally no public decoded-dict,
    legacy, unbound, compatibility, or override path.
    """
    capsule = _decode_execution_capsule_wire(raw_capsule)
    return _verify_execution_capsule_trusted(
        capsule,
        verify_key=verify_key,
        expected_signing_key_id=expected_signing_key_id,
        signing_key_active=signing_key_active,
        expected_audience_daemon_id=expected_audience_daemon_id,
        expected_job_id=expected_job_id,
        expected_lease_fence=expected_lease_fence,
        supported_request_schema_versions=supported_request_schema_versions,
        now=now,
    )

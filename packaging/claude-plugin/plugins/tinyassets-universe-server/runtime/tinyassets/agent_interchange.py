"""Private staging and loss-aware interchange for portable agent definitions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tinyassets.custom_agents import (
    AgentConflictError,
    AgentNotFoundError,
    AgentValidationError,
    _author_and_key,
    _canonical_json,
    _check_secret_fields,
    _definition_from_row,
    _ensure_schema,
    _fingerprint,
    _is_sensitive_field_name,
    _looks_sensitive_value,
    _normalize_definition_payload,
    _publish_normalized,
    _read_definition_row,
)
from tinyassets.ids import new_ulid

ADAPTER_SCHEMA = "agent-interchange-adapter/v1"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_CANDIDATE_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_BASE64_CHARS = 1_398_104
MAX_POINTER_CHARS = 512
MAX_DETAIL_CHARS = 256
MAX_MAPPING_BYTES = 128 * 1024
MAX_MAPPING_RULES = 512
MAX_REPORT_ITEMS = 4096
MAX_DEPTH = 32
STAGE_TTL_SECONDS = 24 * 60 * 60
_HMAC_ENV = "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY"
_MASTER_HMAC_ENV = "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"
_HMAC_PURPOSE = b"tinyassets-agent-interchange-source-v1"
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLASSIFICATIONS = frozenset(
    {
        "preserved",
        "normalized",
        "unsupported",
        "omitted_secret",
        "requires_private_binding",
        "requires_runtime",
    }
)
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_INITIALIZED: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_import_stages (
    stage_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged', 'published')),
    direction TEXT NOT NULL CHECK (direction IN ('import', 'export')),
    source_media_type TEXT NOT NULL,
    sanitized_source_digest TEXT NOT NULL,
    source_commitment TEXT NOT NULL,
    adapter_ref TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    adapter_digest TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    published_definition_id TEXT,
    FOREIGN KEY(published_definition_id)
        REFERENCES agent_definitions(agent_definition_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_agent_import_stage_actor
    ON agent_import_stages(actor_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_interchange_idempotency (
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS agent_conversion_receipts (
    receipt_digest TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    stage_id TEXT,
    receipt_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(stage_id) REFERENCES agent_import_stages(stage_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS agent_conversion_receipt_links (
    stage_id TEXT PRIMARY KEY,
    receipt_digest TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(stage_id) REFERENCES agent_import_stages(stage_id) ON DELETE CASCADE,
    FOREIGN KEY(receipt_digest)
        REFERENCES agent_conversion_receipts(receipt_digest) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_agent_receipt_link_digest
    ON agent_conversion_receipt_links(receipt_digest, created_at);

CREATE TABLE IF NOT EXISTS agent_conversion_receipt_owners (
    actor_id TEXT NOT NULL,
    receipt_digest TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('convert_export')),
    created_at REAL NOT NULL,
    PRIMARY KEY(actor_id, receipt_digest, operation),
    FOREIGN KEY(receipt_digest)
        REFERENCES agent_conversion_receipts(receipt_digest) ON DELETE RESTRICT
);
"""


class InterchangeValidationError(AgentValidationError):
    """An interchange envelope violates the bounded public contract."""


class InterchangeConflictError(AgentConflictError):
    """An actor-scoped interchange idempotency identity conflicts."""


class InterchangeNotFoundError(AgentNotFoundError):
    """A private stage is absent, expired, or invisible to the caller."""


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _check_depth(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise InterchangeValidationError(f"payload nesting exceeds {MAX_DEPTH}")
    if isinstance(value, dict):
        for nested in value.values():
            _check_depth(nested, depth=depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _check_depth(nested, depth=depth + 1)


def _bounded_json(value: Any, *, limit: int, label: str) -> Any:
    try:
        cloned = _json_clone(value)
    except AgentValidationError as exc:
        raise InterchangeValidationError(str(exc)) from exc
    _check_depth(cloned)
    size = len(_canonical_json(cloned).encode("utf-8"))
    if size > limit:
        raise InterchangeValidationError(f"{label} exceeds {limit} bytes")
    return cloned


def _json_without_duplicate_keys(raw: str, *, label: str, limit: int) -> Any:
    if len(raw.encode("utf-8")) > limit:
        raise InterchangeValidationError(f"{label} exceeds {limit} bytes")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, nested in pairs:
            if key in document:
                raise InterchangeValidationError(f"{label} has duplicate object key: {key}")
            document[key] = nested
        return document

    try:
        return json.loads(raw, object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise InterchangeValidationError(f"{label} is invalid JSON: {exc}") from exc


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if (
        not isinstance(pointer, str)
        or not pointer.startswith("/")
        or len(pointer) > MAX_POINTER_CHARS
    ):
        raise InterchangeValidationError(
            f"JSON Pointer is invalid or exceeds {MAX_POINTER_CHARS} characters"
        )
    if re.search(r"~(?![01])", pointer):
        raise InterchangeValidationError("JSON Pointer contains an invalid RFC 6901 escape")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def enumerate_json_inventory(value: Any, pointer: str = "") -> list[str]:
    """Return canonical RFC 6901 paths for scalar leaves and empty containers."""

    if isinstance(value, dict):
        if not value:
            return [pointer]
        paths: list[str] = []
        for key in sorted(value):
            child = f"{pointer}/{_pointer_segment(str(key))}"
            paths.extend(enumerate_json_inventory(value[key], child))
        return paths
    if isinstance(value, list):
        if not value:
            return [pointer]
        paths = []
        for index, item in enumerate(value):
            paths.extend(enumerate_json_inventory(item, f"{pointer}/{index}"))
        return paths
    return [pointer]


def _validated_inventory(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_REPORT_ITEMS:
        raise InterchangeValidationError(
            f"source inventory must contain at most {MAX_REPORT_ITEMS} paths"
        )
    inventory: list[str] = []
    for path in value:
        if not isinstance(path, str):
            raise InterchangeValidationError("source inventory paths must be strings")
        if any(_looks_sensitive_value(part) for part in _pointer_parts(path)):
            raise InterchangeValidationError(
                "source inventory contains a credential-shaped path segment"
            )
        inventory.append(path)
    if len(set(inventory)) != len(inventory):
        raise InterchangeValidationError("source inventory paths must be unique")
    return inventory


def _validate_conversion_report(
    value: Any,
    *,
    direction: str,
    source_inventory: list[str],
) -> dict[str, Any]:
    report = _bounded_json(value, limit=MAX_RESPONSE_BYTES, label="conversion report")
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise InterchangeValidationError("conversion report schema_version must equal 1")
    expected_report_fields = {
        "schema_version",
        "direction",
        "inventory_verification",
        "exhaustive",
        "lossless",
        "items",
    }
    if report.get("inventory_verification") == "format_verifier":
        expected_report_fields.add("verifier_id")
    if set(report) != expected_report_fields:
        raise InterchangeValidationError(
            "conversion report fields do not match the canonical schema"
        )
    if report.get("direction") != direction:
        raise InterchangeValidationError("conversion report direction does not match request")
    verification = report.get("inventory_verification")
    if verification not in {"core_json", "format_verifier", "unverified"}:
        raise InterchangeValidationError("conversion report inventory verification is invalid")
    exhaustive = report.get("exhaustive")
    lossless = report.get("lossless")
    if not isinstance(exhaustive, bool) or not isinstance(lossless, bool):
        raise InterchangeValidationError("conversion report flags must be booleans")
    if verification == "unverified" and (exhaustive or lossless):
        raise InterchangeValidationError(
            "unverified inventory must be non-exhaustive and non-lossless"
        )
    if verification == "format_verifier":
        verifier_id = report.get("verifier_id")
        if not isinstance(verifier_id, str) or not verifier_id or len(verifier_id) > 256:
            raise InterchangeValidationError("format_verifier requires a bounded verifier_id")
    elif "verifier_id" in report:
        raise InterchangeValidationError("verifier_id is only valid for format_verifier")
    items = report.get("items")
    if not isinstance(items, list) or len(items) > MAX_REPORT_ITEMS:
        raise InterchangeValidationError(
            f"conversion report must contain at most {MAX_REPORT_ITEMS} items"
        )
    paths: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise InterchangeValidationError("conversion report items must be objects")
        expected_item_fields = {
            "source_path",
            "classification",
            "reason_code",
        }
        if "target_path" in item:
            expected_item_fields.add("target_path")
        if "detail" in item:
            expected_item_fields.add("detail")
        if set(item) != expected_item_fields:
            raise InterchangeValidationError(
                "conversion report item fields do not match the canonical schema"
            )
        source_path = item.get("source_path")
        if not isinstance(source_path, str):
            raise InterchangeValidationError("conversion report source_path is required")
        _pointer_parts(source_path)
        paths.append(source_path)
        target_path = item.get("target_path")
        if target_path is not None:
            if not isinstance(target_path, str):
                raise InterchangeValidationError("conversion report target_path must be a string")
            if any(_looks_sensitive_value(part) for part in _pointer_parts(target_path)):
                raise InterchangeValidationError(
                    "conversion report contains a credential-shaped target path"
                )
        if item.get("classification") not in _CLASSIFICATIONS:
            raise InterchangeValidationError("conversion report classification is invalid")
        reason_code = item.get("reason_code")
        if not isinstance(reason_code, str) or not _REASON_CODE.fullmatch(reason_code):
            raise InterchangeValidationError("conversion report reason_code is invalid")
        detail = item.get("detail")
        if detail is not None and (
            not isinstance(detail, str) or len(detail) > MAX_DETAIL_CHARS
        ):
            raise InterchangeValidationError(
                f"conversion report detail exceeds {MAX_DETAIL_CHARS} characters"
            )
        if _looks_sensitive_value(detail):
            raise InterchangeValidationError(
                "conversion report detail contains secret/credential content"
            )
    if len(set(paths)) != len(paths) or sorted(paths) != sorted(source_inventory):
        raise InterchangeValidationError(
            "conversion report must cover every inventory path exactly once"
        )
    if lossless:
        raise InterchangeValidationError(
            "lossless requires independent normalized source/output equality proof"
        )
    return report


def validate_adapter_request(
    request: str | dict[str, Any],
    *,
    admitted_source_locator: bool = False,
) -> dict[str, Any]:
    """Validate the authority-free request passed to an admitted adapter runtime."""

    raw = (
        _json_without_duplicate_keys(
            request,
            label="adapter request",
            limit=MAX_RESPONSE_BYTES,
        )
        if isinstance(request, str)
        else request
    )
    document = _bounded_json(raw, limit=MAX_RESPONSE_BYTES, label="adapter request")
    if not isinstance(document, dict) or document.get("schema_version") != ADAPTER_SCHEMA:
        raise InterchangeValidationError(
            f"adapter request schema_version must equal {ADAPTER_SCHEMA}"
        )
    if document.get("direction") not in {"import", "export"}:
        raise InterchangeValidationError("adapter request direction is invalid")
    for field in ("source_media_type", "target_media_type"):
        value = document.get(field)
        if not isinstance(value, str) or not value or len(value) > 127:
            raise InterchangeValidationError(f"adapter request {field} is invalid")
    source_fields = [
        field
        for field in ("source_json", "source_base64", "source_locator")
        if field in document
    ]
    if len(source_fields) != 1:
        raise InterchangeValidationError(
            "adapter request requires exactly one source_json, source_base64, or source_locator"
        )
    source_field = source_fields[0]
    expected_request_fields = {
        "schema_version",
        "direction",
        "source_media_type",
        "target_media_type",
        source_field,
    }
    if source_field == "source_json":
        expected_request_fields.add("source_inventory")
    if set(document) != expected_request_fields:
        raise InterchangeValidationError(
            "adapter request fields do not match the canonical schema"
        )
    if source_field == "source_json":
        source = document["source_json"]
        if not isinstance(source, dict):
            raise InterchangeValidationError("adapter request source_json must be an object")
        document["source_json"] = _bounded_json(
            source,
            limit=MAX_SOURCE_BYTES,
            label="source",
        )
        supplied_inventory = _validated_inventory(document.get("source_inventory"))
        enumerated_inventory = enumerate_json_inventory(document["source_json"])
        if supplied_inventory != enumerated_inventory:
            raise InterchangeValidationError(
                "source_inventory must equal the independently enumerated JSON inventory"
            )
    elif source_field == "source_base64":
        if "source_inventory" in document:
            raise InterchangeValidationError(
                "opaque adapter request must not claim a JSON source_inventory"
            )
        encoded = document["source_base64"]
        if not isinstance(encoded, str) or len(encoded) > MAX_BASE64_CHARS:
            raise InterchangeValidationError("source_base64 exceeds its encoded bound")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise InterchangeValidationError("source_base64 is not canonical base64") from exc
        if (
            len(decoded) > MAX_SOURCE_BYTES
            or base64.b64encode(decoded).decode("ascii") != encoded
        ):
            raise InterchangeValidationError(
                "source_base64 violates decoded or canonical bounds"
            )
    else:
        if "source_inventory" in document:
            raise InterchangeValidationError(
                "locator adapter request must not claim a JSON source_inventory"
            )
        locator = document["source_locator"]
        if not isinstance(locator, str) or not locator or len(locator) > 2048:
            raise InterchangeValidationError("source_locator is required and bounded to 2048")
        if not admitted_source_locator:
            raise InterchangeValidationError(
                "source_locator requires a governed runtime entitlement"
            )
    return document


def validate_adapter_response(
    response: str | dict[str, Any],
    *,
    direction: str,
    trusted_preservation: bool = False,
) -> dict[str, Any]:
    """Validate an untrusted Engine OS adapter response before any persistence."""

    if direction not in {"import", "export"}:
        raise InterchangeValidationError("adapter direction must be import or export")
    raw = (
        _json_without_duplicate_keys(
            response,
            label="adapter response",
            limit=MAX_RESPONSE_BYTES,
        )
        if isinstance(response, str)
        else response
    )
    document = _bounded_json(raw, limit=MAX_RESPONSE_BYTES, label="adapter response")
    if not isinstance(document, dict) or document.get("schema_version") != ADAPTER_SCHEMA:
        raise InterchangeValidationError(
            f"adapter response schema_version must equal {ADAPTER_SCHEMA}"
        )
    status = document.get("status")
    if status not in {"converted", "requires_runtime", "unsupported", "invalid"}:
        raise InterchangeValidationError("adapter response status is invalid")
    for field, limit in (("adapter_ref", 256), ("adapter_version", 64)):
        value = document.get(field)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise InterchangeValidationError(f"adapter response {field} is invalid")
    if document.get("adapter_digest_algorithm") != "sha256" or not re.fullmatch(
        r"[0-9a-f]{64}", str(document.get("adapter_digest") or "")
    ):
        raise InterchangeValidationError("adapter response digest is invalid")
    inventory = _validated_inventory(document.get("source_inventory"))
    document["report"] = _validate_conversion_report(
        document.get("report"),
        direction=direction,
        source_inventory=inventory,
    )
    if not trusted_preservation and any(
        item["classification"] in {"preserved", "normalized"}
        for item in document["report"]["items"]
    ):
        raise InterchangeValidationError(
            "preserved or normalized claims require an independent preservation proof"
        )
    output_fields = [
        field for field in ("candidate_json", "output_base64") if field in document
    ]
    if status == "converted":
        if len(output_fields) != 1 or "error_code" in document:
            raise InterchangeValidationError(
                "converted response requires exactly one output and forbids error_code"
            )
        if "candidate_json" in document:
            candidate = _bounded_json(
                document["candidate_json"],
                limit=MAX_CANDIDATE_BYTES,
                label="canonical candidate",
            )
            try:
                document["candidate_json"] = _normalize_definition_payload(candidate)
            except AgentValidationError as exc:
                raise InterchangeValidationError(str(exc)) from exc
        else:
            encoded = document["output_base64"]
            if not isinstance(encoded, str) or len(encoded) > MAX_BASE64_CHARS:
                raise InterchangeValidationError("output_base64 exceeds its encoded bound")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise InterchangeValidationError("output_base64 is not canonical base64") from exc
            if (
                len(decoded) > MAX_SOURCE_BYTES
                or base64.b64encode(decoded).decode("ascii") != encoded
            ):
                raise InterchangeValidationError(
                    "output_base64 violates decoded or canonical bounds"
                )
        expected_response_fields = {
            "schema_version",
            "status",
            "adapter_ref",
            "adapter_version",
            "adapter_digest_algorithm",
            "adapter_digest",
            "source_inventory",
            "report",
            output_fields[0],
        }
    else:
        if output_fields:
            raise InterchangeValidationError("non-converted response forbids adapter output")
        error_code = document.get("error_code")
        if not isinstance(error_code, str) or not _REASON_CODE.fullmatch(error_code):
            raise InterchangeValidationError("non-converted response requires error_code")
        expected_response_fields = {
            "schema_version",
            "status",
            "adapter_ref",
            "adapter_version",
            "adapter_digest_algorithm",
            "adapter_digest",
            "source_inventory",
            "report",
            "error_code",
        }
    if set(document) != expected_response_fields:
        raise InterchangeValidationError(
            "adapter response fields do not match the canonical schema"
        )
    _ensure_no_sensitive_content(document, label="adapter response")
    return document


def requires_runtime_response(
    adapter: dict[str, Any],
    *,
    direction: str,
    source_json: dict[str, Any] | None = None,
    source_base64: str | None = None,
    source_locator: str | None = None,
) -> dict[str, Any]:
    """Return a bounded terminal response without executing an unadmitted adapter."""

    sources = [source_json is not None, source_base64 is not None, source_locator is not None]
    if sum(sources) != 1:
        raise InterchangeValidationError(
            "adapter request requires exactly one source_json, source_base64, or source_locator"
        )
    mapping = _bounded_json(adapter, limit=MAX_MAPPING_BYTES, label="adapter mapping")
    if mapping.get("schema_version") != ADAPTER_SCHEMA:
        raise InterchangeValidationError(f"adapter schema_version must equal {ADAPTER_SCHEMA}")
    if _sanitize(mapping) != mapping:
        raise InterchangeValidationError("adapter mapping contains a secret-bearing field")
    adapter_ref = mapping.get("adapter_ref")
    adapter_version = mapping.get("adapter_version")
    if not isinstance(adapter_ref, str) or not adapter_ref or len(adapter_ref) > 256:
        raise InterchangeValidationError("adapter_ref is required and bounded to 256 characters")
    if (
        not isinstance(adapter_version, str)
        or not adapter_version
        or len(adapter_version) > 64
    ):
        raise InterchangeValidationError("adapter_version is required and bounded to 64 characters")

    if source_json is not None:
        source = _bounded_json(source_json, limit=MAX_SOURCE_BYTES, label="source")
        inventory = enumerate_json_inventory(source)
        if len(inventory) > MAX_REPORT_ITEMS:
            raise InterchangeValidationError(
                f"source inventory exceeds {MAX_REPORT_ITEMS} items"
            )
        verification = "core_json"
        exhaustive = True
        items = [
            {
                "source_path": path,
                "classification": "requires_runtime",
                "reason_code": "requires_runtime",
            }
            for path in inventory
        ]
    else:
        inventory = []
        verification = "unverified"
        exhaustive = False
        items = []
        if source_base64 is not None:
            if len(source_base64) > MAX_BASE64_CHARS:
                raise InterchangeValidationError("source_base64 exceeds its encoded bound")
            try:
                decoded = base64.b64decode(source_base64, validate=True)
            except (ValueError, TypeError) as exc:
                raise InterchangeValidationError("source_base64 is not canonical base64") from exc
            if (
                len(decoded) > MAX_SOURCE_BYTES
                or base64.b64encode(decoded).decode("ascii") != source_base64
            ):
                raise InterchangeValidationError(
                    "source_base64 violates decoded or canonical bounds"
                )
        elif (
            not isinstance(source_locator, str)
            or not source_locator
            or len(source_locator) > 2048
        ):
            raise InterchangeValidationError("source_locator is required and bounded to 2048")
    response = {
        "schema_version": ADAPTER_SCHEMA,
        "status": "requires_runtime",
        "adapter_ref": adapter_ref,
        "adapter_version": adapter_version,
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": _sha256(mapping),
        "source_inventory": inventory,
        "report": {
            "schema_version": 1,
            "direction": direction,
            "inventory_verification": verification,
            "exhaustive": exhaustive,
            "lossless": False,
            "items": items,
        },
        "error_code": "requires_engine_os",
    }
    return validate_adapter_response(response, direction=direction)


def _pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for part in _pointer_parts(pointer):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise InterchangeValidationError(f"source path {pointer} does not exist")
    return _json_clone(current)


def _pointer_set(root: dict[str, Any], pointer: str, value: Any) -> None:
    parts = _pointer_parts(pointer)
    if not parts:
        if not isinstance(value, dict):
            raise InterchangeValidationError("root adapter output must be a JSON object")
        root.clear()
        root.update(_json_clone(value))
        return
    current = root
    for part in parts[:-1]:
        nested = current.setdefault(part, {})
        if not isinstance(nested, dict):
            raise InterchangeValidationError(f"target path {pointer} collides")
        current = nested
    current[parts[-1]] = _json_clone(value)


def _is_secret_path(pointer: str) -> bool:
    return any(_is_sensitive_field_name(part) for part in _pointer_parts(pointer))


def _looks_secret_value(value: Any) -> bool:
    return _looks_sensitive_value(value)


def _ensure_no_sensitive_content(value: Any, *, label: str) -> None:
    try:
        _check_secret_fields(value)
    except AgentValidationError as exc:
        raise InterchangeValidationError(f"{label} contains secret/private content: {exc}") from exc


def _sanitize(value: Any, pointer: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            child = f"{pointer}/{_pointer_segment(str(key))}"
            sanitized[key] = (
                "[omitted_secret]"
                if _is_secret_path(child)
                else _sanitize(nested, child)
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, f"{pointer}/{index}") for index, item in enumerate(value)]
    if _looks_secret_value(value):
        return "[omitted_secret]"
    return _json_clone(value)


def _matching_rule(path: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    matches = []
    for rule in rules:
        source_path = rule.get("source_path")
        if isinstance(source_path, str) and (
            path == source_path or path.startswith(f"{source_path}/")
        ):
            matches.append(rule)
    if len(matches) != 1:
        suffix = "is missing" if not matches else "is covered more than once"
        raise InterchangeValidationError(f"inventory path {path} {suffix}")
    return matches[0]


def _validate_declarative_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise InterchangeValidationError(
            "adapter rule does not match the canonical grammar"
        )
    op = rule.get("op")
    optional_reason = {"reason_code"} if "reason_code" in rule else set()
    if op == "constant":
        expected = {"op", "target_path", "value"}
        allowed_classifications: set[str] = set()
    elif op in {"copy", "namespace_preserve"}:
        expected = {"op", "source_path", "target_path", "classification"}
        expected |= optional_reason
        allowed_classifications = {"preserved", "normalized"}
    elif op == "omit":
        expected = {"op", "source_path", "classification"} | optional_reason
        allowed_classifications = {
            "unsupported",
            "omitted_secret",
            "requires_private_binding",
            "requires_runtime",
        }
    else:
        raise InterchangeValidationError(
            "adapter rule does not match the canonical grammar"
        )
    if set(rule) != expected:
        raise InterchangeValidationError(
            "adapter rule fields do not match the canonical grammar"
        )
    if "source_path" in rule:
        if not isinstance(rule["source_path"], str):
            raise InterchangeValidationError(
                "adapter rule source_path does not match the canonical grammar"
            )
        _pointer_parts(rule["source_path"])
    if "target_path" in rule:
        if not isinstance(rule["target_path"], str):
            raise InterchangeValidationError(
                "adapter rule target_path does not match the canonical grammar"
            )
        _pointer_parts(rule["target_path"])
        if _is_secret_path(rule["target_path"]):
            raise InterchangeValidationError(
                "adapter rule target_path contains secret/private content"
            )
    if allowed_classifications and rule.get("classification") not in allowed_classifications:
        raise InterchangeValidationError(
            "adapter rule classification does not match the canonical grammar"
        )
    reason_code = rule.get("reason_code")
    if reason_code is not None and (
        not isinstance(reason_code, str) or not _REASON_CODE.fullmatch(reason_code)
    ):
        raise InterchangeValidationError(
            "adapter rule reason_code does not match the canonical grammar"
        )
    return rule


def _adapter_metadata(adapter: dict[str, Any]) -> tuple[dict[str, Any], str]:
    document = _bounded_json(adapter, limit=MAX_MAPPING_BYTES, label="adapter mapping")
    _ensure_no_sensitive_content(document, label="adapter mapping")
    if document.get("schema_version") != ADAPTER_SCHEMA:
        raise InterchangeValidationError(f"adapter schema_version must equal {ADAPTER_SCHEMA}")
    adapter_ref = str(document.get("adapter_ref") or "").strip()
    adapter_version = str(document.get("adapter_version") or "").strip()
    if not adapter_ref or len(adapter_ref) > 256:
        raise InterchangeValidationError("adapter_ref is required and bounded to 256 characters")
    if not adapter_version or len(adapter_version) > 64:
        raise InterchangeValidationError("adapter_version is required and bounded to 64 characters")
    target_media_type = str(document.get("target_media_type") or "application/json")
    if not target_media_type or len(target_media_type) > 127:
        raise InterchangeValidationError("target_media_type is bounded to 127 characters")
    rules = document.get("rules")
    if not isinstance(rules, list) or len(rules) > MAX_MAPPING_RULES:
        raise InterchangeValidationError(
            f"adapter rules must be a list of at most {MAX_MAPPING_RULES}"
        )
    expected_mapping_fields = {
        "schema_version",
        "adapter_ref",
        "adapter_version",
        "rules",
    }
    if "target_media_type" in document:
        expected_mapping_fields.add("target_media_type")
    if set(document) != expected_mapping_fields:
        raise InterchangeValidationError(
            "adapter mapping fields do not match the canonical grammar"
        )
    document["rules"] = [_validate_declarative_rule(rule) for rule in rules]
    target_paths = [
        _pointer_parts(str(rule["target_path"]))
        for rule in document["rules"]
        if "target_path" in rule
    ]
    for index, left in enumerate(target_paths):
        for right in target_paths[index + 1 :]:
            shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
            if longer[: len(shorter)] == shorter:
                raise InterchangeValidationError(
                    "adapter rule target paths overlap in the canonical grammar"
                )
    return document, _sha256(document)


def convert_declarative_json(
    source_json: dict[str, Any],
    adapter: dict[str, Any],
) -> dict[str, Any]:
    """Apply the closed declarative JSON mapping grammar."""

    source = _bounded_json(source_json, limit=MAX_SOURCE_BYTES, label="source")
    mapping, adapter_digest = _adapter_metadata(adapter)
    rules: list[dict[str, Any]] = mapping["rules"]
    inventory = enumerate_json_inventory(source)
    if len(inventory) > MAX_REPORT_ITEMS:
        raise InterchangeValidationError(f"source inventory exceeds {MAX_REPORT_ITEMS} items")
    validate_adapter_request(
        {
            "schema_version": ADAPTER_SCHEMA,
            "direction": "import",
            "source_json": source,
            "source_media_type": "application/json",
            "target_media_type": "application/vnd.tinyassets.agent+json",
            "source_inventory": inventory,
        }
    )
    sanitized = _sanitize(source)
    candidate: dict[str, Any] = {}
    for rule in rules:
        op = str(rule.get("op") or "")
        if op not in {"constant", "copy", "namespace_preserve", "omit"}:
            raise InterchangeValidationError("adapter rule uses unsupported operation")

    items: list[dict[str, Any]] = []
    for path in inventory:
        rule = _matching_rule(path, rules)
        op = str(rule.get("op") or "")
        classification = str(rule.get("classification") or "")
        if classification not in _CLASSIFICATIONS:
            raise InterchangeValidationError(f"inventory path {path} has invalid classification")
        secret_path = _is_secret_path(path) or _looks_secret_value(
            _pointer_get(source, path)
        )
        if secret_path and (
            op != "omit" or classification not in {"omitted_secret", "requires_private_binding"}
        ):
            raise InterchangeValidationError(f"secret inventory path {path} must be omitted")
        source_path = str(rule.get("source_path"))
        target_path = str(rule.get("target_path") or "")
        item = {
            "source_path": path,
            "classification": classification,
            "reason_code": str(rule.get("reason_code") or classification),
        }
        if not _REASON_CODE.fullmatch(item["reason_code"]):
            raise InterchangeValidationError(f"inventory path {path} has invalid reason_code")
        if target_path:
            suffix = path[len(source_path) :]
            item["target_path"] = f"{target_path}{suffix}"
        items.append(item)

    for rule in rules:
        if rule.get("op") in {"copy", "namespace_preserve"}:
            _pointer_set(
                candidate,
                str(rule.get("target_path") or ""),
                _pointer_get(sanitized, str(rule.get("source_path") or "")),
            )
    for rule in rules:
        if rule.get("op") == "constant":
            _pointer_set(
                candidate,
                str(rule.get("target_path") or ""),
                rule.get("value"),
            )

    try:
        normalized = _normalize_definition_payload(candidate)
    except AgentValidationError as exc:
        raise InterchangeValidationError(str(exc)) from exc
    report = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        # A declarative foreign mapping proves exhaustive accounting, not
        # semantic equivalence between two independently defined formats.
        "lossless": False,
        "items": items,
    }
    report = _validate_conversion_report(
        report,
        direction="import",
        source_inventory=inventory,
    )
    return {
        "candidate": normalized,
        "report": report,
        "sanitized_source": sanitized,
        "adapter_ref": mapping["adapter_ref"],
        "adapter_version": mapping["adapter_version"],
        "adapter_digest": adapter_digest,
    }


def _convert_declarative_export(
    source_json: dict[str, Any],
    adapter: dict[str, Any],
) -> dict[str, Any]:
    source = _bounded_json(source_json, limit=MAX_CANDIDATE_BYTES, label="definition")
    mapping, adapter_digest = _adapter_metadata(adapter)
    rules: list[dict[str, Any]] = mapping["rules"]
    inventory = enumerate_json_inventory(source)
    if len(inventory) > MAX_REPORT_ITEMS:
        raise InterchangeValidationError(f"source inventory exceeds {MAX_REPORT_ITEMS} items")
    validate_adapter_request(
        {
            "schema_version": ADAPTER_SCHEMA,
            "direction": "export",
            "source_json": source,
            "source_media_type": "application/vnd.tinyassets.agent+json",
            "target_media_type": str(
                mapping.get("target_media_type") or "application/json"
            ),
            "source_inventory": inventory,
        }
    )
    sanitized = _sanitize(source)

    items: list[dict[str, Any]] = []
    for path in inventory:
        rule = _matching_rule(path, rules)
        op = str(rule.get("op") or "")
        if op not in {"copy", "namespace_preserve", "omit"}:
            raise InterchangeValidationError(
                "export inventory rules must copy, namespace-preserve, or omit"
            )
        classification = str(rule.get("classification") or "")
        if classification not in _CLASSIFICATIONS:
            raise InterchangeValidationError(f"inventory path {path} has invalid classification")
        secret_path = _is_secret_path(path) or _looks_secret_value(
            _pointer_get(source, path)
        )
        if secret_path and (
            op != "omit"
            or classification not in {
                "omitted_secret",
                "requires_private_binding",
            }
        ):
            raise InterchangeValidationError(f"secret inventory path {path} must be omitted")
        reason_code = str(rule.get("reason_code") or classification)
        if not _REASON_CODE.fullmatch(reason_code):
            raise InterchangeValidationError(f"inventory path {path} has invalid reason_code")
        source_path = str(rule.get("source_path") or "")
        target_path = str(rule.get("target_path") or "")
        item = {
            "source_path": path,
            "classification": classification,
            "reason_code": reason_code,
        }
        if target_path:
            _pointer_parts(target_path)
            item["target_path"] = f"{target_path}{path[len(source_path):]}"
        items.append(item)

    output: dict[str, Any] = {}
    for rule in rules:
        op = str(rule.get("op") or "")
        if op in {"copy", "namespace_preserve"}:
            _pointer_set(
                output,
                str(rule.get("target_path") or ""),
                _pointer_get(sanitized, str(rule.get("source_path") or "")),
            )
        elif op == "constant":
            _pointer_set(output, str(rule.get("target_path") or ""), rule.get("value"))
        elif op != "omit":
            raise InterchangeValidationError("adapter rule uses unsupported operation")

    output = _bounded_json(output, limit=MAX_SOURCE_BYTES, label="foreign output")
    _ensure_no_sensitive_content(output, label="foreign output")
    report = {
        "schema_version": 1,
        "direction": "export",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": False,
        "items": items,
    }
    report = _validate_conversion_report(
        report,
        direction="export",
        source_inventory=inventory,
    )
    return {
        "output": output,
        "source_inventory": inventory,
        "report": report,
        "adapter_ref": mapping["adapter_ref"],
        "adapter_version": mapping["adapter_version"],
        "adapter_digest": adapter_digest,
        "target_media_type": str(mapping.get("target_media_type") or "application/json"),
    }


def _ensure_interchange_schema(base_path: str | Path) -> Path:
    path = _ensure_schema(base_path)
    key = str(path)
    if key in _SCHEMA_INITIALIZED:
        return path
    with _SCHEMA_LOCK:
        if key in _SCHEMA_INITIALIZED:
            return path
        conn = sqlite3.connect(path, timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                conn.executescript(_SCHEMA)
                conn.execute(
                    """
                    UPDATE agent_import_stages
                    SET source_commitment = ''
                    WHERE status = 'published' AND source_commitment != ''
                    """
                )
        finally:
            conn.close()
        _SCHEMA_INITIALIZED.add(key)
    return path


@contextmanager
def _interchange_connect(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = _ensure_interchange_schema(base_path)
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _source_commitment(source: Any) -> str:
    dedicated = os.environ.get(_HMAC_ENV, "").encode("utf-8")
    master = os.environ.get(_MASTER_HMAC_ENV, "").encode("utf-8")
    material = dedicated or master
    if len(material) < 32:
        raise InterchangeValidationError(
            f"{_HMAC_ENV} or {_MASTER_HMAC_ENV} must contain at least 32 bytes"
        )
    key = hmac.new(material, _HMAC_PURPOSE, hashlib.sha256).digest()
    return hmac.new(key, _canonical_json(source).encode("utf-8"), hashlib.sha256).hexdigest()


def _receipt(
    *,
    conversion: dict[str, Any],
    sanitized_source_digest: str,
    created_at: float,
) -> dict[str, Any]:
    candidate_fingerprint = _fingerprint(conversion["candidate"])
    report_digest = _sha256(conversion["report"])
    receipt = {
        "schema_version": 1,
        "direction": "import",
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": sanitized_source_digest,
        "adapter_ref": conversion["adapter_ref"],
        "adapter_version": conversion["adapter_version"],
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": conversion["adapter_digest"],
        "output_kind": "canonical_definition",
        "output_digest_algorithm": "sha256",
        "output_digest": candidate_fingerprint,
        "content_fingerprint": candidate_fingerprint,
        "report_digest_algorithm": "sha256",
        "report_digest": report_digest,
        "created_at": created_at,
        "receipt_digest_algorithm": "sha256",
    }
    receipt["receipt_digest"] = _sha256(receipt)
    verify_conversion_receipt(receipt)
    return receipt


def _export_receipt(
    *,
    conversion: dict[str, Any],
    source: dict[str, Any],
    output_bytes: bytes,
    created_at: float,
) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "direction": "export",
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": _sha256(source),
        "adapter_ref": conversion["adapter_ref"],
        "adapter_version": conversion["adapter_version"],
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": conversion["adapter_digest"],
        "output_kind": "foreign_bytes",
        "output_digest_algorithm": "sha256",
        "output_digest": _sha256_bytes(output_bytes),
        "report_digest_algorithm": "sha256",
        "report_digest": _sha256(conversion["report"]),
        "created_at": created_at,
        "receipt_digest_algorithm": "sha256",
    }
    receipt["receipt_digest"] = _sha256(receipt)
    verify_conversion_receipt(receipt)
    return receipt


def verify_conversion_receipt(receipt: dict[str, Any]) -> bool:
    document = _bounded_json(receipt, limit=MAX_SOURCE_BYTES, label="receipt")
    required = {
        "schema_version",
        "direction",
        "sanitized_source_digest_algorithm",
        "sanitized_source_digest",
        "adapter_ref",
        "adapter_version",
        "adapter_digest_algorithm",
        "adapter_digest",
        "output_kind",
        "output_digest_algorithm",
        "output_digest",
        "report_digest_algorithm",
        "report_digest",
        "created_at",
        "receipt_digest_algorithm",
        "receipt_digest",
    }
    if document.get("output_kind") == "canonical_definition":
        required.add("content_fingerprint")
    if set(document) != required:
        raise InterchangeValidationError("receipt fields do not match the canonical schema")
    _ensure_no_sensitive_content(document, label="conversion receipt")
    if document.get("schema_version") != 1 or document.get("direction") not in {
        "import",
        "export",
    }:
        raise InterchangeValidationError("receipt schema or direction is invalid")
    for field in (
        "sanitized_source_digest_algorithm",
        "adapter_digest_algorithm",
        "output_digest_algorithm",
        "report_digest_algorithm",
        "receipt_digest_algorithm",
    ):
        if document.get(field) != "sha256":
            raise InterchangeValidationError(f"receipt {field} algorithm must equal sha256")
    for field in (
        "sanitized_source_digest",
        "adapter_digest",
        "output_digest",
        "report_digest",
        "receipt_digest",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(document.get(field) or "")):
            raise InterchangeValidationError(f"receipt {field} must be lowercase SHA-256")
    for field, limit in (("adapter_ref", 256), ("adapter_version", 64)):
        value = document.get(field)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise InterchangeValidationError(f"receipt {field} is invalid")
    if document.get("output_kind") not in {"canonical_definition", "foreign_bytes"}:
        raise InterchangeValidationError("receipt output_kind is invalid")
    if document.get("output_kind") == "canonical_definition" and (
        document.get("content_fingerprint") != document.get("output_digest")
    ):
        raise InterchangeValidationError(
            "canonical receipt content_fingerprint must equal output_digest"
        )
    created_at = document.get("created_at")
    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        raise InterchangeValidationError("receipt created_at must be finite")
    if not math.isfinite(float(created_at)):
        raise InterchangeValidationError("receipt created_at must be finite")
    supplied = str(document.pop("receipt_digest"))
    if not re.fullmatch(r"[0-9a-f]{64}", supplied) or supplied != _sha256(document):
        raise InterchangeValidationError("receipt digest does not match")
    return True


def convert_export(
    base_path: str | Path,
    *,
    actor_id: str,
    definition_id: str,
    adapter: dict[str, Any],
    idempotency_key: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Convert one public canonical definition through a bounded mapping artifact."""

    actor, key = _author_and_key(actor_id, idempotency_key)
    created_at = time.time() if now is None else float(now)
    if not math.isfinite(created_at):
        raise InterchangeValidationError("now must be finite")
    with _interchange_connect(base_path) as conn:
        row = _read_definition_row(conn, (definition_id or "").strip())
        if row is None:
            raise InterchangeNotFoundError("agent definition is unavailable")
        definition = _definition_from_row(conn, row)
        source = definition["portable_definition"]
        conversion = _convert_declarative_export(source, adapter)
        output_bytes = _canonical_json(conversion["output"]).encode("utf-8")
        output_base64 = base64.b64encode(output_bytes).decode("ascii")
        request_digest = _sha256(
            {
                "direction": "export",
                "definition_fingerprint": definition["content_fingerprint"],
                "adapter_digest": conversion["adapter_digest"],
            }
        )
        existing_receipt_id = _idempotent_resource(
            conn,
            actor=actor,
            operation="convert_export",
            key=key,
            request_digest=request_digest,
        )
        if existing_receipt_id:
            receipt_row = conn.execute(
                "SELECT receipt_json FROM agent_conversion_receipts WHERE receipt_digest = ?",
                (existing_receipt_id,),
            ).fetchone()
            if receipt_row is None:
                raise InterchangeNotFoundError("conversion receipt is unavailable")
            receipt = json.loads(str(receipt_row["receipt_json"]))
        else:
            receipt = _export_receipt(
                conversion=conversion,
                source=source,
                output_bytes=output_bytes,
                created_at=created_at,
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_conversion_receipts (
                    receipt_digest, actor_id, stage_id, receipt_json, created_at
                ) VALUES (?, ?, NULL, ?, ?)
                """,
                (
                    receipt["receipt_digest"],
                    "content-addressed",
                    _canonical_json(receipt),
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_conversion_receipt_owners (
                    actor_id, receipt_digest, operation, created_at
                ) VALUES (?, ?, 'convert_export', ?)
                """,
                (actor, receipt["receipt_digest"], created_at),
            )
            if key:
                conn.execute(
                    """
                    INSERT INTO agent_interchange_idempotency (
                        actor_id, operation, idempotency_key,
                        request_digest, resource_id, created_at
                    ) VALUES (?, 'convert_export', ?, ?, ?, ?)
                    """,
                    (
                        actor,
                        key,
                        request_digest,
                        receipt["receipt_digest"],
                        created_at,
                    ),
                )
        adapter_response = {
            "schema_version": ADAPTER_SCHEMA,
            "status": "converted",
            "adapter_ref": conversion["adapter_ref"],
            "adapter_version": conversion["adapter_version"],
            "adapter_digest_algorithm": "sha256",
            "adapter_digest": conversion["adapter_digest"],
            "source_inventory": conversion["source_inventory"],
            "output_base64": output_base64,
            "report": conversion["report"],
        }
        validated = validate_adapter_response(
            adapter_response,
            direction="export",
            trusted_preservation=True,
        )
        validated.update(
            {
                "direction": "export",
                "target_media_type": conversion["target_media_type"],
                "receipt": receipt,
            }
        )
        return _bounded_json(validated, limit=MAX_RESPONSE_BYTES, label="export response")


def _stage_from_row(row: sqlite3.Row) -> dict[str, Any]:
    stage = {
        "schema_version": 1,
        "stage_id": str(row["stage_id"]),
        "actor_id": str(row["actor_id"]),
        "status": str(row["status"]),
        "direction": str(row["direction"]),
        "source_media_type": str(row["source_media_type"]),
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": str(row["sanitized_source_digest"]),
        "adapter_ref": str(row["adapter_ref"]),
        "adapter_version": str(row["adapter_version"]),
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": str(row["adapter_digest"]),
        "candidate": json.loads(str(row["candidate_json"])),
        "report": json.loads(str(row["report_json"])),
        "receipt": json.loads(str(row["receipt_json"])),
        "created_at": float(row["created_at"]),
        "expires_at": float(row["expires_at"]),
        "published_definition_id": row["published_definition_id"],
    }
    source_commitment = str(row["source_commitment"] or "")
    if source_commitment:
        stage["source_commitment_algorithm"] = "hmac-sha256"
        stage["source_commitment"] = source_commitment
    return stage


def _idempotent_resource(
    conn: sqlite3.Connection,
    *,
    actor: str,
    operation: str,
    key: str,
    request_digest: str,
) -> str | None:
    if not key:
        return None
    row = conn.execute(
        """
        SELECT request_digest, resource_id
        FROM agent_interchange_idempotency
        WHERE actor_id = ? AND operation = ? AND idempotency_key = ?
        """,
        (actor, operation, key),
    ).fetchone()
    if row is None:
        return None
    if row["request_digest"] != request_digest:
        raise InterchangeConflictError("idempotency key was used for different input")
    return str(row["resource_id"])


def _prune_expired_stages(
    conn: sqlite3.Connection,
    *,
    current: float,
    actor: str = "",
    stage_id: str = "",
) -> set[str]:
    clauses = ["status = 'staged'", "expires_at <= ?"]
    params: list[Any] = [current]
    if actor:
        clauses.append("actor_id = ?")
        params.append(actor)
    if stage_id:
        clauses.append("stage_id = ?")
        params.append(stage_id)
    rows = conn.execute(
        f"SELECT stage_id FROM agent_import_stages WHERE {' AND '.join(clauses)}",
        params,
    ).fetchall()
    expired = {str(row["stage_id"]) for row in rows}
    if not expired:
        return expired
    placeholders = ",".join("?" for _ in expired)
    ordered = sorted(expired)
    conn.execute(
        f"DELETE FROM agent_interchange_idempotency WHERE resource_id IN ({placeholders})",
        ordered,
    )
    conn.execute(
        f"DELETE FROM agent_import_stages WHERE stage_id IN ({placeholders})",
        ordered,
    )
    return expired


def _attach_public_import_origin(
    conversion: dict[str, Any],
    *,
    sanitized_source_digest: str,
) -> None:
    origin = {
        "kind": "agent_interchange_import",
        "source_media_type": "application/json",
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": sanitized_source_digest,
        "adapter_ref": conversion["adapter_ref"],
        "adapter_version": conversion["adapter_version"],
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": conversion["adapter_digest"],
    }
    candidate = json.loads(_canonical_json(conversion["candidate"]))
    origins = list(candidate.get("external_origins", []))
    if origin not in origins:
        origins.append(origin)
    candidate["external_origins"] = origins
    try:
        conversion["candidate"] = _normalize_definition_payload(candidate)
    except AgentValidationError as exc:
        raise InterchangeValidationError(str(exc)) from exc


def stage_import(
    base_path: str | Path,
    *,
    actor_id: str,
    source_json: dict[str, Any],
    adapter: dict[str, Any],
    idempotency_key: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    actor, key = _author_and_key(actor_id, idempotency_key)
    created_at = time.time() if now is None else float(now)
    if not math.isfinite(created_at):
        raise InterchangeValidationError("now must be finite")
    source = _bounded_json(source_json, limit=MAX_SOURCE_BYTES, label="source")
    commitment = _source_commitment(source)
    conversion = convert_declarative_json(source, adapter)
    sanitized_digest = _sha256(conversion["sanitized_source"])
    _attach_public_import_origin(
        conversion,
        sanitized_source_digest=sanitized_digest,
    )
    receipt = _receipt(
        conversion=conversion,
        sanitized_source_digest=sanitized_digest,
        created_at=created_at,
    )
    request_digest = _sha256(
        {
            "source_commitment": commitment,
            "adapter_digest": conversion["adapter_digest"],
            "direction": "import",
        }
    )
    with _interchange_connect(base_path) as conn:
        _prune_expired_stages(conn, current=created_at)
        existing_id = _idempotent_resource(
            conn,
            actor=actor,
            operation="stage_import",
            key=key,
            request_digest=request_digest,
        )
        if existing_id:
            row = conn.execute(
                "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
                (existing_id, actor),
            ).fetchone()
            if row is None:
                raise InterchangeNotFoundError("import stage is unavailable")
            return _stage_from_row(row)
        stage_id = f"agent_stage_{new_ulid()}"
        expires_at = created_at + STAGE_TTL_SECONDS
        conn.execute(
            """
            INSERT INTO agent_import_stages (
                stage_id, actor_id, status, direction, source_media_type,
                sanitized_source_digest, source_commitment, adapter_ref,
                adapter_version, adapter_digest, candidate_json, report_json,
                receipt_json, created_at, expires_at
            ) VALUES (?, ?, 'staged', 'import', 'application/json', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stage_id,
                actor,
                sanitized_digest,
                commitment,
                conversion["adapter_ref"],
                conversion["adapter_version"],
                conversion["adapter_digest"],
                _canonical_json(conversion["candidate"]),
                _canonical_json(conversion["report"]),
                _canonical_json(receipt),
                created_at,
                expires_at,
            ),
        )
        if key:
            conn.execute(
                """
                INSERT INTO agent_interchange_idempotency (
                    actor_id, operation, idempotency_key,
                    request_digest, resource_id, created_at
                ) VALUES (?, 'stage_import', ?, ?, ?, ?)
                """,
                (actor, key, request_digest, stage_id, created_at),
            )
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ?",
            (stage_id,),
        ).fetchone()
        assert row is not None
        return _stage_from_row(row)


def get_import_stage(
    base_path: str | Path,
    *,
    actor_id: str,
    stage_id: str,
    now: float | None = None,
) -> dict[str, Any] | None:
    actor = (actor_id or "").strip()
    current = time.time() if now is None else float(now)
    if not math.isfinite(current):
        raise InterchangeValidationError("now must be finite")
    with _interchange_connect(base_path) as conn:
        _prune_expired_stages(
            conn,
            current=current,
            actor=actor,
            stage_id=(stage_id or "").strip(),
        )
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
            ((stage_id or "").strip(), actor),
        ).fetchone()
        if row is None:
            return None
        return _stage_from_row(row)


def publish_import_stage(
    base_path: str | Path,
    *,
    actor_id: str,
    stage_id: str,
    idempotency_key: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    actor, key = _author_and_key(actor_id, idempotency_key)
    current = time.time() if now is None else float(now)
    if not math.isfinite(current):
        raise InterchangeValidationError("now must be finite")
    normalized_stage_id = (stage_id or "").strip()
    with _interchange_connect(base_path) as conn:
        expired = _prune_expired_stages(
            conn,
            current=current,
            actor=actor,
            stage_id=normalized_stage_id,
        )
    if normalized_stage_id in expired:
        raise InterchangeNotFoundError("import stage is unavailable")
    with _interchange_connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
            (normalized_stage_id, actor),
        ).fetchone()
        if row is None:
            raise InterchangeNotFoundError("import stage is unavailable")
        candidate = json.loads(str(row["candidate_json"]))
        report = json.loads(str(row["report_json"]))
        receipt = json.loads(str(row["receipt_json"]))
        verify_conversion_receipt(receipt)
        receipt_matches_stage = (
            receipt["sanitized_source_digest"] == row["sanitized_source_digest"]
            and receipt["adapter_ref"] == row["adapter_ref"]
            and receipt["adapter_version"] == row["adapter_version"]
            and receipt["adapter_digest"] == row["adapter_digest"]
            and receipt["content_fingerprint"] == _fingerprint(candidate)
            and receipt["report_digest"] == _sha256(report)
        )
        if not receipt_matches_stage:
            raise InterchangeValidationError(
                "import stage receipt does not match staged content"
            )
        conversion = {
            "candidate": candidate,
            "report": report,
            "adapter_ref": str(row["adapter_ref"]),
            "adapter_version": str(row["adapter_version"]),
            "adapter_digest": str(row["adapter_digest"]),
        }
        _attach_public_import_origin(
            conversion,
            sanitized_source_digest=str(row["sanitized_source_digest"]),
        )
        if conversion["candidate"] != candidate:
            receipt = _receipt(
                conversion=conversion,
                sanitized_source_digest=str(row["sanitized_source_digest"]),
                created_at=float(receipt["created_at"]),
            )
        candidate = conversion["candidate"]
        normalized = _normalize_definition_payload(candidate)
        request_digest = _sha256(
            {
                "stage_id": normalized_stage_id,
                "candidate_fingerprint": _fingerprint(normalized),
            }
        )
        existing_id = _idempotent_resource(
            conn,
            actor=actor,
            operation="publish_stage",
            key=key,
            request_digest=request_digest,
        )
        if existing_id:
            existing = _read_definition_row(conn, existing_id)
            if existing is None:
                raise InterchangeNotFoundError("published definition is unavailable")
            return _definition_from_row(conn, existing)
        if row["status"] == "published":
            existing = _read_definition_row(conn, str(row["published_definition_id"]))
            if existing is None:
                raise InterchangeNotFoundError("published definition is unavailable")
            return _definition_from_row(conn, existing)
        published = _publish_normalized(
            conn,
            actor=actor,
            normalized=normalized,
            key="",
            imported=True,
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_conversion_receipts (
                receipt_digest, actor_id, stage_id, receipt_json, created_at
            ) VALUES (?, ?, NULL, ?, ?)
            """,
            (
                receipt["receipt_digest"],
                "content-addressed",
                _canonical_json(receipt),
                current,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_conversion_receipt_links (
                stage_id, receipt_digest, actor_id, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                normalized_stage_id,
                receipt["receipt_digest"],
                actor,
                current,
            ),
        )
        conn.execute(
            """
            UPDATE agent_import_stages
            SET status = 'published', published_definition_id = ?,
                source_commitment = '', candidate_json = ?, receipt_json = ?
            WHERE stage_id = ?
            """,
            (
                published["agent_definition_id"],
                _canonical_json(candidate),
                _canonical_json(receipt),
                normalized_stage_id,
            ),
        )
        if key:
            conn.execute(
                """
                INSERT INTO agent_interchange_idempotency (
                    actor_id, operation, idempotency_key,
                    request_digest, resource_id, created_at
                ) VALUES (?, 'publish_stage', ?, ?, ?, ?)
                """,
                (
                    actor,
                    key,
                    request_digest,
                    published["agent_definition_id"],
                    current,
                ),
            )
        return published


__all__ = [
    "InterchangeConflictError",
    "InterchangeNotFoundError",
    "InterchangeValidationError",
    "convert_declarative_json",
    "convert_export",
    "enumerate_json_inventory",
    "get_import_stage",
    "publish_import_stage",
    "requires_runtime_response",
    "stage_import",
    "validate_adapter_request",
    "validate_adapter_response",
    "verify_conversion_receipt",
]

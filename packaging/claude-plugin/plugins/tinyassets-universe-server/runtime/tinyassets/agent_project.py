"""Inert, bounded source projects for native agent definitions.

This text-only interchange profile never writes files, installs dependencies,
registers code, or changes a private binding. Execution compatibility is separate.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any

from tinyassets.agent_interchange import MAX_SOURCE_BYTES
from tinyassets.custom_agents import (
    AgentValidationError,
    _canonical_json,
    _check_secret_fields,
    _fingerprint,
    _normalize_definition_payload,
)

SCHEMA = "tinyassets-source-project/v1"
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


class ProjectValidationError(AgentValidationError):
    """The package is invalid; diagnostics never contain source values."""


def _fail(reason: str) -> None:
    raise ProjectValidationError(reason)


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                _fail("duplicate JSON key")
            out[key] = value
        return out

    def finite_float(raw: str) -> float:
        value = float(raw)
        if not math.isfinite(value):
            _fail("non-finite JSON number")
        return value

    try:
        return json.loads(
            raw, object_pairs_hook=pairs,
            parse_constant=lambda _: _fail("non-finite JSON number"),
            parse_float=finite_float,
        )
    except (ValueError, RecursionError) as exc:
        raise ProjectValidationError("invalid project JSON") from exc


def _text_bytes(value: Any) -> bytes:
    if not isinstance(value, str):
        _fail("only UTF-8 text files are supported")
    try:
        return value.encode("utf-8")
    except UnicodeError as exc:
        raise ProjectValidationError("invalid Unicode text") from exc


def _path(path: Any) -> str:
    if not isinstance(path, str) or not path:
        _fail("invalid project path")
    if unicodedata.normalize("NFC", path) != path:
        _fail("project paths must use NFC Unicode")
    if any(ord(c) < 32 or c in '\\:*?"<>|\x7f' for c in path):
        _fail("unsupported project path")
    parts = path.split("/")
    if any(
        p in {"", ".", ".."} or p.endswith((" ", "."))
        or _RESERVED.match(p) for p in parts
    ):
        _fail("unsafe project path")
    _text_bytes(path)
    return path


def _files(files: Any) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not isinstance(files, dict) or not files:
        _fail("project files must be a non-empty explicit inventory")
    seen: set[str] = set()
    total = 0
    inventory = []
    for path, value in files.items():
        _path(path)
        folded = path.casefold()
        if folded in seen:
            _fail("colliding project paths")
        seen.add(folded)
        data = _text_bytes(value)
        total += len(data)
        if total > MAX_SOURCE_BYTES:
            _fail("project exceeds interchange source budget")
        inventory.append({
            "path": path, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    for path in seen:
        parts = path.split("/")
        if any("/".join(parts[:i]) in seen for i in range(1, len(parts))):
            _fail("file and directory paths collide")
    parsed_sources = []
    for path, value in files.items():
        if path.endswith(".json"):
            try:
                parsed_sources.append(_json(value))
            except ProjectValidationError as exc:
                raise ProjectValidationError("invalid JSON source file") from exc
    try:
        _check_secret_fields(files)
        for value in parsed_sources:
            _check_secret_fields(value)
    except AgentValidationError as exc:
        raise ProjectValidationError("source contains forbidden private content") from exc
    return dict(files), sorted(inventory, key=lambda item: item["path"])


def _descriptor(value: Any, files: dict[str, str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "native_definition", "entry_points", "runtime_requirements",
    }:
        _fail("unsupported project descriptor")
    if value["native_definition"] != "agent.json" or "agent.json" not in files:
        _fail("native definition must be agent.json")
    entries = value["entry_points"]
    if not isinstance(entries, dict) or not all(
        isinstance(k, str) and _NAME.fullmatch(k) for k in entries
    ):
        _fail("invalid entry point names")
    for path in entries.values():
        if _path(path) not in files:
            _fail("entry point is absent from inventory")
    requirements = value["runtime_requirements"]
    if not isinstance(requirements, list) or not all(
        isinstance(x, str) and x and len(_text_bytes(x)) <= MAX_SOURCE_BYTES
        for x in requirements
    ):
        _fail("invalid runtime requirements")
    if len(requirements) != len(set(requirements)):
        _fail("duplicate runtime requirement")
    return json.loads(_canonical_json(value))


def _digest(descriptor: dict[str, Any], inventory: list[dict[str, Any]]) -> str:
    # This CLOSED grammar has ASCII object keys, string values, arrays and bounded
    # integer byte lengths only. Python's compact UTF-8 JSON is JCS for this grammar;
    # arbitrary native JSON (including floats) is hashed by the EXISTING native codec.
    # Never extend this grammar to arbitrary numeric or object-key metadata without
    # using the repository's rfc8785 dependency and extending the cross-language tests.
    encoded = json.dumps(
        {"descriptor": descriptor, "inventory": inventory},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _native(raw: str) -> tuple[dict[str, Any], str]:
    value = _json(raw)
    if not isinstance(value, dict):
        _fail("agent.json must contain only a portable native definition")
    try:
        normalized = _normalize_definition_payload(value)
    except AgentValidationError as exc:
        raise ProjectValidationError("invalid portable native definition") from exc
    if normalized != value:
        _fail("agent.json must be normalized before packaging")
    return normalized, _fingerprint(normalized)


def export_project(
    definition: dict[str, Any],
    *,
    sources: dict[str, str],
    entry_points: dict[str, str] | None = None,
    runtime_requirements: list[str] | None = None,
) -> str:
    """Package explicitly supplied public source; never traverse a working directory."""
    if not isinstance(definition, dict):
        _fail("export requires a portable native definition, not a binding or run")
    try:
        native = _normalize_definition_payload(definition)
    except AgentValidationError as exc:
        raise ProjectValidationError("invalid portable native definition") from exc
    # The native normalizer owns the portable field set; do not duplicate it.
    if set(definition) - set(native):
        _fail("export requires a portable native definition, not a binding or run")
    if not isinstance(sources, dict) or "agent.json" in sources:
        _fail("sources must not replace agent.json")
    files, inventory = _files({"agent.json": _canonical_json(native), **sources})
    descriptor = _descriptor({
        "native_definition": "agent.json",
        "entry_points": {} if entry_points is None else entry_points,
        "runtime_requirements": [] if runtime_requirements is None else runtime_requirements,
    }, files)
    package = {
        "schema_version": SCHEMA, "descriptor": descriptor, "files": files,
        "lock": {
            "inventory": inventory, "native_fingerprint": _fingerprint(native),
            "project_digest": _digest(descriptor, inventory),
        },
    }
    raw = _canonical_json(package)
    inspect_project(raw)
    return raw


def inspect_project(raw: str) -> dict[str, Any]:
    """Validate all bytes in memory and return an inert inspection receipt.

    The caller may retain the original bytes privately. This function does not
    create a definition or assert that an entry point is executable.
    """
    if len(_text_bytes(raw)) > MAX_SOURCE_BYTES:
        _fail("project exceeds interchange source budget")
    package = _json(raw)
    if not isinstance(package, dict) or set(package) != {
        "schema_version", "descriptor", "files", "lock",
    } or package["schema_version"] != SCHEMA:
        _fail("unsupported project representation")
    files, inventory = _files(package["files"])
    descriptor = _descriptor(package["descriptor"], files)
    native, fingerprint = _native(files["agent.json"])
    digest = _digest(descriptor, inventory)
    expected = {
        "inventory": inventory, "native_fingerprint": fingerprint,
        "project_digest": digest,
    }
    if _canonical_json(package["lock"]) != _canonical_json(expected):
        _fail("project inventory or fingerprint mismatch")
    return {
        "schema_version": SCHEMA, "project_digest": digest,
        "native_fingerprint": fingerprint, "inventory": inventory,
        "portable_definition": native,
        "compatibility": {
            "representation_understood": True, "content_preserved": True,
            "runtime_requirements_satisfied": None, "executable": False,
            "reason": "runtime execution and private binding have not been evaluated",
        },
    }


def edit_project_sources(
    raw: str,
    *,
    expected_digest: str,
    changes: dict[str, str | None],
) -> str:
    """Return a validated candidate with explicit source replacements/deletions.

    None deletes an existing source. agent.json and the descriptor stay unchanged.
    This in-memory precondition is not a lock on any caller's persistent storage.
    No source executes and no binding is activated.
    """
    receipt = inspect_project(raw)
    if expected_digest != receipt["project_digest"]:
        _fail("project changed; inspect it again before editing")
    if not isinstance(changes, dict):
        _fail("source changes must be an explicit path map")
    package = _json(raw)
    sources = {p: text for p, text in package["files"].items() if p != "agent.json"}
    for path, text in changes.items():
        _path(path)
        if path.casefold() == "agent.json":
            _fail("source edits must not replace the native definition")
        if text is None:
            if path not in sources:
                _fail("cannot delete an absent source")
            del sources[path]
        else:
            _text_bytes(text)
            sources[path] = text
    if sources == {p: text for p, text in package["files"].items() if p != "agent.json"}:
        return raw
    return export_project(
        receipt["portable_definition"], sources=sources,
        entry_points=package["descriptor"]["entry_points"],
        runtime_requirements=package["descriptor"]["runtime_requirements"],
    )

"""Typed authoring file I/O — declared manifests, execution-scoped handles, and
bounded deliverables.

Task 4.2 of ``openspec/changes/complete-independent-full-platform-targets``.

The primitive is the *declaration*: a draft declares what it accepts and emits
(name, type, media types, cardinality, size bound), and this module is the only
gate that turns supplied bytes into something a run can read. Two invariants make
the boundary real:

- **A shared definition never carries a client or host path.** An attachment
  becomes an opaque, expiring, owner-scoped handle (``fh_…``); the definition and
  every result payload see the handle, its declared filename, media type, size,
  and digest — never a filesystem location.
- **Violations fail before execution, with field-level evidence.** Wrong media
  type, over-size, wrong cardinality, missing required input, or an undeclared
  input raises :class:`~tinyassets.authoring.models.ManifestViolation` carrying
  one issue per offending field path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Any

from tinyassets.authoring.models import (
    AuthoringValidationError,
    ManifestViolation,
    ValidationIssue,
    access_denied,
)

IO_TYPES: frozenset[str] = frozenset({"scalar", "object", "file", "file_bundle"})
FILE_IO_TYPES: frozenset[str] = frozenset({"file", "file_bundle"})
DISPOSITIONS: frozenset[str] = frozenset({"download", "connector_effect", "connector_push"})

#: Handles outlive one invocation only long enough for the run to read them.
DEFAULT_HANDLE_LIFETIME_SECONDS = 3600.0
#: Platform ceiling for one declared file, regardless of declaration.
MAX_FILE_BYTES = 8 * 1024 * 1024

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\- ]+")


@dataclass(frozen=True)
class IODeclaration:
    """One declared input or output slot."""

    name: str
    io_type: str
    direction: str
    media_types: tuple[str, ...] = ()
    min_count: int = 1
    max_count: int = 1
    max_bytes: int = MAX_FILE_BYTES
    required: bool = True
    dispositions: tuple[str, ...] = ("download",)

    @property
    def is_file(self) -> bool:
        return self.io_type in FILE_IO_TYPES

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "io_type": self.io_type,
            "direction": self.direction,
            "media_types": list(self.media_types),
            "min_count": self.min_count,
            "max_count": self.max_count,
            "max_bytes": self.max_bytes,
            "required": self.required,
            "dispositions": list(self.dispositions),
        }


@dataclass(frozen=True)
class Manifest:
    inputs: tuple[IODeclaration, ...]
    outputs: tuple[IODeclaration, ...]

    def input(self, name: str) -> IODeclaration:
        for declaration in self.inputs:
            if declaration.name == name:
                return declaration
        raise KeyError(f"no declared input named {name!r}")

    def output(self, name: str) -> IODeclaration:
        for declaration in self.outputs:
            if declaration.name == name:
                return declaration
        raise KeyError(f"no declared output named {name!r}")


@dataclass(frozen=True)
class BoundInputs:
    """Validated invocation inputs: scalars inline, files as handles."""

    values: dict[str, Any]
    handles: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"values": self.values, "handle_count": len(self.handles)}


def parse_manifest(definition: dict[str, Any]) -> Manifest:
    """Parse ``definition['io_manifest']`` or raise with field-level issues."""
    raw = definition.get("io_manifest") or {}
    if not isinstance(raw, dict):
        raise AuthoringValidationError([
            ValidationIssue("manifest.malformed", "io_manifest", "must be an object"),
        ])
    issues: list[ValidationIssue] = []
    parsed: dict[str, list[IODeclaration]] = {"inputs": [], "outputs": []}

    for direction in ("inputs", "outputs"):
        declarations = raw.get(direction, [])
        if not isinstance(declarations, list):
            issues.append(ValidationIssue(
                "manifest.malformed", f"io_manifest.{direction}", "must be a list",
            ))
            continue
        for index, declaration in enumerate(declarations):
            where = f"io_manifest.{direction}[{index}]"
            if not isinstance(declaration, dict):
                issues.append(ValidationIssue("manifest.malformed", where, ""))
                continue
            name = str(declaration.get("name", "")).strip()
            io_type = str(declaration.get("io_type", "")).strip()
            if not name:
                issues.append(ValidationIssue("manifest.unnamed", where, "name is required"))
                continue
            if io_type not in IO_TYPES:
                issues.append(ValidationIssue(
                    "manifest.unknown_io_type",
                    f"{where}.io_type",
                    f"io_type must be one of {sorted(IO_TYPES)}",
                ))
                continue
            max_count = int(declaration.get("max_count", 1) or 1)
            min_count = int(declaration.get("min_count", 1 if declaration.get(
                "required", True) else 0))
            if io_type != "file_bundle":
                max_count = 1
            declared_bytes = int(declaration.get("max_bytes", MAX_FILE_BYTES) or MAX_FILE_BYTES)
            dispositions = declaration.get("dispositions") or ["download"]
            if not isinstance(dispositions, list) or any(
                str(item) not in DISPOSITIONS for item in dispositions
            ):
                issues.append(ValidationIssue(
                    "manifest.unknown_disposition", f"{where}.dispositions", "",
                ))
                continue
            parsed[direction].append(IODeclaration(
                name=name,
                io_type=io_type,
                direction=direction,
                media_types=tuple(
                    str(item).strip().lower()
                    for item in (declaration.get("media_types") or [])
                ),
                min_count=max(0, min_count),
                max_count=max(1, max_count),
                max_bytes=min(declared_bytes, MAX_FILE_BYTES),
                required=bool(declaration.get("required", True)),
                dispositions=tuple(str(item) for item in dispositions),
            ))

    if issues:
        raise AuthoringValidationError(issues)
    return Manifest(tuple(parsed["inputs"]), tuple(parsed["outputs"]))


def safe_filename(raw: str, *, fallback: str = "unnamed") -> str:
    """Reduce any supplied name to one safe leaf filename.

    Path separators split the name into segments; traversal segments (pure dots)
    are dropped rather than escaped, disallowed characters are removed, and the
    surviving segments join with ``_``. So ``../../etc/passwd`` becomes
    ``etc_passwd`` — never a path, never empty.
    """
    text = str(raw or "").replace("\\", "/").strip()
    segments: list[str] = []
    for segment in text.split("/"):
        cleaned = _UNSAFE_FILENAME.sub("", segment).strip()
        if not cleaned or set(cleaned) <= {".", " "}:
            continue
        segments.append(cleaned)
    joined = re.sub(r"_{2,}", "_", "_".join(segments)).strip("_")
    joined = re.sub(r"^\.+", "", joined)
    return joined[:200] or fallback


def _decode_attachment(
    entry: Any, where: str, issues: list[ValidationIssue]
) -> tuple[str, str, bytes] | None:
    if not isinstance(entry, dict):
        issues.append(ValidationIssue(
            "manifest.unresolvable_attachment", where, "attachment must be an object",
        ))
        return None
    media_type = str(entry.get("media_type", "")).strip().lower()
    filename = safe_filename(entry.get("filename", ""))
    if "content_b64" in entry:
        try:
            content = base64.b64decode(str(entry["content_b64"]), validate=True)
        except (binascii.Error, ValueError) as exc:
            issues.append(ValidationIssue(
                "manifest.unresolvable_attachment", where, f"content_b64 is not base64: {exc}",
            ))
            return None
    elif "content" in entry and isinstance(entry["content"], (bytes, bytearray)):
        content = bytes(entry["content"])
    else:
        # A client/host path is never a resolvable attachment: the invocation
        # boundary takes bytes, so a shared definition can never carry a path.
        issues.append(ValidationIssue(
            "manifest.unresolvable_attachment",
            where,
            "supply attachment bytes as 'content_b64'; filesystem paths are not accepted",
        ))
        return None
    return filename, media_type, content


def bind_inputs(
    session: Any,
    supplied: dict[str, Any] | None,
    *,
    store: Any,
    actor_id: str,
    lifetime_seconds: float = DEFAULT_HANDLE_LIFETIME_SECONDS,
    now: float | None = None,
) -> BoundInputs:
    """Validate *supplied* against the draft manifest and bind file handles."""
    manifest = parse_manifest(session.definition)
    payload = dict(supplied or {})
    issues: list[ValidationIssue] = []
    values: dict[str, Any] = {}
    handles: list[dict[str, Any]] = []

    declared_names = {declaration.name for declaration in manifest.inputs}
    for name in payload:
        if name not in declared_names:
            issues.append(ValidationIssue(
                "manifest.undeclared_input", name, "input is not declared by the draft",
            ))

    for declaration in manifest.inputs:
        present = declaration.name in payload
        if not present:
            if declaration.required:
                issues.append(ValidationIssue(
                    "manifest.required_missing",
                    declaration.name,
                    "required input was not supplied",
                ))
            continue

        raw = payload[declaration.name]
        if not declaration.is_file:
            if declaration.io_type == "object" and not isinstance(raw, dict):
                issues.append(ValidationIssue(
                    "manifest.type_mismatch", declaration.name, "expected an object",
                ))
                continue
            if declaration.io_type == "scalar" and isinstance(raw, (dict, list)):
                issues.append(ValidationIssue(
                    "manifest.type_mismatch", declaration.name, "expected a scalar",
                ))
                continue
            values[declaration.name] = raw
            continue

        entries = raw if isinstance(raw, list) else [raw]
        if len(entries) < declaration.min_count or len(entries) > declaration.max_count:
            issues.append(ValidationIssue(
                "manifest.cardinality",
                declaration.name,
                f"expected between {declaration.min_count} and {declaration.max_count} "
                f"file(s), got {len(entries)}",
            ))
            continue

        bound_for_declaration: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            where = f"{declaration.name}[{index}]"
            decoded = _decode_attachment(entry, where, issues)
            if decoded is None:
                continue
            filename, media_type, content = decoded
            if declaration.media_types and media_type not in declaration.media_types:
                issues.append(ValidationIssue(
                    "manifest.media_type_not_allowed",
                    where,
                    f"media_type {media_type!r} is not in "
                    f"{list(declaration.media_types)}",
                ))
                continue
            if len(content) > declaration.max_bytes:
                issues.append(ValidationIssue(
                    "manifest.size_exceeded",
                    where,
                    f"{len(content)} bytes exceeds the declared bound "
                    f"{declaration.max_bytes}",
                ))
                continue
            bound_for_declaration.append({
                "filename": filename,
                "media_type": media_type,
                "content": content,
            })

        if issues:
            continue
        materialized = [
            store.put_file_handle(
                session_id=session.session_id,
                owner_id=actor_id,
                input_name=declaration.name,
                filename=item["filename"],
                media_type=item["media_type"],
                content=item["content"],
                lifetime_seconds=lifetime_seconds,
                now=now,
            )
            for item in bound_for_declaration
        ]
        handles.extend(materialized)
        values[declaration.name] = (
            materialized if declaration.io_type == "file_bundle" else materialized[0]
        )

    if issues:
        raise ManifestViolation(issues)
    return BoundInputs(values=values, handles=tuple(handles))


def bind_output(
    declaration: IODeclaration,
    *,
    filename: str,
    media_type: str,
    content: bytes,
    disposition: str = "download",
) -> dict[str, Any]:
    """Validate one emitted deliverable against its declaration."""
    issues: list[ValidationIssue] = []
    normalized = str(media_type).strip().lower()
    if declaration.media_types and normalized not in declaration.media_types:
        issues.append(ValidationIssue(
            "manifest.media_type_not_allowed",
            declaration.name,
            f"media_type {normalized!r} is not in {list(declaration.media_types)}",
        ))
    if len(content) > declaration.max_bytes:
        issues.append(ValidationIssue(
            "manifest.size_exceeded",
            declaration.name,
            f"{len(content)} bytes exceeds the declared bound {declaration.max_bytes}",
        ))
    if disposition not in DISPOSITIONS:
        issues.append(ValidationIssue(
            "manifest.unknown_disposition", declaration.name, disposition,
        ))
    elif disposition not in declaration.dispositions:
        issues.append(ValidationIssue(
            "manifest.disposition_not_declared",
            declaration.name,
            f"disposition {disposition!r} is not declared for this output; "
            "a connector push requires its own declaration and authorization",
        ))
    if issues:
        raise ManifestViolation(issues)
    return {
        "name": declaration.name,
        "filename": safe_filename(filename),
        "media_type": normalized,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "disposition": disposition,
    }


def read_handle_bytes(
    store: Any,
    handle_id: str,
    *,
    actor_id: str,
    session_id: str,
    now: float | None = None,
) -> bytes:
    """Read handle content, failing closed on expiry, revocation, or scope.

    *session_id* is required, not optional: a handle is *execution-scoped*, so the
    caller must state which session it is reading for. Leaving it defaultable let
    a caller silently read one of the owner's handles from an unrelated session.
    """
    handle = store.get_file_handle(
        handle_id, actor_id=actor_id, session_id=session_id, now=now
    )
    blob = store.blob_path(handle["session_id"], handle["handle_id"])
    if not blob.exists():
        raise access_denied()
    return blob.read_bytes()

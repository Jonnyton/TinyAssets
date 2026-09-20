"""Pure run-file declarations/references, never file ownership or read grants.

Services first resolve current owned rows, then compare this exact metadata.
Arbitrary dictionaries outside declared file fields remain ordinary user data.
"""

from dataclasses import asdict

from tinyassets.authoring.models import ManifestViolation, ValidationIssue
from tinyassets.storage.run_files import CapturedFile, FileCustodyRefused

_FIELDS = {"file_id", "size_bytes", "sha256", "filename", "media_type"}


def _metadata(value):
    if not isinstance(value, dict) or set(value) != _FIELDS | {"version"}:
        raise FileCustodyRefused("run_file_reference_invalid")
    if type(value["version"]) is not int or value["version"] != 1:
        raise FileCustodyRefused("run_file_reference_version")
    item = CapturedFile(**{name: value[name] for name in _FIELDS})
    if len(item.filename) > 4096 or len(item.media_type) > 256:
        raise FileCustodyRefused("run_file_metadata_limit")
    return item


def public_reference(row):
    result = {"version": 1, **{name: row[name] for name in _FIELDS}}
    _metadata(result)
    return result


def verify_reference(value, owned_row):
    """Compare after current owned-row lookup; a matching hash alone is no grant."""
    item = _metadata(value)
    expected = public_reference(owned_row)
    if {"version": 1, **asdict(item)} != expected:
        raise FileCustodyRefused("run_file_metadata_mismatch")
    return item.file_id


def declared_file_inputs(manifest, inputs, state_schema):
    """Validate shape/limits only; caller must resolve each reference's authority."""
    if not isinstance(inputs, dict) or not isinstance(state_schema, list):
        raise ManifestViolation(
            [ValidationIssue("manifest.malformed", "inputs", "invalid state/input shape")]
        )
    fields = {}
    issues = []
    for field in state_schema:
        if isinstance(field, dict) and type(field.get("name")) is str:
            if field["name"] in fields:
                issues.append(
                    ValidationIssue(
                        "manifest.invalid_state", field["name"], "duplicate state field"
                    )
                )
            fields[field["name"]] = field.get("type")
    resolved = {}
    for declaration in manifest.inputs:
        if not declaration.is_file:
            continue
        name = declaration.name
        expected_type = "list" if declaration.io_type == "file_bundle" else "dict"
        if fields.get(name) != expected_type:
            issues.append(
                ValidationIssue(
                    "manifest.invalid_state", name, f"file field requires {expected_type} state"
                )
            )
            continue
        if name not in inputs:
            if declaration.required:
                issues.append(
                    ValidationIssue(
                        "manifest.required_missing", name, "required file input missing"
                    )
                )
            continue
        value = inputs[name]
        if (expected_type == "list" and not isinstance(value, list)) or (
            expected_type == "dict" and not isinstance(value, dict)
        ):
            issues.append(
                ValidationIssue("manifest.type_mismatch", name, f"expected {expected_type}")
            )
            continue
        values = value if expected_type == "list" else [value]
        if not declaration.min_count <= len(values) <= declaration.max_count:
            issues.append(
                ValidationIssue("manifest.cardinality", name, "file count outside declaration")
            )
            continue
        valid = True
        for ref in values:
            try:
                item = _metadata(ref)
                if item.size_bytes > declaration.max_bytes:
                    raise FileCustodyRefused("run_file_size_limit")
                if (
                    declaration.media_types
                    and item.media_type.lower() not in declaration.media_types
                ):
                    raise FileCustodyRefused("run_file_media_type_not_allowed")
            except FileCustodyRefused as exc:
                issues.append(ValidationIssue("manifest.invalid_reference", name, str(exc)))
                valid = False
        if valid:
            resolved[name] = list(values)
    if issues:
        raise ManifestViolation(issues)
    return resolved

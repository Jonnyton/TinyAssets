"""Strict runtime declarations reuse authoring vocabulary without silent clamps."""

import pytest

from tinyassets.authoring.io import MAX_FILE_BYTES, parse_manifest
from tinyassets.authoring.models import AuthoringValidationError
from tinyassets.run_file_contract import declared_file_inputs, public_reference, verify_reference


def definition(**updates):
    field = {"name": "file", "io_type": "file", "max_bytes": 10 * 1024 * 1024}
    field.update(updates)
    return {"io_manifest": {"inputs": [field]}}


def strict(value):
    return parse_manifest(value, strict=True, max_file_bytes=12 * 1024 * 1024, max_files=8)


def test_runtime_ceiling_is_explicit_and_legacy_authoring_limit_unchanged():
    assert parse_manifest(definition()).inputs[0].max_bytes == MAX_FILE_BYTES
    assert strict(definition()).inputs[0].max_bytes == 10 * 1024 * 1024
    with pytest.raises(AuthoringValidationError):
        strict(definition(max_bytes=13 * 1024 * 1024))


@pytest.mark.parametrize(
    "values",
    [
        {"max_bytes": True},
        {"max_bytes": "10"},
        {"max_bytes": -1},
        {"max_count": 2},
        {"max_count": "1"},
        {"min_count": -1},
        {"required": "false"},
        {"name": 3},
        {"name": " file "},
        {"media_types": "text/plain"},
        {"media_types": [1]},
        {"io_type": "file_bundle", "min_count": 3, "max_count": 2},
        {"io_type": "file_bundle", "max_count": 9},
    ],
)
def test_strict_manifest_rejects_lossy_or_contradictory_declarations(values):
    with pytest.raises(AuthoringValidationError):
        strict(definition(**values))


def test_duplicate_declared_names_refuse():
    value = definition()
    value["io_manifest"]["inputs"] *= 2
    with pytest.raises(AuthoringValidationError):
        strict(value)


def test_reference_metadata_is_exact_not_path_authority():
    row = dict(
        file_id="a" * 32,
        size_bytes=0,
        sha256="b" * 64,
        filename="../🧪 Original Name.bin",
        media_type="application/octet-stream",
        storage_key="server-private",
        owner_id="owner",
    )
    ref = public_reference(row)
    assert ref["filename"] == row["filename"]
    assert set(ref) == {"version", "file_id", "size_bytes", "sha256", "filename", "media_type"}
    assert verify_reference(ref, row) == row["file_id"]
    for change in (
        {"size_bytes": False},
        {"version": True},
        {"filename": "renamed"},
        {"path": "/private"},
        {"sha256": "c" * 64},
    ):
        with pytest.raises(ValueError):
            verify_reference({**ref, **change}, row)


def test_declared_binary_bundle_shape_and_state_types_are_required():
    value = definition(io_type="file_bundle", min_count=0, max_count=2, required=False)
    manifest = strict(value)
    row = dict(
        file_id="a" * 32,
        size_bytes=0,
        sha256="b" * 64,
        filename="empty",
        media_type="application/octet-stream",
    )
    ref = public_reference(row)
    state = [{"name": "file", "type": "list"}]
    assert declared_file_inputs(manifest, {"file": [ref, ref]}, state) == {"file": [ref, ref]}
    assert declared_file_inputs(manifest, {"file": []}, state) == {"file": []}
    assert declared_file_inputs(manifest, {}, state) == {}
    for inputs, schema in [
        ({"file": ref}, state),
        ({"file": [ref]}, []),
        ({"file": [ref]}, [{"name": "file", "type": "any"}]),
    ]:
        with pytest.raises(AuthoringValidationError):
            declared_file_inputs(manifest, inputs, schema)

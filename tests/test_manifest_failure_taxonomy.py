"""The set_io_manifest repair advice is scoped to the unsupported-key refusal.

Root finding on the 2026-09-21 mis-keyed-manifest fix: the taxonomy row matched
EVERY ``AuthoringValidationError`` yet its advice asserted an invalid stored
io_manifest. That parent class also covers supplied inputs violating a valid
manifest and malformed node definitions; telling those callers to rewrite the
manifest is false advice. Only ``UnsupportedManifestKeyError`` earns it.
"""

from __future__ import annotations

import pytest

from tinyassets.api.runs import _classify_run_error
from tinyassets.authoring.io import (
    MANIFEST_SHAPE_HINT,
    UnsupportedManifestKeyError,
    _parse_strict_manifest,
)
from tinyassets.authoring.models import (
    AuthoringValidationError,
    ManifestViolation,
    ValidationIssue,
)


def _unsupported_key_refusal() -> UnsupportedManifestKeyError:
    definition = {"io_manifest": {"file_inputs": [{"name": "files", "io_type": "file_bundle"}]}}
    with pytest.raises(UnsupportedManifestKeyError) as caught:
        _parse_strict_manifest(definition, max_file_bytes=4_194_304, max_files=4)
    return caught.value


def test_unsupported_manifest_key_refusal_is_classified_with_repair_advice():
    exc = _unsupported_key_refusal()
    assert isinstance(exc, AuthoringValidationError)  # still one authoring failure family
    assert "'file_inputs'" in str(exc) and MANIFEST_SHAPE_HINT in str(exc)

    out = _classify_run_error(exc, "b1")
    assert out["failure_class"] == "compile_error"
    assert "set_io_manifest" in out["suggested_action"]
    assert "unsupported top-level key" in out["suggested_action"]
    assert out["actionable_by"] == "chatbot"


@pytest.mark.parametrize(
    "exc",
    [
        AuthoringValidationError(
            [ValidationIssue("node.invalid", "node_defs.0", "input_keys must be a list")]
        ),
        ManifestViolation(
            [ValidationIssue("manifest.violation", "inputs.files", "too many files")],
            message="inputs.files: too many files (max 4)",
        ),
        AuthoringValidationError(
            [ValidationIssue("manifest.malformed", "io_manifest", "must be an object")]
        ),
    ],
    ids=["node_definition", "manifest_violation_by_inputs", "malformed_manifest"],
)
def test_other_authoring_failures_are_not_told_to_rewrite_the_manifest(exc):
    """A parent-class failure keeps whatever class it had before; never this advice."""
    assert not isinstance(exc, UnsupportedManifestKeyError)
    out = _classify_run_error(exc, "b1")
    assert "set_io_manifest" not in out["suggested_action"], out
    assert "unsupported top-level key" not in out["suggested_action"], out
    assert out["failure_class"] != "compile_error", out

"""validate_patch opaque node — deterministic patch-apply verification.

The loop's first EXECUTABLE check: does the proposed packet's edits_json apply
to the fetched current contents? No LLM, no network. Catches the dominant
patch-failure mode (a search string that isn't verbatim-unique) before
review_gate/open_pr, and emits a concrete reason for a retry.
"""
from __future__ import annotations

import json

from workflow.effectors.validate_patch import (
    DOMAIN_ID,
    NODE_ID,
    register_validate_patch,
    validate_patch,
)

_FILE = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


def _packet(edits):
    return json.dumps({
        "sink": "github_pull_request",
        "destination": "Owner/Repo",
        "payload": {"title": "t", "edits_json": edits},
    })


def _state(packet, contents):
    return {
        "pr_packet_draft": packet,
        "current_contents_json": json.dumps(contents),
    }


def test_valid_patch_applies_cleanly():
    edits = {"m.py": [{"search": "return a - b", "replace": "return a - b  # fixed"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "VALID", out
    assert "apply to the fetched" in out["patch_validity_detail"]


def test_invalid_search_not_found():
    edits = {"m.py": [{"search": "return a * b", "replace": "x"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID"
    assert "m.py" in out["patch_validity_detail"]


def test_invalid_search_not_unique():
    # "a, b" occurs in both function signatures -> not unique.
    edits = {"m.py": [{"search": "a, b", "replace": "a, b, c"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID"
    assert "unique" in out["patch_validity_detail"].lower()


def test_invalid_unfetched_target_path():
    edits = {"missing.py": [{"search": "x", "replace": "y"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID"
    assert "missing.py" in out["patch_validity_detail"]


def test_malformed_packet_is_invalid_not_crash():
    out = validate_patch({"pr_packet_draft": "not json {{{", "current_contents_json": "{}"})
    assert out["patch_validity"] == "INVALID"
    assert "json" in out["patch_validity_detail"].lower()


def test_no_sink_packet_is_invalid():
    # The effector's _parse_packet requires a sink; mirror it (no false VALID).
    packet = json.dumps({"payload": {"changes_json": {"new.py": "x\n"}}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "INVALID"


def test_new_file_only_packet_defers_to_review():
    # changes_json string = new file; no edits to verify, but packet is well-formed.
    packet = json.dumps({"sink": "github_pull_request",
                         "payload": {"changes_json": {"new.py": "print('hi')\n"}}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "VALID", out


def test_code_fence_wrapped_packet_is_invalid():
    # The effector rejects non-'{'-leading strings; we must too (else false VALID).
    edits = {"m.py": [{"search": "return a - b", "replace": "return b - a"}]}
    fenced = "```json\n" + _packet(edits) + "\n```"
    out = validate_patch(_state(fenced, {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID", out


def test_empty_change_set_is_invalid():
    packet = json.dumps({"sink": "github_pull_request", "payload": {"title": "t"}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "INVALID"
    assert "no effective change set" in out["patch_validity_detail"]


def test_bad_changes_json_shape_is_invalid():
    packet = json.dumps({"sink": "github_pull_request",
                         "payload": {"changes_json": {"p.py": 123}}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "INVALID"


def test_duplicate_path_in_edits_and_changes_is_invalid():
    packet = json.dumps({"sink": "github_pull_request", "payload": {
        "edits_json": {"m.py": [{"search": "return a - b", "replace": "return b - a"}]},
        "changes_json": {"m.py": "y = 2\n"},
    }})
    out = validate_patch(_state(packet, {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID"
    assert "both" in out["patch_validity_detail"].lower()


def test_registered_as_opaque_domain_callable():
    register_validate_patch()
    from workflow.domain_registry import resolve_domain_callable

    fn = resolve_domain_callable(DOMAIN_ID, NODE_ID)
    assert fn is validate_patch


def test_never_raises_on_empty_state():
    out = validate_patch({})
    assert out["patch_validity"] == "INVALID"


# ── Syntax lint-guard: an edit can APPLY yet break the file (SWE-agent pattern) ──

def test_edit_that_breaks_python_syntax_is_invalid():
    edits = {"m.py": [{"search": "return a + b", "replace": "return a +"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "INVALID"
    detail = out["patch_validity_detail"].lower()
    assert "pars" in detail or "syntax" in detail


def test_valid_python_edit_passes_syntax_check():
    edits = {"m.py": [{"search": "return a + b", "replace": "return (a + b)"}]}
    out = validate_patch(_state(_packet(edits), {"m.py": _FILE}))
    assert out["patch_validity"] == "VALID", out


def test_new_python_file_with_bad_syntax_is_invalid():
    packet = json.dumps({"sink": "github_pull_request",
                         "payload": {"changes_json": {"n.py": "def f(:\n    pass\n"}}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "INVALID"


def test_non_python_file_edit_skips_syntax_check():
    # A markdown edit applies; we must NOT false-INVALID on non-code prose.
    md = "# Title\n\nsome text here\n"
    edits = {"doc.md": [{"search": "some text here", "replace": "x {{ not python"}]}
    out = validate_patch(_state(_packet(edits), {"doc.md": md}))
    assert out["patch_validity"] == "VALID", out


def test_new_json_file_invalid_json_is_invalid():
    packet = json.dumps({"sink": "github_pull_request",
                         "payload": {"changes_json": {"c.json": "{not valid json"}}})
    out = validate_patch(_state(packet, {}))
    assert out["patch_validity"] == "INVALID"

"""Diff-based change format: edits_json (search/replace blocks) in the effector.

The full-file `changes_json` path makes the writer re-emit a whole file, which
truncates to placeholders on large files. `edits_json` lets the writer emit only
the changed hunks as ``{path: [{search, replace}, ...]}``; the effector fetches
the file at base_branch and applies the blocks (exact, unique-match, fail-closed)
to produce full contents, then reuses the existing blob -> tree -> commit -> ref
materialize path.

Mocks ``_git_data_api`` so no network is touched. The contents fetch (Contents
API GET) happens before the ref sequence.

Design note: docs/design-notes/2026-05-29-diff-based-change-format.md
"""

from __future__ import annotations

import base64

from workflow.effectors import github_pr

_DEST = "Jonnyton/Workflow"
_HEAD = "patch-loop/edit-probe"
_BASE = "main"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _scripted_api(responses):
    def fake(*, method, path, capability_token, body=None):
        fake.calls.append((method, path, body))
        for matcher, result in responses:
            if matcher(method, path):
                return result
        raise AssertionError(f"no scripted response for {method} {path}")

    fake.calls = []
    return fake


def _contents_response(path_frag: str, text: str):
    return (
        lambda m, p: m == "GET" and "/contents/" in p and path_frag in p,
        ({"type": "file", "content": _b64(text)}, None),
    )


def _happy_tail():
    """ref -> commit -> blob -> tree -> commit -> ref success sequence."""
    return [
        (lambda m, p: m == "GET" and p.endswith(f"/git/ref/heads/{_BASE}"),
         ({"object": {"sha": "basecommitsha"}}, None)),
        (lambda m, p: m == "GET" and "/git/commits/basecommitsha" in p,
         ({"tree": {"sha": "basetreesha"}}, None)),
        (lambda m, p: m == "POST" and p.endswith("/git/blobs"),
         ({"sha": "blobsha"}, None)),
        (lambda m, p: m == "POST" and p.endswith("/git/trees"),
         ({"sha": "newtreesha"}, None)),
        (lambda m, p: m == "POST" and p.endswith("/git/commits"),
         ({"sha": "newcommitsha"}, None)),
        (lambda m, p: m == "POST" and p.endswith("/git/refs"),
         ({"ref": f"refs/heads/{_HEAD}"}, None)),
    ]


def _materialize(*, changes=None, edits=None):
    return github_pr._materialize_branch(
        changes_json=changes,
        edits_json=edits,
        destination=_DEST,
        base_branch=_BASE,
        head_branch=_HEAD,
        commit_message="Edit probe",
        capability_token="tok",
    )


# ── _apply_edit_blocks unit tests ──────────────────────────────────────────

def test_apply_blocks_single_replace():
    out, err = github_pr._apply_edit_blocks(
        "a\nTARGET\nb\n", [{"search": "TARGET", "replace": "FIXED"}]
    )
    assert err is None
    assert out == "a\nFIXED\nb\n"


def test_apply_blocks_ordered_sequential():
    out, err = github_pr._apply_edit_blocks(
        "one two\n",
        [{"search": "one", "replace": "1"}, {"search": "two", "replace": "2"}],
    )
    assert err is None and out == "1 2\n"


def test_apply_blocks_not_found():
    out, err = github_pr._apply_edit_blocks("abc", [{"search": "zzz", "replace": "x"}])
    assert out is None and err["error_kind"] == "edit_search_not_found"


def test_apply_blocks_not_unique():
    out, err = github_pr._apply_edit_blocks(
        "dup dup", [{"search": "dup", "replace": "x"}]
    )
    assert out is None and err["error_kind"] == "edit_search_not_unique"


def test_apply_blocks_invalid_shape():
    assert github_pr._apply_edit_blocks("a", [])[1]["error_kind"] == "invalid_edits"
    assert github_pr._apply_edit_blocks("a", "nope")[1]["error_kind"] == "invalid_edits"
    assert github_pr._apply_edit_blocks(
        "a", [{"search": "", "replace": "x"}]
    )[1]["error_kind"] == "invalid_edits"


# ── _materialize_branch with edits_json ────────────────────────────────────

def test_edits_happy_builds_branch_with_edited_content(monkeypatch):
    current = "import os\n\n\ndef f():\n    return OLD\n"
    responses = [_contents_response("calc.py", current)] + _happy_tail()
    fake = _scripted_api(responses)
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    result = _materialize(edits={"calc.py": [{"search": "return OLD", "replace": "return NEW"}]})
    assert result["materialized"] is True
    # The blob created must hold the EDITED full contents, not the original.
    blob_body = next(b for m, p, b in fake.calls if p.endswith("/git/blobs"))
    assert blob_body["content"] == "import os\n\n\ndef f():\n    return NEW\n"
    # Contents fetch happened before the ref lookup.
    assert "/contents/" in fake.calls[0][1]


def test_edits_only_no_changes_json_is_allowed(monkeypatch):
    # Proves changes_json is no longer required when edits_json carries the change.
    responses = [_contents_response("a.py", "x = 1\n")] + _happy_tail()
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize(edits={"a.py": [{"search": "x = 1", "replace": "x = 2"}]})
    assert result["materialized"] is True


def test_edit_target_missing_maps_to_distinct_kind(monkeypatch):
    responses = [
        (lambda m, p: m == "GET" and "/contents/" in p,
         (None, {"http_status": 404, "detail": "Not Found"})),
    ]
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize(edits={"missing.py": [{"search": "a", "replace": "b"}]})
    assert result["error_kind"] == "edit_target_missing"


def test_edit_search_not_found_fails_closed(monkeypatch):
    responses = [_contents_response("a.py", "actual contents\n")]
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize(edits={"a.py": [{"search": "nonexistent", "replace": "x"}]})
    assert result["error_kind"] == "edit_search_not_found"
    # No blob/commit/ref were created — failed before any write.


def test_edit_search_not_unique_fails_closed(monkeypatch):
    responses = [_contents_response("a.py", "dup\ndup\n")]
    fake = _scripted_api(responses)
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    result = _materialize(edits={"a.py": [{"search": "dup", "replace": "x"}]})
    assert result["error_kind"] == "edit_search_not_unique"
    assert not any(p.endswith("/git/blobs") for _m, p, _b in fake.calls)


def test_edit_fetch_scope_denied_maps_to_contents_write(monkeypatch):
    responses = [
        (lambda m, p: m == "GET" and "/contents/" in p,
         (None, {"http_status": 403, "detail": "denied"})),
    ]
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize(edits={"a.py": [{"search": "a", "replace": "b"}]})
    assert result["error_kind"] == "github_contents_write_denied"


def test_path_in_both_changes_and_edits_rejected(monkeypatch):
    responses = [_contents_response("a.py", "x\n")] + _happy_tail()
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize(
        changes={"a.py": "whole\n"},
        edits={"a.py": [{"search": "x", "replace": "y"}]},
    )
    assert result["error_kind"] == "invalid_edits"


def test_neither_changes_nor_edits_is_missing_changes(monkeypatch):
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api([]))
    assert _materialize()["error_kind"] == "missing_changes"


def test_changes_json_still_works_alongside_edits(monkeypatch):
    # changes_json (new file) + edits_json (existing file) in one packet.
    responses = [_contents_response("existing.py", "v = 1\n")] + _happy_tail()
    # Two blobs needed (one per path); the scripted blob matcher returns the
    # same sha for both, which is fine for this materialize-shape assertion.
    fake = _scripted_api(responses)
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    result = _materialize(
        changes={"newfile.py": "created\n"},
        edits={"existing.py": [{"search": "v = 1", "replace": "v = 2"}]},
    )
    assert result["materialized"] is True
    tree_call = next(b for m, p, b in fake.calls if p.endswith("/git/trees"))
    paths = {e["path"] for e in tree_call["tree"]}
    assert paths == {"newfile.py", "existing.py"}

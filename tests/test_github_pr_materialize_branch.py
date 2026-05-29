"""BUG-111: github_pull_request effector materializes the change into a branch.

The effector used to call ``gh pr create`` against a head branch nothing ever
created, so GitHub rejected with "No commits between base and head". These
tests cover ``_materialize_branch`` — building the head branch via the GitHub
Git Data API (blobs -> tree -> commit -> ref) — by mocking ``_git_data_api`` so
no network is touched.

Design note: docs/design-notes/2026-05-29-github-pr-effector-materialize-branch.md
Codex checker key: PR #1144.
"""

from __future__ import annotations

import pytest

from workflow.effectors import github_pr

_DEST = "Jonnyton/Workflow"
_HEAD = "autolab/probe-v3-k9x4m2"
_BASE = "main"


def _scripted_api(responses):
    """Build a fake ``_git_data_api`` from a list of ``(matcher, result)``.

    ``matcher`` is called with (method, path); the first match's ``result``
    (a ``(parsed, error)`` tuple) is returned. Records the call sequence on
    the returned function's ``.calls`` list.
    """

    def fake(*, method, path, capability_token, body=None):
        fake.calls.append((method, path, body))
        for matcher, result in responses:
            if matcher(method, path):
                return result
        raise AssertionError(f"no scripted response for {method} {path}")

    fake.calls = []
    return fake


def _happy_responses():
    """Standard success sequence: ref -> commit -> blob -> tree -> commit -> ref."""
    return [
        (
            lambda m, p: m == "GET" and p.endswith(f"/git/ref/heads/{_BASE}"),
            ({"object": {"sha": "basecommitsha"}}, None),
        ),
        (
            lambda m, p: m == "GET" and "/git/commits/basecommitsha" in p,
            ({"tree": {"sha": "basetreesha"}}, None),
        ),
        (
            lambda m, p: m == "POST" and p.endswith("/git/blobs"),
            ({"sha": "blobsha"}, None),
        ),
        (
            lambda m, p: m == "POST" and p.endswith("/git/trees"),
            ({"sha": "newtreesha"}, None),
        ),
        (
            lambda m, p: m == "POST" and p.endswith("/git/commits"),
            ({"sha": "newcommitsha"}, None),
        ),
        (
            lambda m, p: m == "POST" and p.endswith("/git/refs"),
            ({"ref": f"refs/heads/{_HEAD}"}, None),
        ),
    ]


def _materialize(changes=None, head=_HEAD):
    return github_pr._materialize_branch(
        changes_json={"README_PROBE.md": "probe\n"} if changes is None else changes,
        destination=_DEST,
        base_branch=_BASE,
        head_branch=head,
        commit_message="Probe",
        capability_token="tok",
    )


def test_happy_path_builds_branch(monkeypatch):
    fake = _scripted_api(_happy_responses())
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    result = _materialize()
    assert result == {
        "materialized": True,
        "head_branch": _HEAD,
        "commit_sha": "newcommitsha",
        "tree_sha": "newtreesha",
    }


def test_api_call_order(monkeypatch):
    """ref -> base commit -> blob -> tree -> commit -> ref, in that order."""
    fake = _scripted_api(_happy_responses())
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    _materialize()
    steps = [(m, p.rsplit("/git/", 1)[-1].split("/")[0]) for m, p, _ in fake.calls]
    assert steps == [
        ("GET", "ref"),
        ("GET", "commits"),
        ("POST", "blobs"),
        ("POST", "trees"),
        ("POST", "commits"),
        ("POST", "refs"),
    ]


def test_base_tree_passed_to_tree_create(monkeypatch):
    """The new tree must be built on top of the base commit's tree sha."""
    fake = _scripted_api(_happy_responses())
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    _materialize()
    tree_call = next(b for m, p, b in fake.calls if p.endswith("/git/trees"))
    assert tree_call["base_tree"] == "basetreesha"
    assert tree_call["tree"] == [
        {"path": "README_PROBE.md", "mode": "100644", "type": "blob", "sha": "blobsha"}
    ]


def test_commit_parents_on_base_commit(monkeypatch):
    fake = _scripted_api(_happy_responses())
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    _materialize()
    commit_call = next(b for m, p, b in fake.calls if p.endswith("/git/commits"))
    assert commit_call["parents"] == ["basecommitsha"]
    assert commit_call["tree"] == "newtreesha"


def test_deletion_emits_null_sha_entry_without_blob(monkeypatch):
    fake = _scripted_api(_happy_responses())
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    _materialize(changes={"old.py": None})
    # No blob POST for a deletion.
    assert not any(p.endswith("/git/blobs") for _m, p, _b in fake.calls)
    tree_call = next(b for m, p, b in fake.calls if p.endswith("/git/trees"))
    assert tree_call["tree"] == [
        {"path": "old.py", "mode": "100644", "type": "blob", "sha": None}
    ]


def test_missing_changes_fails_loudly(monkeypatch):
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api([]))
    assert _materialize(changes={})["error_kind"] == "missing_changes"


def test_missing_head_branch(monkeypatch):
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api([]))
    assert _materialize(head="")["error_kind"] == "missing_head_branch"


def test_invalid_changes_non_string_value(monkeypatch):
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api([]))
    assert _materialize(changes={"x": 123})["error_kind"] == "invalid_changes"


def test_invalid_destination(monkeypatch):
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api([]))
    result = github_pr._materialize_branch(
        changes_json={"a": "b"},
        destination="not-a-repo",
        base_branch=_BASE,
        head_branch=_HEAD,
        commit_message="m",
        capability_token="tok",
    )
    assert result["error_kind"] == "invalid_destination"


def test_base_ref_lookup_failure(monkeypatch):
    fake = _scripted_api([
        (
            lambda m, p: m == "GET" and "/git/ref/heads/" in p,
            (None, {"http_status": 404, "detail": "Not Found"}),
        ),
    ])
    monkeypatch.setattr(github_pr, "_git_data_api", fake)
    # 404 on a lookup is treated as a scope/capability signal.
    assert _materialize()["error_kind"] == "github_contents_write_denied"


def test_blob_create_scope_denied_maps_to_contents_write(monkeypatch):
    responses = _happy_responses()
    # Replace blob response with a 403.
    responses[2] = (
        lambda m, p: m == "POST" and p.endswith("/git/blobs"),
        (None, {"http_status": 403, "detail": "Resource not accessible"}),
    )
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    assert _materialize()["error_kind"] == "github_contents_write_denied"


def test_tree_create_failure_distinct_error_kind(monkeypatch):
    responses = _happy_responses()
    responses[3] = (
        lambda m, p: m == "POST" and p.endswith("/git/trees"),
        (None, {"http_status": 500, "detail": "boom"}),
    )
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    assert _materialize()["error_kind"] == "tree_create_failed"


def test_head_ref_conflict_when_existing_tree_differs(monkeypatch):
    responses = _happy_responses()
    # ref create -> 422 already exists.
    responses[5] = (
        lambda m, p: m == "POST" and p.endswith("/git/refs"),
        (None, {"http_status": 422, "detail": "Reference already exists"}),
    )
    # GET existing head ref -> commit -> different tree.
    responses.append((
        lambda m, p: m == "GET" and p.endswith(f"/git/ref/heads/{_HEAD}"),
        ({"object": {"sha": "othercommit"}}, None),
    ))
    responses.append((
        lambda m, p: m == "GET" and "/git/commits/othercommit" in p,
        ({"tree": {"sha": "DIFFERENTTREE"}}, None),
    ))
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    assert _materialize()["error_kind"] == "head_ref_conflict"


def test_idempotent_reuse_when_existing_tree_matches(monkeypatch):
    responses = _happy_responses()
    responses[5] = (
        lambda m, p: m == "POST" and p.endswith("/git/refs"),
        (None, {"http_status": 422, "detail": "Reference already exists"}),
    )
    responses.append((
        lambda m, p: m == "GET" and p.endswith(f"/git/ref/heads/{_HEAD}"),
        ({"object": {"sha": "existingcommit"}}, None),
    ))
    responses.append((
        lambda m, p: m == "GET" and "/git/commits/existingcommit" in p,
        ({"tree": {"sha": "newtreesha"}}, None),  # same tree we built
    ))
    monkeypatch.setattr(github_pr, "_git_data_api", _scripted_api(responses))
    result = _materialize()
    assert result["materialized"] is True
    assert result["head_ref_reused"] is True
    assert result["commit_sha"] == "existingcommit"

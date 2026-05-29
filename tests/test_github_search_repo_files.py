"""search_repo_files opaque callable — localization side of the patch-request loop.

Mocks the HTTP layer (`_http_get_json`) so no network is touched. Covers happy
path-search + ranking, dotted-name matching, glob matching, default-branch
resolution, explicit ref, result cap/truncation, denied/error mapping, empty
query, invalid destination, separate-read-scope (NOT the write map), and
registration.

Design note: docs/design-notes/2026-05-29-repo-search-primitive.md
"""

from __future__ import annotations

import json

from workflow.effectors import github_search as gs

_DEST = "Jonnyton/Workflow"

_REPO_API = f"https://api.github.com/repos/{_DEST}"


def _tree(*paths):
    return {"tree": [{"type": "blob", "path": p, "sha": "x"} for p in paths], "truncated": False}


def _fake_http(*, repo=None, tree=None, tree_truncated=False, errors=None):
    """Build a fake _http_get_json from canned repo + tree responses.

    `errors` maps a URL-substring -> error dict to force a failure.
    """
    repo = repo if repo is not None else {"default_branch": "main"}
    errors = errors or {}

    def fake(url, token):
        fake.calls.append((url, token))
        for needle, err in errors.items():
            if needle in url:
                return None, err
        if "/git/trees/" in url:
            body = dict(tree or {"tree": []})
            body.setdefault("truncated", tree_truncated)
            return body, None
        # repo metadata endpoint
        return repo, None

    fake.calls = []
    return fake


def _run(state, monkeypatch, http=None, env=None):
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    if http is not None:
        monkeypatch.setattr(gs, "_http_get_json", http)
    result = gs.search_repo_files(state)
    return (
        json.loads(result["matched_paths_json"]),
        json.loads(result["search_status_json"]),
    )


def test_happy_substring_match_and_ranking(monkeypatch):
    http = _fake_http(tree=_tree(
        "workflow/api/wiki.py",
        "tests/test_wiki.py",
        "docs/wiki-notes.md",
        "workflow/api/runs.py",
    ))
    matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki.py"}, monkeypatch, http
    )
    # basename "wiki.py" exact/prefix should outrank the docs/tests substring hits
    assert matched[0] == "workflow/api/wiki.py"
    assert "workflow/api/runs.py" not in matched
    assert status["error"] is None
    assert status["matched"] >= 1
    assert status["ref"] == "main"


def test_dotted_module_matches_slash_path(monkeypatch):
    http = _fake_http(tree=_tree("workflow/api/wiki.py", "workflow/api/runs.py"))
    matched, _status = _run(
        {"search_destination": _DEST, "search_query": "workflow.api.wiki"},
        monkeypatch,
        http,
    )
    assert "workflow/api/wiki.py" in matched


def test_glob_term_matches(monkeypatch):
    http = _fake_http(tree=_tree(
        "workflow/effectors/github_pr.py",
        "workflow/effectors/github_read.py",
        "workflow/api/wiki.py",
    ))
    matched, _status = _run(
        {"search_destination": _DEST, "search_query": "workflow/effectors/*.py"},
        monkeypatch,
        http,
    )
    assert set(matched) == {
        "workflow/effectors/github_pr.py",
        "workflow/effectors/github_read.py",
    }


def test_default_branch_resolved_when_ref_empty(monkeypatch):
    http = _fake_http(repo={"default_branch": "trunk"}, tree=_tree("a/wiki.py"))
    _matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki"}, monkeypatch, http
    )
    assert status["ref"] == "trunk"
    # first call resolves repo metadata, second hits the tree at the resolved ref
    assert any("/git/trees/trunk" in url for url, _ in http.calls)


def test_explicit_ref_skips_repo_lookup(monkeypatch):
    http = _fake_http(tree=_tree("a/wiki.py"))
    _matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki", "search_ref": "dev"},
        monkeypatch,
        http,
    )
    assert status["ref"] == "dev"
    assert all(url.endswith("/repos/" + _DEST) is False for url, _ in http.calls)
    assert any("/git/trees/dev" in url for url, _ in http.calls)


def test_result_cap_truncates(monkeypatch):
    http = _fake_http(tree=_tree(*[f"pkg/wiki_{i}.py" for i in range(10)]))
    matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki"},
        monkeypatch,
        http,
        env={"WORKFLOW_GITHUB_SEARCH_MAX_RESULTS": "3"},
    )
    assert len(matched) == 3
    assert status["returned"] == 3
    assert status["matched"] == 10
    assert status["truncated"] is True


def test_no_match_returns_empty(monkeypatch):
    http = _fake_http(tree=_tree("workflow/api/runs.py"))
    matched, status = _run(
        {"search_destination": _DEST, "search_query": "nonexistentterm"},
        monkeypatch,
        http,
    )
    assert matched == []
    assert status["matched"] == 0
    assert status["error"] is None


def test_tree_denied_maps_to_scope_signal(monkeypatch):
    http = _fake_http(errors={"/git/trees/": {"http_status": 404, "detail": "no"}})
    matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki"}, monkeypatch, http
    )
    assert matched == []
    assert status["error"] == "search_tree_denied"


def test_ref_unresolved_when_repo_lookup_fails(monkeypatch):
    http = _fake_http(errors={"/repos/" + _DEST: {"http_status": 500, "detail": "boom"}})
    _matched, status = _run(
        {"search_destination": _DEST, "search_query": "wiki"}, monkeypatch, http
    )
    assert status["error"] == "search_ref_unresolved"


def test_invalid_destination(monkeypatch):
    _matched, status = _run(
        {"search_destination": "not-a-repo", "search_query": "wiki"}, monkeypatch
    )
    assert status["error"] == "search_destination_invalid"


def test_no_query(monkeypatch):
    _matched, status = _run({"search_destination": _DEST}, monkeypatch)
    assert status["error"] == "no_search_query"


def test_falls_back_to_read_destination(monkeypatch):
    http = _fake_http(tree=_tree("a/wiki.py"))
    matched, status = _run(
        {"read_destination": _DEST, "search_query": "wiki"}, monkeypatch, http
    )
    assert matched == ["a/wiki.py"]
    assert status["error"] is None


def test_search_token_uses_read_map_not_write_map(monkeypatch):
    # Write map present, read map absent -> search stays unauthenticated.
    monkeypatch.setenv("WORKFLOW_GITHUB_PR_CAPABILITIES", json.dumps({_DEST: "WRITETOKEN"}))
    monkeypatch.delenv("WORKFLOW_GITHUB_READ_CAPABILITIES", raising=False)
    http = _fake_http(tree=_tree("a/wiki.py"))
    _run({"search_destination": _DEST, "search_query": "wiki"}, monkeypatch, http)
    assert all(tok == "" for _url, tok in http.calls)  # unauthenticated


def test_search_token_resolved_from_read_map(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_READ_CAPABILITIES", json.dumps({_DEST: "READTOKEN"})
    )
    http = _fake_http(tree=_tree("a/wiki.py"))
    _run({"search_destination": _DEST, "search_query": "wiki"}, monkeypatch, http)
    assert all(tok == "READTOKEN" for _url, tok in http.calls)


def test_registration_resolves_in_domain_registry():
    from workflow.domain_registry import resolve_domain_callable

    gs.register_search_repo_files()
    assert resolve_domain_callable("workflow", "search_repo_files") is gs.search_repo_files

import json

from workflow.api.helpers import _scoped_wiki_root
from workflow.api.wiki import (
    _WIKI_READ_DEFAULT_MAX_CHARS,
    _ensure_wiki_scaffold,
    _wiki_file_bug,
)

_FILE_BUG_UNSUPPORTED_HINT = (
    "Use repro, observed, expected, and workaround for filing body text; "
    "content is only valid for wiki write/patch actions."
)


def _call_file_bug(tmp_path, monkeypatch, **kwargs):
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)
    root = tmp_path / "wiki"
    with _scoped_wiki_root(root):
        _ensure_wiki_scaffold(root)
        payload = json.loads(_wiki_file_bug(**kwargs))
    return root, payload


def test_file_bug_rejects_truthy_unsupported_body_and_content_fields(
    tmp_path,
    monkeypatch,
):
    root, payload = _call_file_bug(
        tmp_path,
        monkeypatch,
        title="Widget render stalls",
        component="workflow.api.wiki",
        severity="major",
        observed="Render blocks for several seconds.",
        expected="Render completes promptly.",
        repro="Open the widget page and trigger a refresh.",
        body="Caller tried to pass filing prose via body.",
        content="Caller tried to pass filing prose via content.",
    )

    assert payload == {
        "error": "Unsupported file_bug field(s): body, content.",
        "hint": _FILE_BUG_UNSUPPORTED_HINT,
    }
    assert list((root / "pages" / "bugs").glob("*.md")) == []


def test_file_bug_rejects_content_instead_of_creating_title_only_shell(
    tmp_path,
    monkeypatch,
):
    root, payload = _call_file_bug(
        tmp_path,
        monkeypatch,
        title="Title-only shell should not file",
        component="workflow.api.wiki",
        severity="major",
        content="Observed: shell filing currently happens when content is dropped.",
    )

    assert payload == {
        "error": "Unsupported file_bug field(s): content.",
        "hint": _FILE_BUG_UNSUPPORTED_HINT,
    }
    assert "bug_id" not in payload
    assert "path" not in payload
    assert "status" not in payload
    assert list((root / "pages" / "bugs").glob("*.md")) == []


def test_file_bug_ignores_empty_unsupported_fields_and_compat_defaults(
    tmp_path,
    monkeypatch,
):
    root, payload = _call_file_bug(
        tmp_path,
        monkeypatch,
        title="Cache miss on read",
        component="workflow.api.wiki",
        severity="major",
        observed="Reads fall back to stale cache entries.",
        expected="Reads should return the latest wiki content.",
        repro="Call read twice after a patch and compare results.",
        workaround="Patch again to refresh the cache.",
        content="",
        body="",
        dry_run=True,
        similarity_threshold=0.25,
        max_results=10,
        offset=0,
        max_chars=_WIKI_READ_DEFAULT_MAX_CHARS,
    )

    assert payload["status"] == "filed"
    assert payload["bug_id"] == "BUG-001"
    assert payload["path"] == "pages/bugs/bug-001-cache-miss-on-read.md"
    assert payload["kind"] == "bug"
    assert payload["severity"] == "major"
    assert payload["component"] == "workflow.api.wiki"
    assert "warning" not in payload

    bug_page = root / payload["path"]
    assert bug_page.exists()
    page_text = bug_page.read_text(encoding="utf-8")
    assert "# BUG-001: Cache miss on read" in page_text
    assert "## What happened\n\nReads fall back to stale cache entries." in page_text
    assert "## What was expected\n\nReads should return the latest wiki content." in page_text

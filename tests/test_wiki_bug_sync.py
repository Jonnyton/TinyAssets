"""Tests for scripts/wiki_bug_sync.py — mocked MCP + GH responses."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from wiki_bug_sync import (  # noqa: E402
    SyncError,
    _bug_number,
    create_gh_issue,
    fetch_bug_detail,
    list_new_bugs,
    list_new_change_requests,
    read_cursor,
    sync,
    write_cursor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INIT_OK = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}
_NOTIF_NONE = None


def _wiki_list_resp(bugs: list[dict]) -> dict:
    """Build a mock MCP tools/call result for wiki action=list."""
    promoted = [
        {"path": b["path"], "title": b.get("title", b["path"]), "type": "bug"}
        for b in bugs
    ]
    return {
        "jsonrpc": "2.0",
        "id": 10,
        "result": {
            "content": [
                {"type": "text", "text": json.dumps({"promoted": promoted, "drafts": []})}
            ]
        },
    }


def _wiki_read_resp(meta: dict) -> dict:
    """Build a mock MCP tools/call result for wiki action=read."""
    fm_lines = "\n".join(f"{k}: {v}" for k, v in meta.items())
    content = f"---\n{fm_lines}\n---\n\n# Body"
    return {
        "jsonrpc": "2.0",
        "id": 10,
        "result": {
            "content": [
                {"type": "text", "text": json.dumps({"content": content})}
            ]
        },
    }


def _make_post_fn(*responses):
    it = iter(responses)

    def _post(url, sid, payload, timeout):
        return next(it)

    return _post


class CapturingPost:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, sid, payload, timeout):
        self.calls.append(payload)
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# _bug_number
# ---------------------------------------------------------------------------


def test_bug_number_standard():
    assert _bug_number("bugs/BUG-003-some-slug") == 3


def test_bug_number_caps():
    assert _bug_number("bugs/BUG-042-foo") == 42


def test_bug_number_missing():
    assert _bug_number("projects/some-page") is None


# ---------------------------------------------------------------------------
# list_new_bugs
# ---------------------------------------------------------------------------


def test_list_new_bugs_filters_by_cursor():
    wiki_list = {
        "promoted": [
            {"path": "bugs/BUG-001-a", "type": "bug", "title": "A"},
            {"path": "bugs/BUG-002-b", "type": "bug", "title": "B"},
            {"path": "bugs/BUG-003-c", "type": "bug", "title": "C"},
        ]
    }
    result = list_new_bugs(wiki_list, cursor=1)
    assert [e["bug_number"] for e in result] == [2, 3]


def test_list_new_bugs_zero_cursor_returns_all():
    wiki_list = {
        "promoted": [
            {"path": "bugs/BUG-001-a", "type": "bug"},
            {"path": "bugs/BUG-002-b", "type": "bug"},
        ]
    }
    result = list_new_bugs(wiki_list, cursor=0)
    assert len(result) == 2


def test_list_new_bugs_skips_non_bug_type():
    wiki_list = {
        "promoted": [
            {"path": "projects/some-project", "type": "project"},
            {"path": "bugs/BUG-001-a", "type": "bug"},
        ]
    }
    result = list_new_bugs(wiki_list, cursor=0)
    assert len(result) == 1
    assert result[0]["bug_number"] == 1


def test_list_new_bugs_empty_promoted():
    result = list_new_bugs({"promoted": []}, cursor=0)
    assert result == []


def test_list_new_bugs_sorted_ascending():
    wiki_list = {
        "promoted": [
            {"path": "bugs/BUG-005-e", "type": "bug"},
            {"path": "bugs/BUG-003-c", "type": "bug"},
            {"path": "bugs/BUG-004-d", "type": "bug"},
        ]
    }
    result = list_new_bugs(wiki_list, cursor=2)
    assert [e["bug_number"] for e in result] == [3, 4, 5]


# ---------------------------------------------------------------------------
# list_new_change_requests
# ---------------------------------------------------------------------------


def test_live_wiki_refactoring_request_is_project_design():
    wiki_list = {
        "promoted": [
            {
                "path": (
                    "pages/plans/"
                    "live-wiki-refactoring-and-multi-generation-attribution.md"
                ),
                "title": "Live Wiki Refactoring + Multi-Generation Attribution",
                "type": "unknown",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "project-design"


def test_plain_promoted_plan_remains_docs_ops():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/plans/methods-prose-rubric.md",
                "title": "Methods-Prose Rubric",
                "type": "plan",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "docs-ops"


def test_patch_request_page_enters_patch_lane():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/patch-requests/pr-001-update-connector-guidance.md",
                "title": "Update connector guidance",
                "type": "patch_request",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "patch"


def test_architectural_patch_request_enters_project_design_lane():
    wiki_list = {
        "promoted": [
            {
                "path": (
                    "pages/patch-requests/"
                    "pr-004-dispatcher-should-detect-filing-shape.md"
                ),
                "title": (
                    "Dispatcher should detect filing-shape mechanical vs "
                    "architectural and route to design-note drafts"
                ),
                "type": "patch_request",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "project-design"


def test_coordination_note_with_design_language_is_not_a_request():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/notes/codex-architectural-coordination-2026-05-06.md",
                "title": "Codex architectural coordination note",
                "type": "note",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert result == []


def test_builder_note_enters_branch_refinement_lane():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/notes/builder-notes-agent-teams.md",
                "title": "Builder notes: agent teams",
                "type": "note",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "branch-refinement"


def test_legacy_bug_typed_patch_request_page_enters_patch_lane():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/patch-requests/pr-002-legacy-type-bug.md",
                "title": "Legacy patch page",
                "type": "bug",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "patch"


def test_feature_request_page_enters_feature_lane():
    wiki_list = {
        "promoted": [
            {
                "path": "pages/feature-requests/feat-001-add-bulk-review.md",
                "title": "Add bulk review",
                "type": "feature",
            }
        ]
    }
    result = list_new_change_requests(wiki_list, seen_paths=set())
    assert len(result) == 1
    assert result[0]["request_kind"] == "feature"


# ---------------------------------------------------------------------------
# cursor read/write
# ---------------------------------------------------------------------------


def test_cursor_roundtrip(tmp_path):
    p = tmp_path / ".wiki_bug_sync_cursor"
    write_cursor(7, p)
    assert read_cursor(p) == 7


def test_cursor_missing_returns_zero(tmp_path):
    p = tmp_path / ".wiki_bug_sync_cursor"
    assert read_cursor(p) == 0


def test_cursor_corrupt_returns_zero(tmp_path):
    p = tmp_path / ".wiki_bug_sync_cursor"
    p.write_text("not-a-number", encoding="utf-8")
    assert read_cursor(p) == 0


# ---------------------------------------------------------------------------
# create_gh_issue — dry-run
# ---------------------------------------------------------------------------


def test_create_gh_issue_dry_run_returns_marker():
    url = create_gh_issue(
        token="", repo="owner/repo",
        bug_id="BUG-001", title="Test bug",
        severity="high", component="chatbot",
        body_md="desc", dry_run=True,
    )
    assert url == "[dry-run]"


def test_create_gh_issue_labels_canonical_wiki_severity(capsys):
    url = create_gh_issue(
        token="", repo="owner/repo",
        bug_id="BUG-001", title="Critical bug",
        severity="critical", component="wiki",
        body_md="desc", dry_run=True,
    )
    out = capsys.readouterr().out
    assert url == "[dry-run]"
    assert "severity:critical" in out


def test_create_gh_issue_no_token_raises():
    with pytest.raises(SyncError) as exc_info:
        create_gh_issue(
            token="", repo="owner/repo",
            bug_id="BUG-001", title="Test bug",
            severity="high", component="chatbot",
            body_md="desc", dry_run=False,
        )
    assert exc_info.value.code == 3


def test_fetch_bug_detail_reads_with_page_not_path():
    post = CapturingPost([
        (_wiki_read_resp({"title": "Bug", "severity": "high"}), "sid1"),
    ])
    detail = fetch_bug_detail(
        "http://fake/mcp",
        "sid1",
        "pages/bugs/BUG-003-new.md",
        5.0,
        post_fn=post,
    )

    args = post.calls[0]["params"]["arguments"]
    assert args == {"action": "read", "page": "BUG-003-new"}
    assert detail["title"] == "Bug"


# ---------------------------------------------------------------------------
# sync() — happy path: no new bugs
# ---------------------------------------------------------------------------


def test_sync_no_new_bugs(tmp_path):
    cursor_path = tmp_path / "cursor"
    write_cursor(5, cursor_path)

    # wiki list returns bugs 1-5 only; cursor=5 → nothing new
    post_fn = _make_post_fn(
        (_INIT_OK, "sid1"),
        (_NOTIF_NONE, "sid1"),
        (_wiki_list_resp([
            {"path": "bugs/BUG-001-a"},
            {"path": "bugs/BUG-005-e"},
        ]), "sid1"),
    )
    rc = sync("http://fake/mcp", 5.0, dry_run=True, cursor_path=cursor_path, post_fn=post_fn)
    assert rc == 0
    assert read_cursor(cursor_path) == 5  # unchanged


# ---------------------------------------------------------------------------
# sync() — happy path: one new bug
# ---------------------------------------------------------------------------


def test_sync_one_new_bug(tmp_path):
    cursor_path = tmp_path / "cursor"
    write_cursor(2, cursor_path)

    post_fn = _make_post_fn(
        (_INIT_OK, "sid1"),
        (_NOTIF_NONE, "sid1"),
        (_wiki_list_resp([
            {"path": "bugs/BUG-001-old"},
            {"path": "bugs/BUG-002-old"},
            {"path": "bugs/BUG-003-new", "title": "New Bug"},
        ]), "sid1"),
        # wiki read for BUG-003
        (_wiki_read_resp({"title": "New Bug", "severity": "high", "component": "chatbot"}), "sid1"),
    )
    rc = sync(
        "http://fake/mcp", 5.0, dry_run=True,
        cursor_path=cursor_path, post_fn=post_fn,
    )
    assert rc == 0
    # dry_run=True → cursor NOT updated
    assert read_cursor(cursor_path) == 2


def test_sync_one_new_bug_updates_cursor(tmp_path):
    cursor_path = tmp_path / "cursor"
    write_cursor(2, cursor_path)

    created_issues = []

    def _fake_post(url, sid, payload, timeout):
        method = payload.get("method", "")
        if method == "initialize":
            return _INIT_OK, "sid1"
        if method == "notifications/initialized":
            return _NOTIF_NONE, "sid1"
        # tools/call
        tool = payload.get("params", {}).get("name")
        if tool == "wiki":
            args = payload.get("params", {}).get("arguments", {})
            if args.get("action") == "list":
                return _wiki_list_resp([{"path": "bugs/BUG-003-new", "title": "New Bug"}]), "sid1"
            if args.get("action") == "read":
                return _wiki_read_resp(
                    {"title": "New Bug", "severity": "medium", "component": "ui"}
                ), "sid1"
        return None, "sid1"

    def _fake_create_issue(token, repo, bug_id, title, severity, component, body_md,
                           dry_run=False, gh_api=None, timeout=20.0):
        created_issues.append(bug_id)
        return "https://github.com/owner/repo/issues/42"

    with patch("wiki_bug_sync.create_gh_issue", side_effect=_fake_create_issue):
        rc = sync(
            "http://fake/mcp", 5.0, dry_run=False,
            token="fake-token", cursor_path=cursor_path, post_fn=_fake_post,
        )

    assert rc == 0
    assert created_issues == ["BUG-003"]
    assert read_cursor(cursor_path) == 3


# ---------------------------------------------------------------------------
# sync() — many new bugs
# ---------------------------------------------------------------------------


def test_sync_many_new_bugs(tmp_path):
    cursor_path = tmp_path / "cursor"
    write_cursor(0, cursor_path)

    bugs = [{"path": f"bugs/BUG-{i:03d}-slug"} for i in range(1, 6)]
    # post_fn returns: init, notif, list, then 5 reads
    responses = [
        (_INIT_OK, "sid1"),
        (_NOTIF_NONE, "sid1"),
        (_wiki_list_resp(bugs), "sid1"),
    ] + [
        (_wiki_read_resp({"title": f"Bug {i}", "severity": "low", "component": "x"}), "sid1")
        for i in range(1, 6)
    ]
    post_fn = _make_post_fn(*responses)

    rc = sync(
        "http://fake/mcp", 5.0, dry_run=True,
        cursor_path=cursor_path, post_fn=post_fn,
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# sync() — network error
# ---------------------------------------------------------------------------


def test_sync_network_error_returns_code2(tmp_path):
    cursor_path = tmp_path / "cursor"
    write_cursor(0, cursor_path)

    def _failing(url, sid, payload, timeout):
        raise SyncError(2, "network down")

    rc = sync("http://fake/mcp", 5.0, dry_run=True, cursor_path=cursor_path, post_fn=_failing)
    assert rc == 2


# ---------------------------------------------------------------------------
# Severity label map
# ---------------------------------------------------------------------------


def test_severity_labels_all_present():
    from wiki_bug_sync import _SEVERITY_LABELS
    for sev in (
        "critical", "major", "minor", "cosmetic",
        "low", "medium", "high", "blocker",
    ):
        assert sev in _SEVERITY_LABELS
        assert _SEVERITY_LABELS[sev].startswith("severity:")

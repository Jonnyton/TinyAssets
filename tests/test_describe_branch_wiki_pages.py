"""Tests for _related_wiki_pages helper and its wiring into
describe_branch + get_branch responses (Task #19, closes BUG-018).

All tests use a tmp_path wiki directory to avoid touching real wiki files.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

# ── shared wiki fixture ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_wiki(tmp_path, monkeypatch):
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    yield wiki_root


def _make_page(wiki_root: Path, category: str, slug: str, content: str) -> Path:
    """Write a wiki page file, creating parent directories as needed."""
    page_dir = wiki_root / "pages" / category
    page_dir.mkdir(parents=True, exist_ok=True)
    p = page_dir / f"{slug}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _branch_dict(
    branch_def_id: str,
    node_ids: list[str] | None = None,
) -> dict:
    """Minimal branch dict that _related_wiki_pages accepts."""
    return {
        "branch_def_id": branch_def_id,
        "node_defs": [{"node_id": nid} for nid in (node_ids or [])],
    }


# ── unit tests for _related_wiki_pages ─────────────────────────────────────


def test_matching_page_returned(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "plans", "my-branch-plan", textwrap.dedent("""\
        ---
        title: My Branch Plan
        ---

        This document describes my-branch-def setup and usage.
    """))

    result = _related_wiki_pages(_branch_dict("my-branch-def"))
    assert result["items"], "Expected at least one matching page"
    paths = [item["path"] for item in result["items"]]
    assert any("my-branch-plan" in p for p in paths)


def test_no_matches_returns_empty_list(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    result = _related_wiki_pages(_branch_dict("no-such-branch-xyz"))
    assert result["items"] == []
    assert result["truncated_count"] == 0


def test_related_wiki_pages_key_never_missing(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    result = _related_wiki_pages(_branch_dict("ghost-branch"))
    assert "items" in result
    assert "truncated_count" in result


def test_matched_via_reflects_matching_terms(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "plans", "node-and-branch", textwrap.dedent("""\
        ---
        title: Node And Branch
        ---

        Describes my-branch-abc and its node node-alpha usage.
    """))

    branch = _branch_dict("my-branch-abc", node_ids=["node-alpha"])
    result = _related_wiki_pages(branch)
    assert result["items"], "Expected a match"
    matched = result["items"][0]["matched_via"]
    assert any("branch_def_id" in m or "node:node-alpha" in m for m in matched)


def test_summary_truncates_at_140_chars(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    long_body = "x" * 200
    _make_page(wiki_root, "plans", "long-doc", textwrap.dedent(f"""\
        ---
        title: Long Doc
        ---

        my-branch-def {long_body}
    """))

    result = _related_wiki_pages(_branch_dict("my-branch-def"))
    assert result["items"], "Expected a match"
    summary = result["items"][0]["summary"]
    assert len(summary) <= 140, f"Summary too long: {len(summary)} chars"


def test_top_20_cap_sets_truncated_count(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    for i in range(25):
        _make_page(wiki_root, "plans", f"page-{i:03d}", textwrap.dedent(f"""\
            ---
            title: Page {i}
            ---

            Mentions my-branch-cap for completeness.
        """))

    result = _related_wiki_pages(_branch_dict("my-branch-cap"))
    assert len(result["items"]) <= 20
    assert result["truncated_count"] == max(0, 25 - 20)


def test_empty_branch_dict_returns_empty():
    from tinyassets.api.branches import _related_wiki_pages

    result = _related_wiki_pages({})
    assert result == {"items": [], "truncated_count": 0}


def test_branch_with_no_node_defs_still_matches_by_branch_id(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "notes", "branch-only", textwrap.dedent("""\
        ---
        title: Branch Only
        ---

        Talks about solo-branch exclusively.
    """))

    result = _related_wiki_pages({"branch_def_id": "solo-branch", "node_defs": []})
    assert result["items"], "Should match by branch_def_id even with no node_defs"


def test_node_match_only_also_returned(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "notes", "node-only", textwrap.dedent("""\
        ---
        title: Node Only
        ---

        This covers node-beta in depth.
    """))

    branch = _branch_dict("no-branch-mention-xyz", node_ids=["node-beta"])
    result = _related_wiki_pages(branch)
    assert result["items"], "Should match by node id even if branch_def_id absent"
    assert any("node:node-beta" in item["matched_via"] for item in result["items"])


def test_sorted_by_match_count_descending(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "notes", "both-match", textwrap.dedent("""\
        ---
        title: Both Match
        ---

        Mentions sort-branch and sort-node together.
    """))
    _make_page(wiki_root, "notes", "single-match", textwrap.dedent("""\
        ---
        title: Single Match
        ---

        Only mentions sort-branch here.
    """))

    branch = _branch_dict("sort-branch", node_ids=["sort-node"])
    result = _related_wiki_pages(branch)
    assert len(result["items"]) >= 2
    first_count = len(result["items"][0]["matched_via"])
    second_count = len(result["items"][1]["matched_via"])
    assert first_count >= second_count, "Higher match-count page must come first"


def test_each_item_has_required_fields(tmp_path):
    from tinyassets.api.branches import _related_wiki_pages

    wiki_root = Path(os.environ["TINYASSETS_WIKI_PATH"])
    _make_page(wiki_root, "notes", "fields-check", textwrap.dedent("""\
        ---
        title: Fields Check
        ---

        Describes fields-branch.
    """))

    result = _related_wiki_pages(_branch_dict("fields-branch"))
    assert result["items"]
    item = result["items"][0]
    assert "path" in item
    assert "title" in item
    assert "summary" in item
    assert "matched_via" in item
    assert isinstance(item["matched_via"], list)


# ── integration: wired into describe_branch + get_branch JSON ──────────────


def test_describe_branch_response_contains_related_wiki_pages_key(tmp_path, monkeypatch):
    """describe_branch JSON must include related_wiki_pages field."""
    from unittest.mock import patch

    from tinyassets.api.branches import _ext_branch_describe

    branch_data = {
        "branch_def_id": "my-integration-branch",
        "name": "My Integration Branch",
        "node_defs": [],
        "graph_nodes": [],
        "edges": [],
        "state_schema": [],
    }
    # Patch the real daemon_server module, not a compatibility alias.
    # Also patch list_branch_definitions + list_branch_versions called for lineage.
    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_data),
        patch("tinyassets.daemon_server.list_branch_definitions", return_value=[]),
        patch("tinyassets.branch_versions.list_branch_versions", return_value=[]),
    ):
        result_json = _ext_branch_describe({"branch_def_id": "my-integration-branch"})

    result = json.loads(result_json)
    assert "related_wiki_pages" in result, (
        "describe_branch response must have 'related_wiki_pages' key"
    )
    assert isinstance(result["related_wiki_pages"], list)


def test_get_branch_response_contains_related_wiki_pages_key(tmp_path, monkeypatch):
    """get_branch JSON must include related_wiki_pages field."""
    from unittest.mock import patch

    from tinyassets.api.branches import _ext_branch_get

    branch_data = {
        "branch_def_id": "my-get-branch",
        "name": "My Get Branch",
        "node_defs": [],
        "graph_nodes": [],
        "edges": [],
        "state_schema": [],
        "visibility": "public",
        "author": "test-user",
    }
    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_data),
        patch("tinyassets.daemon_server.list_gate_claims", return_value=[]),
        patch("tinyassets.api.market._gates_enabled", return_value=False),
    ):
        result_json = _ext_branch_get({"branch_def_id": "my-get-branch"})

    result = json.loads(result_json)
    assert "related_wiki_pages" in result, (
        "get_branch response must have 'related_wiki_pages' key"
    )
    assert isinstance(result["related_wiki_pages"], list)


def test_describe_branch_related_wiki_pages_not_missing_when_no_matches(tmp_path, monkeypatch):
    """related_wiki_pages must be [] not missing when no wiki pages match."""
    from unittest.mock import patch

    from tinyassets.api.branches import _ext_branch_describe

    branch_data = {
        "branch_def_id": "orphan-branch-no-wiki",
        "name": "Orphan",
        "node_defs": [],
        "graph_nodes": [],
        "edges": [],
        "state_schema": [],
    }
    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_data),
        patch("tinyassets.daemon_server.list_branch_definitions", return_value=[]),
        patch("tinyassets.branch_versions.list_branch_versions", return_value=[]),
    ):
        result_json = _ext_branch_describe({"branch_def_id": "orphan-branch-no-wiki"})

    result = json.loads(result_json)
    assert result.get("related_wiki_pages") == [], (
        "No-match branches must return empty list, not missing key"
    )

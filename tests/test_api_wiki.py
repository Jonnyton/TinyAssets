"""Task #9 — direct tests for `workflow.api.wiki` after decomp Step 2.

The legacy test files (`test_wiki_*.py`) import from `workflow.universe_server`
to cover chatbot-facing MCP wrappers. This file exercises `workflow.api.wiki`
directly to lock in the canonical implementation surface.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from workflow.api import wiki as wiki_mod
from workflow.api.wiki import (
    _BUG_DEDUP_THRESHOLD,
    _BUGS_CATEGORY,
    _KIND_ROUTING,
    _UNSUPPORTED_FILE_BUG_BODY_KWARGS,
    _VALID_BUG_KINDS,
    _VALID_SEVERITIES,
    _WIKI_CATEGORIES,
    _WIKI_READ_DEFAULT_MAX_CHARS,
    _WIKI_READ_MAX_CHARS,
    _bug_token_set,
    _ensure_wiki_scaffold,
    _extract_keywords,
    _jaccard,
    _next_id,
    _parse_frontmatter,
    _sanitize_slug,
    _slugify_title,
    _wiki_file_bug,
    _wiki_similarity_score,
    wiki,
)

# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def wiki_env(tmp_path, monkeypatch):
    """Isolated wiki root, scaffold pre-built."""
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    _ensure_wiki_scaffold(wiki_root)
    return wiki_root


# ── module surface ──────────────────────────────────────────────────────────


def test_module_exposes_expected_public_names():
    """The new submodule's contract surface — guards against silent removal."""
    expected = {
        "wiki", "_ensure_wiki_scaffold", "_WIKI_CATEGORIES",
        "_wiki_file_bug", "_wiki_cosign_bug",
    }
    missing = expected - set(dir(wiki_mod))
    assert not missing, f"wiki.py is missing public names: {missing}"


def test_wiki_categories_canonical_order():
    """Category enum stays in a stable order — wiki-mcp/server.js mirrors it."""
    assert _WIKI_CATEGORIES[0] == "projects"
    assert _WIKI_CATEGORIES[-1] == "bugs"
    assert _BUGS_CATEGORY in _WIKI_CATEGORIES
    assert len(_WIKI_CATEGORIES) == 10


def test_kind_routing_covers_all_valid_kinds():
    assert set(_KIND_ROUTING.keys()) == set(_VALID_BUG_KINDS)
    for kind, (subdir, prefix) in _KIND_ROUTING.items():
        assert subdir, f"empty subdir for kind={kind}"
        assert prefix, f"empty prefix for kind={kind}"


# ── helper unit tests ───────────────────────────────────────────────────────


def test_sanitize_slug_strips_extension_and_normalizes():
    assert _sanitize_slug("My Page.md") == "my-page"
    assert _sanitize_slug("UPPER_CASE") == "upper-case"
    assert _sanitize_slug("a/b!c.md") == "a-b-c"


def test_slugify_title_truncates_and_handles_empty():
    long = "x" * 100
    assert len(_slugify_title(long, max_len=20)) <= 20
    assert _slugify_title("!!!") == "untitled"


def test_parse_frontmatter_roundtrip():
    raw = "---\ntitle: Foo\ntype: note\n---\nbody here\n"
    meta, body = _parse_frontmatter(raw)
    assert meta == {"title": "Foo", "type": "note"}
    assert body == "body here\n"


def test_parse_frontmatter_no_frontmatter_returns_empty_meta():
    raw = "just body, no frontmatter"
    meta, body = _parse_frontmatter(raw)
    assert meta == {}
    assert body == raw


def test_extract_keywords_drops_stop_words():
    kws = _extract_keywords("The quick brown fox jumps over the lazy dog")
    assert "quick" in kws
    assert "brown" in kws
    assert "the" not in kws  # stop word
    assert "a" not in kws


def test_wiki_similarity_score_identical_pages_high():
    meta = {"title": "Foo"}
    body = "rabbit hops through forest with [[carrots]]"
    score = _wiki_similarity_score(meta, body, meta, body)
    assert score > 0.4  # same body + same title


def test_wiki_similarity_score_disjoint_pages_low():
    score = _wiki_similarity_score(
        {"title": "A"}, "rabbits hop forest carrots",
        {"title": "B"}, "elephants stomp savanna grass",
    )
    assert score < 0.2


def test_jaccard_basic():
    assert _jaccard(set(), set()) == 1.0
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)


def test_bug_token_set_filters_short_words():
    tokens = _bug_token_set("To do or not to do, that is the question.")
    assert "question" in tokens
    assert "to" not in tokens  # too short
    assert "do" not in tokens


def test_bug_dedup_threshold_constant():
    assert 0 < _BUG_DEDUP_THRESHOLD <= 1.0


def test_next_id_starts_at_001_for_empty_dirs(tmp_path):
    assert _next_id(tmp_path / "missing", tmp_path / "also_missing", "BUG") == "BUG-001"
    pages = tmp_path / "pages"
    drafts = tmp_path / "drafts"
    pages.mkdir()
    drafts.mkdir()
    assert _next_id(pages, drafts, "BUG") == "BUG-001"


def test_next_id_increments_past_existing(tmp_path):
    pages = tmp_path / "pages"
    drafts = tmp_path / "drafts"
    pages.mkdir()
    drafts.mkdir()
    (pages / "BUG-001-foo.md").write_text("x")
    (pages / "BUG-007-bar.md").write_text("x")
    (drafts / "BUG-003-baz.md").write_text("x")
    assert _next_id(pages, drafts, "BUG") == "BUG-008"


# ── scaffold ────────────────────────────────────────────────────────────────


def test_ensure_wiki_scaffold_creates_full_tree(tmp_path):
    root = tmp_path / "fresh"
    _ensure_wiki_scaffold(root)
    for cat in _WIKI_CATEGORIES:
        assert (root / "pages" / cat).is_dir()
        assert (root / "drafts" / cat).is_dir()
    assert (root / "raw").is_dir()
    assert (root / "log").is_dir()
    assert (root / "index.md").is_file()
    assert (root / "WIKI.md").is_file()
    assert (root / "log.md").is_file()


def test_ensure_wiki_scaffold_idempotent_preserves_user_content(tmp_path):
    root = tmp_path / "fresh"
    _ensure_wiki_scaffold(root)
    (root / "index.md").write_text("MY CUSTOM INDEX")
    _ensure_wiki_scaffold(root)  # second call must not overwrite
    assert (root / "index.md").read_text() == "MY CUSTOM INDEX"


# ── dispatch entry ──────────────────────────────────────────────────────────


def test_wiki_unknown_action_returns_error(wiki_env):
    res = json.loads(wiki(action="bogus_action"))
    assert "error" in res
    assert "available_actions" in res
    assert "read" in res["available_actions"]


def test_wiki_list_returns_promoted_and_drafts_keys(wiki_env):
    res = json.loads(wiki(action="list"))
    assert "promoted" in res
    assert "drafts" in res
    assert "promoted_count" in res
    assert "drafts_count" in res


def test_wiki_search_requires_query(wiki_env):
    res = json.loads(wiki(action="search", query=""))
    assert "error" in res


def test_wiki_search_no_results_returns_empty_list(wiki_env):
    res = json.loads(wiki(action="search", query="zzz_nothing_should_match"))
    assert res["results"] == []
    assert res["search_complete"] is False
    assert "action=since" in res["completeness_warning"]


def test_wiki_search_returns_completeness_warning_with_matches(wiki_env):
    page = wiki_env / "pages" / "notes" / "search-target.md"
    page.write_text(
        "---\n"
        "title: Search Target\n"
        "type: note\n"
        "updated: 2026-05-06T12:00:00Z\n"
        "---\n\n"
        "This page mentions cross AI discovery gaps.\n",
        encoding="utf-8",
        newline="\n",
    )

    res = json.loads(wiki(action="search", query="discovery"))

    assert res["count"] == 1
    assert res["search_complete"] is False
    assert "lexical" in res["completeness_warning"]
    assert "action=since" in res["completeness_warning"]


def test_wiki_since_returns_pages_updated_after_timestamp(wiki_env):
    fresh_dir = wiki_env / "pages" / "patch-requests"
    fresh_dir.mkdir(parents=True)
    fresh = fresh_dir / "fresh-patch.md"
    fresh.write_text(
        "---\n"
        "title: Fresh Patch\n"
        "type: patch_request\n"
        "updated: 2026-05-06T12:00:00Z\n"
        "---\n\n"
        "Fresh patch request content.\n",
        encoding="utf-8",
        newline="\n",
    )
    older = wiki_env / "pages" / "notes" / "older-note.md"
    older.write_text(
        "---\n"
        "title: Older Note\n"
        "type: note\n"
        "updated: 2026-05-01T12:00:00Z\n"
        "---\n\n"
        "Older note content.\n",
        encoding="utf-8",
        newline="\n",
    )

    res = json.loads(
        wiki(action="since", changed_since="2026-05-05T00:00:00Z")
    )

    assert res["changed_since"] == "2026-05-05T00:00:00Z"
    assert res["count"] == 1
    assert res["results"][0]["path"] == "pages/patch-requests/fresh-patch.md"
    assert res["results"][0]["title"] == "Fresh Patch"
    assert res["results"][0]["updated"] == "2026-05-06T12:00:00Z"


def test_wiki_since_requires_valid_changed_since(wiki_env):
    missing = json.loads(wiki(action="since"))
    invalid = json.loads(wiki(action="since", changed_since="not-a-date"))

    assert "changed_since parameter is required" in missing["error"]
    assert "valid ISO" in invalid["error"]


def test_wiki_read_requires_page(wiki_env):
    res = json.loads(wiki(action="read", page=""))
    assert "error" in res


def test_wiki_read_index_after_scaffold(wiki_env):
    res = json.loads(wiki(action="read", page="index"))
    assert "content" in res
    assert "Wiki Index" in res["content"]


def test_wiki_read_returns_source_proof_and_ambient_feed(wiki_env):
    source = wiki_env / "pages" / "notes" / "live-brain.md"
    source.write_text(
        "---\n"
        "title: Live Brain\n"
        "type: note\n"
        "updated: 2026-05-01\n"
        "tags: ambient relevance\n"
        "---\n\n"
        "# Live Brain\n\n"
        "Ambient relevance should move source-read proof across sessions.\n",
        encoding="utf-8",
        newline="\n",
    )
    related = wiki_env / "pages" / "notes" / "fresh-related.md"
    related.write_text(
        "---\n"
        "title: Fresh Related\n"
        "type: note\n"
        "updated: 2026-05-06T12:00:00Z\n"
        "tags: relevance feed\n"
        "---\n\n"
        "This note mentions ambient source-read proof for adjacent goals.\n",
        encoding="utf-8",
        newline="\n",
    )
    old = wiki_env / "pages" / "notes" / "old-related.md"
    old.write_text(
        "---\n"
        "title: Old Related\n"
        "type: note\n"
        "updated: 2026-04-01\n"
        "tags: ambient relevance\n"
        "---\n\n"
        "Old ambient relevance should be excluded by changed_since.\n",
        encoding="utf-8",
        newline="\n",
    )

    res = json.loads(
        wiki(
            action="read",
            page="live-brain",
            query="ambient relevance source proof",
            changed_since="2026-05-02T00:00:00Z",
            max_results=5,
        )
    )

    assert res["source_read_proof"]["path"] == "pages/notes/live-brain.md"
    assert res["source_read_proof"]["title"] == "Live Brain"
    assert len(res["source_read_proof"]["sha256"]) == 64
    feed = res["ambient_relevance_feed"]
    assert feed["source_path"] == "pages/notes/live-brain.md"
    paths = [item["path"] for item in feed["items"]]
    assert "pages/notes/fresh-related.md" in paths
    assert "pages/notes/old-related.md" not in paths
    assert "pages/notes/live-brain.md" not in paths
    fresh = next(item for item in feed["items"] if item["path"].endswith("fresh-related.md"))
    assert "ambient" in fresh["matched_terms"]


def test_wiki_read_large_page_marks_content_and_supports_offset(wiki_env):
    path = wiki_env / "pages" / "notes" / "large-read.md"
    body = "start marker\n" + ("x" * 16000) + "\nend marker\n"
    path.write_text(
        "---\n"
        "title: Large Read\n"
        "type: note\n"
        "updated: 2026-05-27T00:00:00Z\n"
        "---\n\n"
        + body,
        encoding="utf-8",
        newline="\n",
    )

    first = json.loads(wiki(action="read", page="large-read", max_chars=4000))

    assert first["truncated"] is True
    assert first["read_start"] == 0
    assert first["read_end"] == 4000
    assert first["next_offset"] == 4000
    assert "WIKI READ TRUNCATED" in first["content"]
    assert "offset=4000" in first["content"]
    assert "end marker" not in first["content"]

    second = json.loads(
        wiki(
            action="read",
            page="large-read",
            offset=first["next_offset"],
            max_chars=20000,
        )
    )

    assert second["truncated"] is False
    assert second["read_start"] == 4000
    assert second["next_offset"] is None
    assert "end marker" in second["content"]


def test_wiki_read_default_window_handles_medium_design_doc(wiki_env):
    path = wiki_env / "pages" / "notes" / "medium-design-doc.md"
    body = "start marker\n" + ("x" * 80_000) + "\nend marker\n"
    path.write_text(
        "---\n"
        "title: Medium Design Doc\n"
        "type: note\n"
        "updated: 2026-05-27T00:00:00Z\n"
        "---\n\n"
        + body,
        encoding="utf-8",
        newline="\n",
    )

    res = json.loads(wiki(action="read", page="medium-design-doc"))

    assert res["truncated"] is False
    assert res["read_limit"] == _WIKI_READ_DEFAULT_MAX_CHARS
    assert res["next_offset"] is None
    assert "end marker" in res["content"]


def test_wiki_read_max_chars_is_capped(wiki_env):
    path = wiki_env / "pages" / "notes" / "oversize-design-doc.md"
    body = "start marker\n" + ("x" * 300_000) + "\nend marker\n"
    path.write_text(
        "---\n"
        "title: Oversize Design Doc\n"
        "type: note\n"
        "updated: 2026-05-27T00:00:00Z\n"
        "---\n\n"
        + body,
        encoding="utf-8",
        newline="\n",
    )

    res = json.loads(
        wiki(action="read", page="oversize-design-doc", max_chars=999_999)
    )

    assert res["truncated"] is True
    assert res["read_limit"] == _WIKI_READ_MAX_CHARS
    assert res["next_offset"] == _WIKI_READ_MAX_CHARS
    assert "WIKI READ TRUNCATED" in res["content"]


def test_wiki_write_requires_filename_and_content(wiki_env):
    res = json.loads(wiki(action="write", category="notes"))
    assert "error" in res


def test_wiki_write_rejects_invalid_category(wiki_env):
    res = json.loads(
        wiki(action="write", category="bogus", filename="x", content="body")
    )
    assert "error" in res
    assert "valid" in res


def test_wiki_write_drafts_then_promote_roundtrip(wiki_env):
    body = (
        "---\ntitle: My Note\ntype: note\nsources: [scratch]\nconfidence: medium\n"
        "---\nThis is the body of my note about [[topic-x]] and [[topic-y]] "
        "with enough characters to clear the body-length lint floor.\n"
    )
    res = json.loads(
        wiki(
            action="write",
            category="notes",
            filename="my-note",
            content=body,
        )
    )
    assert res["status"] == "drafted"
    assert "drafts/notes/my-note.md" in res["path"]

    promoted = json.loads(wiki(action="promote", filename="my-note"))
    assert promoted["status"] == "promoted"
    assert "pages/notes/my-note.md" in promoted["path"]


def test_wiki_write_accepts_wiki_relative_draft_filename(wiki_env):
    res = json.loads(
        wiki(
            action="write",
            category="notes",
            filename="drafts/notes/path-note.md",
            content="body",
        )
    )

    assert res["status"] == "drafted"
    assert res["path"] == "drafts/notes/path-note.md"
    assert (wiki_env / "drafts" / "notes" / "path-note.md").read_text(
        encoding="utf-8"
    ) == "body"
    assert not (wiki_env / "drafts" / "notes" / "drafts-notes-path-note.md").exists()


def test_wiki_patch_updates_long_page_without_full_replace(wiki_env):
    path = wiki_env / "pages" / "notes" / "long-note.md"
    original = (
        "---\ntitle: Long Note\ntype: note\nsources: []\n---\n\n"
        "intro marker\n"
        + ("x" * (_WIKI_READ_DEFAULT_MAX_CHARS + 1_000))
        + "\noriginal tail marker\n"
    )
    path.write_text(original, encoding="utf-8")

    read_result = json.loads(wiki(action="read", page="long-note"))
    assert read_result["truncated"] is True
    assert "original tail marker" not in read_result["content"]

    result = json.loads(
        wiki(
            action="patch",
            page="long-note",
            old_text="intro marker",
            new_text="intro marker\npatched detail",
            expected_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            dry_run=False,
            log_entry="test partial patch",
        )
    )

    assert result["status"] == "patched"
    assert result["path"] == "pages/notes/long-note.md"
    patched = path.read_text(encoding="utf-8")
    assert "intro marker\npatched detail" in patched
    assert "original tail marker" in patched
    assert len(patched) > _WIKI_READ_DEFAULT_MAX_CHARS


def test_wiki_patch_dry_run_reports_without_writing(wiki_env):
    path = wiki_env / "pages" / "notes" / "dry-run-note.md"
    original = "---\ntitle: Dry\ntype: note\n---\n\nbefore\n"
    path.write_text(original, encoding="utf-8")

    result = json.loads(
        wiki(
            action="patch",
            page="dry-run-note",
            old_text="before",
            new_text="after",
        )
    )

    assert result["status"] == "dry_run"
    assert result["would_write"] is True
    assert path.read_text(encoding="utf-8") == original


def test_wiki_patch_rejects_hash_mismatch_without_writing(wiki_env):
    path = wiki_env / "pages" / "notes" / "hash-note.md"
    original = "---\ntitle: Hash\ntype: note\n---\n\nbefore\n"
    path.write_text(original, encoding="utf-8")

    result = json.loads(
        wiki(
            action="patch",
            page="hash-note",
            old_text="before",
            new_text="after",
            expected_sha256="0" * 64,
            dry_run=False,
        )
    )

    assert result["error"] == "content hash mismatch"
    assert result["status"] == "conflict"
    assert path.read_text(encoding="utf-8") == original


def test_wiki_patch_rejects_ambiguous_old_text_without_writing(wiki_env):
    path = wiki_env / "pages" / "notes" / "ambiguous-note.md"
    original = "---\ntitle: Ambiguous\ntype: note\n---\n\nsame\nsame\n"
    path.write_text(original, encoding="utf-8")

    result = json.loads(
        wiki(
            action="patch",
            page="ambiguous-note",
            old_text="same",
            new_text="different",
            dry_run=False,
        )
    )

    assert result["error"] == "old_text must match exactly once"
    assert result["matches"] == 2
    assert path.read_text(encoding="utf-8") == original


def test_wiki_promote_lint_blocks_when_required_fields_missing(wiki_env):
    body = "---\ntitle: Skinny\n---\ntoo short\n"
    json.loads(
        wiki(action="write", category="notes", filename="skinny", content=body)
    )
    res = json.loads(wiki(action="promote", filename="skinny"))
    assert "error" in res
    assert res["error"] == "Promotion blocked."
    assert any("Body too short" in i for i in res["issues"])


def test_wiki_promote_lint_accepts_block_sources_with_non_http_uri(wiki_env):
    body = (
        "---\n"
        "title: Local Source Note\n"
        "type: note\n"
        "sources:\n"
        "  - file:///tmp/local-source.md\n"
        "---\n"
        "This note cites a local [[source-reference]] with enough content "
        "to satisfy promotion lint without requiring an HTTP URL.\n"
    )
    meta, _ = _parse_frontmatter(body)
    assert meta["sources"] == "- file:///tmp/local-source.md"
    assert "- file" not in meta

    json.loads(
        wiki(
            action="write",
            category="notes",
            filename="local-source-note",
            content=body,
        )
    )

    res = json.loads(wiki(action="promote", filename="local-source-note"))

    assert res["status"] == "promoted"


def test_wiki_supersede_requires_three_args(wiki_env):
    res = json.loads(wiki(action="supersede"))
    assert "error" in res


# ── bug-filing dispatch ─────────────────────────────────────────────────────


def test_wiki_file_bug_requires_title_component_severity(wiki_env):
    res = json.loads(wiki(action="file_bug"))
    assert "error" in res
    assert "title" in res["error"]


def test_wiki_file_bug_rejects_invalid_severity(wiki_env):
    res = json.loads(
        wiki(
            action="file_bug",
            component="x",
            severity="catastrophic",  # not a valid level
            title="Something broke",
        )
    )
    assert "error" in res
    assert "valid" in res
    assert set(res["valid"]) == set(_VALID_SEVERITIES)


def test_wiki_file_bug_files_clean_when_no_dups(wiki_env):
    res = json.loads(
        wiki(
            action="file_bug",
            component="universe.inspect",
            severity="minor",
            title="A unique never-seen title aardvark zeppelin",
            observed="aardvark",
            expected="zeppelin",
            force_new=True,
        )
    )
    assert res["status"] == "filed"
    assert res["bug_id"].startswith("BUG-")


def test_wiki_file_bug_title_only_path_still_succeeds(wiki_env):
    res = json.loads(
        wiki(
            action="file_bug",
            component="api.wiki",
            severity="minor",
            title="Title only filing still works",
            force_new=True,
        )
    )

    assert res["status"] == "filed"
    assert res["bug_id"].startswith("BUG-")


def test_wiki_file_bug_rejects_unsupported_body_field(wiki_env):
    res = json.loads(
        wiki(
            action="file_bug",
            component="api.wiki",
            severity="major",
            title="Content body should not be discarded",
            content="This body would be lost if file_bug silently accepted it.",
        )
    )

    assert "error" in res
    assert "content" in res["error"]
    assert "repro, observed, expected, workaround" in res["error"]
    assert "title=..., component=..., severity=..." in res["hint"]
    assert not list((wiki_env / "pages" / "bugs").glob("bug-*.md"))


def test_wiki_file_bug_rejects_unknown_direct_kwarg(wiki_env):
    res = json.loads(
        _wiki_file_bug(
            component="api.wiki",
            severity="major",
            title="Unknown direct kwarg should not be discarded",
            body="This field is not part of the file_bug contract.",
        )
    )

    assert "error" in res
    assert "body" in res["error"]
    assert "content/body are not supported here" in res["error"]
    assert set(_UNSUPPORTED_FILE_BUG_BODY_KWARGS) == {"body", "content"}
    assert not list((wiki_env / "pages" / "bugs").glob("bug-*.md"))


def test_wiki_file_bug_queued_investigation_returns_branch_task_lease_shape(
    wiki_env, tmp_path, monkeypatch,
):
    universe_dir = tmp_path / "default-universe"
    universe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "default-universe")
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID",
        "bug-investigation-branch",
    )
    monkeypatch.delenv("WORKFLOW_REQUEST_TYPE_PRIORITIES", raising=False)

    res = json.loads(
        wiki(
            action="file_bug",
            component="loop",
            severity="major",
            title="Lease metadata response shape",
            observed="queued task lacks visible lease metadata",
            force_new=True,
            verbose=True,
        )
    )

    task = res["investigation"]["branch_task"]
    assert task["branch_task_id"] == res["investigation"]["dispatcher_request_id"]
    assert task["status"] == "pending"
    assert task["worker_owner_id"] == ""
    assert task["lease_expires_at"] == ""
    assert task["heartbeat_at"] == ""
    assert task["last_progress_at"] == ""


def test_wiki_file_bug_dedup_returns_similar_found(wiki_env):
    base = dict(
        action="file_bug",
        component="universe.inspect",
        severity="minor",
        title="Connector returns wrong universe id on inspect",
        observed="inspect returned the wrong universe id under load",
    )
    json.loads(wiki(**base, force_new=True))
    dup = json.loads(wiki(**base))  # no force_new — should dedup
    assert dup["status"] == "similar_found"
    assert dup["bug_id"] is None
    assert isinstance(dup["similar"], list)
    assert len(dup["similar"]) >= 1
    assert dup["effort_dispatch_route"]["lane"] == "standard-triage"


def test_wiki_cosign_bug_requires_args(wiki_env):
    res = json.loads(wiki(action="cosign_bug"))
    assert "error" in res
    res = json.loads(wiki(action="cosign_bug", bug_id="BUG-001"))
    assert "error" in res


def test_wiki_cosign_bug_unknown_id_errors(wiki_env):
    res = json.loads(
        wiki(
            action="cosign_bug",
            bug_id="BUG-999",
            reporter_context="me too on the dev box",
        )
    )
    assert "error" in res


def test_wiki_cosign_bug_appends_to_existing_filing(wiki_env):
    filed = json.loads(
        wiki(
            action="file_bug",
            component="x",
            severity="minor",
            title="The cosign smoke test bug uniquely worded",
            observed="something broke uniquely",
            force_new=True,
        )
    )
    bug_id = filed["bug_id"]
    res = json.loads(
        wiki(
            action="cosign_bug",
            bug_id=bug_id,
            reporter_context="seen on the staging tunnel as well",
        )
    )
    assert res["status"] == "cosigned"
    assert res["cosign_count"] == 1

    # Second cosign increments the count.
    res2 = json.loads(
        wiki(
            action="cosign_bug",
            bug_id=bug_id,
            reporter_context="and on local dev",
        )
    )
    assert res2["cosign_count"] == 2

    # Body now contains both contexts.
    bugs_dir = wiki_env / "pages" / "bugs"
    files = list(bugs_dir.glob(f"{bug_id.lower()}-*.md"))
    assert files, f"expected the bug file in {bugs_dir}"
    body = files[0].read_text(encoding="utf-8")
    assert "## Cosigns" in body
    assert "staging tunnel" in body
    assert "local dev" in body
    _ = filed  # path tracked via bug_id glob above

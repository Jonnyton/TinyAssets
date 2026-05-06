"""Tests for wiki tools in universe_server.py."""

from __future__ import annotations

import asyncio
import json

import pytest

from workflow.api.wiki import (
    _extract_keywords,
    _parse_frontmatter,
    _sanitize_slug,
    _wiki_similarity_score,
)
from workflow.universe_server import (
    mcp,
    wiki,
)

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        content = "---\ntitle: Test Page\ntype: concept\n---\nBody text."
        meta, body = _parse_frontmatter(content)
        assert meta["title"] == "Test Page"
        assert meta["type"] == "concept"
        assert body == "Body text."

    def test_no_frontmatter(self):
        content = "Just a plain body."
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == "Just a plain body."

    def test_empty_frontmatter(self):
        content = "---\n\n---\nBody."
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == "Body."


class TestSanitizeSlug:
    def test_basic_slug(self):
        assert _sanitize_slug("My Page.md") == "my-page"

    def test_special_chars(self):
        assert _sanitize_slug("Hello World! (v2)") == "hello-world---v2"

    def test_already_clean(self):
        assert _sanitize_slug("clean-slug") == "clean-slug"


class TestExtractKeywords:
    def test_removes_stop_words(self):
        kw = _extract_keywords("the quick brown fox is very fast")
        assert "the" not in kw
        assert "very" not in kw
        assert "quick" in kw
        assert "brown" in kw
        assert "fox" in kw
        assert "fast" in kw

    def test_removes_short_words(self):
        kw = _extract_keywords("an ox is by me")
        assert len(kw) == 0

    def test_deduplicates(self):
        kw = _extract_keywords("hello hello hello world")
        assert kw == {"hello", "world"}


class TestSimilarityScore:
    def test_identical_content(self):
        body = "This page discusses [[workflow-engine]] and multi-agent patterns."
        meta = {"title": "Test Page"}
        score = _wiki_similarity_score(meta, body, meta, body)
        assert score > 0.5

    def test_different_content(self):
        body_a = "Quantum physics explores wave particle duality."
        body_b = "Baking bread requires flour yeast water salt."
        score = _wiki_similarity_score({}, body_a, {}, body_b)
        assert score < 0.15

    def test_title_bonus(self):
        body = "Some content about patterns."
        meta_a = {"title": "Multi-Agent Patterns"}
        meta_b = {"title": "Multi-Agent"}
        score = _wiki_similarity_score(meta_a, body, meta_b, body)
        # Should get the 0.3 title bonus
        assert score > 0.5


# ---------------------------------------------------------------------------
# Integration tests using a temporary wiki directory
# ---------------------------------------------------------------------------


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    """Create a temporary wiki directory structure."""
    wiki_root = tmp_path / "Wiki"
    wiki_root.mkdir()

    for sub in ["projects", "concepts", "people", "research"]:
        (wiki_root / "pages" / sub).mkdir(parents=True)
        (wiki_root / "drafts" / sub).mkdir(parents=True)
    (wiki_root / "raw").mkdir()

    # Create index
    index_content = (
        "---\ntitle: Index\ntype: index\nupdated: 2026-04-11\n---\n\n"
        "# Wiki Index\n\n"
        "## Projects\n\n"
        "- [[test-project]] -- Test project\n\n"
        "## Concepts\n\n"
        "## People\n\n"
        "## Research\n\n"
    )
    (wiki_root / "index.md").write_text(index_content, encoding="utf-8")

    # Create log
    (wiki_root / "log.md").write_text("# Wiki Log\n", encoding="utf-8")

    # Create WIKI.md schema
    (wiki_root / "WIKI.md").write_text("# Wiki Schema\n", encoding="utf-8")

    # Create a sample promoted page
    page_content = (
        "---\ntitle: Test Project\ntype: project\n"
        "created: 2026-04-01\nupdated: 2026-04-11\n"
        "sources: []\ntags: [python]\npath: /test\n"
        "confidence: high\n---\n\n"
        "# Test Project\n\nA test project for unit tests.\n\n"
        "## See Also\n\n- [[workflow-engine]]\n"
    )
    (wiki_root / "pages" / "projects" / "test-project.md").write_text(
        page_content, encoding="utf-8"
    )

    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    return wiki_root


class TestWikiRead:
    def test_read_page(self, wiki_dir):
        result = json.loads(wiki("read", page="test-project"))
        assert result["is_draft"] is False
        assert "Test Project" in result["content"]
        assert result["truncated"] is False

    def test_read_special_index(self, wiki_dir):
        result = json.loads(wiki("read", page="index"))
        assert "Wiki Index" in result["content"]

    def test_read_special_schema(self, wiki_dir):
        result = json.loads(wiki("read", page="schema"))
        assert "Wiki Schema" in result["content"]

    def test_read_not_found(self, wiki_dir):
        result = json.loads(wiki("read", page="nonexistent"))
        assert "error" in result

    def test_read_missing_page_param(self, wiki_dir):
        result = json.loads(wiki("read"))
        assert "error" in result

    def test_read_draft_does_not_duplicate_existing_draft_marker(self, wiki_dir):
        content = "[DRAFT] # Pending Concept\n\nDraft body.\n"
        (wiki_dir / "drafts" / "concepts" / "pending-concept.md").write_text(
            content, encoding="utf-8"
        )

        result = json.loads(wiki("read", page="pending-concept"))

        assert result["is_draft"] is True
        assert result["content"].startswith("[DRAFT] # Pending Concept")
        assert not result["content"].startswith("[DRAFT] [DRAFT]")


class TestWikiList:
    def test_list_pages(self, wiki_dir):
        result = json.loads(wiki("list"))
        assert result["promoted_count"] >= 1
        titles = [p["title"] for p in result["promoted"]]
        assert "Test Project" in titles

    def test_list_includes_drafts(self, wiki_dir):
        # Write a draft first
        wiki(
            "write",
            category="concepts",
            filename="new-concept",
            content="---\ntitle: New Concept\ntype: concept\n---\nContent.",
        )
        result = json.loads(wiki("list"))
        assert result["drafts_count"] >= 1


class TestWikiSearch:
    def test_search_finds_page(self, wiki_dir):
        result = json.loads(wiki("search", query="test project"))
        assert result["count"] >= 1
        assert any("Test Project" in r["title"] for r in result["results"])

    def test_search_no_results(self, wiki_dir):
        result = json.loads(wiki("search", query="zzzyyyxxx"))
        assert result.get("count", 0) == 0 or len(result.get("results", [])) == 0

    def test_search_missing_query(self, wiki_dir):
        result = json.loads(wiki("search"))
        assert "error" in result


class TestWikiWrite:
    def test_write_new_draft(self, wiki_dir):
        content = (
            "---\ntitle: New Concept\ntype: concept\n"
            "sources: [test]\n---\n\nSome content about [[test-project]].\n"
        )
        result = json.loads(
            wiki("write", category="concepts", filename="new-concept", content=content)
        )
        assert result["status"] == "drafted"
        assert (wiki_dir / "drafts" / "concepts" / "new-concept.md").exists()

    def test_write_updates_existing_promoted(self, wiki_dir):
        new_content = (
            "---\ntitle: Test Project\ntype: project\n"
            "updated: 2026-04-11\nsources: []\ntags: [python]\n---\n\n"
            "Updated content.\n"
        )
        result = json.loads(
            wiki(
                "write",
                category="projects",
                filename="test-project",
                content=new_content,
            )
        )
        assert result["status"] == "updated"
        actual = (wiki_dir / "pages" / "projects" / "test-project.md").read_text(
            encoding="utf-8"
        )
        assert "Updated content." in actual

    def test_write_invalid_category(self, wiki_dir):
        result = json.loads(
            wiki("write", category="invalid", filename="test", content="test")
        )
        assert "error" in result

    def test_write_missing_params(self, wiki_dir):
        result = json.loads(wiki("write"))
        assert "error" in result

    @pytest.mark.parametrize("category", [
        # Original four.
        "projects", "concepts", "people", "research",
        # 2026-04-13 expansion — stop user-intent content landing in
        # research/ by default. Mirrors wiki-mcp/server.js.
        "recipes", "workflows", "notes", "references", "plans",
    ])
    def test_write_accepts_all_expanded_categories(self, wiki_dir, category):
        """Regression gate for #55: every documented category is
        actually accepted by the write handler."""
        body = (
            "---\ntitle: Test\ntype: note\nsources: []\n---\n\nBody.\n"
        )
        result = json.loads(
            wiki(
                "write",
                category=category,
                filename=f"test-{category}",
                content=body,
            )
        )
        assert result.get("status") in {"drafted", "updated"}, result

    def test_wiki_categories_enum_matches_expanded_taxonomy(self):
        """Lock-in: the module constant carries all ten categories in
        the canonical order."""
        from workflow.api.wiki import _WIKI_CATEGORIES

        assert _WIKI_CATEGORIES == (
            "projects", "concepts", "people", "research",
            "recipes", "workflows", "notes", "references", "plans",
            "bugs",
        )


class TestWikiPromote:
    def test_promote_valid_draft(self, wiki_dir):
        # Write a draft with valid frontmatter and wikilinks
        content = (
            "---\ntitle: Promotable\ntype: concept\n"
            "created: 2026-04-11\nupdated: 2026-04-11\n"
            "sources: [test-source]\n---\n\n"
            "This is a well-formed concept page about [[test-project]] "
            "with enough content to pass the minimum length check.\n"
        )
        wiki("write", category="concepts", filename="promotable", content=content)
        assert (wiki_dir / "drafts" / "concepts" / "promotable.md").exists()

        result = json.loads(wiki("promote", filename="promotable"))
        assert result["status"] == "promoted"
        assert (wiki_dir / "pages" / "concepts" / "promotable.md").exists()
        assert not (wiki_dir / "drafts" / "concepts" / "promotable.md").exists()

    def test_promote_first_page_can_link_to_seed_index(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "FreshWiki"
        monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
        content = (
            "---\ntitle: First Concept\ntype: concept\n"
            "created: 2026-05-05\nupdated: 2026-05-05\n"
            "sources: [first-note]\n---\n\n"
            "This is the first promoted concept in a fresh wiki, so it links "
            "back to the canonical seed [[index]] until another page exists.\n"
        )
        wiki("write", category="concepts", filename="first-concept", content=content)

        result = json.loads(wiki("promote", filename="first-concept"))

        assert result["status"] == "promoted"
        assert (wiki_root / "pages" / "concepts" / "first-concept.md").exists()

    def test_promote_blocks_without_title(self, wiki_dir):
        content = "---\ntype: concept\n---\nShort."
        wiki("write", category="concepts", filename="bad-draft", content=content)
        result = json.loads(wiki("promote", filename="bad-draft"))
        assert "error" in result
        assert any("title" in i.lower() for i in result.get("issues", []))

    def test_promote_skip_lint(self, wiki_dir):
        content = "No frontmatter at all."
        wiki("write", category="concepts", filename="raw-draft", content=content)
        result = json.loads(
            wiki("promote", filename="raw-draft", category="concepts", skip_lint=True)
        )
        assert result["status"] == "promoted"

    def test_promote_not_found(self, wiki_dir):
        result = json.loads(wiki("promote", filename="nonexistent"))
        assert "error" in result


class TestWikiIngest:
    def test_ingest_raw_source(self, wiki_dir):
        result = json.loads(
            wiki(
                "ingest",
                filename="paper.pdf",
                content="Raw paper content.",
                source_url="https://example.com/paper",
            )
        )
        assert result["status"] == "saved"
        assert (wiki_dir / "raw" / "paper.pdf").exists()

    def test_ingest_missing_params(self, wiki_dir):
        result = json.loads(wiki("ingest"))
        assert "error" in result


class TestWikiConsolidate:
    def test_consolidate_similar_drafts(self, wiki_dir):
        content_a = (
            "---\ntitle: Agent Patterns\ntype: concept\n---\n\n"
            "Multi-agent coordination patterns for [[workflow-engine]].\n"
        )
        content_b = (
            "---\ntitle: Agent Patterns Guide\ntype: concept\n---\n\n"
            "Agent coordination patterns for [[workflow-engine]] systems.\n"
        )
        wiki("write", category="concepts", filename="agent-patterns", content=content_a)
        wiki(
            "write",
            category="concepts",
            filename="agent-patterns-guide",
            content=content_b,
        )

        result = json.loads(wiki("consolidate", dry_run=True))
        assert result.get("clusters", 0) >= 1

    def test_consolidate_few_drafts(self, wiki_dir):
        result = json.loads(wiki("consolidate"))
        assert "note" in result

    def test_consolidate_execute(self, wiki_dir):
        content_a = (
            "---\ntitle: Same Topic\ntype: concept\n---\n\n"
            "Long content about multi-agent patterns and coordination for "
            "[[workflow-engine]] with detailed discussion of the workflow.\n"
        )
        content_b = (
            "---\ntitle: Same Topic Extra\ntype: concept\n---\n\n"
            "Multi-agent patterns and coordination for [[workflow-engine]] "
            "workflow systems discussion.\n"
        )
        wiki("write", category="concepts", filename="same-topic", content=content_a)
        wiki(
            "write",
            category="concepts",
            filename="same-topic-extra",
            content=content_b,
        )

        result = json.loads(wiki("consolidate", dry_run=False, similarity_threshold=0.1))
        if result.get("clusters", 0) > 0:
            assert result["mode"] == "executed"


class TestWikiLint:
    def test_lint_finds_issues(self, wiki_dir):
        result = json.loads(wiki("lint"))
        # Should find issues (missing wikilink targets, etc.)
        assert isinstance(result.get("issues", []), list)

    def test_lint_detects_orphan(self, wiki_dir):
        # Create an orphan page (not linked from anywhere, not in index)
        content = (
            "---\ntitle: Orphan\ntype: concept\n"
            "confidence: high\nsources: [test]\n---\n\n"
            "An orphan page nobody links to.\n"
        )
        (wiki_dir / "pages" / "concepts" / "orphan-page.md").write_text(
            content, encoding="utf-8"
        )
        result = json.loads(wiki("lint"))
        issues = result.get("issues", [])
        assert any("ORPHAN" in i and "orphan-page" in i for i in issues)

    def test_lint_single_page_excludes_whole_wiki_backlog(self, wiki_dir):
        clean_content = (
            "---\ntitle: Clean Page\ntype: concept\n"
            "confidence: medium\nsources: [test]\n---\n\n"
            "A clean page that links to [[test-project]] and has enough body "
            "content for page-specific linting.\n"
        )
        (wiki_dir / "pages" / "concepts" / "clean-page.md").write_text(
            clean_content, encoding="utf-8"
        )
        (wiki_dir / "index.md").write_text(
            (wiki_dir / "index.md").read_text(encoding="utf-8")
            + "- [[clean-page]] -- Clean Page\n",
            encoding="utf-8",
        )
        (wiki_dir / "pages" / "concepts" / "orphan-page.md").write_text(
            "---\ntitle: Orphan\ntype: concept\nconfidence: high\n"
            "sources: [test]\n---\n\nUnrelated orphan backlog.\n",
            encoding="utf-8",
        )
        wiki(
            "write",
            category="concepts",
            filename="pending-draft",
            content="---\ntitle: Pending Draft\ntype: concept\n---\n\nDraft backlog.",
        )

        result = json.loads(wiki("lint", page="clean-page"))

        assert result["status"] == "healthy"
        assert result["issues"] == []

    def test_lint_single_draft_reports_promotion_blockers_only(self, wiki_dir):
        wiki(
            "write",
            category="notes",
            filename="skinny",
            content="---\ntitle: Skinny\n---\ntoo short\n",
        )
        (wiki_dir / "pages" / "concepts" / "orphan-page.md").write_text(
            "---\ntitle: Orphan\ntype: concept\nconfidence: high\n"
            "sources: [test]\n---\n\nUnrelated orphan backlog.\n",
            encoding="utf-8",
        )

        result = json.loads(wiki("lint", page="skinny"))
        issues = result.get("issues", [])

        assert result["status"] == "issues_found"
        assert any("Missing type" in issue for issue in issues)
        assert any("Body too short" in issue for issue in issues)
        assert not any("orphan-page" in issue for issue in issues)

    def test_lint_accepts_seed_index_as_wikilink_target(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "FreshWiki"
        monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
        content = (
            "---\ntitle: First Concept\ntype: concept\n"
            "confidence: medium\nsources: [first-note]\n---\n\n"
            "This first page links to the canonical seed [[index]] while the "
            "fresh wiki has no other promoted content to cross-reference.\n"
        )
        wiki("write", category="concepts", filename="first-concept", content=content)
        wiki("promote", filename="first-concept")

        result = json.loads(wiki("lint", page="first-concept"))

        assert "MISSING: [[index]]" not in result.get("issues", [])


class TestWikiSupersede:
    def test_supersede_page(self, wiki_dir):
        # Create a replacement draft
        new_content = (
            "---\ntitle: Test Project V2\ntype: project\n"
            "sources: [test]\n---\n\n"
            "Updated version of [[test-project]].\n"
        )
        wiki(
            "write",
            category="projects",
            filename="test-project-v2",
            content=new_content,
        )

        result = json.loads(
            wiki(
                "supersede",
                old_page="test-project",
                new_draft="test-project-v2",
                reason="Major update to project architecture.",
            )
        )
        assert result["status"] == "superseded"

        # Verify old page was updated
        old_content = (
            wiki_dir / "pages" / "projects" / "test-project.md"
        ).read_text(encoding="utf-8")
        assert "superseded" in old_content
        assert "test-project-v2" in old_content

    def test_supersede_missing_old(self, wiki_dir):
        result = json.loads(
            wiki(
                "supersede",
                old_page="nonexistent",
                new_draft="test",
                reason="test",
            )
        )
        assert "error" in result

    def test_supersede_missing_new(self, wiki_dir):
        result = json.loads(
            wiki(
                "supersede",
                old_page="test-project",
                new_draft="nonexistent",
                reason="test",
            )
        )
        assert "error" in result


class TestWikiSyncProjects:
    def test_sync_discovers_new_project(self, wiki_dir):
        # Create a fake project folder alongside the wiki
        projects_root = wiki_dir.parent
        new_proj = projects_root / "NewProject"
        new_proj.mkdir()
        (new_proj / "README.md").write_text(
            "# New Project\n\nThis is a brand new project for testing.\n",
            encoding="utf-8",
        )
        (new_proj / "pyproject.toml").write_text("[project]\nname='test'\n")

        result = json.loads(wiki("sync_projects"))
        assert result["synced"] >= 1
        assert any("newproject" in c for c in result["created"])

    def test_sync_skips_existing(self, wiki_dir):
        # First sync should say all projects exist (only test-project + wiki)
        result = json.loads(wiki("sync_projects"))
        # May sync some or none depending on what's in parent dir
        assert "synced" in result or "note" in result


class TestWikiDispatch:
    def test_unknown_action(self, wiki_dir):
        result = json.loads(wiki("nonexistent_action"))
        assert "error" in result
        assert "available_actions" in result

    def test_wiki_missing_root_auto_scaffolds(self, monkeypatch, tmp_path):
        """Post-Task-#6: a nonexistent wiki root auto-scaffolds on first
        call and returns the empty-wiki list rather than an error.

        Pre-#6 contract was ``{"error": "Wiki not found at ..."}``. The
        droplet-seeding task flipped this so fresh deploys (empty
        ``/data/wiki``) don't face a broken read path — the scaffold
        writes pages/, drafts/, raw/, log/, plus anchor ``index.md`` /
        ``WIKI.md`` / ``log.md`` files.
        """
        root = tmp_path / "nonexistent"
        assert not root.exists()
        monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(root))
        result = json.loads(wiki("list"))
        assert "error" not in result, (
            f"wiki list errored instead of auto-scaffolding: {result!r}"
        )
        # The new contract: list returns page-collection keys; for a
        # freshly-scaffolded empty wiki both are empty lists.
        assert result.get("promoted") == []
        assert result.get("drafts") == []
        assert result.get("promoted_count") == 0
        assert result.get("drafts_count") == 0
        # Scaffold landed on disk.
        assert root.is_dir()
        assert (root / "pages").is_dir()
        assert (root / "drafts").is_dir()
        assert (root / "index.md").is_file()
        assert (root / "WIKI.md").is_file()
        assert (root / "log.md").is_file()


class TestWikiFileBugDispatch:
    """Dispatch-level tests for wiki(action='file_bug', ...).

    Exercises the wiki() router path — not the helper directly — so that
    the dispatch table wiring is independently verified.
    """

    def test_missing_title_returns_error(self, wiki_dir):
        out = json.loads(
            wiki("file_bug", component="extensions.core", severity="major", title="")
        )
        assert "error" in out

    def test_missing_component_returns_error(self, wiki_dir):
        out = json.loads(
            wiki("file_bug", component="", severity="major", title="Some bug")
        )
        assert "error" in out

    def test_invalid_severity_returns_error(self, wiki_dir):
        out = json.loads(
            wiki("file_bug", component="extensions.core", severity="critical-ish", title="t")
        )
        assert "error" in out

    def test_valid_call_returns_bug_id_and_path(self, wiki_dir):
        (wiki_dir / "pages" / "bugs").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "drafts" / "bugs").mkdir(parents=True, exist_ok=True)
        out = json.loads(
            wiki(
                "file_bug",
                component="extensions.patch_branch",
                severity="major",
                title="Widget explodes on save",
                repro="Click save",
                observed="500 error",
                expected="200 ok",
            )
        )
        assert out["status"] == "filed"
        assert "bug_id" in out
        assert out["bug_id"].startswith("BUG-")
        assert "path" in out

    def test_file_bug_accepts_tags_via_public_wrapper(self, wiki_dir):
        """BUG-040: public wiki wrapper must pass tags through to file_bug."""
        (wiki_dir / "pages" / "bugs").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "drafts" / "bugs").mkdir(parents=True, exist_ok=True)

        out = json.loads(
            wiki(
                "file_bug",
                component="wiki-mcp",
                severity="minor",
                title="Tagged schema regression",
                tags="schema, regression",
                force_new=True,
            )
        )

        assert out["status"] == "filed"
        body = (wiki_dir / out["path"]).read_text(encoding="utf-8")
        tags_line = [ln for ln in body.split("\n") if ln.startswith("tags:")][0]
        assert "schema" in tags_line
        assert "regression" in tags_line

    def test_id_collision_retry_via_dispatch(self, wiki_dir):
        """Collision retry is end-to-end via the wiki() router."""
        from pathlib import Path
        from unittest.mock import patch

        (wiki_dir / "pages" / "bugs").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "drafts" / "bugs").mkdir(parents=True, exist_ok=True)

        real_open = open
        first_call = {"fired": False}

        def fake_open(path, mode="r", *args, **kwargs):
            p = Path(path) if not isinstance(path, Path) else path
            if mode == "x" and "bug-001" in p.name and not first_call["fired"]:
                first_call["fired"] = True
                real_open(path, "w", *args, **kwargs).close()
                raise FileExistsError(path)
            return real_open(path, mode, *args, **kwargs)

        with patch("workflow.api.wiki.open", side_effect=fake_open, create=True):
            out = json.loads(
                wiki(
                    "file_bug",
                    component="x",
                    severity="minor",
                    title="collision test",
                )
            )
        assert out["status"] == "filed"
        assert out["bug_id"] == "BUG-002"


class TestWikiMCPRegistration:
    def test_wiki_tool_registered(self):
        tools = asyncio.run(mcp.list_tools(run_middleware=False))
        tool_names = {t.name for t in tools}
        assert "wiki" in tool_names

    def test_wiki_tool_metadata(self):
        tools = asyncio.run(mcp.list_tools(run_middleware=False))
        wiki_tool = next(t for t in tools if t.name == "wiki")
        assert wiki_tool.title == "Wiki Knowledge Base"
        assert {"wiki", "knowledge"} <= wiki_tool.tags
        assert wiki_tool.annotations.readOnlyHint is False
        assert wiki_tool.annotations.openWorldHint is True

    def test_wiki_tool_schema_advertises_file_bug_tags_field(self):
        """BUG-040: MCP clients must not reject backend-supported tags."""
        tools = asyncio.run(mcp.list_tools(run_middleware=False))
        wiki_tool = next(t for t in tools if t.name == "wiki")
        properties = wiki_tool.parameters["properties"]

        assert properties["tags"]["type"] == "string"
        assert properties["tags"]["default"] == ""

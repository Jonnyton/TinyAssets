"""Tests for `_resolve_filed_page_canonical` + `_wiki_write` alias resolution corner cases.

`_resolve_filed_page_canonical(parent, slug, *, category=...)` is the
generalized successor of the historical bugs-only `_resolve_bugs_canonical`
helper (renamed + parametrized by category in #1280). For the ``bugs``
category it preserves the same corner-case contract exercised below.

Covers Wiki #32 corner-case fixes:

- **BUG-003** — lowercase duplicate at `bugs/bug-003-...md` exists alongside
  uppercase canonical `bugs/BUG-003-...md`. Write must prefer the canonical.
- **BUG-018** — canonical filename has a trailing hyphen (`bugs/bug-018-foo-.md`).
  Slug sanitizer strips the trailing hyphen, so a naive `<slug>.md` lookup
  misses the canonical and writes to drafts. Alias resolution must match the
  trailing-hyphen variant.
- **BUG-028** (regression) — wrong-case canonical resolves correctly when
  no lowercase duplicate exists. Pre-existing behavior preserved.

All tests pass when the alias-resolution block in `_wiki_write` runs BEFORE
the `.exists()` check (the BUG-003 fix shape).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow.api.wiki import (
    _resolve_filed_page_canonical,
    _wiki_write,
)


def _fs_case_sensitive(tmp_path: Path) -> bool:
    """Probe whether the filesystem under tmp_path is case-sensitive.

    Windows NTFS is case-insensitive, so duplicate-case scenarios (BUG-003 /
    BUG-018-with-uppercase variants) collapse into one file at write time.
    Tests that depend on case-sensitive coexistence skip on this platform.
    """
    probe = tmp_path / "_case_probe.tmp"
    probe.write_text("x", encoding="utf-8")
    upper = tmp_path / "_CASE_PROBE.TMP"
    sensitive = not upper.exists()
    probe.unlink(missing_ok=True)
    return sensitive


_skip_case_insensitive = pytest.mark.skipif(
    not _fs_case_sensitive(Path.cwd()),
    reason="Filesystem is case-insensitive; case-coexistence scenarios collapse.",
)


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    """Temporary wiki tree with a `bugs` category pre-created."""
    wiki_root = tmp_path / "Wiki"
    (wiki_root / "pages" / "bugs").mkdir(parents=True)
    (wiki_root / "drafts" / "bugs").mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    return wiki_root


# ── _resolve_filed_page_canonical unit tests (bugs category) ──────────────────


class TestResolveBugsCanonical:
    def test_returns_none_when_no_match(self, wiki_dir):
        parent = wiki_dir / "pages" / "bugs"
        assert _resolve_filed_page_canonical(parent, "bug-001-nope", category="bugs") is None

    def test_returns_none_for_missing_parent(self, tmp_path):
        # _resolve_filed_page_canonical iterates parent.glob; missing dir → empty
        # list → None. Tested here so callers can rely on the contract.
        missing = tmp_path / "does" / "not" / "exist"
        assert _resolve_filed_page_canonical(missing, "bug-001-x", category="bugs") is None

    def test_exact_match_returns_path(self, wiki_dir):
        parent = wiki_dir / "pages" / "bugs"
        target = parent / "bug-001-example.md"
        target.write_text("x", encoding="utf-8")
        result = _resolve_filed_page_canonical(parent, "bug-001-example", category="bugs")
        assert result == target

    def test_wrong_case_canonical_resolved(self, wiki_dir):
        """BUG-028 baseline: uppercase canonical found from lowercase slug."""
        parent = wiki_dir / "pages" / "bugs"
        canonical = parent / "BUG-007-foo-bar.md"
        canonical.write_text("x", encoding="utf-8")
        result = _resolve_filed_page_canonical(parent, "bug-007-foo-bar", category="bugs")
        assert result == canonical

    @_skip_case_insensitive
    def test_uppercase_preferred_over_lowercase_duplicate(self, wiki_dir):
        """BUG-003 fix: uppercase canonical wins when both case variants exist."""
        parent = wiki_dir / "pages" / "bugs"
        canonical = parent / "BUG-003-example.md"
        duplicate = parent / "bug-003-example.md"
        canonical.write_text("canonical", encoding="utf-8")
        duplicate.write_text("dup", encoding="utf-8")
        result = _resolve_filed_page_canonical(parent, "bug-003-example", category="bugs")
        assert result == canonical, (
            "When a lowercase duplicate and an uppercase canonical coexist, "
            "BUG-003 fix requires the uppercase canonical to be preferred."
        )

    def test_trailing_hyphen_canonical_resolved(self, wiki_dir):
        """BUG-018 fix: trailing-hyphen canonical matched when slug strips trailing hyphen."""
        parent = wiki_dir / "pages" / "bugs"
        canonical = parent / "bug-018-foo-.md"
        canonical.write_text("x", encoding="utf-8")
        # Slug sanitization strips trailing hyphens; so the slug entering
        # alias-resolution is "bug-018-foo" not "bug-018-foo-".
        result = _resolve_filed_page_canonical(parent, "bug-018-foo", category="bugs")
        assert result == canonical

    @_skip_case_insensitive
    def test_uppercase_trailing_hyphen_preferred(self, wiki_dir):
        """When both BUG-018 trailing-hyphen and bug-018 (no hyphen) exist, uppercase wins."""
        parent = wiki_dir / "pages" / "bugs"
        upper_dash = parent / "BUG-018-foo-.md"
        lower_no_dash = parent / "bug-018-foo.md"
        upper_dash.write_text("upper", encoding="utf-8")
        lower_no_dash.write_text("lower", encoding="utf-8")
        result = _resolve_filed_page_canonical(parent, "bug-018-foo", category="bugs")
        assert result == upper_dash

    def test_exact_slug_preferred_over_trailing_hyphen(self, wiki_dir):
        """When both bug-018-foo.md and bug-018-foo-.md exist (same case), exact wins."""
        parent = wiki_dir / "pages" / "bugs"
        exact = parent / "bug-018-foo.md"
        with_dash = parent / "bug-018-foo-.md"
        exact.write_text("exact", encoding="utf-8")
        with_dash.write_text("dash", encoding="utf-8")
        result = _resolve_filed_page_canonical(parent, "bug-018-foo", category="bugs")
        assert result == exact


# ── _wiki_write integration tests ──────────────────────────────────────────────


class TestWikiWriteAliasResolution:
    @_skip_case_insensitive
    def test_write_routes_to_uppercase_canonical_over_lowercase_duplicate(self, wiki_dir):
        """BUG-003 end-to-end: write to lowercase slug must update uppercase canonical."""
        bugs = wiki_dir / "pages" / "bugs"
        canonical = bugs / "BUG-003-example.md"
        duplicate = bugs / "bug-003-example.md"
        canonical.write_text("OLD CANONICAL", encoding="utf-8")
        duplicate.write_text("OLD DUPLICATE", encoding="utf-8")

        result = _wiki_write(
            category="bugs",
            filename="bug-003-example.md",
            content="NEW CONTENT",
        )

        parsed = json.loads(result)
        assert parsed.get("status") == "updated", parsed
        # Canonical must have been written; duplicate left alone.
        assert canonical.read_text(encoding="utf-8") == "NEW CONTENT"
        assert duplicate.read_text(encoding="utf-8") == "OLD DUPLICATE"

    def test_write_routes_to_trailing_hyphen_canonical(self, wiki_dir):
        """BUG-018 end-to-end: write to slug-sans-hyphen must update trailing-hyphen canonical."""
        bugs = wiki_dir / "pages" / "bugs"
        canonical = bugs / "bug-018-foo-.md"
        canonical.write_text("OLD", encoding="utf-8")

        result = _wiki_write(
            category="bugs",
            filename="bug-018-foo.md",
            content="NEW",
        )

        parsed = json.loads(result)
        assert parsed.get("status") == "updated", parsed
        assert canonical.read_text(encoding="utf-8") == "NEW"
        # No new draft created.
        drafts_bugs = wiki_dir / "drafts" / "bugs"
        if drafts_bugs.exists():
            assert not list(drafts_bugs.glob("bug-018-foo*.md")), (
                "BUG-018 fix: trailing-hyphen canonical must absorb the write; "
                "drafts/ should not gain a new sibling."
            )

    def test_write_unchanged_when_no_alias_collision(self, wiki_dir):
        """Regression: simple direct match still works."""
        bugs = wiki_dir / "pages" / "bugs"
        canonical = bugs / "bug-099-direct.md"
        canonical.write_text("OLD", encoding="utf-8")

        result = _wiki_write(
            category="bugs",
            filename="bug-099-direct.md",
            content="NEW",
        )

        parsed = json.loads(result)
        assert parsed.get("status") == "updated", parsed
        assert canonical.read_text(encoding="utf-8") == "NEW"

    def test_wrong_case_canonical_still_resolved(self, wiki_dir):
        """BUG-028 regression check: wrong-case canonical resolution preserved."""
        bugs = wiki_dir / "pages" / "bugs"
        canonical = bugs / "BUG-007-mixed.md"
        canonical.write_text("OLD", encoding="utf-8")

        result = _wiki_write(
            category="bugs",
            filename="bug-007-mixed.md",
            content="NEW",
        )

        parsed = json.loads(result)
        assert parsed.get("status") == "updated", parsed
        assert canonical.read_text(encoding="utf-8") == "NEW"

    def test_write_falls_through_to_drafts_when_no_canonical(self, wiki_dir):
        """When no canonical exists at any case/hyphen variant, write goes to drafts."""
        bugs = wiki_dir / "pages" / "bugs"
        assert not list(bugs.glob("*.md"))  # empty

        result = _wiki_write(
            category="bugs",
            filename="bug-500-novel.md",
            content="DRAFT",
        )

        parsed = json.loads(result)
        assert parsed.get("status") == "drafted", parsed
        assert (wiki_dir / "drafts" / "bugs" / "bug-500-novel.md").read_text(
            encoding="utf-8"
        ) == "DRAFT"

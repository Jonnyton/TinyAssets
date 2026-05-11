"""Task #21 — file_bug dedup-at-filing: similarity check + cosign_bug verb.

Before the fix, every call to `wiki action=file_bug` minted a fresh BUG-NNN
even when an identical or near-identical bug already existed. At scale this
floods the bugs directory with duplicates.

Fix: server-side Jaccard similarity check (threshold 0.5) against existing
bugs before allocating a new id. When a similar bug exists, return
`status: "similar_found"` with the top-3 matches. The caller can then use
`wiki action=cosign_bug` to add context without creating a duplicate.
`force_new=true` overrides the check and always mints a new id.
"""

from __future__ import annotations

import json

import pytest

# ── shared fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def wiki_env(tmp_path, monkeypatch):
    """Set up an isolated wiki root with WORKFLOW_WIKI_PATH."""
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    from workflow.api.wiki import _ensure_wiki_scaffold
    _ensure_wiki_scaffold(wiki_root)
    return wiki_root


def _file_bug(wiki_env, **kwargs):  # noqa: ARG001
    from workflow.universe_server import wiki
    defaults = {
        "action": "file_bug",
        "component": "test.surface",
        "severity": "minor",
        "title": "Test bug",
        "observed": "saw X",
        "expected": "expected Y",
    }
    defaults.update(kwargs)
    return json.loads(wiki(**defaults))


def _seed_bug(wiki_env, title: str, observed: str = "") -> dict:
    """Seed a bug directly (force_new so dedup doesn't block seeding)."""
    return _file_bug(wiki_env, title=title, observed=observed, force_new=True)


# ── (a) no similar → mint new id ──────────────────────────────────────────────


def test_no_similar_mints_new_id(wiki_env):
    """When no existing bugs are similar, file_bug mints a new id."""
    result = _file_bug(wiki_env, title="Completely unique bug about xyzzy tokens")
    assert result.get("status") == "filed"
    assert result.get("bug_id") is not None
    assert result["bug_id"].startswith("BUG-")


# ── (b) similar existing → similar_found, no id minted ───────────────────────


def test_similar_existing_returns_similar_found(wiki_env):
    """When an existing bug is ≥50% similar, return similar_found without minting."""
    # Seed an existing bug
    _seed_bug(wiki_env, title="Search goals returns zero results for multi-token query",
              observed="search returns empty list for query containing multiple words")

    # Now file essentially the same bug
    result = _file_bug(
        wiki_env,
        title="Search goals returns zero results for multi token query",
        observed="search returns empty list for query with multiple words",
    )
    assert result.get("status") == "similar_found", (
        f"Expected similar_found, got: {result}"
    )
    assert result.get("bug_id") is None, "No id should be minted on similar_found"
    assert "similar" in result
    assert len(result["similar"]) >= 1


def test_similar_found_includes_top_3(wiki_env):
    """similar_found returns up to top-3 matches sorted by similarity."""
    _seed_bug(wiki_env, title="Login fails with wrong password error message shown",
              observed="wrong error displayed on bad credentials")
    _seed_bug(wiki_env, title="Login fails with wrong error shown on bad password",
              observed="wrong error message shown when credentials fail")

    result = _file_bug(
        wiki_env,
        title="Login fails wrong password error message shown",
        observed="wrong error message on bad credentials",
    )
    assert result.get("status") == "similar_found"
    assert len(result["similar"]) <= 3
    # Each entry has required fields
    for entry in result["similar"]:
        assert "bug_id" in entry
        assert "title" in entry
        assert "similarity" in entry
        assert "status" in entry


def test_similar_found_highest_similarity_first(wiki_env):
    """The most similar bug ranks first in the similar list."""
    _seed_bug(wiki_env,
              title="Widget crashes on double-click with null pointer",
              observed="crashes on double-click null pointer exception")
    _seed_bug(wiki_env,
              title="Unrelated button styling issue",
              observed="button looks wrong")

    result = _file_bug(
        wiki_env,
        title="Widget crashes on double-click null pointer",
        observed="crashes on double-click null pointer",
    )
    assert result.get("status") == "similar_found"
    sims = [e["similarity"] for e in result["similar"]]
    assert sims == sorted(sims, reverse=True), "Should be sorted by similarity descending"


# ── (c) force_new=True → mint new id regardless ───────────────────────────────


def test_force_new_skips_similarity_check(wiki_env):
    """force_new=True always mints a new id even when similar exists."""
    _seed_bug(wiki_env, title="Goals search fails for multi-token queries always",
              observed="zero results returned for multi-token search queries")

    result = _file_bug(
        wiki_env,
        title="Goals search fails for multi-token queries always",
        observed="zero results for multi-token search",
        force_new=True,
    )
    assert result.get("status") == "filed", (
        f"Expected filed with force_new=True, got: {result}"
    )
    assert result.get("bug_id") is not None


# ── (d) cosign_bug roundtrip ──────────────────────────────────────────────────


def test_cosign_bug_roundtrip(wiki_env):
    """cosign_bug appends a Cosigns section, increments count, returns count."""
    from workflow.universe_server import wiki
    filed = _seed_bug(wiki_env, title="Cosign target bug unique string xyzabc",
                      observed="the xyzabc thing broke")
    bug_id = filed["bug_id"]

    result = json.loads(wiki(
        action="cosign_bug",
        bug_id=bug_id,
        reporter_context="I also saw this: xyzabc broken on my machine too",
    ))
    assert result.get("status") == "cosigned", f"Expected cosigned, got: {result}"
    assert result.get("bug_id") == bug_id
    assert result.get("cosign_count") == 1


def test_cosign_bug_increments_count(wiki_env):
    """Each subsequent cosign increments cosign_count by 1."""
    from workflow.universe_server import wiki
    filed = _seed_bug(wiki_env, title="Multi-cosign target bug zyxwvu98",
                      observed="zyxwvu98 broken")
    bug_id = filed["bug_id"]

    for i in range(1, 4):
        result = json.loads(wiki(
            action="cosign_bug",
            bug_id=bug_id,
            reporter_context=f"Reporter {i} sees the zyxwvu98 issue",
        ))
        assert result["cosign_count"] == i, (
            f"Expected cosign_count={i}, got {result['cosign_count']}"
        )


def test_cosign_bug_file_contains_entry(wiki_env):
    """The bug file on disk should contain a ## Cosigns section after cosigning."""
    from workflow.universe_server import wiki
    filed = _seed_bug(wiki_env, title="Readable cosign test bug qwerty99",
                      observed="qwerty99 broke")
    bug_id = filed["bug_id"]
    file_path = wiki_env / filed["path"]

    json.loads(wiki(
        action="cosign_bug",
        bug_id=bug_id,
        reporter_context="I also observed qwerty99 failure in production",
    ))
    content = file_path.read_text(encoding="utf-8")
    assert "## Cosigns" in content
    assert "I also observed qwerty99 failure in production" in content


# ── (e) cosign_bug on missing bug_id → structured error ──────────────────────


def test_cosign_bug_missing_bug_id_returns_error(wiki_env):
    from workflow.universe_server import wiki
    result = json.loads(wiki(
        action="cosign_bug",
        bug_id="BUG-999",
        reporter_context="Test context",
    ))
    assert "error" in result


def test_cosign_bug_missing_required_args_returns_error(wiki_env):
    from workflow.universe_server import wiki  # Missing bug_id
    r1 = json.loads(wiki(action="cosign_bug", reporter_context="ctx"))
    assert "error" in r1

    # Missing reporter_context
    r2 = json.loads(wiki(action="cosign_bug", bug_id="BUG-001"))
    assert "error" in r2


# ── (f) regression — existing file_bug tests still work ──────────────────────


def test_file_bug_still_mints_id_on_empty_bugs_dir(wiki_env):
    """Regression: first-ever bug on a clean wiki must still file cleanly."""
    result = _file_bug(wiki_env, title="First ever unique bug for regression test abc123")
    assert result.get("status") == "filed"
    assert result["bug_id"].startswith("BUG-")


def test_file_bug_returns_path_in_pages_bugs(wiki_env):
    """Filed bug path must be under pages/bugs/."""
    result = _file_bug(wiki_env, title="Path check bug for unique abc987",
                       force_new=True)
    assert result["path"].startswith("pages/bugs/"), (
        f"Expected path under pages/bugs/, got: {result['path']!r}"
    )


def test_file_bug_validation_errors_still_work(wiki_env):
    """Validation errors (missing required field) still return error dict."""
    from workflow.universe_server import wiki
    result = json.loads(wiki(action="file_bug", title=""))
    assert "error" in result

    result = json.loads(wiki(action="file_bug", title="T", component="c", severity="invalid"))
    assert "error" in result


def test_file_bug_unrelated_query_does_not_trigger_similar_found(wiki_env):
    """A query with zero token overlap with existing bugs must file cleanly."""
    _seed_bug(wiki_env, title="Login authentication fails with wrong password error",
              observed="login error message wrong on bad credentials")

    result = _file_bug(
        wiki_env,
        title="Database connection pool exhausted under load",
        observed="connection pool timeout exception thrown",
    )
    # Completely different domain — should not trigger dedup
    assert result.get("status") == "filed", (
        f"Unrelated bug should file cleanly, got: {result}"
    )


# ── Task #42: threshold edge-cases + adversarial depth ────────────────────────


def _token_set(text: str) -> set[str]:
    """Mirror of _bug_token_set for test-side control."""
    import re
    return {w for w in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if len(w) > 2}


def _jaccard_score(a: set[str], b: set[str]) -> float:
    """Mirror of _jaccard for test-side assertions."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class TestThresholdEdgeCases:
    """Direct unit tests against _jaccard + _bug_token_set."""

    def test_exact_duplicate_tokens_score_one(self):
        from workflow.api.wiki import (
            _bug_token_set,
            _jaccard,
        )
        tokens = _bug_token_set("widget crashes null pointer exception button click")
        assert _jaccard(tokens, tokens) == 1.0

    def test_zero_overlap_score_zero(self):
        from workflow.api.wiki import (
            _bug_token_set,
            _jaccard,
        )
        a = _bug_token_set("authentication login password credentials session")
        b = _bug_token_set("database connection pool exhausted timeout network")
        assert _jaccard(a, b) == 0.0

    def test_threshold_boundary_above_fires(self):
        """Jaccard ≥ 0.5 must trigger dedup; construct tokens to guarantee it."""
        from workflow.api.wiki import (
            _bug_token_set,
            _jaccard,
        )
        # 4 shared tokens, 1 unique each → Jaccard = 4/6 ≈ 0.667 > 0.5
        shared = "alpha beta gamma delta"
        a = _bug_token_set(shared + " extra")
        b = _bug_token_set(shared + " other")
        score = _jaccard(a, b)
        assert score >= 0.5, f"Expected ≥0.5, got {score}"

    def test_threshold_boundary_below_silent(self):
        """Jaccard < 0.5 must NOT trigger dedup."""
        from workflow.api.wiki import (
            _bug_token_set,
            _jaccard,
        )
        # 1 shared token, 5 unique each → Jaccard = 1/11 ≈ 0.09 < 0.5
        a = _bug_token_set("alpha bravo charlie delta echo foxtrot")
        b = _bug_token_set("alpha golf hotel india juliet kilo")
        score = _jaccard(a, b)
        assert score < 0.5, f"Expected <0.5, got {score}"

    def test_empty_both_returns_one(self):
        """Two empty sets → Jaccard = 1.0 (both describe nothing)."""
        from workflow.api.wiki import _jaccard
        assert _jaccard(set(), set()) == 1.0

    def test_empty_vs_nonempty_returns_zero(self):
        from workflow.api.wiki import (
            _bug_token_set,
            _jaccard,
        )
        nonempty = _bug_token_set("some words here that matter")
        assert _jaccard(set(), nonempty) == 0.0

    def test_short_tokens_filtered(self):
        """Tokens with len ≤ 2 must be excluded from the set."""
        from workflow.api.wiki import _bug_token_set
        tokens = _bug_token_set("an is it of at to")
        assert tokens == set(), f"Expected all filtered, got {tokens}"


class TestIntegrationEdgeCases:
    """Integration tests through the full wiki() path."""

    def test_100_percent_exact_duplicate_returns_similar_found(self, wiki_env):
        """Exact same title + observed → similar_found with similarity near 1.0."""
        title = "Mxyzptlk widget crashes null pointer exception fatal error"
        observed = "mxyzptlk widget throws null pointer exception on button click"
        _seed_bug(wiki_env, title=title, observed=observed)

        result = _file_bug(wiki_env, title=title, observed=observed)
        assert result.get("status") == "similar_found", f"Got: {result}"
        assert result["similar"][0]["similarity"] >= 0.9

    def test_0_percent_overlap_mints_new_id(self, wiki_env):
        """Completely unrelated tokens → mints new id, no similar_found."""
        _seed_bug(wiki_env,
                  title="Zyxwvut authentication credentials session timeout expiry",
                  observed="zyxwvut session expires too quickly on idle timeout")

        result = _file_bug(
            wiki_env,
            title="Plonkfoo database connection pool exhausted network latency",
            observed="plonkfoo connection pool timeout exception under high load",
        )
        assert result.get("status") == "filed", f"Expected filed, got: {result}"

    def test_many_bugs_above_threshold_returns_top_3_only(self, wiki_env):
        """5+ bugs all similar → only top-3 returned."""
        base = "widget crashes null pointer exception button click fatal error"
        for i in range(5):
            _seed_bug(wiki_env,
                      title=f"{base} variant{i}abc",
                      observed="widget throws null pointer exception on click")

        result = _file_bug(
            wiki_env,
            title=base,
            observed="widget throws null pointer exception on click",
        )
        assert result.get("status") == "similar_found"
        assert len(result["similar"]) <= 3, (
            f"Expected ≤3 results, got {len(result['similar'])}"
        )

    def test_unicode_title_handled_without_crash(self, wiki_env):
        """Non-ASCII / emoji in title does not crash; gracefully degrades."""
        result = _file_bug(
            wiki_env,
            title="Widget écrase avec erreur null pointeur",
            observed="Le widget plante avec une erreur de pointeur null",
            force_new=True,
        )
        # Must not error — either filed or similar_found
        assert result.get("status") in ("filed", "similar_found"), (
            f"Unicode title caused unexpected result: {result}"
        )

    def test_force_new_true_with_high_similarity_mints_new_id(self, wiki_env):
        """force_new=True + high similarity → new id anyway (ignores dedup)."""
        title = "Qqqrrrxxx widget crashes null pointer exception fatal crash"
        observed = "qqqrrrxxx widget throws null pointer fatal exception on click"
        _seed_bug(wiki_env, title=title, observed=observed)

        result = _file_bug(wiki_env, title=title, observed=observed, force_new=True)
        assert result.get("status") == "filed", (
            f"force_new=True should mint new id, got: {result}"
        )
        assert result["bug_id"].startswith("BUG-")

    def test_cosign_count_increments_to_high_values(self, wiki_env):
        """cosign_count increments correctly beyond 2 (up to N)."""
        from workflow.universe_server import wiki
        filed = _seed_bug(wiki_env,
                          title="Cosign stress test bug unique aaabbbccc",
                          observed="aaabbbccc broken")
        bug_id = filed["bug_id"]

        for i in range(1, 6):
            result = json.loads(wiki(
                action="cosign_bug",
                bug_id=bug_id,
                reporter_context=f"Reporter {i} context for aaabbbccc issue",
            ))
            assert result["cosign_count"] == i

    def test_cosign_same_context_twice_appends_both(self, wiki_env):
        """Same reporter_context submitted twice both get appended (no dedup at cosign level).

        Current behavior: cosign does NOT deduplicate by reporter. Both entries
        are appended. This test documents that behavior so a future change is
        explicit, not silent.
        """
        from workflow.universe_server import wiki
        filed = _seed_bug(wiki_env,
                          title="Cosign dedup behavior test unique dddeeefff",
                          observed="dddeeefff broken on my machine")
        bug_id = filed["bug_id"]
        file_path = wiki_env / filed["path"]
        ctx = "I also saw dddeeefff broken on my machine"

        json.loads(wiki(action="cosign_bug", bug_id=bug_id, reporter_context=ctx))
        json.loads(wiki(action="cosign_bug", bug_id=bug_id, reporter_context=ctx))

        content = file_path.read_text(encoding="utf-8")
        # Both entries appended — documented behavior
        assert content.count(ctx) == 2, (
            "cosign_bug does not deduplicate identical contexts — both should appear"
        )

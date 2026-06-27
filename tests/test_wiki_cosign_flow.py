"""FRESH-E — cosign_bug similarity-then-cosign happy-path flow.

Exercises the full chatbot-rule flow that `test_wiki_file_bug_dedup.py` only
tests in pieces:

    file_bug(similar)  → status: "similar_found"
                       → caller pulls bug_id from result["similar"][0]
    cosign_bug(bug_id) → status: "cosigned", count incremented

This is the canonical "default cosign over force_new" path the chatbot rule
prescribes (see project memory `project_file_bug_dedup_at_filing.md`).
The existing dedup file tests similarity OR cosign in isolation — never the
end-to-end stitching, which is the actual production behavior.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def wiki_env(tmp_path, monkeypatch):
    """Isolated wiki root with TINYASSETS_WIKI_PATH."""
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.api.wiki import _ensure_wiki_scaffold
    _ensure_wiki_scaffold(wiki_root)
    return wiki_root


def _file_bug(wiki_env, **kwargs):  # noqa: ARG001
    from tinyassets.universe_server import wiki
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
    """Seed a bug via force_new so dedup doesn't block seeding."""
    return _file_bug(wiki_env, title=title, observed=observed, force_new=True)


def _cosign(wiki_env, bug_id: str, reporter_context: str) -> dict:  # noqa: ARG001
    from tinyassets.universe_server import wiki
    return json.loads(wiki(
        action="cosign_bug",
        bug_id=bug_id,
        reporter_context=reporter_context,
    ))


def test_similarity_then_cosign_happy_path(wiki_env):
    """Full flow: seed bug → file similar → similar_found → cosign top match.

    Asserts every load-bearing step:
      1. file_bug returns similar_found (no new id minted)
      2. similar list has at least one entry with bug_id
      3. cosign_bug on that id returns cosigned with cosign_count=1
      4. bug file on disk gains a Cosigns section with the new context
    """
    seed = _seed_bug(
        wiki_env,
        title="Conditional edge resolver reads stale state under retry",
        observed="resolver reads stale state when branch retries iteratively",
    )
    seeded_bug_id = seed["bug_id"]

    # Step 1: caller files a near-duplicate
    filed = _file_bug(
        wiki_env,
        title="Conditional edge resolver reads stale state during retry",
        observed="resolver reads stale state when branch retries on iteration",
    )
    assert filed.get("status") == "similar_found", (
        f"Expected similar_found, got: {filed}"
    )
    assert filed.get("bug_id") is None, "No new id should be minted on similar_found"
    assert len(filed.get("similar", [])) >= 1

    # Step 2: caller picks the top match (chatbot-rule: default cosign)
    top_match = filed["similar"][0]
    assert top_match["bug_id"] == seeded_bug_id, (
        f"Expected top match to be the seeded bug {seeded_bug_id}, "
        f"got {top_match['bug_id']}"
    )

    # Step 3: caller cosigns the existing bug
    cosigned = _cosign(
        wiki_env,
        bug_id=top_match["bug_id"],
        reporter_context="I also see this on retry — same stale-state symptom",
    )
    assert cosigned.get("status") == "cosigned", f"Expected cosigned, got: {cosigned}"
    assert cosigned.get("bug_id") == seeded_bug_id
    assert cosigned.get("cosign_count") == 1

    # Step 4: bug file on disk reflects the cosign
    file_path = wiki_env / seed["path"]
    content = file_path.read_text(encoding="utf-8")
    assert "## Cosigns" in content
    assert "I also see this on retry" in content


def test_similarity_then_cosign_preserves_original_bug_id(wiki_env):
    """The cosign flow must NOT mint a new BUG-NNN.

    Across the full file_bug → cosign_bug round-trip, only the originally
    seeded bug_id should exist on disk. No second bug file is created.
    """
    seed = _seed_bug(
        wiki_env,
        title="Goals search returns empty for multi-token query patterns",
        observed="multi-token search query returns zero results consistently",
    )
    seeded_bug_id = seed["bug_id"]

    bugs_dir = wiki_env / "pages" / "bugs"
    bug_files_before = sorted(p.name for p in bugs_dir.glob("BUG-*.md"))

    filed = _file_bug(
        wiki_env,
        title="Goals search returns empty for multi-token queries",
        observed="multi-token query returns zero results in search",
    )
    assert filed.get("status") == "similar_found"

    cosigned = _cosign(
        wiki_env,
        bug_id=filed["similar"][0]["bug_id"],
        reporter_context="Confirming this on my fresh install too",
    )
    assert cosigned.get("status") == "cosigned"
    assert cosigned.get("bug_id") == seeded_bug_id

    bug_files_after = sorted(p.name for p in bugs_dir.glob("BUG-*.md"))
    assert bug_files_before == bug_files_after, (
        f"No new bug file should be created. Before: {bug_files_before}, "
        f"After: {bug_files_after}"
    )


def test_similarity_then_cosign_increments_on_repeat(wiki_env):
    """Two chatbot-turns: each does file_bug → cosign_bug.

    cosign_count must increment monotonically. Models the production case
    where multiple users hit the same near-duplicate path on the same bug.
    """
    seed = _seed_bug(
        wiki_env,
        title="Daemon hangs when provider returns rate-limit error response",
        observed="daemon hangs indefinitely on rate-limit response from provider",
    )
    seeded_bug_id = seed["bug_id"]

    titles_and_observations = [
        (
            "Daemon hangs when provider returns rate-limit error",
            "daemon hangs forever on rate-limit response from a provider",
        ),
        (
            "Daemon hangs on provider rate-limit error response",
            "daemon hangs on rate-limit error from provider",
        ),
    ]
    expected_counts = [1, 2]

    for (title, observed), expected_count in zip(
        titles_and_observations, expected_counts, strict=True,
    ):
        filed = _file_bug(wiki_env, title=title, observed=observed)
        assert filed.get("status") == "similar_found", (
            f"Turn for title={title!r} expected similar_found, got: {filed}"
        )

        cosigned = _cosign(
            wiki_env,
            bug_id=filed["similar"][0]["bug_id"],
            reporter_context=f"Reporter for: {title}",
        )
        assert cosigned.get("status") == "cosigned"
        assert cosigned.get("bug_id") == seeded_bug_id
        assert cosigned.get("cosign_count") == expected_count, (
            f"Expected cosign_count={expected_count}, got "
            f"{cosigned.get('cosign_count')}"
        )


def test_similarity_then_cosign_persists_to_disk(wiki_env):
    """Re-reading the bug file shows BOTH the original report + the cosign.

    Smoke-test that the cosign survives a fresh disk read: original
    frontmatter + body remain intact, cosign_count frontmatter field is
    written, and the appended Cosigns entry contains the reporter context.
    """
    original_observed = "auth middleware drops session token on cross-tab navigation"
    seed = _seed_bug(
        wiki_env,
        title="Auth middleware drops session token on cross-tab navigation",
        observed=original_observed,
    )

    filed = _file_bug(
        wiki_env,
        title="Auth middleware drops session token on cross tab navigation",
        observed="auth middleware loses session token across tab navigation",
    )
    assert filed.get("status") == "similar_found"

    cosign_text = "Repro on Firefox 120 — same lost-session symptom"
    _cosign(
        wiki_env,
        bug_id=filed["similar"][0]["bug_id"],
        reporter_context=cosign_text,
    )

    file_path = wiki_env / seed["path"]
    content = file_path.read_text(encoding="utf-8")

    # Original observed text is preserved
    assert original_observed in content, (
        "Original observed text must remain after cosign"
    )
    # Cosign frontmatter field reflects the increment
    assert "cosign_count: 1" in content
    # Cosigns section contains the new reporter context
    assert "## Cosigns" in content
    assert cosign_text in content

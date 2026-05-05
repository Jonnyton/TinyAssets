from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow.api.universe as us
from workflow.api.wiki import _ensure_wiki_scaffold


@pytest.fixture
def continuity_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    data_root = tmp_path / "output"
    wiki_root = tmp_path / "wiki"
    universe_dir = data_root / "u"
    (universe_dir / "canon").mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(data_root))
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "u")
    _ensure_wiki_scaffold(wiki_root)
    return universe_dir, wiki_root


def test_continuity_audit_flags_canon_and_wiki_conflicts(
    continuity_env: tuple[Path, Path],
) -> None:
    universe_dir, wiki_root = continuity_env
    (universe_dir / "canon" / "characters.md").write_text(
        "# Characters\n\nRyn is dead after the bridge duel.\n",
        encoding="utf-8",
    )
    (wiki_root / "pages" / "concepts" / "moonsteel.md").write_text(
        "---\ntitle: Moonsteel\n---\n"
        "Constraint: moonsteel cannot cross salt water.\n",
        encoding="utf-8",
    )

    out = json.loads(us._action_continuity_audit(
        universe_id="u",
        text="Ryn is alive. The moonsteel blade can cross salt water.",
        limit=10,
    ))

    assert out["status"] == "needs_revision"
    assert out["conflict_count"] == 2
    conflict_paths = {conflict["path"] for conflict in out["conflicts"]}
    assert "canon/characters.md" in conflict_paths
    assert "pages/concepts/moonsteel.md" in conflict_paths
    assert out["canon_hits"][0]["path"] == "canon/characters.md"
    assert out["wiki_constraint_hits"][0]["path"] == "pages/concepts/moonsteel.md"
    assert any("heuristic" in caveat for caveat in out["caveats"])


def test_continuity_audit_returns_insufficient_evidence_without_matches(
    continuity_env: tuple[Path, Path],
) -> None:
    out = json.loads(us._action_continuity_audit(
        universe_id="u",
        text="A new lighthouse appears on the eastern reef.",
    ))

    assert out["status"] == "insufficient_evidence"
    assert out["conflicts"] == []
    assert out["canon_hits"] == []
    assert out["wiki_constraint_hits"] == []
    assert "No related canon or wiki constraint passages found." in out["caveats"]


def test_continuity_audit_is_available_through_universe_dispatch(
    continuity_env: tuple[Path, Path],
) -> None:
    out = json.loads(us._universe_impl(
        action="continuity_audit",
        universe_id="u",
        text="Ryn watches the river.",
    ))

    assert out["action"] == "continuity_audit"
    assert out["universe_id"] == "u"


def test_continuity_audit_requires_fragment_text(
    continuity_env: tuple[Path, Path],
) -> None:
    out = json.loads(us._action_continuity_audit(universe_id="u", text=""))

    assert out["error"] == (
        "Text required. Pass the prose fragment to audit in the text field."
    )

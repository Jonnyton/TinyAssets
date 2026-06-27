"""Tests for the synthesis-skip fix (task #17).

Covers:
- **Fix A (revised):** ``run_book`` entry barrier in
  ``domains/fantasy_daemon/graphs/universe.py``. Refuses to draft when
  ``worldbuild_signals.json`` has a queued ``synthesize_source`` whose
  manifest entry has empty ``synthesized_docs``.
- **Fix C:** ``_synthesize_bite_by_bite`` per-bite diagnostics populate
  ``_LAST_BITE_OUTCOMES`` and the handler mirrors them into the
  manifest's ``last_bite_outcomes`` field.
- **Fix E:** Post-synthesis drift-KG cleanup deletes facts whose
  ``seeded_scene`` matches ``{universe}-B*-C*-S*_chunk_*``. Scope is
  facts-only; entities/edges have no scene attribution in the current
  schema.

Diagnosis reference: ``docs/concerns/2026-04-16-synthesis-skip-echoes.md``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from domains.fantasy_daemon.graphs.universe import (
    _has_unsynthesized_canon,
    run_book,
)
from domains.fantasy_daemon.phases.drift_cleanup import (
    cleanup_drift_kg,
    is_drift_seeded_scene,
)
from tinyassets.ingestion.extractors import (
    _LAST_BITE_OUTCOMES,
    _synthesize_bite_by_bite,
    get_last_bite_outcomes,
)


def _write_manifest(canon_dir: Path, entries: dict[str, dict]) -> None:
    (canon_dir / ".manifest.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8",
    )


def _write_signals(udir: Path, signals: list[dict]) -> None:
    (udir / "worldbuild_signals.json").write_text(
        json.dumps(signals, indent=2), encoding="utf-8",
    )


@pytest.fixture
def universe(tmp_path: Path) -> Path:
    udir = tmp_path / "uni"
    (udir / "canon").mkdir(parents=True)
    return udir


# ─── Fix A (revised): run_book entry barrier ────────────────────────────


class TestUnsynthesizedCanonDetector:
    """``_has_unsynthesized_canon`` — the Fix A inspection helper."""

    def test_no_universe_path_returns_false(self):
        assert _has_unsynthesized_canon("") is False

    def test_no_manifest_returns_false(self, universe: Path):
        _write_signals(universe, [])
        assert _has_unsynthesized_canon(str(universe)) is False

    def test_no_signals_returns_false(self, universe: Path):
        _write_manifest(universe / "canon", {
            "foo.md": {"synthesized_docs": []},
        })
        assert _has_unsynthesized_canon(str(universe)) is False

    def test_signal_plus_empty_synthesized_docs_returns_true(
        self, universe: Path,
    ):
        """The Echoes case: signal queued, manifest entry exists, no docs yet."""
        _write_manifest(universe / "canon", {
            "canon.md": {
                "filename": "canon.md",
                "synthesized_docs": [],
                "byte_count": 9000,
            },
        })
        _write_signals(universe, [
            {"type": "synthesize_source", "source_file": "canon.md"},
        ])
        assert _has_unsynthesized_canon(str(universe)) is True

    def test_signal_plus_populated_synthesized_docs_returns_false(
        self, universe: Path,
    ):
        """Signal lingering but synthesis already completed — no barrier."""
        _write_manifest(universe / "canon", {
            "canon.md": {
                "filename": "canon.md",
                "synthesized_docs": ["doc_a.md", "doc_b.md"],
            },
        })
        _write_signals(universe, [
            {"type": "synthesize_source", "source_file": "canon.md"},
        ])
        assert _has_unsynthesized_canon(str(universe)) is False

    def test_mixed_sources_returns_true_if_any_pending(
        self, universe: Path,
    ):
        _write_manifest(universe / "canon", {
            "done.md": {"synthesized_docs": ["x.md"]},
            "pending.md": {"synthesized_docs": []},
        })
        _write_signals(universe, [
            {"type": "synthesize_source", "source_file": "done.md"},
            {"type": "synthesize_source", "source_file": "pending.md"},
        ])
        assert _has_unsynthesized_canon(str(universe)) is True

    def test_non_synthesize_signal_ignored(self, universe: Path):
        _write_manifest(universe / "canon", {
            "canon.md": {"synthesized_docs": []},
        })
        _write_signals(universe, [
            {"type": "new_element", "source_file": "canon.md"},
        ])
        assert _has_unsynthesized_canon(str(universe)) is False

    def test_malformed_manifest_returns_false(self, universe: Path):
        """Fail-open: bad JSON mustn't hard-stop drafting."""
        (universe / "canon" / ".manifest.json").write_text(
            "not json", encoding="utf-8",
        )
        _write_signals(universe, [
            {"type": "synthesize_source", "source_file": "canon.md"},
        ])
        assert _has_unsynthesized_canon(str(universe)) is False


class TestRunBookBarrier:
    """``run_book`` returns ``needs_synthesis`` without drafting when the
    barrier trips."""

    def test_barrier_trips_returns_needs_synthesis(self, universe: Path):
        _write_manifest(universe / "canon", {
            "canon.md": {"synthesized_docs": []},
        })
        _write_signals(universe, [
            {"type": "synthesize_source", "source_file": "canon.md"},
        ])
        state = {
            "universe_id": "uni",
            "_universe_path": str(universe),
            "_db_path": "",
            "_kg_path": "",
            "total_chapters": 0,
            "total_words": 0,
            "workflow_instructions": {},
        }
        result = run_book(state)
        assert result.get("needs_synthesis") is True
        # No chapters drafted; no drift-producing side effects.
        assert "total_chapters" not in result
        trace = result.get("quality_trace", [])
        assert trace and trace[0]["action"] == "barrier_needs_synthesis"

    def test_no_barrier_proceeds_to_subgraph(
        self, universe: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """When synthesis is complete, run_book invokes the book subgraph
        rather than short-circuiting."""
        _write_manifest(universe / "canon", {
            "canon.md": {"synthesized_docs": ["a.md"]},
        })
        _write_signals(universe, [])

        invoked = {"called": False}

        class _FakeCompiled:
            def invoke(self, inp):
                invoked["called"] = True
                return {"chapters_completed": 1, "chapter_word_count": 100}

        class _FakeGraph:
            def compile(self):
                return _FakeCompiled()

        monkeypatch.setattr(
            "domains.fantasy_daemon.graphs.book.build_book_graph",
            lambda: _FakeGraph(),
        )
        state = {
            "universe_id": "uni",
            "_universe_path": str(universe),
            "_db_path": "",
            "_kg_path": "",
            "total_chapters": 0,
            "total_words": 0,
            "workflow_instructions": {},
            "selected_target_id": None,
            "selected_intent": "",
        }
        result = run_book(state)
        assert invoked["called"] is True
        assert result.get("needs_synthesis") is None or not result.get(
            "needs_synthesis"
        )


# ─── Fix C: bite-loop diagnostics ──────────────────────────────────────


class TestBiteLoopDiagnostics:
    """``_synthesize_bite_by_bite`` records per-bite outcomes so
    empty-result failure modes are debuggable from logs and manifest
    state."""

    def setup_method(self):
        _LAST_BITE_OUTCOMES.clear()

    def test_all_parse_failures_tally_nonzero(self):
        def bad_provider(prompt, system, role):
            return "I'm sorry, I can't help with that."

        source = "Lorem ipsum " * 10_000
        result = _synthesize_bite_by_bite(
            source, "big.md", premise="", provider_call=bad_provider,
        )
        assert result == {}
        outcomes = get_last_bite_outcomes("big.md")
        assert outcomes["ok"] == 0
        assert outcomes["parse_failed"] >= 1
        assert outcomes["bites_total"] >= 1

    def test_empty_response_tally(self):
        def empty_provider(prompt, system, role):
            return ""

        source = "x " * 30_000
        result = _synthesize_bite_by_bite(
            source, "empty.md", premise="", provider_call=empty_provider,
        )
        assert result == {}
        outcomes = get_last_bite_outcomes("empty.md")
        assert outcomes["empty_response"] >= 1
        assert outcomes["ok"] == 0

    def test_provider_error_tally(self):
        def erroring_provider(prompt, system, role):
            raise RuntimeError("rate limit")

        source = "x " * 30_000
        result = _synthesize_bite_by_bite(
            source, "err.md", premise="", provider_call=erroring_provider,
        )
        assert result == {}
        outcomes = get_last_bite_outcomes("err.md")
        assert outcomes["provider_error"] >= 1

    def test_ok_tally_on_success(self):
        def good_provider(prompt, system, role):
            return '{"topic_a": "content from this bite"}'

        source = "x " * 10_000
        result = _synthesize_bite_by_bite(
            source, "ok.md", premise="", provider_call=good_provider,
        )
        assert result
        outcomes = get_last_bite_outcomes("ok.md")
        assert outcomes["ok"] >= 1

    def test_parsed_but_empty_tally(self):
        def empty_obj_provider(prompt, system, role):
            return "{}"

        source = "x " * 30_000
        result = _synthesize_bite_by_bite(
            source, "empty_obj.md", premise="", provider_call=empty_obj_provider,
        )
        assert result == {}
        outcomes = get_last_bite_outcomes("empty_obj.md")
        assert outcomes["parsed_but_empty"] >= 1

    def test_get_last_bite_outcomes_empty_for_unknown_file(self):
        assert get_last_bite_outcomes("never-seen.md") == {}


# ─── Fix E: drift-KG cleanup ──────────────────────────────────────────


def _init_minimal_kg(db_path: Path) -> None:
    """Minimal schema mirror of the facts/entities/edges tables used by Fix E."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE facts (
                fact_id TEXT PRIMARY KEY,
                text TEXT NOT NULL DEFAULT '',
                seeded_scene TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation_type TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (source, target, relation_type)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


class TestDriftCleanup:
    def test_is_drift_seeded_scene_pattern(self):
        assert is_drift_seeded_scene("echoes_of_the_cosmos-B1-C1-S1_chunk_0")
        assert is_drift_seeded_scene("sporemarch-B2-C3-S4_chunk_12-extra")
        # Canon-doc patterns (filenames / synthesized ids) must not match.
        assert not is_drift_seeded_scene("magic_systems.md")
        assert not is_drift_seeded_scene("echoes-canon-b1")
        assert not is_drift_seeded_scene("")

    def test_cleanup_deletes_drift_facts(self, tmp_path: Path):
        db = tmp_path / "knowledge.db"
        _init_minimal_kg(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.executemany(
                "INSERT INTO facts (fact_id, text, seeded_scene) VALUES (?,?,?)",
                [
                    ("f1", "drift1", "echoes-B1-C1-S1_chunk_0"),
                    ("f2", "drift2", "echoes-B1-C1-S2_chunk_3"),
                    ("f3", "canon1", "magic_systems.md"),
                    ("f4", "canon2", ""),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        result = cleanup_drift_kg("echoes", str(db))
        assert result["facts_deleted"] == 2

        conn = sqlite3.connect(str(db))
        try:
            remaining = {
                r[0] for r in conn.execute(
                    "SELECT fact_id FROM facts"
                ).fetchall()
            }
        finally:
            conn.close()
        assert remaining == {"f3", "f4"}

    def test_cleanup_preserves_entities(self, tmp_path: Path):
        """Facts-only scope: entities are never deleted, even when orphaned.
        Deleting edgeless entities would risk wiping canon entities that
        have facts but no relationship structure (facts reference entities
        by name, not FK)."""
        db = tmp_path / "knowledge.db"
        _init_minimal_kg(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.executemany(
                "INSERT INTO entities (entity_id, entity_type) VALUES (?,?)",
                [
                    ("ally", "character"),
                    ("blast_door", "object"),
                    ("canon_hero", "character"),
                ],
            )
            conn.execute(
                "INSERT INTO facts (fact_id, text, seeded_scene) VALUES (?,?,?)",
                ("f1", "drift", "echoes-B1-C1-S1_chunk_0"),
            )
            conn.commit()
        finally:
            conn.close()

        cleanup_drift_kg("echoes", str(db))

        conn = sqlite3.connect(str(db))
        try:
            entities = {
                r[0] for r in conn.execute(
                    "SELECT entity_id FROM entities"
                ).fetchall()
            }
        finally:
            conn.close()
        assert entities == {"ally", "blast_door", "canon_hero"}

    def test_cleanup_missing_db_is_noop(self, tmp_path: Path):
        result = cleanup_drift_kg("echoes", str(tmp_path / "missing.db"))
        assert result == {"facts_deleted": 0}

    def test_cleanup_other_universe_left_alone(self, tmp_path: Path):
        """Cleaning universe 'A' must not touch universe 'B' drift facts
        that happen to share a db (not expected in prod but safety check)."""
        db = tmp_path / "knowledge.db"
        _init_minimal_kg(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.executemany(
                "INSERT INTO facts (fact_id, text, seeded_scene) VALUES (?,?,?)",
                [
                    ("f1", "drift_a", "alpha-B1-C1-S1_chunk_0"),
                    ("f2", "drift_b", "beta-B1-C1-S1_chunk_0"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        cleanup_drift_kg("alpha", str(db))

        conn = sqlite3.connect(str(db))
        try:
            remaining = {
                r[0] for r in conn.execute(
                    "SELECT fact_id FROM facts"
                ).fetchall()
            }
        finally:
            conn.close()
        assert remaining == {"f2"}

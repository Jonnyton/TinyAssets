"""Tests for scripts/rebuild_sporemarch_kg.py.

Covers scene discovery ordering, dry-run no-op safety, and a wet run against
a synthetic mini-universe with a patched ``provider_call`` so no real provider
is hit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_script_module():
    name = "rebuild_sporemarch_kg"
    spec = importlib.util.spec_from_file_location(
        name,
        str(_REPO_ROOT / "scripts" / "rebuild_sporemarch_kg.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load_script_module()


def _make_universe(tmp_path: Path, universe_name: str = "testverse") -> Path:
    """Create a synthetic universe with two scenes under book-1."""
    udir = tmp_path / universe_name
    c1 = udir / "output" / "book-1" / "chapter-01"
    c2 = udir / "output" / "book-1" / "chapter-02"
    c1.mkdir(parents=True, exist_ok=True)
    c2.mkdir(parents=True, exist_ok=True)
    (c1 / "scene-01.md").write_text(
        "Caro walked the Threshold Gate. The air was warm like a wound.\n",
        encoding="utf-8",
    )
    (c2 / "scene-01.md").write_text(
        "Corin watched the boundary collapse at dawn in Thornwall.\n",
        encoding="utf-8",
    )
    return udir


def test_discover_scenes_orders_by_book_chapter_scene(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path)
    # Add an out-of-order scene to ensure sorting works
    c1 = udir / "output" / "book-1" / "chapter-01"
    (c1 / "scene-02.md").write_text("second scene.\n", encoding="utf-8")

    scenes = MOD.discover_scenes(udir)
    ids = [(s.book, s.chapter, s.scene) for s in scenes]
    assert ids == [(1, 1, 1), (1, 1, 2), (1, 2, 1)]


def test_scene_id_format(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path, universe_name="myverse")
    scenes = MOD.discover_scenes(udir)
    assert scenes[0].scene_id("myverse") == "myverse-B1-C1-S1"


def test_dry_run_does_not_write_kg(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path)
    totals = MOD.rebuild(udir, dry_run=True)
    assert totals["scenes"] == 2
    assert totals["entities"] == 0
    assert not (udir / "knowledge.db").exists()


def test_rebuild_writes_to_knowledge_db(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path)

    extraction_json = json.dumps({
        "entities": [
            {
                "entity_id": "caro",
                "entity_type": "character",
                "aliases": ["Caro"],
                "description": "Protagonist",
                "access_tier": 0,
            },
            {
                "entity_id": "threshold_gate",
                "entity_type": "location",
                "aliases": ["Threshold Gate"],
                "description": "A permafrost boundary",
                "access_tier": 0,
            },
        ],
        "relationships": [
            {
                "source": "caro",
                "target": "threshold_gate",
                "relation_type": "visits",
                "weight": 0.9,
                "access_tier": 0,
            },
        ],
        "facts": [
            {
                "text": "Caro walked the Threshold Gate.",
                "source_type": "narrator_claim",
                "language_type": "literal",
                "narrative_function": "world_fact",
                "confidence": 0.9,
                "importance": 0.6,
                "access_tier": 0,
            },
        ],
    })

    def fake_provider_call(prompt, system="", *, role="writer", fallback_response=None, **_kw):
        return extraction_json

    with patch.object(MOD, "_load_provider_call", return_value=fake_provider_call):
        totals = MOD.rebuild(udir, dry_run=False)

    kg_path = udir / "knowledge.db"
    assert kg_path.exists()
    assert totals["scenes"] == 2
    assert totals["db_entities"] >= 2
    assert totals["db_edges"] >= 1
    assert totals["db_facts"] >= 2


def test_rebuild_is_idempotent(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path)
    extraction_json = json.dumps({
        "entities": [{
            "entity_id": "caro",
            "entity_type": "character",
            "aliases": [],
            "description": "",
            "access_tier": 0,
        }],
        "relationships": [],
        "facts": [],
    })

    def fake_provider_call(prompt, system="", *, role="writer", fallback_response=None, **_kw):
        return extraction_json

    with patch.object(MOD, "_load_provider_call", return_value=fake_provider_call):
        first = MOD.rebuild(udir, dry_run=False)
        second = MOD.rebuild(udir, dry_run=False)

    assert first["db_entities"] == second["db_entities"]
    assert second["db_entities"] == 1


def test_empty_scene_file_counts_as_failure(tmp_path: Path) -> None:
    udir = _make_universe(tmp_path)
    empty = udir / "output" / "book-1" / "chapter-01" / "scene-99.md"
    empty.write_text("", encoding="utf-8")

    def fake_provider_call(prompt, system="", *, role="writer", fallback_response=None, **_kw):
        return json.dumps({"entities": [], "relationships": [], "facts": []})

    with patch.object(MOD, "_load_provider_call", return_value=fake_provider_call):
        totals = MOD.rebuild(udir, dry_run=False)

    assert totals["failures"] >= 1


def test_missing_output_dir_raises(tmp_path: Path) -> None:
    udir = tmp_path / "ghost"
    udir.mkdir()
    with pytest.raises(FileNotFoundError):
        MOD.discover_scenes(udir)

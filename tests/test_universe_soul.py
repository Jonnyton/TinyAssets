from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def us(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    import workflow.api.universe as module

    importlib.reload(module)
    yield module
    importlib.reload(module)


def _mkuniverse(base: Path, uid: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def test_set_premise_writes_versioned_soul_profile(us):
    base = Path(us._base_path())
    _mkuniverse(base, "u1")

    result = json.loads(us._action_set_premise(
        universe_id="u1",
        text="A wandering lab studies civic memory.",
    ))

    assert result["status"] == "updated"
    assert result["soul"]["path"] == "soul.md"
    assert result["soul"]["schema_version"] == 1
    assert result["soul"]["versions_dir"] == "soul_versions"
    soul_md = (base / "u1" / "soul.md").read_text(encoding="utf-8")
    assert "# Universe Soul" in soul_md
    assert "## Purpose" in soul_md
    assert "A wandering lab studies civic memory." in soul_md
    assert "## Edit Authority" in soul_md
    assert "soul.edit" in soul_md
    version = base / "u1" / "soul_versions" / "0001.md"
    assert version.exists()
    assert version.read_text(encoding="utf-8") == soul_md


def test_read_premise_falls_back_to_soul_purpose(us):
    base = Path(us._base_path())
    udir = _mkuniverse(base, "u1")
    us._action_set_premise(universe_id="u1", text="A solar archive wakes up.")
    (udir / "PROGRAM.md").unlink()

    result = json.loads(us._action_read_premise(universe_id="u1"))

    assert result["premise"] == "A solar archive wakes up."
    assert result["source"] == "soul.md"
    assert result["soul"]["schema_version"] == 1


def test_create_universe_always_writes_soul_profile(us):
    base = Path(us._base_path())

    result = json.loads(us._action_create_universe(
        universe_id="fresh-uni",
        text="A seedling kingdom.",
    ))

    assert result["status"] == "created"
    assert result["has_soul"] is True
    assert result["soul"]["path"] == "soul.md"
    assert (base / "fresh-uni" / "soul.md").exists()
    assert (base / "fresh-uni" / "PROGRAM.md").read_text(
        encoding="utf-8",
    ) == "A seedling kingdom."


def test_create_universe_without_premise_still_has_thin_soul(us):
    base = Path(us._base_path())

    result = json.loads(us._action_create_universe(universe_id="thin-uni"))

    assert result["status"] == "created"
    assert result["has_premise"] is False
    assert result["has_soul"] is True
    soul_md = (base / "thin-uni" / "soul.md").read_text(encoding="utf-8")
    assert "# Universe Soul" in soul_md
    assert "## Purpose" in soul_md
    assert not (base / "thin-uni" / "PROGRAM.md").exists()

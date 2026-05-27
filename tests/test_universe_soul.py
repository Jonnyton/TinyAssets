from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from workflow.universe_soul import read_pinned_universe_soul


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
    assert "- Loop branch: _None recorded._" in soul_md
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


def test_read_pinned_universe_soul_reports_version_hash(us):
    base = Path(us._base_path())
    _mkuniverse(base, "u1")
    us._action_set_premise(
        universe_id="u1",
        text="A civic-memory workflow checks every source.",
    )

    pinned = read_pinned_universe_soul(base / "u1")

    assert pinned is not None
    assert pinned.version_id == "soul_versions/0001.md"
    assert len(pinned.content_sha256) == 64
    context = pinned.context()
    assert context["purpose"] == "A civic-memory workflow checks every source."
    assert context["version_id"] == "soul_versions/0001.md"
    assert context["identity_boundary"] == (
        "Universe soul guides this context only; it does not change "
        "the actor identity or user memory scope."
    )


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
    assert result["loop_dispatch"] == {
        "source": "soul.md",
        "branch_def_id": "",
        "declared": False,
    }
    soul_md = (base / "thin-uni" / "soul.md").read_text(encoding="utf-8")
    assert "# Universe Soul" in soul_md
    assert "## Purpose" in soul_md
    assert "- Loop branch: _None recorded._" in soul_md
    assert not (base / "thin-uni" / "PROGRAM.md").exists()


def test_create_universe_records_declared_loop_branch(us):
    base = Path(us._base_path())

    result = json.loads(us._action_create_universe(
        universe_id="workflow-uni",
        text="A civic workflow lab.",
        branch_def_id="workflow:review_loop",
    ))

    assert result["status"] == "created"
    assert result["soul"]["loop_branch_def_id"] == "workflow:review_loop"
    assert result["loop_dispatch"] == {
        "source": "soul.md",
        "branch_def_id": "workflow:review_loop",
        "declared": True,
    }
    soul_md = (base / "workflow-uni" / "soul.md").read_text(encoding="utf-8")
    assert "- Loop branch: workflow:review_loop" in soul_md
    pinned = read_pinned_universe_soul(base / "workflow-uni")
    assert pinned is not None
    assert pinned.context()["loop_branch_def_id"] == "workflow:review_loop"


def test_submit_request_uses_soul_declared_loop_branch(us):
    base = Path(us._base_path())
    us._action_create_universe(
        universe_id="loop-uni",
        text="A civic workflow lab.",
        branch_def_id="workflow:review_loop",
    )

    result = json.loads(us._action_submit_request(
        universe_id="loop-uni",
        text="Review this packet.",
        request_type="general",
    ))

    assert result["status"] == "pending"
    assert result["loop_dispatch"] == {
        "source": "soul.md",
        "has_soul": True,
        "branch_def_id": "workflow:review_loop",
    }
    queue = json.loads((base / "loop-uni" / "branch_tasks.json").read_text(
        encoding="utf-8",
    ))
    assert queue[0]["branch_def_id"] == "workflow:review_loop"
    assert queue[0]["inputs"]["loop_dispatch"]["source"] == "soul.md"


def test_submit_request_rejects_souled_universe_without_declared_loop(us):
    base = Path(us._base_path())
    us._action_create_universe(universe_id="thin-uni")

    result = json.loads(us._action_submit_request(
        universe_id="thin-uni",
        text="Do work.",
        request_type="general",
    ))

    assert result["error"] == "universe_loop_not_declared"
    assert result["loop_dispatch"]["source"] == "soul.md"
    assert not (base / "thin-uni" / "requests.json").exists()
    assert not (base / "thin-uni" / "branch_tasks.json").exists()


def test_submit_request_legacy_no_soul_keeps_named_compat_loop(us):
    base = Path(us._base_path())
    legacy = _mkuniverse(base, "legacy-uni")
    assert not (legacy / "soul.md").exists()

    result = json.loads(us._action_submit_request(
        universe_id="legacy-uni",
        text="Do legacy work.",
        request_type="general",
    ))

    assert result["status"] == "pending"
    assert result["loop_dispatch"]["source"] == "legacy_no_soul_compat"
    queue = json.loads((legacy / "branch_tasks.json").read_text(encoding="utf-8"))
    assert queue[0]["branch_def_id"] == "fantasy_author:universe_cycle_wrapper"

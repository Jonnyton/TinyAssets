"""Private manuscript workspace tests for the universe API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow.api.universe as us


def _call(action: str, **kwargs) -> dict:
    base_kwargs = {
        "universe_id": "",
        "text": "",
        "filename": "",
        "tag": "",
        "limit": 30,
    }
    base_kwargs.update(kwargs)
    dispatch = {
        "save_manuscript_fragment": us._action_save_manuscript_fragment,
        "list_manuscript_fragments": us._action_list_manuscript_fragments,
        "read_manuscript_fragment": us._action_read_manuscript_fragment,
    }
    return json.loads(
        us._dispatch_with_ledger(action, dispatch[action], base_kwargs),
    )


@pytest.fixture
def universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    base = tmp_path / "output"
    uid = "draft-uni"
    (base / uid).mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", uid)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "author-1")
    return uid


def test_save_fragment_keeps_private_version_history(universe: str) -> None:
    first = _call(
        "save_manuscript_fragment",
        filename="chapter-1-scene-2",
        text="First draft.",
        tag="rough",
    )
    second = _call(
        "save_manuscript_fragment",
        filename="chapter-1-scene-2",
        text="Second draft.",
        tag="revision",
    )

    assert first["visibility"] == "host_private"
    assert first["version"] == 1
    assert second["version"] == 2
    assert second["history_retained"] is True

    read = _call("read_manuscript_fragment", filename="chapter-1-scene-2")
    assert read["universe_id"] == universe
    assert read["visibility"] == "host_private"
    assert read["current_version"] == 2
    assert [v["text"] for v in read["versions"]] == [
        "First draft.",
        "Second draft.",
    ]
    assert [v["tag"] for v in read["versions"]] == ["rough", "revision"]


def test_list_fragments_excludes_body_text(universe: str) -> None:
    _call(
        "save_manuscript_fragment",
        filename="private-scene",
        text="Secret scene body.",
    )

    out = _call("list_manuscript_fragments")

    assert out["universe_id"] == universe
    assert out["visibility"] == "host_private"
    assert out["count"] == 1
    assert out["fragments"][0]["fragment_id"] == "private-scene"
    assert out["fragments"][0]["current_version"] == 1
    assert "text" not in out["fragments"][0]


def test_save_fragment_does_not_emit_canon_signal(universe: str) -> None:
    _call(
        "save_manuscript_fragment",
        filename="not-canon",
        text="Author-authored manuscript prose.",
    )

    udir = us._base_path() / universe
    assert (udir / "manuscript" / "fragments" / "not-canon.json").exists()
    assert not (udir / "canon").exists()
    assert not (udir / "worldbuild_signals.json").exists()


def test_save_fragment_ledger_omits_body_text(universe: str) -> None:
    _call(
        "save_manuscript_fragment",
        filename="ledger-safe",
        text="Private body must stay out of ledger.",
    )

    ledger_path = us._base_path() / universe / "ledger.json"
    entries = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert entries[0]["action"] == "save_manuscript_fragment"
    assert entries[0]["target"] == "manuscript/fragments/ledger-safe.json"
    assert entries[0]["payload"]["private"] is True
    assert "Private body" not in json.dumps(entries)


def test_rejects_empty_fragment_text(universe: str) -> None:
    out = _call(
        "save_manuscript_fragment",
        filename="empty",
        text="   ",
    )
    assert "error" in out
    assert "empty" in out["error"].lower()


def test_corrupt_fragment_history_fails_loudly(universe: str) -> None:
    frag_path = (
        us._base_path()
        / universe
        / "manuscript"
        / "fragments"
        / "broken.json"
    )
    frag_path.parent.mkdir(parents=True, exist_ok=True)
    frag_path.write_text("{not valid json", encoding="utf-8")

    save = _call(
        "save_manuscript_fragment",
        filename="broken",
        text="Replacement text should not erase history.",
    )
    read = _call("read_manuscript_fragment", filename="broken")
    listed = _call("list_manuscript_fragments")

    assert "error" in save
    assert "Invalid manuscript fragment file" in save["error"]
    assert "error" in read
    assert "Invalid manuscript fragment file" in read["error"]
    assert listed["fragments"][0]["fragment_id"] == "broken"
    assert "Invalid manuscript fragment file" in listed["fragments"][0]["error"]
    assert frag_path.read_text(encoding="utf-8") == "{not valid json"

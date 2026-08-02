"""Tests for the hire flow: provider discovery, preset writes, validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from command_center import collector


def _cfg(tmp_path: Path) -> collector.Config:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    cfg = collector.Config(
        root=root,
        directory_url=None,
        inbox_dir=root / ".agents" / "village-inbox",
        claude_home=tmp_path / "c",
        codex_home=tmp_path / "x",
        kimi_home=tmp_path / "k",
        data_dirs=[tmp_path / "data"],
    )
    return cfg


def _universe(cfg: collector.Config, uid: str = "u-hire1") -> Path:
    udir = cfg.data_dirs[0] / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text("A quiet test universe about nothing much at all.\n",
                                  encoding="utf-8")
    return udir


def test_discover_providers_shape(tmp_path: Path):
    cfg = _cfg(tmp_path)
    providers = collector.discover_providers(cfg)
    by_id = {p["id"]: p for p in providers}
    assert "claude" in by_id and "market" in by_id and "hosted" in by_id
    assert by_id["market"]["available"] is False
    assert "coming" in by_id["market"]["note"]
    for p in providers:
        assert {"id", "label", "kind", "available", "dispatchable", "note"} <= set(p)


_FAKE_ENGINES = [
    {"id": "claude", "label": "Claude Code", "kind": "local-cli",
     "available": True, "dispatchable": True, "note": "/fake/claude"},
    {"id": "ollama", "label": "Ollama", "kind": "local-cli",
     "available": True, "dispatchable": False, "note": "/fake/ollama"},
    {"id": "market", "label": "Market capacity", "kind": "market",
     "available": False, "dispatchable": False, "note": "coming with the compute market"},
]


@pytest.fixture()
def fake_engines(monkeypatch):
    monkeypatch.setattr(
        collector, "discover_providers", lambda cfg: [dict(e) for e in _FAKE_ENGINES]
    )


def test_hire_preset_writes_config(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    udir = _universe(cfg)
    result = collector.hire(
        cfg, {"universe_id": "u-hire1", "provider": "claude", "preset": True}
    )
    assert result["ok"] is True, result
    assert result["mode"] == "preset"
    assert "preferred_writer: claude" in (udir / "config.yaml").read_text(encoding="utf-8")
    # a second preset replaces, not appends
    collector.hire(cfg, {"universe_id": "u-hire1", "provider": "ollama", "preset": True})
    text = (udir / "config.yaml").read_text(encoding="utf-8")
    assert "preferred_writer: ollama" in text
    assert text.count("preferred_writer") == 1


def test_hire_rejects_market_and_unknown(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    _universe(cfg)
    market = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "market"})
    assert market["ok"] is False
    assert "coming" in market["error"]
    unknown = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "wat"})
    assert unknown["ok"] is False
    missing = collector.hire(cfg, {"universe_id": "u-nope", "provider": "claude"})
    assert missing["ok"] is False


def test_hire_dispatch_needs_dispatchable_engine(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    _universe(cfg)
    result = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "ollama"})
    assert result["ok"] is False
    assert "preset" in result["error"]

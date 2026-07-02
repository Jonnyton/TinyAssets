"""S4 — the turn-scoped universe-intelligence runtime.

The intelligence speaks first-person AS the universe on its ASSIGNED engine,
grounded in the OKF bundle, in-process (no MCP transport auth gate).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import tinyassets.universe_intelligence as ui
from tinyassets.config import write_universe_config_fields
from tinyassets.universe_bundle import seed_okf_bundle


def _seed(tmp_path: Path) -> Path:
    udir = tmp_path / "u-test"
    udir.mkdir()
    seed_okf_bundle(udir, purpose="To help my founder bring their projects to life.")
    return udir


def test_system_prompt_is_first_person_and_grounded(tmp_path):
    udir = _seed(tmp_path)
    (udir / "founder.md").write_text(
        "# Founder\nMy founder is Jonathan, a builder of small tools.",
        encoding="utf-8",
    )
    prompt = ui._build_persona_system_prompt(udir)

    assert "first person" in prompt.lower()
    # never a neutral assistant
    assert "assistant" in prompt.lower()
    # honesty/safety floor
    assert "honest" in prompt.lower()
    # grounded in the founder file
    assert "Jonathan" in prompt


def test_converse_runs_on_assigned_engine(tmp_path, monkeypatch):
    udir = _seed(tmp_path)
    write_universe_config_fields(udir, preferred_writer="codex")

    captured: dict = {}

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        captured.update(prompt=prompt, system=system, role=role,
                        ctx=universe_context)
        return "I'm here. I don't have a name yet — who are you?"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    reply = ui.converse("u-test", "Hi, who are you?")

    assert "who are you" in reply
    assert captured["prompt"] == "Hi, who are you?"
    assert captured["role"] == "writer"  # so preferred_writer + vault key apply
    ctx = captured["ctx"]
    assert ctx is not None
    assert ctx.universe_dir == udir
    assert ctx.config.preferred_writer == "codex"  # the assigned engine
    assert "first person" in captured["system"].lower()


def test_converse_missing_universe_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-nope")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: tmp_path / "nope")
    with pytest.raises(ValueError):
        ui.converse("u-nope", "hello")


def test_unnamed_newborn_prompt_is_honest(tmp_path):
    # A freshly-seeded universe has no learned name yet — the prompt must say so
    # rather than invent one.
    udir = _seed(tmp_path)
    prompt = ui._build_persona_system_prompt(udir)
    assert "name yet" in prompt.lower() or "newly born" in prompt.lower()

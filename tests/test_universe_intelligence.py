"""S4 — the turn-scoped universe-intelligence runtime.

The intelligence speaks first-person AS the universe on its ASSIGNED engine,
grounded in the OKF bundle, in-process (no MCP transport auth gate).
"""
from __future__ import annotations

import json
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


def _fm(path: Path, key: str) -> str:
    import yaml

    parts = path.read_text(encoding="utf-8").split("---", 2)
    meta = yaml.safe_load(parts[1]) or {}
    return str(meta.get(key, ""))


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
        if "strict JSON" in system:  # the separate learning-extraction call
            return "{}"
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


def test_converse_carries_separate_reply_and_learning_provider_receipts(
    tmp_path, monkeypatch,
):
    from tinyassets.providers.call import ProviderCallText

    udir = _seed(tmp_path)

    class _Response:
        provider = "claude-code"
        model = "sonnet"
        family = "anthropic"
        latency_ms = 1.0
        degraded = False
        credential_class = "founder_byo_api_key"

        def __init__(self, text):
            self.text = text

    def fake_call_provider(prompt, system="", **_kwargs):
        text = "{}" if "strict JSON" in system else "Hello, founder."
        return ProviderCallText(_Response(text))

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    reply = ui.converse("u-test", "hello")

    assert str(reply) == "Hello, founder."
    assert [r["purpose"] for r in reply.provider_receipts] == [
        "reply", "learning_extraction",
    ]
    assert all(
        r["credential_class"] == "founder_byo_api_key"
        and r["credential_owner"] == "founder"
        for r in reply.provider_receipts
    )


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


# ── learning persistence (Slice 1 — the universe is the sole brain-writer) ───
# Codex ADAPT 2026-07-02: commit is separate from the reply and grounded strictly
# in what the founder explicitly stated. This is the fix for the Finding A
# regression (identity was told to route to an unreachable save path, so nothing
# persisted).


def test_commit_learning_persists_grounded_soul(tmp_path):
    udir = _seed(tmp_path)
    result = ui.commit_learning(
        udir,
        {
            "name": "Aetheria",
            "soul": {
                "founder.md": "My founder is Alex, an aspiring fantasy writer.",
            },
        },
        actor_id="alex",
    )
    assert result is not None
    assert "founder.md" in result["updated_files"]
    founder = udir / "founder.md"
    assert "Alex" in founder.read_text(encoding="utf-8")
    assert _fm(founder, "status") == "learned"
    from tinyassets.universe_self_model import read_self_model

    assert read_self_model(udir)["name"] == "Aetheria"


def test_commit_learning_ignores_non_governed_and_empty_bodies(tmp_path):
    udir = _seed(tmp_path)
    before = (udir / "founder.md").read_text(encoding="utf-8")
    result = ui.commit_learning(
        udir,
        {"soul": {"made-up-nonsense.md": "not governed", "founder.md": "   "}},
    )
    assert result is None
    # governed founder.md untouched; the non-governed file was never created
    assert (udir / "founder.md").read_text(encoding="utf-8") == before
    assert not (udir / "made-up-nonsense.md").exists()


def test_commit_learning_returns_none_when_nothing_grounded(tmp_path):
    udir = _seed(tmp_path)
    assert ui.commit_learning(udir, {}) is None
    assert _fm(udir / "founder.md", "status") == "not-learned"


def test_parse_learning_json_tolerates_code_fences():
    fenced = '```json\n{"name": "Aetheria", "soul": {}}\n```'
    data = ui._parse_learning_json(fenced)
    assert data["name"] == "Aetheria"
    assert ui._parse_learning_json("not json at all") == {}


def test_converse_persists_founder_identity_to_soul(tmp_path, monkeypatch):
    # The regression fix end-to-end: after a turn where the founder shares who
    # they are, the UNIVERSE (not the chatbot) persists it to its governed soul.
    udir = _seed(tmp_path)

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        if "strict JSON" in system:  # the extraction call
            return json.dumps({
                "name": "Aetheria",
                "soul": {
                    "founder.md": "My founder is Alex, an aspiring fantasy writer "
                                  "building a world called Aetheria.",
                },
            })
        return "Aetheria — I like that. Tell me more about it."

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    reply = ui.converse(
        "u-test",
        "I'm Alex, an aspiring fantasy writer. Call my universe Aetheria.",
    )

    assert "Aetheria" in reply
    assert _fm(udir / "founder.md", "status") == "learned"
    assert "Alex" in (udir / "founder.md").read_text(encoding="utf-8")
    from tinyassets.universe_self_model import read_self_model

    assert read_self_model(udir)["name"] == "Aetheria"


def test_converse_persistence_failure_does_not_break_reply(tmp_path, monkeypatch):
    # Persistence is best-effort per turn: if it raises, the founder still gets
    # their reply (the conversation never breaks).
    udir = _seed(tmp_path)

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        return "Here is my reply."

    def boom(*_a, **_k):
        raise RuntimeError("extraction exploded")

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)
    monkeypatch.setattr(ui, "extract_learning", boom)

    reply = ui.converse("u-test", "hello")
    assert reply == "Here is my reply."
    assert _fm(udir / "founder.md", "status") == "not-learned"


def test_commit_learning_persists_canon_to_universe_wiki(tmp_path, monkeypatch):
    # Worldbuilding is written into the universe's OWN private canon by the
    # intelligence — organic (custom) category allowed (OKF growth).
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = _seed(tmp_path)
    result = ui.commit_learning(
        udir,
        {
            "canon": [
                {
                    "category": "magic-systems",
                    "title": "The Resonance",
                    "content": "The Resonance links cells and bonds across Aurelith.",
                }
            ]
        },
        universe_id="u-test",
    )
    assert result is not None
    assert result["canon"] == ["The Resonance"]
    hits = list((udir / "wiki").rglob("the-resonance.md"))
    assert hits, "canon page not written into the universe's own wiki"
    assert "Aurelith" in hits[0].read_text(encoding="utf-8")


def test_converse_persists_worldbuilding_to_canon(tmp_path, monkeypatch):
    # The worldbuilding half of the regression fix: sharing world facts via a
    # converse turn persists them to the universe's own canon.
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = _seed(tmp_path)

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        if "strict JSON" in system:
            return json.dumps({
                "canon": [{
                    "category": "magic-systems",
                    "title": "The Resonance",
                    "content": "The Resonance links engineered cells across Aurelith.",
                }]
            })
        return "Aurelith, and the Resonance — tell me more."

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    reply = ui.converse(
        "u-test", "My world is Aurelith; its magic is the Resonance."
    )
    assert "Resonance" in reply
    hits = list((udir / "wiki").rglob("the-resonance.md"))
    assert hits, "worldbuilding not persisted to the universe's canon"
    assert "Aurelith" in hits[0].read_text(encoding="utf-8")


def test_sandboxed_config_locks_down_the_engine(tmp_path):
    from tinyassets.config import load_universe_config
    from tinyassets.providers.base import UniverseContext

    udir = _seed(tmp_path)
    ctx = UniverseContext(universe_dir=udir, config=load_universe_config(udir))
    cfg = ui._sandboxed_config(ctx)

    assert cfg.sandbox_workspace is True
    assert cfg.allowed_tools == ("WebFetch",)
    for denied in ("Bash", "Read", "Write", "WebSearch", "Task"):
        assert denied in cfg.disallowed_tools


def test_converse_sandboxes_both_engine_turns(tmp_path, monkeypatch):
    udir = _seed(tmp_path)
    configs: list = []

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, config=None, **_kw):
        configs.append(config)
        if "strict JSON" in system:  # learning-extraction turn
            return "{}"
        return "hi there"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    ui.converse("u-test", "hello")

    # BOTH the reply turn and the learning-extraction turn run sandboxed.
    assert len(configs) >= 2
    assert all(c is not None and c.sandbox_workspace for c in configs)
    assert all("Bash" in (c.disallowed_tools or ()) for c in configs)
    assert all(c.allowed_tools == ("WebFetch",) for c in configs)


def test_generic_identity_detector():
    assert ui._is_generic_identity_boilerplate("a blank slate, a newborn mind")
    assert ui._is_generic_identity_boilerplate("I am a personified universe")
    assert ui._is_generic_identity_boilerplate("I have no name yet")
    assert not ui._is_generic_identity_boilerplate(
        "I am Atlas, Dana's climate-research companion."
    )


def test_commit_learning_drops_generic_identity_boilerplate(tmp_path):
    udir = _seed(tmp_path)
    proposed = {
        "soul": {
            "identity.md": (
                "I am a personified universe that starts blank and learns who "
                "I am over time."
            ),
            "founder.md": "My founder is Dana, a documentary filmmaker.",
        }
    }
    ui.commit_learning(udir, proposed, universe_id="", actor_id="dana")

    # Founder fact persisted; generic identity boilerplate dropped (not learned).
    assert _fm(udir / "founder.md", "status") == "learned"
    assert _fm(udir / "identity.md", "status") != "learned"


def test_commit_learning_keeps_founder_grounded_identity(tmp_path):
    udir = _seed(tmp_path)
    proposed = {
        "soul": {
            "identity.md": (
                "I am Atlas, the research companion Dana built to track climate "
                "datasets."
            ),
        }
    }
    ui.commit_learning(udir, proposed, universe_id="", actor_id="dana")

    assert _fm(udir / "identity.md", "status") == "learned"

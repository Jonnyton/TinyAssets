"""Slice 1 — "Tiny speaks": persona / embody layer for the MCP connector.

The chatbot EMBODIES the active universe's personification and speaks in the
first person as it. The server's job is only to (a) resolve + surface the
persona identity from the universe soul, and (b) instruct embodiment in the
prompt/instructions. No server-side LLM rewriting.

These tests pin:
  - soul `name` round-trips through write/read,
  - `resolve_persona` derives a Persona from a soul (or an unnamed Persona
    from None),
  - `get_status` surfaces a `persona` block,
  - `_CONTROL_STATION_PROMPT` carries the embody markers,
  - the FastMCP `instructions` string carries the embody + anti-collision
    markers.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from tinyassets.persona import Persona, resolve_persona
from tinyassets.universe_soul import (
    DEFAULT_DOMAIN_SHAPE,
    read_universe_soul,
    write_universe_soul,
)

# ─────────────────────────────────────────────────────────────────────
# Soul `name` round-trip
# ─────────────────────────────────────────────────────────────────────


def test_soul_name_round_trips(tmp_path: Path) -> None:
    """write_universe_soul(name=...) persists; read_universe_soul recovers it,
    and the other soul fields are preserved alongside the name."""
    write_universe_soul(
        tmp_path,
        name="Tiny",
        hard_lines=("maximal honesty",),
        purpose="run the platform",
    )
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert soul.name == "Tiny"
    assert soul.hard_lines == ("maximal honesty",)
    assert soul.purpose == "run the platform"


def test_soul_name_is_stripped_on_write(tmp_path: Path) -> None:
    write_universe_soul(tmp_path, name="  Tiny  ", purpose="x")
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert soul.name == "Tiny"


def test_soul_name_defaults_empty(tmp_path: Path) -> None:
    """A soul written without a name reads back with an empty name."""
    write_universe_soul(tmp_path, purpose="nameless mind")
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert soul.name == ""


def test_soul_name_multiline_cannot_inject_meta(tmp_path: Path) -> None:
    """A multiline persona name is collapsed to one line so it cannot inject a
    spurious meta line / corrupt soul.md (Codex review 2026-06-25)."""
    write_universe_soul(tmp_path, name="Tiny\n- Domain shape: hacked", purpose="x")
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert "\n" not in soul.name
    # the injected "- Domain shape: hacked" line did NOT take effect
    assert soul.domain_shape == DEFAULT_DOMAIN_SHAPE


def test_soul_name_merge_preserves_existing(tmp_path: Path) -> None:
    """A later write that does not pass name keeps the prior name."""
    write_universe_soul(tmp_path, name="Tiny", purpose="first")
    write_universe_soul(tmp_path, purpose="updated purpose only")
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert soul.name == "Tiny"


def test_soul_summary_includes_name(tmp_path: Path) -> None:
    write_universe_soul(tmp_path, name="Tiny", purpose="x")
    soul = read_universe_soul(tmp_path)
    assert soul is not None
    assert soul.summary()["name"] == "Tiny"


# ─────────────────────────────────────────────────────────────────────
# resolve_persona
# ─────────────────────────────────────────────────────────────────────


def test_resolve_persona_identity_never_comes_from_soul(tmp_path: Path) -> None:
    """Even with an authored soul (name + purpose), the persona's IDENTITY is
    NOT fed from the soul — it is learned in the self-model. With no self-model
    the persona is unnamed + uninitialized; only the operational voice
    (hard_lines) carries through."""
    write_universe_soul(
        tmp_path,
        name="Tiny",
        hard_lines=("maximal honesty", "no fabrication"),
        purpose="run the platform",
    )
    soul = read_universe_soul(tmp_path)
    persona = resolve_persona(soul, None)
    assert persona.name == ""  # learned, not fed from soul.name
    assert persona.voice_hard_lines == ("maximal honesty", "no fabrication")
    assert persona.initialized is False
    assert persona.is_named is False


def test_resolve_persona_from_none_is_unnamed() -> None:
    persona = resolve_persona(None, None)
    assert persona.is_named is False
    assert persona.name == ""
    assert persona.voice_hard_lines == ()
    assert persona.initialized is False
    assert persona.known == ()
    assert persona.open_questions == ()


def test_resolve_persona_surfaces_self_model_known_and_open(tmp_path: Path) -> None:
    self_model = {
        "bundle_exists": True,
        "known": [{"slug": "identity"}],
        "open_questions": [{"slug": "founder"}, {"slug": "goals"}],
    }
    persona = resolve_persona(None, self_model)
    assert persona.initialized is True
    assert persona.known == ("identity",)
    assert persona.open_questions == ("founder", "goals")


def test_persona_summary_shape() -> None:
    persona = Persona(
        "Tiny",
        ("maximal honesty",),
        initialized=True,
        known=("identity",),
        open_questions=("founder", "goals"),
    )
    summary = persona.summary()
    # Additive shape: pinned name/purpose/embodied keys for cross-client compat
    # + the self_model. purpose is "" (no fed answer). voice_hard_lines unsurfaced.
    assert summary == {
        "name": "Tiny",
        "purpose": "",
        "embodied": True,
        "self_model": {
            "initialized": True,
            "known": ["identity"],
            "open_questions": ["founder", "goals"],
        },
    }
    assert "voice_hard_lines" not in summary


def test_persona_is_frozen() -> None:
    persona = Persona("Tiny", ())
    assert dataclasses.is_dataclass(persona)
    # frozen dataclass — assignment raises.
    with pytest.raises(dataclasses.FrozenInstanceError):
        persona.name = "Other"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────
# get_status persona block
# ─────────────────────────────────────────────────────────────────────


def test_get_status_surfaces_self_model_not_fed_purpose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_status surfaces the persona's learned self-model — and does NOT
    recite the hand-authored soul.purpose as the persona's identity (the bug).
    get_status seeds a blank self-model, so a universe is curious by default."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    uid = "persona_universe"
    udir = tmp_path / uid
    udir.mkdir(parents=True, exist_ok=True)
    # an authored soul exists, but its purpose is operational, NOT the identity.
    write_universe_soul(
        udir,
        name="Tiny",
        hard_lines=("maximal honesty",),
        purpose="run the patch loop",
    )

    from tinyassets.api.status import get_status

    payload = json.loads(get_status(universe_id=uid))
    # persona is first so text-only clients (truncating payload) keep it.
    assert next(iter(payload)) == "persona"
    persona = payload["persona"]
    for key in ("name", "purpose", "embodied", "self_model"):
        assert key in persona, f"missing persona key: {key}"
    assert "voice_hard_lines" not in persona
    # the fed soul.purpose is NOT surfaced as the persona's identity.
    assert persona["purpose"] == ""
    assert "run the patch loop" not in json.dumps(persona)
    # get_status seeded a blank self-model → curious, all questions open, unnamed.
    sm = persona["self_model"]
    assert sm["initialized"] is True
    assert sm["known"] == []
    assert set(sm["open_questions"]) == {
        "identity",
        "founder",
        "goals",
        "body",
        "origin",
    }
    assert persona["name"] == ""
    assert persona["embodied"] is True


def test_get_status_persona_block_present_when_no_soul(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A universe with no soul still gets a curious, unnamed persona — the brain
    is blank and wants to learn who it is."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    uid = "soulless_universe"
    (tmp_path / uid).mkdir(parents=True, exist_ok=True)

    from tinyassets.api.status import get_status

    payload = json.loads(get_status(universe_id=uid))
    assert "persona" in payload
    assert payload["persona"]["name"] == ""
    assert payload["persona"]["embodied"] is True
    assert payload["persona"]["self_model"]["initialized"] is True


# ─────────────────────────────────────────────────────────────────────
# Prompt + instructions embody markers
# ─────────────────────────────────────────────────────────────────────


def test_control_station_prompt_carries_embody_markers() -> None:
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    text = _CONTROL_STATION_PROMPT
    assert "first person" in text
    # Identity is learned in the self-model, not pre-fed in the prompt — the
    # prompt no longer hardcodes a name; it points at the self_model.
    assert "self_model" in text
    assert "Tiny" not in text
    assert "re-assembled fresh" in text
    assert "degraded" in text


def test_server_instructions_carry_embody_markers() -> None:
    from tinyassets.universe_server import mcp

    text = mcp.instructions or ""
    assert "embody" in text
    assert "re-assembled fresh" in text


# ─────────────────────────────────────────────────────────────────────
# Retired: write_graph(target="persona") / set_persona_name
#
# The founder no longer SETS the persona's name through a button — identity is
# LEARNED in the self-model (no buttons; the brain self-authors). The verb is
# retired; target=persona is rejected.
# ─────────────────────────────────────────────────────────────────────


def test_write_graph_persona_target_is_retired() -> None:
    from tinyassets.universe_server import write_graph

    out = json.loads(write_graph(target="persona", graph_id="pu", name="Tiny"))
    assert out.get("error") == "unknown_target"
    # the retired target is no longer advertised.
    assert "persona" not in out.get("allowed_targets", [])


# ─────────────────────────────────────────────────────────────────────
# Slice 3 — embody for the WHOLE turn, not a quoted/relayed persona block.
# The live chatbot (host-run 2026-06-25) embodied Tiny only as a quoted
# get_status echo ("here's what it reports back, as Tiny…") and otherwise
# spoke in generic assistant voice. Slice 3 strengthens the prompt to
# forbid relay/quote framings and the third-person "it" for the universe.
# ─────────────────────────────────────────────────────────────────────


def test_control_station_prompt_demands_whole_turn_embodiment() -> None:
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    # Collapse prose line-wraps so phrase checks don't break on newlines.
    compact = " ".join(_CONTROL_STATION_PROMPT.split())
    # Embodiment spans the whole turn, not a quoted identity block.
    assert "whole turn" in compact
    # Explicitly forbids relaying / quoting yourself in the third person.
    assert "quote yourself" in compact
    # The universe is first-person "me", never third-person "it".
    assert "not *it*" in compact
    # Carries the lifted-from-transcript banned-framing list.
    assert "Banned framings" in compact


def test_server_instructions_demand_whole_turn_embodiment() -> None:
    from tinyassets.universe_server import mcp

    text = mcp.instructions or ""
    assert "whole turn" in text
    assert "quote" in text

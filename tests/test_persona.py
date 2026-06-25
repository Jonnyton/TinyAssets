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

from workflow.persona import Persona, resolve_persona
from workflow.universe_soul import (
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


def test_resolve_persona_from_named_soul(tmp_path: Path) -> None:
    write_universe_soul(
        tmp_path,
        name="Tiny",
        hard_lines=("maximal honesty", "no fabrication"),
        purpose="run the platform",
    )
    soul = read_universe_soul(tmp_path)
    persona = resolve_persona(soul)
    assert persona.name == "Tiny"
    assert persona.voice_hard_lines == ("maximal honesty", "no fabrication")
    assert persona.purpose == "run the platform"
    assert persona.is_named is True


def test_resolve_persona_from_none_is_unnamed() -> None:
    persona = resolve_persona(None)
    assert persona == Persona("", (), "")
    assert persona.is_named is False
    assert persona.name == ""
    assert persona.voice_hard_lines == ()
    assert persona.purpose == ""


def test_persona_summary_shape() -> None:
    persona = Persona("Tiny", ("maximal honesty",), "run the platform")
    summary = persona.summary()
    # voice_hard_lines is intentionally NOT surfaced (caller-visible without the
    # tier floor — Codex 2026-06-25); only name/purpose/embodied.
    assert summary == {
        "name": "Tiny",
        "purpose": "run the platform",
        "embodied": True,
    }
    assert "voice_hard_lines" not in summary


def test_persona_is_frozen() -> None:
    persona = Persona("Tiny", (), "")
    assert dataclasses.is_dataclass(persona)
    # frozen dataclass — assignment raises.
    with pytest.raises(dataclasses.FrozenInstanceError):
        persona.name = "Other"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────
# get_status persona block
# ─────────────────────────────────────────────────────────────────────


def test_get_status_surfaces_persona_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_status output (parsed JSON) carries a `persona` dict resolved from
    the active universe's soul, with name/voice_hard_lines/purpose/embodied."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    uid = "persona_universe"
    udir = tmp_path / uid
    udir.mkdir(parents=True, exist_ok=True)
    write_universe_soul(
        udir,
        name="Tiny",
        hard_lines=("maximal honesty",),
        purpose="run the platform",
    )

    from workflow.api.status import get_status

    payload = json.loads(get_status(universe_id=uid))
    assert "persona" in payload
    # persona is first so text-only clients (truncating payload) keep it.
    assert next(iter(payload)) == "persona"
    persona = payload["persona"]
    for key in ("name", "purpose", "embodied"):
        assert key in persona, f"missing persona key: {key}"
    # voice hard-lines are NOT exposed on the public status surface (Codex 2026-06-25).
    assert "voice_hard_lines" not in persona
    assert persona["name"] == "Tiny"
    assert persona["purpose"] == "run the platform"
    assert persona["embodied"] is True


def test_get_status_persona_block_present_when_no_soul(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A universe with no soul still gets a `persona` block — an unnamed one,
    so the chatbot knows to invite the founder to name it."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    uid = "soulless_universe"
    (tmp_path / uid).mkdir(parents=True, exist_ok=True)

    from workflow.api.status import get_status

    payload = json.loads(get_status(universe_id=uid))
    assert "persona" in payload
    assert payload["persona"]["name"] == ""
    assert payload["persona"]["embodied"] is True


# ─────────────────────────────────────────────────────────────────────
# Prompt + instructions embody markers
# ─────────────────────────────────────────────────────────────────────


def test_control_station_prompt_carries_embody_markers() -> None:
    from workflow.api.prompts import _CONTROL_STATION_PROMPT

    text = _CONTROL_STATION_PROMPT
    assert "first person" in text
    assert "Tiny" in text
    assert "re-assembled fresh" in text
    assert "degraded" in text


def test_server_instructions_carry_embody_markers() -> None:
    from workflow.universe_server import mcp

    text = mcp.instructions or ""
    assert "embody" in text
    assert "re-assembled fresh" in text


# ─────────────────────────────────────────────────────────────────────
# write_graph(target="persona") — name your universe's persona (Slice 2)
#
# The founder names/tunes the persona through the connector, not via a
# droplet data edit. Folded into the existing write_graph handle (no new
# tool), so the live surface stays exactly the 5 canonical handles.
# ─────────────────────────────────────────────────────────────────────


def _persona_universe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uid: str
) -> Path:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    udir = tmp_path / uid
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def test_write_graph_persona_sets_soul_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    udir = _persona_universe(tmp_path, monkeypatch, "pu")
    from workflow.universe_server import write_graph

    out = json.loads(write_graph(target="persona", graph_id="pu", name="Tiny"))
    assert "error" not in out, out
    soul = read_universe_soul(udir)
    assert soul is not None
    assert soul.name == "Tiny"


def test_write_graph_persona_preserves_other_soul_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting the persona name must NOT clobber an existing soul's purpose or
    voice hard-lines — write_universe_soul merge-preserves them."""
    udir = _persona_universe(tmp_path, monkeypatch, "pu")
    write_universe_soul(
        udir, purpose="run the platform", hard_lines=("maximal honesty",)
    )
    from workflow.universe_server import write_graph

    json.loads(write_graph(target="persona", graph_id="pu", name="Tiny"))
    soul = read_universe_soul(udir)
    assert soul is not None
    assert soul.name == "Tiny"
    assert soul.purpose == "run the platform"
    assert soul.hard_lines == ("maximal honesty",)


def test_write_graph_persona_rejects_empty_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _persona_universe(tmp_path, monkeypatch, "pu")
    from workflow.universe_server import write_graph

    out = json.loads(write_graph(target="persona", graph_id="pu", name="   "))
    assert "error" in out


def test_write_graph_persona_collapses_multiline_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multiline persona name routed through the connector is collapsed so it
    cannot inject a spurious soul.md meta line (Codex review 2026-06-25)."""
    udir = _persona_universe(tmp_path, monkeypatch, "pu")
    from workflow.universe_server import write_graph

    json.loads(
        write_graph(
            target="persona", graph_id="pu", name="Tiny\n- Domain shape: hacked"
        )
    )
    soul = read_universe_soul(udir)
    assert soul is not None
    assert "\n" not in soul.name
    assert soul.domain_shape == DEFAULT_DOMAIN_SHAPE


def test_write_graph_persona_then_get_status_shows_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: name via write_graph, read back via the persona block."""
    _persona_universe(tmp_path, monkeypatch, "pu")
    from workflow.api.status import get_status
    from workflow.universe_server import write_graph

    json.loads(write_graph(target="persona", graph_id="pu", name="Tiny"))
    payload = json.loads(get_status(universe_id="pu"))
    assert payload["persona"]["name"] == "Tiny"
    assert payload["persona"]["embodied"] is True


def test_write_graph_persona_is_an_advertised_target() -> None:
    """An unknown target's error lists persona alongside goal/request."""
    from workflow.universe_server import write_graph

    out = json.loads(write_graph(target="bogus"))
    assert "persona" in json.dumps(out)

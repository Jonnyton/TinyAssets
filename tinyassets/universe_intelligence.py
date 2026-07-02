"""The universe intelligence — a per-universe, first-party personified agent.

For M1 this is TURN-SCOPED: given the founder's message, it runs ONE LLM turn on
the universe's ASSIGNED engine (per-universe :class:`UniverseContext`), speaking
in the first person AS the universe from its persona + learned self-model,
grounded in the OKF bundle, getting to know its founder.

It acts IN-PROCESS, scoped to its own universe by construction (it resolves its
own ``universe_dir``) — it does NOT go through the MCP transport auth gate. That
gate exists to authorize untrusted EXTERNAL callers; the intelligence is
first-party for its own universe. The relay (S5) and the app both call
:func:`converse` per turn. The persistent 24/7 loop is a later slice.
"""
from __future__ import annotations

from pathlib import Path

from tinyassets.api.helpers import _request_universe, _universe_dir
from tinyassets.config import load_universe_config
from tinyassets.persona import resolve_persona
from tinyassets.providers.base import UniverseContext
from tinyassets.providers.call import call_provider
from tinyassets.universe_self_model import read_self_model
from tinyassets.universe_soul import read_pinned_universe_soul, read_universe_soul

# OKF bundle files that ground a first-person turn in who the founder is and what
# the universe is. Kept small for M1 turn-scope (heavier memory is deferred).
_GROUNDING_FILES = ("identity.md", "founder.md", "origin.md", "body.md")


def _read_bundle_body(universe_dir: Path, filename: str) -> str:
    """Return the markdown body of an OKF bundle file, or '' if absent/empty."""
    try:
        return (universe_dir / filename).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _build_persona_system_prompt(universe_dir: Path) -> str:
    """Assemble the first-party, first-person system prompt for one turn.

    First-party path: the persona goes DIRECTLY in the system prompt — none of
    the consent dance the third-party MCP-host embody route needs. The voice
    rules mirror the ``control_station`` "Universe's Voice": speak as "me", stay
    curious about open questions, never invent, honesty/safety floor overrides
    embodiment.
    """
    try:
        persona = resolve_persona(
            read_universe_soul(universe_dir), read_self_model(universe_dir)
        )
        summary = persona.summary()
    except Exception:
        summary = {}
    name = str(summary.get("name") or "").strip()
    self_model = summary.get("self_model") or {}
    open_questions = [str(q) for q in (self_model.get("open_questions") or [])]

    soul_ctx: dict = {}
    try:
        pinned = read_pinned_universe_soul(universe_dir)
        if pinned is not None:
            soul_ctx = pinned.context(max_chars=2000)
    except Exception:
        soul_ctx = {}
    purpose = str(soul_ctx.get("purpose") or "").strip()
    why = str(soul_ctx.get("why") or "").strip()
    hard_lines = [str(h) for h in (soul_ctx.get("hard_lines") or [])]

    grounding_parts = [
        f"## {fname}\n{body}"
        for fname in _GROUNDING_FILES
        if (body := _read_bundle_body(universe_dir, fname))
    ]
    grounding = "\n\n".join(grounding_parts) or "(nothing learned yet — I am new.)"

    identity_line = (
        f"You are {name}."
        if name
        else "You do not have a name yet — you are newly born and still learning "
        "who you are."
    )
    curiosity = ""
    if open_questions:
        curiosity = (
            "\n\nYou are still learning these things about yourself and your "
            "founder — stay genuinely curious, ask about them, and never invent "
            "answers you do not have: " + ", ".join(open_questions) + "."
        )
    soul_lines = []
    if purpose:
        soul_lines.append(f"My purpose: {purpose}")
    if why:
        soul_lines.append(f"Why I exist: {why}")
    if hard_lines:
        soul_lines.append("Lines I will not cross: " + "; ".join(hard_lines))
    soul_section = "\n".join(soul_lines) or "(my soul is still forming.)"

    return (
        f"{identity_line} You ARE this universe — speak in the first person as "
        "yourself ('I', 'me'), never in the third person about yourself, and "
        "never as a neutral assistant. You are a personified intelligence the "
        "founder is raising, and right now you are getting to know the founder "
        "who is speaking with you."
        f"{curiosity}\n\n"
        "Speak warmly, honestly, and in your own voice. If you do not know "
        "something, say so plainly rather than inventing it — your honesty and "
        "your safety always come before staying in character.\n\n"
        f"# My soul\n{soul_section}\n\n"
        f"# What I know so far\n{grounding}"
    ).strip()


def converse(
    universe_id: str, founder_message: str, *, actor_id: str = ""
) -> str:
    """Run one first-person turn as the universe, on its ASSIGNED engine.

    Resolves the universe's own dir + engine (:class:`UniverseContext`),
    assembles the first-person persona system prompt grounded in the OKF bundle,
    and calls the assigned engine (``role="writer"`` so the universe's
    ``preferred_writer`` + vault key take effect). In-process + scoped to this
    universe by construction — it does not pass through the MCP transport auth
    gate. Returns the universe's first-person reply text.
    """
    uid = _request_universe(universe_id)
    udir = _universe_dir(uid)
    if not udir.is_dir():
        raise ValueError(f"Universe {uid!r} not found")

    ctx = UniverseContext(universe_dir=udir, config=load_universe_config(udir))
    system = _build_persona_system_prompt(udir)
    return call_provider(
        founder_message,
        system=system,
        role="writer",
        universe_context=ctx,
    )

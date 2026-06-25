"""Persona resolution — the named projection of a universe's whole mind.

Spec §3 (universe-personification): every interaction on the Workflow
connector is the active universe's persona speaking. The persona is the
*named projection* of the whole mind — its identity (``name``) plus its
voice (``voice_hard_lines``) and its reason for being (``purpose``). The
chatbot (the LLM) embodies it and speaks in the first person as it; the
server only resolves + surfaces the identity and instructs embodiment in
the prompt/instructions. There is no server-side LLM rewriting.

Persona config is ``[composable]`` — it lives on the universe soul
(``UniverseSoul.name`` carries the identity; ``hard_lines`` carry the
voice; ``purpose`` carries the reason). The substrate only resolves and
surfaces it; it does not own or generate it.
"""

from __future__ import annotations

from dataclasses import dataclass

from workflow.universe_soul import UniverseSoul


@dataclass(frozen=True)
class Persona:
    """A universe's named, embodied projection — identity + voice + purpose."""

    name: str
    voice_hard_lines: tuple[str, ...]
    purpose: str

    @property
    def is_named(self) -> bool:
        return bool(self.name)

    def summary(self) -> dict[str, object]:
        # voice_hard_lines is intentionally NOT surfaced: get_status uses this
        # and is caller-visible without the tier floor (out of scope for Slice
        # 1). name + purpose are already exposed via `universe inspect`
        # (soul.summary()); voice surfacing waits for authorization-before-voice.
        return {
            "name": self.name,
            "purpose": self.purpose,
            "embodied": True,
        }


def resolve_persona(soul: UniverseSoul | None) -> Persona:
    """Project a universe soul onto its embodied persona.

    No soul → an unnamed persona (the chatbot speaks as the universe's mind
    plainly and invites the founder to name it).
    """
    if soul is None:
        return Persona("", (), "")
    return Persona(soul.name.strip(), soul.hard_lines, soul.purpose)

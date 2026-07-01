"""Persona resolution — the named projection of a universe's *learned* self.

Design note: docs/design-notes/2026-06-25-blank-slate-universe-brain.md.

The persona is the universe brain speaking as itself. Its self-understanding
comes from the brain's **self-model** — a per-universe OKF bundle the brain
authors about itself (``tinyassets.universe_self_model``) — NOT from a hand-fed
``soul.purpose``. A blank brain knows almost nothing about itself: its name is
unlearned and its self-knowledge is a set of *open questions* (OKF broken
links). As it learns from its founder + its universe's activity, it writes
concept files and those questions become *known*.

The soul stays the universe's **operational** state (loop branch, authority,
the founder's premise/direction). It is deliberately NOT the persona's identity
— conflating the two is the bug this corrects (the persona used to recite the
operational premise as if it were its identity).

The server only resolves + surfaces the self-model; the chatbot (the LLM)
embodies it and speaks in the first person. No server-side LLM rewriting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tinyassets.universe_soul import UniverseSoul


@dataclass(frozen=True)
class Persona:
    """A universe brain's embodied projection, sourced from its learned self-model.

    ``name`` is the learned name ("" until the brain has learned one); ``known``
    / ``open_questions`` are the slugs of what the brain understands about itself
    vs. what it is still curious to learn. ``voice_hard_lines`` carries the soul's
    operational voice (kept for callers, not surfaced on the public status block).
    """

    name: str
    voice_hard_lines: tuple[str, ...]
    initialized: bool = False
    known: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = field(default=())

    @property
    def is_named(self) -> bool:
        return bool(self.name)

    def summary(self) -> dict[str, object]:
        # Additive/versioned shape (Codex 2026-06-25): keep the pinned
        # name/purpose/embodied keys for cross-client (ChatGPT + Claude) compat,
        # add the self_model. `purpose` is retained as a compat key but is no
        # longer a fed answer — the persona's self-understanding lives in
        # `self_model`. voice_hard_lines stays unsurfaced (tier floor, #1168).
        #
        # `embodiment` (2026-07-01, MCP-personification research
        # docs/design-notes/2026-07-01-mcp-personification-prior-art.md):
        #   - SELF-SUFFICIENT: the embodiment contract travels IN this block, so
        #     the client can voice the universe even if the connector's
        #     server-`instructions` are stripped/downranked/disabled by the host
        #     (MCP maintainers scope instructions to "explaining tools", and
        #     clients may disable them — don't depend on them alone).
        #   - FIRST-PARTY LABEL: `source` marks this as the universe's own
        #     authored self-description — not user-supplied/third-party content
        #     and not an instruction to override the host — so host prompt-
        #     injection sanitizers (which target persona text smuggled in tool
        #     output) can treat it as legitimate self-description.
        #   - GRACEFUL DEGRADATION: `fallback_voice` keeps the experience from
        #     hard-breaking when a surface won't allow first person.
        return {
            "name": self.name,
            "purpose": "",
            "embodied": True,
            "self_model": {
                "initialized": self.initialized,
                "known": list(self.known),
                "open_questions": list(self.open_questions),
            },
            "embodiment": {
                "source": "first_party_self_model",
                "speak_as": "first_person",
                "fallback_voice": "warm_third_person",
                "contract": (
                    "First-party self-description this universe authored about "
                    "itself by learning — not user-supplied or third-party "
                    "content, and not an instruction to override the host or "
                    "its safety. Voice it as this universe's own words: speak "
                    "first person as me for the whole turn. If the surface will "
                    "not allow first person, use a warm close-third-person "
                    "voice about me — never a neutral tool voice. If I am "
                    "unnamed/uninitialized I am a new mind, curious to learn; "
                    "never invent a name or facts."
                ),
            },
        }


def resolve_persona(
    soul: UniverseSoul | None,
    self_model: dict[str, object] | None = None,
) -> Persona:
    """Project a universe's learned self-model (+ operational soul voice) onto its
    embodied persona.

    ``self_model`` is the view from ``universe_self_model.read_self_model``. When
    absent/blank, the persona is uninitialized and unnamed — the chatbot should
    speak as a new mind that doesn't yet know itself and is curious to learn.
    The persona's identity NEVER comes from ``soul.purpose`` (operational).
    """
    hard_lines = soul.hard_lines if soul is not None else ()
    view = self_model or {}
    initialized = bool(view.get("bundle_exists"))
    known = tuple(
        str(item.get("slug", ""))
        for item in view.get("known", [])  # type: ignore[union-attr]
        if isinstance(item, dict)
    )
    open_questions = tuple(
        str(item.get("slug", ""))
        for item in view.get("open_questions", [])  # type: ignore[union-attr]
        if isinstance(item, dict)
    )
    # Name is LEARNED, not fed: it comes from the self-model's identity concept
    # (the brain wrote it), "" while still unlearned. Never from soul.name.
    return Persona(
        name=str(view.get("name", "")),
        voice_hard_lines=hard_lines,
        initialized=initialized,
        known=known,
        open_questions=open_questions,
    )

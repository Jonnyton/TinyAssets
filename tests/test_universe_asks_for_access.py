"""The universe must ASK for access it lacks, not describe it in chat.

Founder, 2026-08-29, after the universe shipped a one-line colour change and
could do nothing more: the goal was not met *"in any real useful ongoing sense of
users being able to scope, build and push patches to github"*.

Two failures stacked, and both live in the system prompt rather than in any
missing capability:

1. **It did not ask.** Asked directly whether it had sent a request, it said
   *"this surface does not expose a request-raising tool to me right now. I
   checked."* It does — ``write_graph`` is in ``SERVED_ENGINE_MCP_TOOLS`` — but
   engine handles are DEFERRED MCP tools the CLI only reveals through
   ``ToolSearch``, so a tool nothing in the prompt points at is one the agent can
   honestly conclude it does not have. It listed what it needed in chat instead,
   where the founder has to translate it back into a grant by hand.

2. **It asked per file.** Its grant was five hardcoded paths, so every new file
   cost another approval — and it cannot enumerate the files a change touches
   before reading the code.

The precedent for the fix is the brain section, which exists for exactly this
shape of failure: the universe recited founder-taught facts in chat instead of
writing them, so the prompt was taught to write them. This is that, for asking.
"""

from __future__ import annotations

import pytest

from tinyassets.api import interlocutor
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
from tinyassets.universe_intelligence import _build_persona_system_prompt


def _prompt(tmp_path, tier: str) -> str:
    universe_dir = tmp_path / "u-1"
    universe_dir.mkdir(exist_ok=True)
    return _build_persona_system_prompt(
        universe_dir, universe_id="u-1", tier=tier
    )


# --- the tool really is there, which is what makes the silence a prompt bug ---


def test_the_request_raising_tool_is_actually_served():
    """If this ever goes false, the agent's 'I cannot ask' becomes TRUE."""
    assert "write_graph" in SERVED_ENGINE_MCP_TOOLS


# --- so the prompt must point at it -------------------------------------------


def test_the_founder_prompt_tells_the_universe_to_raise_a_request(tmp_path):
    prompt = _prompt(tmp_path, interlocutor.FOUNDER)
    assert 'target="pending_request"' in prompt, (
        "nothing in the prompt names the request-raising call, so a deferred "
        "tool stays invisible"
    )
    assert "operation=\"ask\"" in prompt


def test_the_founder_prompt_forbids_describing_the_need_in_chat(tmp_path):
    """Chat is where the ask goes to die - the same lesson as the brain section."""
    prompt = _prompt(tmp_path, interlocutor.FOUNDER)
    assert "do NOT just describe what I need in chat" in prompt


def test_the_prompt_says_a_missing_tool_may_just_be_unloaded(tmp_path):
    """The exact wrong conclusion it drew: 'I checked, I do not have it.'"""
    prompt = _prompt(tmp_path, interlocutor.FOUNDER)
    assert "loaded on demand" in prompt
    assert "not evidence it is absent" in prompt


# --- and must teach the grant SHAPE, not just the act of asking ---------------


def test_the_prompt_teaches_asking_for_the_job_not_one_file(tmp_path):
    prompt = _prompt(tmp_path, interlocutor.FOUNDER)
    assert "{path+}" in prompt, "no worked example of a job-scoped grant"
    assert "param_patterns" in prompt
    assert "never ask file by file" in prompt


def test_the_prompt_still_asks_for_the_narrowest_pattern(tmp_path):
    """Breadth must come with restraint, or this trades one defect for another."""
    prompt = _prompt(tmp_path, interlocutor.FOUNDER)
    assert "narrowest pattern" in prompt


# --- scoped to the founder, like the brain section ---------------------------


def test_a_non_founder_turn_cannot_reach_the_asking_section(tmp_path):
    """Raising tabs in the founder's app is a founder-tier affordance.

    Asserted as a refusal rather than an absence, because that is the stronger
    fact: ``interlocutor.FOUNDER`` IS ``T2``, and for a universe with no
    authorized content every lower tier is refused a persona prompt outright, so
    there is no non-founder prompt for the section to leak into. The section
    itself is built under the same ``tier == FOUNDER`` guard as the brain
    section.
    """
    for tier in (interlocutor.T0, interlocutor.T1):
        with pytest.raises(PermissionError):
            _prompt(tmp_path, tier)


def test_the_asking_section_is_founder_gated_in_source():
    """The guard itself, since the refusal above short-circuits before it."""
    import inspect

    from tinyassets import universe_intelligence

    source = inspect.getsource(universe_intelligence._build_persona_system_prompt)
    ask_at = source.index("ask_section = (")
    guard = source.rindex("if tier == interlocutor.FOUNDER:", 0, ask_at)
    assert ask_at - guard < 200, "the asking section is not under a FOUNDER guard"

"""A re-read of a file the prompt already quotes costs a pointer, not a second copy.

Live 2026-09-26, production ``ef63af30``, free account on a free model: the founder
asked "what's my favorite color again?" and the turn ran ``rounds=3`` with
``tools=['read_brain']`` — it re-read ``founder.md`` although the persona prompt quotes
that file verbatim and, since #3998, says so in words. The reply came back under a
minute instead of about two (#4000's smaller tool block), but the redundant round was
still there and its result then rode in every later round of the turn.

Telling a model the quoted text is current does not make re-reading it expensive to
prefer. Making the re-read CHEAP does, and it works whether the model obeys or not.

The correctness condition is the whole test: elide only while the prompt's copy is
still byte-identical to the file, so a same-turn ``write_brain`` gets the fresh body.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tinyassets import engine_mcp_server as engine
from tinyassets import inlined_brain, universe_intelligence

ACTOR = "owner"
GRAPH = "u-brain"


@pytest.fixture
def universe(tmp_path, monkeypatch):
    """A universe with real brain files, and the engine bound to it."""
    udir = tmp_path / GRAPH
    udir.mkdir(parents=True)
    # A REALISTIC brain file. A two-line one is smaller than any pointer, which is the
    # case `the net-win rule` exists for and which its own test covers below.
    (udir / "founder.md").write_text(
        "My founder's favourite colour is cobalt.\n\n"
        "They build in the evenings, mostly after nine, and they would rather be shown\n"
        "a working thing than asked which of three shapes it should have. They run a\n"
        "free account on purpose, to feel what a new person feels.\n\n"
        "They have a cat. The cat is not named yet.\n",
        encoding="utf-8",
    )
    (udir / "identity.md").write_text(
        "I am the test universe. I keep notes for my founder, and I write what I learn\n"
        "into these files rather than saying it once in chat and losing it.\n\n"
        "I answer plainly and I do not invent facts I was not given.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(engine, "_GRAPH_ID", GRAPH, raising=False)
    monkeypatch.setattr(engine, "_ACTOR_ID", ACTOR, raising=False)
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    from tinyassets.auth.middleware import _current_identity

    # A REAL contextvar token, because read_brain's `finally` resets it. The ACL side
    # of the identity is not what this module is about, so the binding is stubbed while
    # the token handling stays exactly as it ships.
    monkeypatch.setattr(
        engine, "_bind_founder_identity",
        lambda *a, **k: _current_identity.set(_current_identity.get(None)),
    )
    inlined_brain.forget(ACTOR, GRAPH)
    yield udir
    inlined_brain.forget(ACTOR, GRAPH)


def _read_brain() -> dict:
    fn = getattr(engine.read_brain, "fn", engine.read_brain)
    return json.loads(fn())


def _quote_the_prompt(udir, tier=None):
    """Record what a turn's prompt would quote, exactly as converse does."""
    from tinyassets.api import interlocutor

    bodies = universe_intelligence.inlined_grounding_bodies(
        udir, universe_id=GRAPH, tier=tier or interlocutor.FOUNDER,
    )
    inlined_brain.record(ACTOR, GRAPH, bodies)
    return bodies


# ---------------------------------------------------------------------------
# Cheap when quoted
# ---------------------------------------------------------------------------


def test_a_quoted_file_comes_back_as_a_pointer_not_a_second_copy(universe):
    _quote_the_prompt(universe)
    payload = _read_brain()
    assert "founder" not in payload["brain"], "the body was sent twice"
    entry = payload["already_in_your_prompt"]["founder"]
    assert entry["heading"] == "## founder.md"
    # The explanation lives in the handle's own DESCRIPTION, not in every response:
    # repeating it per read is the duplication this whole lane is about, and it cost
    # more than the bodies it replaced.
    doc = getattr(engine.read_brain, 'fn', engine.read_brain).__doc__ or ''
    assert 'already quoted verbatim in this turn' in doc
    # The digest and length are there so an edit can still be exact.
    assert len(entry["sha256"]) == 64
    assert entry["chars"] > 0


def test_the_payload_actually_gets_smaller(universe):
    """The point of the change, measured rather than asserted in prose."""
    before = len(json.dumps(_read_brain()))
    _quote_the_prompt(universe)
    after = len(json.dumps(_read_brain()))
    assert after < before, f"{after} is not smaller than {before}"
    # Measured on this fixture: 726 -> 480 bytes, a 246-byte saving against 502 bytes
    # of quoted body, the difference being the pointers. A third of the quoted text is
    # the floor asserted, so the test says "most of it goes" without pinning an exact
    # byte count that every prose edit to a brain file would move.
    quoted_chars = sum(len(body) for body in _quote_the_prompt(universe).values())
    assert before - after > quoted_chars * 0.3, (
        f"saved only {before - after} of {quoted_chars} quoted characters"
    )


def test_a_pointer_is_never_reachable_as_a_body(universe):
    """An agent echoing brain[section] into write_brain must not write a pointer."""
    _quote_the_prompt(universe)
    payload = _read_brain()
    for section, entry in payload["already_in_your_prompt"].items():
        assert section not in payload["brain"]
        assert entry["heading"] not in json.dumps(payload["brain"])


# ---------------------------------------------------------------------------
# Correct, not merely cheap
# ---------------------------------------------------------------------------


def test_a_same_turn_write_brings_the_fresh_body_back(universe):
    """The correctness condition. The prompt's copy is stale the moment it changes."""
    _quote_the_prompt(universe)
    assert "founder" not in _read_brain()["brain"]
    # Whatever changed it -- write_brain, an external edit -- the digest moves.
    (universe / "founder.md").write_text(
        "My founder's favourite colour is cobalt. They also own a cat named Nebula.\n",
        encoding="utf-8",
    )
    payload = _read_brain()
    assert "Nebula" in payload["brain"]["founder"], "a stale pointer hid a real change"
    assert "founder" not in payload.get("already_in_your_prompt", {})


def test_a_file_the_prompt_never_quoted_still_reads_in_full(universe):
    """Only what the prompt actually carried may be elided."""
    (universe / "origin.md").write_text("I was made to keep notes.\n", encoding="utf-8")
    bodies = _quote_the_prompt(universe)
    assert "origin.md" in bodies  # quoted, so elided
    # Now forget only origin by re-recording without it: the prompt did not carry it.
    inlined_brain.record(ACTOR, GRAPH, {k: v for k, v in bodies.items() if k != "origin.md"})
    payload = _read_brain()
    assert "I was made to keep notes." in payload["brain"]["origin"]
    assert "origin" not in payload.get("already_in_your_prompt", {})


def test_with_nothing_recorded_every_file_reads_in_full(universe):
    """The default is the old behaviour: not knowing costs a read, never a lie."""
    inlined_brain.forget(ACTOR, GRAPH)
    payload = _read_brain()
    assert "cobalt" in payload["brain"]["founder"]
    assert "already_in_your_prompt" not in payload


def test_another_universes_record_does_not_elide_this_ones(universe):
    """Keyed on (actor, graph): a neighbour's turn must not answer for this one."""
    bodies = universe_intelligence.inlined_grounding_bodies(
        universe, universe_id=GRAPH, tier="T2",
    )
    inlined_brain.record("someone-else", GRAPH, bodies)
    inlined_brain.record(ACTOR, "u-other", bodies)
    payload = _read_brain()
    assert "cobalt" in payload["brain"]["founder"]
    assert "already_in_your_prompt" not in payload


# ---------------------------------------------------------------------------
# One definition, one path for every account
# ---------------------------------------------------------------------------


def test_the_prompt_and_the_recorder_read_the_same_set(universe):
    """Two definitions of "what was inlined" would elide a file the prompt lacks."""
    from tinyassets.api import interlocutor

    bodies = universe_intelligence.inlined_grounding_bodies(
        universe, universe_id=GRAPH, tier=interlocutor.FOUNDER,
    )
    prompt = universe_intelligence._build_persona_system_prompt(
        universe, universe_id=GRAPH, tier=interlocutor.FOUNDER,
    )
    for fname, body in bodies.items():
        assert f"## {fname}" in prompt
        assert body.strip() in prompt


def test_the_registry_is_bounded_and_the_answer_never_varies_by_account(universe):
    inlined_brain.forget(ACTOR, GRAPH)
    for index in range(inlined_brain.MAX_TRACKED + 5):
        inlined_brain.record(f"actor-{index}", GRAPH, {"founder.md": "x"})
    assert len(inlined_brain._INLINED) <= inlined_brain.MAX_TRACKED
    # Dropping an entry only costs a full read.
    payload = _read_brain()
    assert "cobalt" in payload["brain"]["founder"]


def test_bodies_smaller_than_their_pointers_are_not_elided_at_all(universe, tmp_path):
    """An optimisation that can pessimise is not one.

    The first version elided every quoted file, and for two-line brain files the
    pointers -- a heading, a 64-char digest and JSON keys each -- measured BIGGER than
    the bodies they replaced: 829 bytes where the plain read was 310. The decision is
    now arithmetic and set-level, so a whole candidate set that would not pay is
    dropped rather than half-applied.
    """
    small = tmp_path / GRAPH  # the same universe, rewritten small
    for name in ("founder.md", "identity.md"):
        (small / name).write_text("Short.\n", encoding="utf-8")
    plain = len(json.dumps(_read_brain()))
    _quote_the_prompt(small)
    payload = _read_brain()
    assert "already_in_your_prompt" not in payload, "tiny bodies were elided anyway"
    assert payload["brain"]["founder"] == "Short."
    assert len(json.dumps(payload)) == plain, "the response grew for no saving"


def test_the_digest_is_defined_once():
    """Both sides must compare the same function, or elision is a coin toss."""
    assert inlined_brain.digest("abc") == inlined_brain.digest("abc")
    assert inlined_brain.digest("abc") != inlined_brain.digest("abd")
    assert inlined_brain.is_already_quoted("", "", "founder.md", "abc") is False

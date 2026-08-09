"""Bounded conversation memory for the universe turn.

The turn is stateless (fresh claude -p, current message only), so it forgets the
conversation between turns — live 2026-08-08 a costly post 402'd, the founder
said "try again", and the turn had no memory of what to retry. The SDK model
(vercel/ai agents/memory + chatbot-message-persistence) is load-on-start: pull
the recent conversation for this id and feed it in. This is the pure formatter
that turns loaded messages into a bounded prompt block; memory
[[agent-needs-cross-turn-memory]].
"""

from __future__ import annotations

from tinyassets.conversation_memory import Msg, format_history


def test_empty_history_is_empty_string():
    assert format_history([]) == ""


def test_a_single_founder_message_is_rendered_labeled():
    block = format_history([Msg(speaker="founder", text="post the update")])
    assert "post the update" in block
    # The block is clearly labeled as prior conversation, not the current ask.
    assert "conversation" in block.lower()
    # Founder is distinguishable from the universe's own voice.
    assert "founder" in block.lower()


def test_ordering_is_oldest_first_most_recent_last():
    block = format_history([
        Msg(speaker="founder", text="FIRST"),
        Msg(speaker="universe", text="SECOND"),
        Msg(speaker="founder", text="THIRD"),
    ])
    assert block.index("FIRST") < block.index("SECOND") < block.index("THIRD")


def test_limit_keeps_only_the_most_recent_n():
    msgs = [Msg(speaker="founder", text=f"m{i}") for i in range(20)]
    block = format_history(msgs, limit=5)
    # Oldest dropped, newest kept.
    assert "m0" not in block
    assert "m14" not in block
    assert "m15" in block and "m19" in block


def test_char_cap_drops_oldest_to_fit():
    msgs = [Msg(speaker="founder", text="x" * 500) for _ in range(20)]
    block = format_history(msgs, limit=20, char_cap=1200)
    assert len(block) <= 1200
    # It still rendered something (the most recent messages).
    assert "x" in block


def test_universe_and_founder_are_distinguishable_speakers():
    block = format_history([
        Msg(speaker="founder", text="ALPHA"),
        Msg(speaker="universe", text="BRAVO"),
    ])
    # The two speakers get different labels so the turn can tell who said what.
    alpha_label = block[: block.index("ALPHA")].rsplit("\n", 1)[-1]
    bravo_label = block[: block.index("BRAVO")].rsplit("\n", 1)[-1]
    assert alpha_label != bravo_label


def test_blank_messages_are_skipped():
    block = format_history([
        Msg(speaker="founder", text="   "),
        Msg(speaker="founder", text="real"),
    ])
    assert "real" in block
    # No empty label lines dangling.
    assert block.count("real") == 1


# -- continuity: WHO, WHEN, and one ongoing conversation ----------------------

def test_messages_are_tagged_with_when_they_were_sent():
    now = 1_000_000.0
    block = format_history(
        [
            Msg(speaker="founder", text="earlier ask", ts=now - 3 * 3600),
            Msg(speaker="founder", text="a moment ago", ts=now - 30),
        ],
        now=now,
    )
    # Relative "when" tags let the turn reason about how long ago things happened.
    assert "3h ago" in block
    assert "just now" in block


def test_header_anchors_the_current_time():
    block = format_history(
        [Msg(speaker="founder", text="hi", ts=1_000_000.0)], now=1_000_000.0
    )
    assert "current time" in block.lower()


def test_interlocutor_is_named_so_the_turn_knows_who():
    block = format_history(
        [Msg(speaker="founder", text="hi")], interlocutor="Jonathan"
    )
    assert "Jonathan" in block


def test_it_reads_as_one_continuous_conversation():
    block = format_history([Msg(speaker="founder", text="hi")])
    low = block.lower()
    assert "continuous" in low or "conversation so far" in low
    # Security fence preserved.
    assert "NOT consent" in block


def test_no_timestamp_still_renders_without_a_when_tag():
    # ts=None (e.g. an old backfill) must not crash or print a bogus time.
    block = format_history([Msg(speaker="founder", text="untimed")], now=1_000_000.0)
    assert "untimed" in block
    assert "[]" not in block


# -- the turn actually receives the memory ------------------------------------

def test_converse_injects_history_into_the_turn_system_prompt(tmp_path, monkeypatch):
    """The decisive wiring test: a follow-up turn must SEE the prior messages.
    This is what makes 'try again' work — the turn remembers the request."""
    import tinyassets.universe_intelligence as ui
    from tests.test_universe_intelligence import _seed

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = _seed(tmp_path)
    captured: dict = {}

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        if "strict JSON" in system:
            return "{}"
        captured["system"] = system
        captured["prompt"] = prompt
        return "on it"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)
    # History rides the founder path (granted); force a founder turn.
    monkeypatch.setattr(ui.interlocutor, "resolve_interlocutor_tier",
                        lambda uid: type("R", (), {"tier": ui.interlocutor.FOUNDER})())

    ui.converse(
        "u-test", "try again",
        conversation_history=[
            Msg(speaker="founder", text="post the shipped update to X"),
            Msg(speaker="universe", text="it hit a 402, credits depleted"),
        ],
    )
    prompt = captured["prompt"]
    # Memory rides the USER message as delimited untrusted context, NOT system.
    assert "post the shipped update to X" in prompt
    assert "402" in prompt
    assert "try again" in prompt  # the current message follows the history
    assert "NOT consent" in prompt  # fenced as memory, never authorization
    # It must NOT be merged into the trusted persona system prompt.
    assert "post the shipped update to X" not in captured["system"]


def test_converse_without_history_omits_the_memory_block(tmp_path, monkeypatch):
    import tinyassets.universe_intelligence as ui
    from tests.test_universe_intelligence import _seed

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = _seed(tmp_path)
    captured: dict = {}

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        if "strict JSON" in system:
            return "{}"
        captured["system"] = system
        captured["prompt"] = prompt
        return "hello"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)

    ui.converse("u-test", "hi")
    assert "CONVERSATION SO FAR" not in captured["prompt"]
    assert captured["prompt"] == "hi"


def test_history_is_gated_to_founder_turns(tmp_path, monkeypatch):
    """Codex ADAPT: other-tier/prior-universe history must not ride into a turn.
    A non-founder turn gets NO injected history until tier-preserving history
    exists."""
    import tinyassets.universe_intelligence as ui
    from tests.test_universe_intelligence import _seed

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = _seed(tmp_path)
    captured: dict = {}

    def fake_call_provider(prompt, system="", *, role="writer",
                           universe_context=None, **_kw):
        if "strict JSON" in system:
            return "{}"
        captured["prompt"] = prompt
        return "hello"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: udir)
    monkeypatch.setattr(ui, "call_provider", fake_call_provider)
    # A non-founder (external floor) turn.
    monkeypatch.setattr(ui.interlocutor, "resolve_interlocutor_tier",
                        lambda uid: type("R", (), {"tier": ui.EXTERNAL_SENDER_FLOOR})())

    ui.converse(
        "u-test", "hello",
        conversation_history=[Msg(speaker="founder", text="secret prior thing")],
    )
    assert "secret prior thing" not in captured["prompt"]

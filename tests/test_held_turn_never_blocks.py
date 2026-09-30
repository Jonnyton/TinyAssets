"""A turn that ended ``held_transport`` never blocks the universe's next turn.

2026-09-28, the free account: turn b1675c7d ended ``held_transport`` at round 2
and read as "stuck" for hours. It is a TERMINAL failure state (not in the
journal's ``WORKING_STATES``), so nothing waits on it: the next message is a
new turn. Pinned through the real ``converse`` so a future gate on the previous
turn's state cannot silently wedge an owner.
"""

from __future__ import annotations

import pytest

from tests import test_served_model_preferences as prefs
from tinyassets.storage.agent_turn_journal import WORKING_STATES

rig = prefs.rig
reader = prefs.reader
configured = prefs.configured
served = prefs.served
agent = prefs.agent


def test_the_next_message_after_a_held_transport_turn_is_a_new_turn_that_answers(
    agent, monkeypatch,
):
    from tinyassets.exceptions import AllProvidersExhaustedError

    agent.unknown_inference = True
    with pytest.raises(AllProvidersExhaustedError):
        prefs._converse(agent, monkeypatch)
    held = agent.latest()
    assert held.state == "held_transport"
    assert held.state not in WORKING_STATES

    # The failed attempt cooled its source (router quota, a separate concern
    # with its own tests); let that window pass so what is measured here is
    # only whether the HELD TURN gates the next one.
    import time as real_time
    from types import SimpleNamespace

    from tinyassets.providers import quota

    later = real_time.monotonic() + 3600
    # quota's own clock only: the event loop keeps real time.
    monkeypatch.setattr(quota, "time", SimpleNamespace(monotonic=lambda: later))
    agent.unknown_inference = False
    assert prefs._converse(agent, monkeypatch) == "finished exact answer"

    answered = agent.latest()
    assert answered.turn_id != held.turn_id
    assert answered.state == "completed"

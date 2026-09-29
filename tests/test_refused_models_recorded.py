"""The turn that meets a source's refusal records it for the turns after it.

Drives #4078's refusal path (real writer, router, ``ApiKeyHttpProvider``,
coordinator, journal; synthetic wire) and reads the durable mark it leaves. The
reading side -- the next turn's real plan ordering the model last -- is
``tests/test_refused_models_remembered.py``.
"""

from __future__ import annotations

from tests import test_interactive_http_agent as integration
from tests import test_provider_model_refusal as refusal

rig = integration.rig
reader = integration.reader
served = integration.served
agent = integration.agent


def _marks(agent):
    from tinyassets.storage.refused_models import active_refused_models

    return active_refused_models(agent.served.rig.base, owner_user_id="owner")


def test_a_refusal_is_remembered_with_the_sources_reason(agent, monkeypatch):
    refusal._order(agent, monkeypatch, ["lab/refusing:free", "lab/answering:free"])
    agent.requested_rounds = 0
    # The live sequence: rate limited, then refused, then an answer.
    agent.capacity_failures.update({1: 429, 2: 403})
    agent.failure_bodies[2] = refusal.RECORDED_SHAPE_403

    assert integration.run(agent) == "finished exact answer"

    marks = _marks(agent)
    assert [(m.model_id, m.failure_class) for m in marks] == [
        ("lab/refusing:free", "provider_refused")]
    assert "Synthetic refusal" in marks[0].detail
    assert marks[0].connection_id == agent.served.context.model_selection.connection_id

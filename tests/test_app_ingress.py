"""Server-side delivery of one external chat event.

The properties under test are the ones that let the Slack agent stop mounting
the production volume: the daemon decides the universe, the daemon holds the
credential, and the transport gets back nothing it could forge or leak.
"""

from __future__ import annotations

import logging

import pytest

from tinyassets import app_ingress
from tinyassets.custom_agents import create_binding, publish_definition
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
)
from tinyassets.storage.app_channel_bindings import AppChannelBindingStore

APP = "A0INGRESS01"
TEAM = "T0INGRESS01"
CHANNEL = "C0INGRESS01"
SENDER = "U0INGRESSFO"
OWNER = "U0INGRESSFO"


class _Receipt:
    def __init__(self, ref: str) -> None:
        self.provider_receipt_ref = ref


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(str(tmp_path))
    return tmp_path


def _make_universe(base, universe_id: str, owner: str = OWNER) -> str:
    grant_universe_access(
        str(base),
        universe_id=universe_id,
        actor_id=owner,
        permission="admin",
        granted_by=owner,
    )
    definition = publish_definition(
        str(base),
        author_id=owner,
        payload={
            "schema_version": 1,
            "name": f"agent for {universe_id}",
            "description": "ingress test",
            "tags": ["t"],
            "components": {
                "identity": {"kind": "soul", "config": {"instructions": "hi"}}
            },
        },
    )
    binding = create_binding(
        str(base),
        universe_id=universe_id,
        definition_id=definition["agent_definition_id"],
        created_by=owner,
        payload={"schema_version": 1, "name": "b", "model": "test"},
    )
    (base / universe_id).mkdir(exist_ok=True)
    return binding["agent_binding_id"]


def _bind(base, universe_id: str, agent_binding_id: str, channel_id: str = "") -> None:
    AppChannelBindingStore(base).bind(
        provider="slack",
        installation_id=f"{APP}:{TEAM}",
        workspace_id=TEAM,
        channel_id=channel_id,
        universe_id=universe_id,
        agent_binding_id=agent_binding_id,
        binding_revision=1,
        bound_by=OWNER,
    )


def _deliver(**overrides):
    calls: dict = {"converse": [], "post": []}

    def _converse(universe_id, prompt, *, actor_id="", founder_grant=None):
        calls["converse"].append(
            {
                "universe_id": universe_id,
                "prompt": prompt,
                "actor_id": actor_id,
                "founder_grant": founder_grant,
            }
        )
        return "the universe answers"

    def _transport(destination, body, *, thread_ts=""):
        calls["post"].append(
            {"destination": destination, "body": body, "thread_ts": thread_ts}
        )
        return _Receipt("1700000000.000100")

    kwargs = {
        "provider": "slack",
        "api_app_id": APP,
        "workspace_id": TEAM,
        "actor_team_id": TEAM,
        "external_sender_id": SENDER,
        "channel_id": CHANNEL,
        "event_id": "Ev-ingress-1",
        "event_type": "app_mention",
        "text": "<@U0BOT> what do you know?",
        "converse": _converse,
        "transport": _transport,
    }
    kwargs.update(overrides)
    result = app_ingress.deliver_app_event(**kwargs)
    return result, calls


def test_a_bound_workspace_is_answered(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver()

    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-a"
    assert calls["post"][0]["body"] == "the universe answers"


def test_an_unbound_installation_is_silent(base):
    """No binding must mean silence, not a guessed universe."""
    _make_universe(base, "u-ingress-a")  # exists, but nothing routes to it

    result, calls = _deliver()

    assert result.handled is False
    assert calls["converse"] == []
    assert calls["post"] == []


def test_the_caller_cannot_name_the_universe(base):
    """The transport used to pass its own configured universe as a fallback.

    That made "which brain answers" a caller-supplied value. `deliver_app_event`
    takes no such parameter, so a caller trying to smuggle one in is a
    TypeError rather than a universe it was never entitled to.
    """
    binding = _make_universe(base, "u-ingress-a")
    _make_universe(base, "u-ingress-victim", owner="U0STRANGER1")
    _bind(base, "u-ingress-a", binding)

    with pytest.raises(TypeError):
        _deliver(fallback_universe_id="u-ingress-victim")

    # And the routed answer is still the bound one.
    result, calls = _deliver()
    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-a"


def test_the_channel_binding_wins_over_the_workspace_default(base):
    work = _make_universe(base, "u-ingress-work")
    hobby = _make_universe(base, "u-ingress-hobby")
    _bind(base, "u-ingress-work", work)  # workspace-wide
    _bind(base, "u-ingress-hobby", hobby, channel_id=CHANNEL)

    result, calls = _deliver()

    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-hobby"


def test_the_receipt_carries_no_reply_text_and_no_authority(base):
    """A transport that never sees the reply cannot log it elsewhere."""
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, _ = _deliver()

    rendered = repr(result)
    assert "the universe answers" not in rendered
    assert not hasattr(result, "founder_grant")
    assert not hasattr(result, "universe_id")
    assert not hasattr(result, "universe_dir")
    assert result.provider_receipt_ref == "1700000000.000100"


def test_an_empty_prompt_costs_no_provider_call(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(text="<@U0BOT>   ")

    assert result.handled is False
    assert calls["converse"] == []


def test_an_unsupported_provider_is_silent(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(provider="discord")

    assert result.handled is False
    assert calls["converse"] == []


def test_the_actor_id_is_workspace_namespaced(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    _, calls = _deliver()

    assert calls["converse"][0]["actor_id"] == f"slack:{TEAM}:{SENDER}"


def test_a_replayed_event_mints_no_second_grant(base, monkeypatch):
    """Answer again, but never grant founder authority twice for one event.

    A recogniser that always grants is what makes this bite. Asserting only
    "the replay got None" passes with the replay guard DELETED, because with no
    founder mapping in the fixture the grant is None on both deliveries — the
    test would be measuring the absent mapping, not the guard.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    sentinel = object()
    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        lambda self, event, **kwargs: sentinel,
        raising=True,
    )

    _, first = _deliver()
    _, second = _deliver()

    assert first["converse"][0]["founder_grant"] is sentinel
    assert second["converse"][0]["founder_grant"] is None
    assert first["converse"][0]["prompt"] == second["converse"][0]["prompt"]


def test_an_unattributable_sender_gets_no_turn(base):
    """A sender with no id must not reach the universe at all.

    Without the identity guard this still routes — routing does not depend on
    the sender — and `converse` runs with an actor id of ``slack:<team>:``,
    which is an unattributable turn wearing a well-formed name.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(external_sender_id="")

    assert result.handled is False
    assert calls["converse"] == []
    assert calls["post"] == []


def test_recognition_failure_degrades_instead_of_killing_the_turn(base, monkeypatch):
    """A broken recogniser must cost authority, not the whole workspace."""
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    def _boom(*a, **k):
        raise RuntimeError("recogniser is down")

    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        _boom,
        raising=True,
    )
    result, calls = _deliver()

    # `handled is True` is the load-bearing assertion, and it is not vacuous:
    # without the except-branch in `_recognize` the RuntimeError propagates and
    # this call raises instead of returning. (Do NOT call `monkeypatch.undo()`
    # here — the fixture set TINYASSETS_DATA_DIR through the same object, so
    # undoing reverts the data dir too and every later lookup silently misses.)
    assert result.handled is True
    assert calls["converse"][0]["founder_grant"] is None


def test_an_unmapped_principal_is_named_in_the_log(base, caplog):
    """An operator must be able to discover which id has no mapping.

    Found live: `u-tiny` answered in Slack for a whole evening and learned
    nothing, because the founder had no app-principal mapping. Every surface
    was silent about it — `recognize` returns None for a stranger and for an
    unprovisioned founder alike, by design — so the id needed to fix it existed
    nowhere: not in the logs, not in the ledger (which is content-free), and
    not in any persisted actor record, because nothing was persisted.

    Asserts the SENDER's workspace, not the delivery workspace: the mapping is
    keyed on the former, so logging the latter would send an operator to
    provision a key that never matches.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    with caplog.at_level(logging.INFO, logger="tinyassets.app_ingress"):
        result, _ = _deliver(actor_team_id="T-GUEST-HOME")

    assert result.handled is True
    unmapped = [r.getMessage() for r in caplog.records if "no founder mapping" in r.getMessage()]
    assert len(unmapped) == 1, caplog.text
    message = unmapped[0]
    assert SENDER in message
    assert "workspace=T-GUEST-HOME" in message
    assert f"installation={APP}:{TEAM}" in message


def test_a_recognised_founder_is_not_logged_as_unmapped(base, monkeypatch, caplog):
    """The notice must track recognition, not merely "we looked".

    Without this, a log line emitted unconditionally still passes the test
    above while telling an operator their working founder is broken.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)
    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        lambda self, event, **kwargs: object(),
        raising=True,
    )

    with caplog.at_level(logging.INFO, logger="tinyassets.app_ingress"):
        _deliver()

    assert not [r for r in caplog.records if "no founder mapping" in r.getMessage()]


def test_an_empty_reply_is_a_fault_not_a_silent_success(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    with pytest.raises(ValueError):
        _deliver(converse=lambda *a, **k: "   ")

"""Server-side delivery of one external chat event.

The properties under test are the ones that let the Slack agent stop mounting
the production volume: the daemon decides the universe, the daemon holds the
credential, and the transport gets back nothing it could forge or leak.
"""

from __future__ import annotations

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

    def _converse(universe_id, prompt, *, actor_id="", founder_grant=None,
                  conversation_history=None):
        calls["converse"].append(
            {
                "universe_id": universe_id,
                "prompt": prompt,
                "actor_id": actor_id,
                "founder_grant": founder_grant,
                "conversation_history": conversation_history,
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


def test_an_empty_reply_tells_the_founder_instead_of_going_silent(base):
    # An empty reply is still a fault — but the founder must HEAR it, not be left
    # in silence. (Was: raise into silence; a persistent agent never goes dark.)
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(converse=lambda *a, **k: "   ")
    assert result.handled is True
    # The last post is an honest notice, not silence and not a fake success.
    last = calls["post"][-1]["body"].lower()
    assert "empty" in last or "again" in last


def test_a_failed_turn_posts_an_honest_notice_not_silence(base):
    # The live 2026-08-09 outage: the writer model hit its rate limit, the turn
    # raised, and the founder got only silence for minutes. Now the daemon says
    # so honestly (it holds the token) and stays handled.
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    def _boom(*a, **k):
        from tinyassets.exceptions import AllProvidersExhaustedError

        raise AllProvidersExhaustedError("All providers exhausted for role=writer")

    result, calls = _deliver(converse=_boom)
    assert result.handled is True
    body = calls["post"][-1]["body"].lower()
    # Names the real cause (capacity / rate limit) rather than vanishing.
    assert "capacity" in body or "rate limit" in body


#: A 1:1 DM channel id (Slack DM ids start with "D"). Durable memory is only
#: enabled here — the fail-closed multi-principal guard.
_DM = "D0INGRESSDM"


def _grant_founder(monkeypatch):
    """Make the ingress recognize the sender as the founder (a non-None grant)."""
    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        lambda self, event, **kwargs: object(),
        raising=True,
    )


def test_memory_persists_across_turns(base, monkeypatch):
    """The durable store makes a stateless turn remember the last one.

    This is the whole point: u-tiny forgot everything between turns because the
    turn is a fresh `claude -p`. Turn 1 is recorded; turn 2 gets turn 1 fed back
    as PRIOR conversation, without the current message being double-shown. Runs
    only in a founder-authorized 1:1 DM (the fail-closed guard).
    """
    binding = _make_universe(base, "u-ingress-mem")
    _bind(base, "u-ingress-mem", binding)
    _grant_founder(monkeypatch)

    # Turn 1: nothing to remember yet (cold store, no Slack token to backfill),
    # but the turn is recorded for next time.
    _, calls1 = _deliver(
        channel_id=_DM,
        text="<@U0BOT> my favorite topic is tide pools",
        event_id="Ev-mem-1",
    )
    first_history = calls1["converse"][0]["conversation_history"] or []
    assert all("tide pools" not in m.text for m in first_history)

    # Turn 2: the durable store feeds turn 1 back in as prior context.
    _, calls2 = _deliver(
        channel_id=_DM,
        text="<@U0BOT> what did I say my favorite topic was?",
        event_id="Ev-mem-2",
    )
    history = calls2["converse"][0]["conversation_history"]
    texts = [m.text for m in history]
    assert "my favorite topic is tide pools" in texts  # founder's earlier turn
    assert "the universe answers" in texts  # the universe's own earlier reply
    # The current turn's own prompt is not shown inside its own memory block.
    assert "what did I say my favorite topic was?" not in texts


def test_a_dropped_record_is_re_synced_from_the_live_timeline(base, monkeypatch):
    """HARDENING: `backfill_once` runs exactly once, so a dropped `record_turn`
    leaves the store BEHIND the live thread forever. The load path reconciles the
    tail from the live timeline so recent context is never lost.

    Mutation-check: remove the `sync_tail` call in `deliver_app_event` and the
    missed universe reply never reaches the next turn — this test goes red.
    """
    binding = _make_universe(base, "u-ingress-drift")
    _bind(base, "u-ingress-drift", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-drift")
    session = f"slack:{_DM}"
    # Store already backfilled (marker set) but then MISSED recording a later
    # reply — the exact silent-drift regression.
    cs.backfill_once(conv_dir, session, [{"speaker": "founder", "text": "start the plan"}])
    cs.record_turn(conv_dir, session, "universe", "starting now")

    # The live Slack timeline is AHEAD: it also holds the turns the store missed.
    live = [
        {"speaker": "founder", "text": "start the plan"},
        {"speaker": "universe", "text": "starting now"},
        {"speaker": "founder", "text": "any update?"},        # store MISSED this
        {"speaker": "universe", "text": "shipped part one"},  # store MISSED this
    ]
    monkeypatch.setattr(sat, "load_thread_history", lambda **k: live)

    _, calls = _deliver(
        channel_id=_DM, text="<@U0BOT> what did you ship?", event_id="Ev-drift-1"
    )
    history = calls["converse"][0]["conversation_history"]
    texts = [m.text for m in history]
    assert "any update?" in texts
    assert "shipped part one" in texts  # the missed tail is reconciled in


def test_memory_is_off_in_a_shared_channel(base, monkeypatch):
    """Fail-closed multi-principal guard (Codex REJECT 2026-08-09): even a
    recognized founder gets NO durable memory outside a 1:1 DM. A shared channel
    is multi-principal and the session is channel-keyed, so loading its history
    could inject another person's words into a founder turn.

    Mutation-check: drop the `startswith("D")` half of `memory_on` and the seeded
    shared-channel history rides into the turn — this goes red.
    """
    binding = _make_universe(base, "u-ingress-share")
    _bind(base, "u-ingress-share", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-share")
    shared = "C0SHAREDXX"
    # Seed a store for this channel so an empty history can ONLY be the guard.
    cs.record_turn(conv_dir, f"slack:{shared}", "founder", "prior shared secret")

    _, calls = _deliver(channel_id=shared, text="<@U0BOT> hi", event_id="Ev-share-1")
    history = calls["converse"][0]["conversation_history"] or []
    assert history == []  # nothing loaded or injected in a shared channel


def test_the_reply_is_recorded_only_after_it_is_posted(base, monkeypatch):
    """POST-THEN-RECORD (Codex REJECT 2026-08-09): history must never claim a
    reply the founder never received. If delivery fails, the universe reply is
    NOT in the store (the founder's own message, recorded before converse, is).

    Mutation-check: record the reply BEFORE `_post` and this goes red.
    """
    binding = _make_universe(base, "u-ingress-por")
    _bind(base, "u-ingress-por", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-por")
    session = f"slack:{_DM}"

    def _post_boom(destination, body, *, thread_ts=""):
        raise RuntimeError("slack post 500")

    with pytest.raises(RuntimeError):
        _deliver(
            channel_id=_DM, transport=_post_boom,
            text="<@U0BOT> hello there", event_id="Ev-por-1",
        )

    stored = [m.text for m in cs.load_recent(conv_dir, session)]
    assert "the universe answers" not in stored  # undelivered reply not recorded
    assert "hello there" in stored  # the founder's message WAS recorded pre-converse


def test_memory_load_never_raises_into_the_turn(base, monkeypatch):
    """Best-effort: if the memory load path blows up (vault error, store bug), the
    turn still answers — memory degrades to empty, never drops the reply.

    Mutation-check: remove the try/except around the memory block and this raises.
    """
    binding = _make_universe(base, "u-ingress-safe")
    _bind(base, "u-ingress-safe", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs

    def _boom(*a, **k):
        raise RuntimeError("vault down")

    monkeypatch.setattr(cs, "load_recent", _boom)

    result, calls = _deliver(channel_id=_DM, text="<@U0BOT> hi", event_id="Ev-safe-1")
    assert result.handled is True
    assert calls["post"][-1]["body"] == "the universe answers"
    assert calls["converse"][0]["conversation_history"] == []


def test_composite_transport_receipt_does_not_duplicate_the_reply(base, monkeypatch):
    """FIX2 (Codex 2026-08-10): the REAL Slack transport returns a COMPOSITE
    receipt ``slack:<channel>:<ts>``, but sync_tail dedups on the RAW ts from the
    live timeline. Storing the composite as ext_id meant the reply never matched
    on re-sync and was re-recorded as a duplicate every turn. The reply must be
    stored under its RAW ts and survive a re-sync without duplicating.

    Note: this uses a transport with the PROD receipt shape — the round-2 test
    double returned a raw ts, which is exactly why this bug slipped through.

    Mutation-check: drop the rsplit normalization in ``_record_universe`` (store
    the composite) and the re-sync below re-appends the reply — this goes red.
    """
    binding = _make_universe(base, "u-ingress-fix2")
    _bind(base, "u-ingress-fix2", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-fix2")
    session = f"slack:{_DM}"
    reply_ts = "1700000000.000200"

    def _composite_transport(destination, body, *, thread_ts=""):
        # Exactly what tinyassets/effectors/slack_transport.py returns.
        return _Receipt(f"slack:{_DM}:{reply_ts}")

    # Turn 1: the reply is recorded from the COMPOSITE receipt.
    _deliver(
        channel_id=_DM, transport=_composite_transport,
        text="<@U0BOT> hello", event_id="Ev-fix2-1",
    )
    ids = {ext for _sp, _tx, ext in cs._recent_identities(conv_dir, session, limit=50)}
    assert reply_ts in ids, "reply must be stored under its RAW ts"
    assert f"slack:{_DM}:{reply_ts}" not in ids, "composite must never become an ext_id"

    # Turn 2: the live timeline reports the reply at its RAW ts; sync_tail must
    # recognize it and NOT re-append.
    live = [
        {"speaker": "founder", "text": "hello", "ts": "1700000000.000100"},
        {"speaker": "universe", "text": "the universe answers", "ts": reply_ts},
    ]
    monkeypatch.setattr(sat, "load_thread_history", lambda **k: live)
    _deliver(
        channel_id=_DM, transport=_composite_transport,
        text="<@U0BOT> still there?", event_id="Ev-fix2-2",
    )
    replies = [
        m.text for m in cs.load_recent(conv_dir, session, limit=100)
        if m.text == "the universe answers"
    ]
    assert replies == ["the universe answers"], f"reply duplicated {len(replies)}x"


def test_a_non_founder_dm_gets_no_founder_history(base, monkeypatch):
    """FIX5 (Codex 2026-08-10): the guard is BOTH halves — 1:1 DM AND a founder
    grant. A DM sender the recognizer does NOT grant must get NO durable memory,
    or one visitor's DM could read the founder's history.

    Mutation-check: drop the ``grant is not None`` half of ``memory_on`` and the
    seeded history rides into the ungranted DM turn — this goes red.
    """
    binding = _make_universe(base, "u-ingress-nofdr")
    _bind(base, "u-ingress-nofdr", binding)
    # NOTE: deliberately do NOT grant founder — recognize returns None by default.

    import tinyassets.conversation_store as cs
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-nofdr")
    # Seed the DM session so an empty history can ONLY be the guard, not emptiness.
    cs.record_turn(conv_dir, f"slack:{_DM}", "founder", "prior founder-only secret")

    _, calls = _deliver(channel_id=_DM, text="<@U0BOT> hi", event_id="Ev-nofdr-1")
    history = calls["converse"][0]["conversation_history"] or []
    assert history == [], "an ungranted DM must load no history"
